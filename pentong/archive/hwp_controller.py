"""HWP COM Controller — 한글 프로그램 실시간 제어 모듈.

한글 프로그램과의 COM 연결을 유지하면서
문서 읽기, 구조 파악, 텍스트 교체, 섹션 교체 등을 수행한다.
Claude API tool_use에서 호출되는 함수들의 백엔드.
"""

from __future__ import annotations

import os
import threading
from typing import Optional


class HwpController:
    """한글 프로그램 COM 자동화 컨트롤러.

    연결을 유지한 채로 여러 작업을 수행할 수 있다.
    모든 COM 호출은 생성된 스레드에서 이루어져야 하므로,
    외부에서 호출 시 동일 스레드를 보장해야 한다.
    """

    def __init__(self):
        self._hwp = None
        self._lock = threading.Lock()
        self._current_file: Optional[str] = None

    # ------------------------------------------------------------------
    # 연결 관리
    # ------------------------------------------------------------------

    def connect(self, visible: bool = True) -> str:
        """한글 프로그램에 연결한다."""
        if self._hwp is not None:
            return "이미 한글 프로그램에 연결되어 있습니다."

        import pythoncom
        pythoncom.CoInitialize()

        import win32com.client as win32

        for prog_id in ("HWPFrame.HwpObject", "Hwp.HwpObject"):
            try:
                self._hwp = win32.gencache.EnsureDispatch(prog_id)
                break
            except Exception:
                continue

        if self._hwp is None:
            raise RuntimeError("한글 프로그램을 찾을 수 없습니다. 한컴 한글이 설치되어 있는지 확인하세요.")

        self._hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
        if visible:
            try:
                self._hwp.XHwpWindows.Item(0).Visible = True
            except Exception:
                pass

        return "한글 프로그램 연결 성공"

    def disconnect(self) -> str:
        """한글 프로그램 연결을 해제한다."""
        if self._hwp is None:
            return "연결된 한글 프로그램이 없습니다."
        try:
            self._hwp.Quit()
        except Exception:
            pass
        self._hwp = None
        self._current_file = None

        import pythoncom
        pythoncom.CoUninitialize()
        return "한글 프로그램 종료 완료"

    def _ensure_connected(self):
        if self._hwp is None:
            self.connect(visible=True)

    # ------------------------------------------------------------------
    # 파일 관리
    # ------------------------------------------------------------------

    def open_file(self, filepath: str) -> str:
        """HWP/HWPX 파일을 연다."""
        self._ensure_connected()
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            return f"파일을 찾을 수 없습니다: {filepath}"

        try:
            self._hwp.Open(filepath)
            self._current_file = filepath
            return f"파일 열기 성공: {os.path.basename(filepath)}"
        except Exception as e:
            return f"파일 열기 실패: {e}"

    def save_file(self) -> str:
        """현재 문서를 저장한다."""
        self._ensure_connected()
        try:
            self._hwp.Save()
            return f"저장 완료: {self._current_file}"
        except Exception as e:
            return f"저장 실패: {e}"

    def save_as(self, filepath: str) -> str:
        """다른 이름으로 저장한다."""
        self._ensure_connected()
        filepath = os.path.abspath(filepath)
        try:
            self._hwp.SaveAs(filepath)
            self._current_file = filepath
            return f"저장 완료: {filepath}"
        except Exception as e:
            return f"저장 실패: {e}"

    def get_current_file(self) -> str:
        """현재 열린 파일 경로를 반환한다."""
        if self._current_file:
            return f"현재 열린 파일: {self._current_file}"
        return "현재 열린 파일이 없습니다."

    # ------------------------------------------------------------------
    # 문서 읽기
    # ------------------------------------------------------------------

    def read_full_text(self) -> str:
        """문서 전체 텍스트를 읽는다."""
        self._ensure_connected()
        try:
            self._hwp.HAction.Run("MoveDocBegin")
            self._hwp.InitScan(0x0010)

            paragraphs = []
            while True:
                state, text = self._hwp.GetText()
                if state in (0, 1):
                    if text and text.strip():
                        paragraphs.append(text.strip())
                    break
                if text and text.strip():
                    paragraphs.append(text.strip())

            self._hwp.ReleaseScan()

            if not paragraphs:
                return "문서가 비어있거나 텍스트를 읽을 수 없습니다."

            full_text = "\n".join(paragraphs)
            return full_text

        except Exception as e:
            return f"텍스트 읽기 실패: {e}"

    def read_document_structure(self) -> str:
        """문서 구조를 분석하여 섹션/제목 목록을 반환한다."""
        self._ensure_connected()
        try:
            self._hwp.HAction.Run("MoveDocBegin")
            self._hwp.InitScan(0x0010)

            paragraphs = []
            while True:
                state, text = self._hwp.GetText()
                if state in (0, 1):
                    if text and text.strip():
                        paragraphs.append(text.strip())
                    break
                if text and text.strip():
                    paragraphs.append(text.strip())

            self._hwp.ReleaseScan()

            if not paragraphs:
                return "문서가 비어있습니다."

            result_lines = [f"총 {len(paragraphs)}개 문단\n"]
            sections = []

            for i, para in enumerate(paragraphs):
                heading = self._is_heading(para)
                if heading:
                    sections.append({"index": i, "title": para})
                    result_lines.append(f"[{i:3d}] >> {para[:120]}")
                elif i < 20:
                    preview = para[:100] + ("..." if len(para) > 100 else "")
                    result_lines.append(f"[{i:3d}]    {preview}")

            result_lines.append(f"\n제목/섹션 후보 {len(sections)}개:")
            for s in sections:
                result_lines.append(f"  [{s['index']:3d}] {s['title']}")

            return "\n".join(result_lines)

        except Exception as e:
            return f"구조 분석 실패: {e}"

    def read_section(self, keyword: str) -> str:
        """특정 키워드가 포함된 섹션의 내용을 읽는다."""
        self._ensure_connected()
        try:
            paragraphs = self._get_all_paragraphs()
            if not paragraphs:
                return "문서가 비어있습니다."

            sections = self._find_sections(paragraphs, keyword)
            if not sections:
                # 키워드가 포함된 문단이라도 찾기
                matches = []
                for i, p in enumerate(paragraphs):
                    if keyword in p:
                        matches.append(f"  [{i}] {p[:100]}")
                if matches:
                    return f'"{keyword}" 제목 섹션은 없지만 포함된 문단:\n' + "\n".join(matches[:10])
                return f'"{keyword}"가 포함된 섹션이나 문단을 찾을 수 없습니다.'

            results = []
            for start, end, title in sections:
                body = paragraphs[start:end]
                results.append(f"섹션: {title}")
                results.append(f"위치: 문단 {start}~{end - 1} ({end - start}개 문단)")
                results.append("내용:")
                for j, p in enumerate(body):
                    results.append(f"  [{start + j}] {p}")
                results.append("")

            return "\n".join(results)

        except Exception as e:
            return f"섹션 읽기 실패: {e}"

    def find_text(self, search_text: str) -> str:
        """문서에서 특정 텍스트를 검색한다."""
        self._ensure_connected()
        try:
            paragraphs = self._get_all_paragraphs()
            if not paragraphs:
                return "문서가 비어있습니다."

            matches = []
            for i, para in enumerate(paragraphs):
                if search_text in para:
                    # 해당 텍스트 주변 컨텍스트 표시
                    idx = para.find(search_text)
                    context_start = max(0, idx - 30)
                    context_end = min(len(para), idx + len(search_text) + 30)
                    context = para[context_start:context_end]
                    if context_start > 0:
                        context = "..." + context
                    if context_end < len(para):
                        context = context + "..."
                    matches.append(f"  문단[{i}]: {context}")

            if not matches:
                return f'"{search_text}"를 찾을 수 없습니다.'

            return f'"{search_text}" 검색 결과 ({len(matches)}건):\n' + "\n".join(matches)

        except Exception as e:
            return f"검색 실패: {e}"

    # ------------------------------------------------------------------
    # 문서 수정
    # ------------------------------------------------------------------

    def replace_text(self, find_str: str, replace_str: str) -> str:
        """문서 전체에서 텍스트를 찾아 바꾼다."""
        self._ensure_connected()
        try:
            self._hwp.HAction.Run("MoveDocBegin")

            pset = self._hwp.HParameterSet.HFindReplace
            self._hwp.HAction.GetDefault("AllReplace", pset.HSet)
            pset.FindString = find_str
            pset.ReplaceString = replace_str
            pset.IgnoreMessage = 1
            pset.HSet.SetItem("IgnoreCase", 0)
            pset.HSet.SetItem("WholeWordOnly", 0)
            pset.HSet.SetItem("AllWordForms", 0)
            pset.HSet.SetItem("SeveralWords", 0)
            pset.HSet.SetItem("UseWildCards", 0)
            pset.HSet.SetItem("AutoSpell", 1)
            pset.Direction = 0
            pset.ReplaceMode = 1

            result = self._hwp.HAction.Execute("AllReplace", pset.HSet)
            return f'찾아 바꾸기 완료: "{find_str}" → "{replace_str}" (result={result})'

        except Exception as e:
            return f"찾아 바꾸기 실패: {e}"

    def replace_section_content(self, keyword: str, new_content: str) -> str:
        """특정 섹션의 본문을 새 내용으로 교체한다.

        keyword: 섹션 제목에 포함된 키워드
        new_content: 교체할 새 내용 (줄바꿈으로 문단 구분)
        """
        self._ensure_connected()
        try:
            paragraphs = self._get_all_paragraphs()
            if not paragraphs:
                return "문서가 비어있습니다."

            sections = self._find_sections(paragraphs, keyword)
            if not sections:
                return f'"{keyword}" 섹션을 찾을 수 없습니다.'

            mst_start, mst_end, mst_title = sections[0]
            body_count = mst_end - mst_start - 1  # 제목 제외한 본문 문단 수

            # 새 내용을 문단 단위로 분리
            new_paras = [p.strip() for p in new_content.split("\n") if p.strip()]
            if not new_paras:
                return "교체할 새 내용이 비어있습니다."

            # 제목 다음 문단(본문 시작)으로 커서 이동
            self._hwp.HAction.Run("MoveDocBegin")
            for _ in range(mst_start + 1):
                self._hwp.HAction.Run("MoveNextParaBegin")
            self._hwp.HAction.Run("MoveParaBegin")

            # 기존 본문 선택 및 삭제
            if body_count > 0:
                for _ in range(body_count - 1):
                    self._hwp.HAction.Run("MoveSelectNextParaBegin")
                self._hwp.HAction.Run("MoveSelectParaEnd")
                self._hwp.HAction.Run("Delete")

            # 새 내용 삽입
            for i, para in enumerate(new_paras):
                if i > 0:
                    self._hwp.HAction.Run("BreakPara")
                pset = self._hwp.HParameterSet.HInsertText
                self._hwp.HAction.GetDefault("InsertText", pset.HSet)
                pset.Text = para
                self._hwp.HAction.Execute("InsertText", pset.HSet)

            return (
                f'섹션 교체 완료: "{mst_title}"\n'
                f"  기존 본문 {body_count}개 문단 삭제\n"
                f"  새 내용 {len(new_paras)}개 문단 삽입"
            )

        except Exception as e:
            return f"섹션 교체 실패: {e}"

    def insert_text_at_cursor(self, text: str) -> str:
        """현재 커서 위치에 텍스트를 삽입한다."""
        self._ensure_connected()
        try:
            pset = self._hwp.HParameterSet.HInsertText
            self._hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = text
            self._hwp.HAction.Execute("InsertText", pset.HSet)
            return f"텍스트 삽입 완료 ({len(text)}자)"
        except Exception as e:
            return f"텍스트 삽입 실패: {e}"

    def move_to_paragraph(self, para_index: int) -> str:
        """특정 문단으로 커서를 이동한다."""
        self._ensure_connected()
        try:
            self._hwp.HAction.Run("MoveDocBegin")
            for _ in range(para_index):
                self._hwp.HAction.Run("MoveNextParaBegin")
            return f"문단 [{para_index}]로 커서 이동 완료"
        except Exception as e:
            return f"커서 이동 실패: {e}"

    def replace_paragraph(self, para_index: int, new_text: str) -> str:
        """특정 문단의 내용을 새 텍스트로 교체한다."""
        self._ensure_connected()
        try:
            # 해당 문단으로 이동
            self._hwp.HAction.Run("MoveDocBegin")
            for _ in range(para_index):
                self._hwp.HAction.Run("MoveNextParaBegin")

            # 문단 전체 선택
            self._hwp.HAction.Run("MoveParaBegin")
            self._hwp.HAction.Run("MoveSelectParaEnd")

            # 삭제 후 새 텍스트 삽입
            self._hwp.HAction.Run("Delete")

            pset = self._hwp.HParameterSet.HInsertText
            self._hwp.HAction.GetDefault("InsertText", pset.HSet)
            pset.Text = new_text
            self._hwp.HAction.Execute("InsertText", pset.HSet)

            return f"문단 [{para_index}] 교체 완료 → \"{new_text[:50]}{'...' if len(new_text) > 50 else ''}\""
        except Exception as e:
            return f"문단 교체 실패: {e}"

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _get_all_paragraphs(self) -> list[str]:
        """문서의 모든 문단을 리스트로 반환."""
        self._hwp.HAction.Run("MoveDocBegin")
        self._hwp.InitScan(0x0010)

        paragraphs = []
        while True:
            state, text = self._hwp.GetText()
            if state in (0, 1):
                if text and text.strip():
                    paragraphs.append(text.strip())
                break
            if text and text.strip():
                paragraphs.append(text.strip())

        self._hwp.ReleaseScan()
        return paragraphs

    @staticmethod
    def _is_heading(para: str) -> bool:
        """제목 후보인지 판별."""
        return len(para) < 80 and (
            "전공" in para
            or "학과" in para
            or "제목" in para
            or para.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."))
            or para.startswith(("I.", "II.", "III.", "IV.", "V."))
            or para.startswith(("제1", "제2", "제3"))
            or para.startswith(("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"))
            or para.startswith(("▮", "∙"))
            or para.startswith(("가.", "나.", "다.", "라.", "마."))
        )

    def _find_sections(self, paragraphs: list[str], keyword: str) -> list[tuple[int, int, str]]:
        """키워드가 포함된 섹션의 (시작, 끝, 제목) 목록 반환."""
        headings = []
        for i, para in enumerate(paragraphs):
            if self._is_heading(para):
                headings.append(i)

        results = []
        for hi, idx in enumerate(headings):
            if keyword in paragraphs[idx]:
                start = idx
                end = headings[hi + 1] if hi + 1 < len(headings) else len(paragraphs)
                results.append((start, end, paragraphs[idx]))

        return results
