"""HWP AI Chat — 한글 문서 실시간 제어 채팅 앱.

채팅으로 자연어 명령 → Claude Sonnet이 판단 → 한글 프로그램 COM으로 실시간 문서 조작.

실행:
  set ANTHROPIC_API_KEY=sk-ant-...
  python hwp_chat_app.py
"""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from typing import Any

from hwp_controller import HwpController

# ---------------------------------------------------------------------------
# Claude API tool definitions — Claude에게 주는 HWP 조작 도구 목록
# ---------------------------------------------------------------------------

HWP_TOOLS = [
    {
        "name": "open_file",
        "description": "한글(HWP/HWPX) 파일을 연다. 파일 경로를 받아서 한글 프로그램에서 해당 문서를 연다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "열 HWP/HWPX 파일의 전체 경로"
                }
            },
            "required": ["filepath"]
        }
    },
    {
        "name": "save_file",
        "description": "현재 열린 문서를 저장한다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "save_as",
        "description": "현재 열린 문서를 다른 이름으로 저장한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "저장할 파일 경로"
                }
            },
            "required": ["filepath"]
        }
    },
    {
        "name": "get_current_file",
        "description": "현재 열려있는 파일 경로를 확인한다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "read_full_text",
        "description": "현재 열린 문서의 전체 텍스트를 읽는다. 문서 내용을 파악할 때 사용한다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "read_document_structure",
        "description": "문서의 구조를 분석한다. 제목, 섹션, 문단 번호 등을 파악하여 문서의 전체 윤곽을 보여준다.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "read_section",
        "description": "특정 키워드가 포함된 섹션의 내용을 읽는다. 예: '교육목표' 섹션, 'AI공학' 섹션 등.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "찾을 섹션의 키워드 (예: '교육목표', 'AI공학전공')"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "find_text",
        "description": "문서에서 특정 텍스트를 검색한다. 해당 텍스트가 어느 문단에 있는지 찾아준다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "검색할 텍스트"
                }
            },
            "required": ["search_text"]
        }
    },
    {
        "name": "replace_text",
        "description": "문서 전체에서 특정 텍스트를 찾아 다른 텍스트로 바꾼다. 한글 프로그램의 '찾아 바꾸기' 기능과 동일하다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "find_str": {
                    "type": "string",
                    "description": "찾을 텍스트"
                },
                "replace_str": {
                    "type": "string",
                    "description": "바꿀 텍스트"
                }
            },
            "required": ["find_str", "replace_str"]
        }
    },
    {
        "name": "replace_section_content",
        "description": "특정 섹션의 본문 내용을 새 내용으로 통째로 교체한다. 섹션 제목은 유지하고 본문만 교체한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "교체할 섹션의 제목 키워드"
                },
                "new_content": {
                    "type": "string",
                    "description": "새로 넣을 내용 (줄바꿈으로 문단 구분)"
                }
            },
            "required": ["keyword", "new_content"]
        }
    },
    {
        "name": "replace_paragraph",
        "description": "특정 문단 번호의 내용을 새 텍스트로 교체한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "para_index": {
                    "type": "integer",
                    "description": "교체할 문단 번호 (0부터 시작)"
                },
                "new_text": {
                    "type": "string",
                    "description": "새로 넣을 텍스트"
                }
            },
            "required": ["para_index", "new_text"]
        }
    },
    {
        "name": "insert_text_at_cursor",
        "description": "현재 커서 위치에 텍스트를 삽입한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "삽입할 텍스트"
                }
            },
            "required": ["text"]
        }
    },
]

# ---------------------------------------------------------------------------
# Tool 실행기
# ---------------------------------------------------------------------------

def execute_tool(controller: HwpController, tool_name: str, tool_input: dict) -> str:
    """Claude가 요청한 도구를 실행하고 결과를 반환한다."""
    dispatch = {
        "open_file": lambda: controller.open_file(tool_input["filepath"]),
        "save_file": lambda: controller.save_file(),
        "save_as": lambda: controller.save_as(tool_input["filepath"]),
        "get_current_file": lambda: controller.get_current_file(),
        "read_full_text": lambda: controller.read_full_text(),
        "read_document_structure": lambda: controller.read_document_structure(),
        "read_section": lambda: controller.read_section(tool_input["keyword"]),
        "find_text": lambda: controller.find_text(tool_input["search_text"]),
        "replace_text": lambda: controller.replace_text(tool_input["find_str"], tool_input["replace_str"]),
        "replace_section_content": lambda: controller.replace_section_content(
            tool_input["keyword"], tool_input["new_content"]
        ),
        "replace_paragraph": lambda: controller.replace_paragraph(
            tool_input["para_index"], tool_input["new_text"]
        ),
        "insert_text_at_cursor": lambda: controller.insert_text_at_cursor(tool_input["text"]),
    }

    func = dispatch.get(tool_name)
    if func is None:
        return f"알 수 없는 도구: {tool_name}"

    try:
        return func()
    except Exception as e:
        return f"도구 실행 오류 ({tool_name}): {e}"


# ---------------------------------------------------------------------------
# Claude API 호출 (tool_use 루프)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """당신은 한글(HWP) 문서 편집 전문 AI 어시스턴트입니다.
사용자가 자연어로 요청하면, 제공된 도구를 사용하여 한글 프로그램에서 열린 문서를 실시간으로 읽고 수정합니다.

작업 규칙:
1. 문서를 수정하기 전에 반드시 먼저 해당 부분을 읽어서 현재 내용을 확인하세요.
2. 수정 작업 후에는 결과를 사용자에게 간결하게 보고하세요.
3. 사용자가 파일을 지정하지 않으면 현재 열린 파일을 사용하세요.
4. 중요한 변경 전에는 사용자에게 확인을 받으세요.
5. 한국어로 응답하세요.
6. 문서 구조를 파악할 때는 read_document_structure를, 특정 부분을 읽을 때는 read_section을 사용하세요.
7. 파일 경로에는 항상 전체 경로를 사용하세요."""


def call_claude_with_tools(
    messages: list[dict],
    controller: HwpController,
    on_status: Any = None,
    api_key: str = "",
) -> str:
    """Claude API에 메시지를 보내고 tool_use 루프를 돌려 최종 응답을 반환한다."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    while True:
        if on_status:
            on_status("Claude 응답 대기 중...")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=HWP_TOOLS,
            messages=messages,
        )

        # 응답 처리
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # tool_use 블록이 있는지 확인
        tool_uses = [b for b in assistant_content if b.type == "tool_use"]

        if not tool_uses:
            # 최종 텍스트 응답 추출
            text_parts = [b.text for b in assistant_content if b.type == "text"]
            return "\n".join(text_parts)

        # tool_use 실행 후 결과를 messages에 추가
        tool_results = []
        for tu in tool_uses:
            if on_status:
                on_status(f"도구 실행: {tu.name}...")

            result = execute_tool(controller, tu.name, tu.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# GUI 앱
# ---------------------------------------------------------------------------

class HwpChatApp:
    """한글 문서 AI 채팅 데스크톱 앱."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PenTong AI — 한글 문서 실시간 편집 채팅")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        # 상태
        self.controller = HwpController()
        self.messages: list[dict] = []
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.result_queue: queue.Queue = queue.Queue()
        self.is_processing = False

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self):
        # 스타일
        style = ttk.Style()
        style.configure("Status.TLabel", foreground="gray")
        style.configure("Connected.TLabel", foreground="green")

        # 상단 바: API 키 + 연결 상태
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))

        ttk.Label(top_frame, text="API Key:").pack(side="left")
        self.api_key_var = tk.StringVar(value=self.api_key)
        api_entry = ttk.Entry(top_frame, textvariable=self.api_key_var, width=40, show="*")
        api_entry.pack(side="left", padx=(4, 10))

        ttk.Button(top_frame, text="한글 연결", command=self._connect_hwp).pack(side="left", padx=(0, 4))
        ttk.Button(top_frame, text="파일 열기", command=self._open_file_dialog).pack(side="left", padx=(0, 4))
        ttk.Button(top_frame, text="저장", command=self._save_file).pack(side="left", padx=(0, 4))
        ttk.Button(top_frame, text="대화 초기화", command=self._clear_chat).pack(side="left")

        self.status_var = tk.StringVar(value="한글 미연결")
        self.status_label = ttk.Label(top_frame, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(side="right")

        # 파일 경로 표시
        file_frame = ttk.Frame(self.root)
        file_frame.pack(fill="x", padx=10, pady=(4, 0))
        ttk.Label(file_frame, text="파일:").pack(side="left")
        self.file_var = tk.StringVar(value="없음")
        ttk.Label(file_frame, textvariable=self.file_var, foreground="blue").pack(side="left", padx=4)

        # 채팅 영역
        chat_frame = ttk.LabelFrame(self.root, text="대화")
        chat_frame.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap="word",
            state="disabled",
            font=("맑은 고딕", 11),
            spacing3=6,
            padx=10,
            pady=10,
        )
        self.chat_display.pack(fill="both", expand=True)

        # 태그 설정
        self.chat_display.tag_configure("user", foreground="#0066cc", font=("맑은 고딕", 11, "bold"))
        self.chat_display.tag_configure("assistant", foreground="#333333")
        self.chat_display.tag_configure("system", foreground="#888888", font=("맑은 고딕", 9))
        self.chat_display.tag_configure("tool", foreground="#cc6600", font=("Consolas", 9))

        # 입력 영역 — 눈에 잘 보이도록 LabelFrame + 배경색
        input_wrapper = ttk.LabelFrame(self.root, text="메시지 입력 (Enter: 전송 / Shift+Enter: 줄바꿈)")
        input_wrapper.pack(fill="x", padx=10, pady=(4, 10))
        input_wrapper.columnconfigure(0, weight=1)

        self.input_text = tk.Text(
            input_wrapper,
            height=4,
            wrap="word",
            font=("맑은 고딕", 12),
            bg="#FFFFF0",
            relief="solid",
            borderwidth=1,
            insertbackground="blue",
        )
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
        self.input_text.bind("<Return>", self._on_enter)
        self.input_text.bind("<Shift-Return>", lambda e: None)  # Shift+Enter는 줄바꿈

        self.send_btn = tk.Button(
            input_wrapper,
            text="보내기\n(Enter)",
            command=self._send_message,
            font=("맑은 고딕", 11, "bold"),
            bg="#4A90D9",
            fg="white",
            width=8,
            height=3,
            relief="raised",
        )
        self.send_btn.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=6)

        # 입력란에 포커스
        self.input_text.focus_set()

        # 초기 메시지
        self._append_chat("system", "PenTong AI에 오신 것을 환영합니다.\n"
                          "1. 'API Key'에 Anthropic API 키를 입력하세요.\n"
                          "2. '한글 연결' 버튼으로 한글 프로그램에 연결하세요.\n"
                          "3. '파일 열기'로 문서를 열거나, 채팅에서 파일 경로를 알려주세요.\n"
                          "4. 자연어로 문서 작업을 요청하세요!\n\n"
                          "예시: \"문서 구조 보여줘\", \"교육목표 섹션 읽어줘\", "
                          "\"'2025년'을 '2026년'으로 바꿔줘\"")

    # ------------------------------------------------------------------
    # 채팅 표시
    # ------------------------------------------------------------------

    def _append_chat(self, role: str, text: str):
        self.chat_display.configure(state="normal")

        if role == "user":
            prefix = "\n나: "
        elif role == "assistant":
            prefix = "\nAI: "
        elif role == "tool":
            prefix = "\n  [도구] "
        else:
            prefix = "\n"

        self.chat_display.insert("end", prefix, role)
        self.chat_display.insert("end", text + "\n", role)
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _set_status(self, text: str):
        self.status_var.set(text)

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _connect_hwp(self):
        def worker():
            try:
                result = self.controller.connect(visible=True)
                self.result_queue.put(("status", result))
                self.result_queue.put(("set_status", "한글 연결됨"))
            except Exception as e:
                self.result_queue.put(("status", f"연결 실패: {e}"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("한글 연결 중...")

    def _open_file_dialog(self):
        filepath = filedialog.askopenfilename(
            title="HWP/HWPX 파일 선택",
            filetypes=[("한글 파일", "*.hwp *.hwpx"), ("모든 파일", "*.*")],
        )
        if filepath:
            self._open_file(filepath)

    def _open_file(self, filepath: str):
        def worker():
            try:
                result = self.controller.open_file(filepath)
                self.result_queue.put(("status", result))
                self.result_queue.put(("file", filepath))
            except Exception as e:
                self.result_queue.put(("status", f"파일 열기 실패: {e}"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("파일 열기 중...")

    def _save_file(self):
        def worker():
            try:
                result = self.controller.save_file()
                self.result_queue.put(("status", result))
            except Exception as e:
                self.result_queue.put(("status", f"저장 실패: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_chat(self):
        self.messages.clear()
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self._append_chat("system", "대화가 초기화되었습니다.")

    def _on_enter(self, event):
        if not event.state & 1:  # Shift 키가 안 눌렸으면
            self._send_message()
            return "break"

    def _send_message(self):
        if self.is_processing:
            return

        text = self.input_text.get("1.0", "end").strip()
        if not text:
            return

        self.input_text.delete("1.0", "end")
        self._append_chat("user", text)

        api_key = self.api_key_var.get().strip()
        if not api_key:
            self._append_chat("system", "API Key를 먼저 입력해주세요.")
            return

        self.api_key = api_key
        self.messages.append({"role": "user", "content": text})

        self.is_processing = True
        self.send_btn.configure(state="disabled")
        self._set_status("AI 처리 중...")

        def worker():
            try:
                reply = call_claude_with_tools(
                    messages=self.messages,
                    controller=self.controller,
                    on_status=lambda s: self.result_queue.put(("set_status", s)),
                    api_key=self.api_key,
                )
                self.result_queue.put(("reply", reply))
            except Exception as e:
                self.result_queue.put(("error", str(e)))
            finally:
                self.result_queue.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Queue 폴링 (메인 스레드에서 UI 업데이트)
    # ------------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                msg_type, msg_data = self.result_queue.get_nowait()

                if msg_type == "reply":
                    self._append_chat("assistant", msg_data)
                elif msg_type == "error":
                    self._append_chat("system", f"오류: {msg_data}")
                elif msg_type == "status":
                    self._append_chat("system", msg_data)
                elif msg_type == "set_status":
                    self._set_status(msg_data)
                elif msg_type == "file":
                    self.file_var.set(os.path.basename(msg_data))
                elif msg_type == "done":
                    self.is_processing = False
                    self.send_btn.configure(state="normal")
                    self._set_status("준비")

        except queue.Empty:
            pass

        self.root.after(100, self._poll_queue)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# 엔트리포인트
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = HwpChatApp()
    app.run()
