"""뚝딱비서 — 한글 문서 AI 어시스턴트 데스크톱앱.

Claude Code CLI 기반. Node.js + Claude CLI 자동 설치 지원.
파일 드래그 앤 드롭으로 문서를 바로 언급할 수 있다.

실행:
  python pentong_chat.py
"""
from __future__ import annotations

__version__ = "0.0.25"

# GitHub Releases 자동 업데이트 좌표
GITHUB_OWNER = "FirstNotFists"
GITHUB_REPO = "Quick-Secretary-Release"


import json
import os
import shutil
import subprocess
import sys
import threading
import time
import queue
import unicodedata
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
from pathlib import Path


# ── 경로 설정 ──

def _resource_path(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def _short_path_windows(path: str) -> str:
    """Windows GetShortPathNameW 로 ASCII 8.3 short path 변환.

    한글 NFC/NFD 자모 분리 path 가 Popen 의 cwd 인자로 들어가면
    CreateProcessW 가 silent fail 한다 (Google Drive zip 다운로드는 NFD 로
    저장). short path (예: C:\\PROGRA~1\\NEWSCE~1) 는 ASCII 만 사용해서
    NFC/NFD 무관 동작.

    NTFS 8.3 short name 이 비활성화된 환경 또는 변환 실패 시 원본 반환.
    """
    if sys.platform != 'win32':
        return path
    try:
        import ctypes
        from ctypes import wintypes
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        GetShortPathNameW.restype = wintypes.DWORD
        buf = ctypes.create_unicode_buffer(520)
        rv = GetShortPathNameW(path, buf, 520)
        if rv == 0 or rv >= 520:
            return path
        result = buf.value
        # short path 변환이 의미있게 일어났는지 확인
        if not result or not os.path.isdir(result):
            return path
        return result
    except Exception:
        return path


def _resolve_actual_path(path: str) -> str:
    """Windows 에서 한글 NFC/NFD path mismatch 해결.

    Google Drive 의 zip 다운로드는 폴더명을 macOS 스타일 NFD (자모 분리) 로
    저장한다. 이 path 가 Popen 의 cwd 인자로 들어가면 Windows CreateProcessW
    가 NFC↔NFD 매칭을 못 해서 process 가 silent fail (returncode 0, stdout/
    stderr 모두 비어있음) 한다.

    이 함수는 각 path component 를 부모의 listdir 결과와 비교해 실제 디스크
    저장 표기로 재구성한다. 매칭은 NFC/NFD 둘 다 시도. 매칭 실패한 component
    는 원본 그대로 두고 진행 (호출자가 적절히 에러 처리).
    """
    if not path:
        return path
    abs_path = os.path.abspath(path)
    parts = abs_path.replace('/', os.sep).split(os.sep)
    if not parts:
        return abs_path
    rebuilt = parts[0] + os.sep  # 'C:\\' 시작
    for part in parts[1:]:
        if not part:
            continue
        candidate = os.path.join(rebuilt, part)
        # 이미 실제 표기와 일치하면 그대로
        try:
            entries = os.listdir(rebuilt)
        except (OSError, FileNotFoundError):
            return abs_path
        if part in entries:
            rebuilt = candidate
            continue
        target_nfc = unicodedata.normalize('NFC', part)
        target_nfd = unicodedata.normalize('NFD', part)
        match = None
        for e in entries:
            if (e == part
                    or unicodedata.normalize('NFC', e) == target_nfc
                    or unicodedata.normalize('NFD', e) == target_nfd):
                match = e
                break
        if match:
            rebuilt = os.path.join(rebuilt, match)
        else:
            return abs_path  # 매칭 실패 — 원본으로 fallback
    return rebuilt


if getattr(sys, 'frozen', False):
    DEFAULT_WORK_DIR = os.path.dirname(sys.executable)
else:
    DEFAULT_WORK_DIR = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT_FILE = _resource_path("pentong_system_prompt.txt")
# v0.0.25: markdown harness 토대 모듈 디렉토리. _invariants.md / _index.md /
# _session.md / _output_contract.md / _loop_guard.md 자동 합성됨.
SKILLS_DIR = _resource_path("prompts/skills")
TEMPLATES_DIR = os.path.join(DEFAULT_WORK_DIR, "templates")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ddukddak")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
# 대화 맥락 캐시 — 시스템 프롬프트 주입이 실패해도 Claude 가 스스로 Read 로
# 읽어서 맥락 복원 가능한 self-managed memory 파일.
SESSION_CACHE_FILE = os.path.join(CONFIG_DIR, "current_session.md")


def _find_claude_cmd() -> str:
    """Claude CLI 경로를 찾는다."""
    candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "nodejs", "claude.cmd"),
        "claude",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "claude"


CLAUDE_CMD = _find_claude_cmd()

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ── 설정 관리 ──

def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(config: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _check_claude_cli() -> bool:
    try:
        result = subprocess.run(
            [CLAUDE_CMD, "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _check_claude_logged_in() -> bool:
    """Claude CLI에 로그인되어 있는지 확인."""
    # .claude 디렉토리에 인증 정보가 있는지 확인
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return False
    # credentials 또는 auth 파일 확인
    for name in [".credentials.json", "credentials.json", "auth.json", ".auth"]:
        if (claude_dir / name).exists():
            return True
    # 설정 파일에서 로그인 이력 확인
    config = _load_config()
    return config.get("logged_in", False)


def _open_inprivate(url: str = ""):
    """InPrivate/시크릿 브라우저를 열어 구글 세션을 남기지 않는다."""
    browsers = [
        ("msedge", "--inprivate"),
        ("chrome", "--incognito"),
        ("firefox", "--private-window"),
    ]
    for exe, flag in browsers:
        try:
            if url:
                subprocess.Popen([exe, flag, url], creationflags=_CREATE_NO_WINDOW)
            else:
                subprocess.Popen([exe, flag], creationflags=_CREATE_NO_WINDOW)
            return True
        except FileNotFoundError:
            continue
    # 실패하면 기본 브라우저로
    if url:
        os.startfile(url)
    return False


# ── 업데이트 확인 다이얼로그 (스크롤 가능 노트 + 고정 버튼) ──

def _ask_update_confirm(parent: tk.Misc, tag_name: str, size_str: str,
                        notes: str) -> bool:
    """새 버전 발견 다이얼로그. 릴리스 노트가 길어도 [예]/[아니오] 가 항상 보임."""
    dlg = tk.Toplevel(parent)
    dlg.title("새 버전 발견")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    header = ttk.Frame(dlg, padding=(15, 12, 15, 6))
    header.pack(fill="x")
    ttk.Label(header, text=f"새 버전 {tag_name} 이 있습니다.",
              font=("맑은 고딕", 11, "bold")).pack(anchor="w")
    ttk.Label(header, text=f"다운로드 크기: {size_str}",
              font=("맑은 고딕", 9), foreground="gray").pack(anchor="w", pady=(2, 0))

    notes_body = (notes or "").strip()
    if notes_body:
        ttk.Label(dlg, text="변경점:", padding=(15, 4, 15, 0),
                  font=("맑은 고딕", 9)).pack(anchor="w")
        notes_frame = ttk.Frame(dlg, padding=(15, 0, 15, 0))
        notes_frame.pack(fill="both", expand=False)
        txt = tk.Text(notes_frame, width=60, height=10, wrap="word",
                      font=("맑은 고딕", 9), relief="solid", borderwidth=1)
        scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.insert("1.0", notes_body)
        txt.configure(state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    prompt = ttk.Label(dlg, text="지금 업데이트하고 재시작하시겠습니까?",
                       padding=(15, 10, 15, 4), font=("맑은 고딕", 10))
    prompt.pack(anchor="w")

    btns = ttk.Frame(dlg, padding=(15, 4, 15, 12))
    btns.pack(fill="x")
    result = {"ok": False}

    def on_yes():
        result["ok"] = True
        dlg.destroy()

    def on_no():
        result["ok"] = False
        dlg.destroy()

    yes_btn = ttk.Button(btns, text="예 (업데이트)", command=on_yes)
    no_btn = ttk.Button(btns, text="나중에", command=on_no)
    no_btn.pack(side="right", padx=(6, 0))
    yes_btn.pack(side="right")

    dlg.protocol("WM_DELETE_WINDOW", on_no)
    dlg.bind("<Escape>", lambda e: on_no())
    dlg.bind("<Return>", lambda e: on_yes())

    # 부모 창 중앙에 배치
    dlg.update_idletasks()
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dw = dlg.winfo_width()
        dh = dlg.winfo_height()
        dlg.geometry(f"+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
    except Exception:
        pass

    yes_btn.focus_set()
    parent.wait_window(dlg)
    return result["ok"]


# ── 첫 실행 설정 마법사 ──

class SetupWizard:
    """Claude CLI 설치 + 로그인 설정 마법사."""

    def __init__(self, parent: tk.Tk | None = None):
        self.result: dict | None = None
        self._installing = False

        self.win = tk.Toplevel(parent) if parent else tk.Tk()
        self.win.title("뚝딱비서 — 설정 / 업데이트")
        self.win.geometry("580x580")
        self.win.resizable(False, False)
        self.win.grab_set()
        self._pending_update = None  # UpdateInfo 인스턴스 (업데이트 확인 후 세팅)

        self._build_ui()

        if not parent:
            self.win.mainloop()

    def _build_ui(self):
        pad = {"padx": 20, "pady": 5}

        # 타이틀
        ttk.Label(self.win, text="뚝딱비서 설정 / 업데이트",
                  font=("맑은 고딕", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(self.win, text="처음엔 1-2단계만 완료하면 OK. 3단계는 버전 관리/업데이트용입니다.",
                  font=("맑은 고딕", 10)).pack(pady=(0, 10))

        # ── STEP 1: Claude CLI 설치 ──
        f1 = ttk.LabelFrame(self.win, text="1단계: Claude AI 엔진 설치", padding=10)
        f1.pack(fill="x", **pad)

        status_frame = ttk.Frame(f1)
        status_frame.pack(fill="x")

        self.cli_status_var = tk.StringVar()
        self.cli_status_label = ttk.Label(status_frame, textvariable=self.cli_status_var,
                                          font=("맑은 고딕", 10))
        self.cli_status_label.pack(side="left")

        self.install_btn = ttk.Button(status_frame, text="자동 설치",
                                      command=self._auto_install)
        self.install_btn.pack(side="right")

        self.install_progress_var = tk.StringVar()
        self.install_progress_label = ttk.Label(
            f1, textvariable=self.install_progress_var,
            foreground="#4A90D9", font=("맑은 고딕", 9), wraplength=500,
        )
        self.install_progress_label.pack(anchor="w", pady=(4, 0))

        self.install_bar = ttk.Progressbar(f1, mode="indeterminate", length=500)

        # ── STEP 2: Claude 로그인 ──
        f2 = ttk.LabelFrame(self.win, text="2단계: Claude 로그인", padding=10)
        f2.pack(fill="x", **pad)

        self.login_status_var = tk.StringVar()
        self.login_status_label = ttk.Label(f2, textvariable=self.login_status_var,
                                            font=("맑은 고딕", 10))
        self.login_status_label.pack(side="left")

        login_btn_frame = ttk.Frame(f2)
        login_btn_frame.pack(anchor="e")

        self.login_btn = ttk.Button(login_btn_frame, text="Claude 로그인하기",
                                    command=self._do_login)
        self.login_btn.pack(side="left", padx=2)

        self.google_logout_btn = ttk.Button(login_btn_frame, text="구글 로그아웃",
                                            command=self._google_logout)
        self.google_logout_btn.pack(side="left", padx=2)

        ttk.Label(f2, text="로그인 시 시크릿 브라우저가 열립니다. 로그인 후 창을 닫으면 구글 세션은 자동 삭제됩니다.",
                  foreground="gray", font=("맑은 고딕", 8), wraplength=500).pack(anchor="w", pady=(5, 0))

        self.login_progress_var = tk.StringVar()
        ttk.Label(f2, textvariable=self.login_progress_var,
                  foreground="#4A90D9", font=("맑은 고딕", 9)).pack(anchor="w", pady=(2, 0))

        # ── STEP 3: 버전 / 업데이트 ──
        f3 = ttk.LabelFrame(self.win, text="3단계: 버전 / 자동 업데이트", padding=10)
        f3.pack(fill="x", **pad)

        ver_row = ttk.Frame(f3)
        ver_row.pack(fill="x")

        ttk.Label(ver_row, text=f"현재 버전: v{__version__}",
                  font=("맑은 고딕", 10)).pack(side="left")

        self.check_update_btn = ttk.Button(ver_row, text="업데이트 확인",
                                           command=self._check_update)
        self.check_update_btn.pack(side="right")

        self.update_status_var = tk.StringVar(value="버튼을 눌러 새 버전을 확인하세요.")
        self.update_status_label = ttk.Label(
            f3, textvariable=self.update_status_var,
            font=("맑은 고딕", 9), foreground="gray", wraplength=500,
        )
        self.update_status_label.pack(anchor="w", pady=(6, 0))

        self.update_apply_btn = ttk.Button(
            f3, text="지금 업데이트하고 재시작",
            command=self._apply_update,
        )  # pack 은 업데이트 발견 시에만

        self.update_bar = ttk.Progressbar(f3, mode="determinate",
                                          length=500, maximum=100)
        # pack 은 다운로드 중에만

        # ── 하단 버튼 ──
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=20, pady=15)

        self.save_btn = ttk.Button(btn_frame, text="설정 완료",
                                   command=self._save)
        self.save_btn.pack(side="right", padx=5)
        ttk.Button(btn_frame, text="취소",
                   command=self._cancel).pack(side="right")

        # 초기 상태 표시
        self._refresh_status()

    def _refresh_status(self):
        """설치/로그인 상태 갱신."""
        from core.setup_helper import check_python, check_git, check_nodejs, check_claude_cli
        py = check_python()
        git = check_git()
        node = check_nodejs()
        cli = check_claude_cli()

        installed = [x for x, v in [("Python", py), ("Git", git), ("Node", node), ("CLI", cli)] if v["installed"]]
        missing = [x for x, v in [("Python", py), ("Git", git), ("Node.js", node), ("Claude CLI", cli)] if not v["installed"]]

        if not missing:
            self.cli_status_var.set(f"모두 설치 완료!")
            self.cli_status_label.configure(foreground="green")
            self.install_btn.configure(text="재설치", state="normal")
        elif missing:
            self.cli_status_var.set(f"필요: {', '.join(missing)}")
            self.cli_status_label.configure(foreground="red" if len(missing) > 2 else "orange")
            self.install_btn.configure(state="normal")

        # 로그인 상태
        if cli["installed"]:
            self.login_btn.configure(state="normal")
            logged_in = _check_claude_logged_in()
            if logged_in:
                self.login_status_var.set("로그인됨")
                self.login_status_label.configure(foreground="green")
            else:
                self.login_status_var.set("로그인 필요")
                self.login_status_label.configure(foreground="orange")
        else:
            self.login_btn.configure(state="disabled")
            self.login_status_var.set("먼저 1단계를 완료하세요")
            self.login_status_label.configure(foreground="gray")

    # ── 자동 설치 ──

    def _auto_install(self):
        if self._installing:
            return
        self._installing = True
        self.install_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")
        self.install_bar.pack(fill="x", pady=(4, 0))
        self.install_bar.start(20)

        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        from core.setup_helper import install_all

        def on_progress(msg):
            self.win.after(0, lambda m=msg: self.install_progress_var.set(m))

        result = install_all(progress_cb=on_progress)

        def on_done():
            self.install_bar.stop()
            self.install_bar.pack_forget()
            self._installing = False
            self.save_btn.configure(state="normal")
            self._refresh_status()

            if result["success"]:
                self.install_progress_var.set("설치 완료!")
            else:
                failed = []
                if not result.get("python_ok"):
                    failed.append("Python")
                if not result.get("git_ok"):
                    failed.append("Git")
                if not result.get("nodejs_ok"):
                    failed.append("Node.js")
                if not result.get("claude_cli_ok"):
                    failed.append("Claude CLI")
                self.install_progress_var.set(f"{', '.join(failed)} 설치 실패. 다시 시도하세요.")

        self.win.after(0, on_done)

    # ── Claude 로그인 ──

    def _do_login(self):
        """Claude CLI 로그인 — 콘솔 창을 열어서 대화형 로그인 진행."""
        self.login_progress_var.set("로그인 콘솔이 열립니다. 브라우저에서 로그인을 완료하세요.")
        self.login_btn.configure(state="disabled")

        threading.Thread(target=self._run_login, daemon=True).start()

    def _run_login(self):
        """사용자가 보이는 콘솔 창에서 claude를 실행하여 로그인."""
        try:
            import tempfile
            from core.setup_helper import _find_claude, _refresh_path, NPM_GLOBAL_DIR

            _refresh_path()

            # claude 경로 찾기
            claude_path = _find_claude()
            if not claude_path:
                claude_path = CLAUDE_CMD

            # 시크릿 브라우저 래퍼 생성
            wrapper_path = os.path.join(tempfile.gettempdir(), "ddukddak_browser.bat")
            with open(wrapper_path, "w") as f:
                f.write('@echo off\n')
                f.write('start msedge --inprivate %1 2>nul || start chrome --incognito %1 2>nul || start "" %1\n')

            # 로그인용 bat 스크립트 생성
            # claude를 대화형으로 실행 → 미로그인 시 자동으로 브라우저 로그인 유도
            login_bat = os.path.join(tempfile.gettempdir(), "ddukddak_login.bat")
            with open(login_bat, "w", encoding="utf-8") as f:
                f.write('@echo off\n')
                f.write('chcp 65001 >nul\n')
                f.write(f'set BROWSER={wrapper_path}\n')
                f.write(f'set PATH={NPM_GLOBAL_DIR};%PATH%\n')
                f.write('echo.\n')
                f.write('echo ============================================\n')
                f.write('echo   뚝딱비서 - Claude 로그인\n')
                f.write('echo ============================================\n')
                f.write('echo.\n')
                f.write('echo   브라우저가 열리면 로그인을 진행하세요.\n')
                f.write('echo   (시크릿 모드로 열리므로 구글 세션은 남지 않습니다)\n')
                f.write('echo.\n')
                f.write('echo   로그인 완료 후 이 창은 자동으로 닫힙니다.\n')
                f.write('echo.\n')
                f.write(f'"{claude_path}" -p "안녕" --model sonnet --max-turns 1\n')
                f.write('if %ERRORLEVEL% EQU 0 (\n')
                f.write('    echo.\n')
                f.write('    echo   로그인 성공! 이 창을 닫아주세요.\n')
                f.write(') else (\n')
                f.write('    echo.\n')
                f.write('    echo   로그인에 문제가 있습니다. 다시 시도하세요.\n')
                f.write(')\n')
                f.write('echo.\n')
                f.write('pause\n')

            # 사용자에게 보이는 새 콘솔 창에서 실행
            process = subprocess.Popen(
                ["cmd", "/c", "start", "뚝딱비서 로그인", "/wait", login_bat],
            )

            # 콘솔 창이 닫힐 때까지 대기
            process.wait(timeout=300)

            # 로그인 결과 확인
            from core.setup_helper import check_claude_cli
            cli = check_claude_cli()

            if cli["installed"]:
                # 실제로 로그인 되었는지 간단한 호출로 확인
                test = subprocess.run(
                    [claude_path, "-p", "ok", "--model", "sonnet", "--max-turns", "1"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=30,
                    creationflags=_CREATE_NO_WINDOW,
                )
                if test.returncode == 0:
                    config = _load_config()
                    config["logged_in"] = True
                    _save_config(config)

                    def on_success():
                        self.login_progress_var.set("로그인 완료!")
                        self.login_btn.configure(state="normal")
                        self._refresh_status()
                    self.win.after(0, on_success)
                    return

            def on_unknown():
                self.login_progress_var.set("로그인 확인 필요. '로그인하기'를 다시 눌러보세요.")
                self.login_btn.configure(state="normal")
                self._refresh_status()
            self.win.after(0, on_unknown)

        except subprocess.TimeoutExpired:
            def on_timeout():
                self.login_progress_var.set("시간 초과. 다시 시도하세요.")
                self.login_btn.configure(state="normal")
            self.win.after(0, on_timeout)
        except Exception as e:
            def on_error(err=str(e)):
                self.login_progress_var.set(f"오류: {err}")
                self.login_btn.configure(state="normal")
            self.win.after(0, on_error)

    def _google_logout(self):
        """구글 계정 로그아웃 — 시크릿 창으로 열어서 세션 정리."""
        _open_inprivate("https://accounts.google.com/Logout")

    # ── 업데이트 ──

    def _check_update(self):
        """GitHub API 로 최신 버전 확인."""
        self.check_update_btn.configure(state="disabled")
        self.update_status_var.set("GitHub 에서 최신 버전 확인 중...")
        self.update_status_label.configure(foreground="#4A90D9")
        self.update_apply_btn.pack_forget()
        threading.Thread(target=self._do_check_update, daemon=True).start()

    def _do_check_update(self):
        from core import updater
        info = updater.check_for_update(__version__)

        def on_done():
            self.check_update_btn.configure(state="normal")
            if info is None:
                # 최신이거나 네트워크 오류 — 한 번 더 찍어봐서 네트워크 판정
                try:
                    latest = updater.fetch_latest_release()
                    self.update_status_var.set(
                        f"최신 버전입니다 (현재 v{__version__} = 서버 {latest.tag_name})"
                    )
                    self.update_status_label.configure(foreground="green")
                except Exception:
                    self.update_status_var.set(
                        "업데이트 확인 실패 — 아직 릴리스가 없거나 네트워크 오류입니다."
                    )
                    self.update_status_label.configure(foreground="orange")
                return

            # 새 버전 발견 — 즉시 확인 다이얼로그 (단일 클릭 플로우)
            self._pending_update = info
            size_str = updater.human_size(info.asset_size) if info.asset_size else "?"

            if _ask_update_confirm(self.win, info.tag_name, size_str, info.body or ""):
                # 사용자 확인 — 바로 다운로드 시작 (다이얼로그 한 번 더 안 뜸)
                self._apply_update(skip_confirm=True)
            else:
                # 나중에 — 버튼 남겨둬서 다시 누르면 시도 가능
                self.update_status_var.set(
                    f"새 버전 {info.tag_name} 발견됨 — '지금 업데이트' 버튼으로 진행"
                )
                self.update_status_label.configure(foreground="#0066cc")
                self.update_apply_btn.pack(fill="x", pady=(8, 0))

        self.win.after(0, on_done)

    def _apply_update(self, skip_confirm: bool = False):
        info = self._pending_update
        if not info or not info.asset_url:
            return
        from core import updater
        current_exe = updater.get_current_exe_path()
        if current_exe is None:
            messagebox.showwarning(
                "개발 모드",
                "현재는 python 으로 직접 실행 중입니다.\n"
                "자동 업데이트는 PyInstaller 빌드된 exe 에서만 동작합니다.",
                parent=self.win,
            )
            return

        if not skip_confirm:
            if not messagebox.askyesno(
                "업데이트 확인",
                f"버전 {info.tag_name} 로 업데이트합니다.\n"
                f"다운로드 후 자동 재시작됩니다. 진행할까요?",
                parent=self.win,
            ):
                return

        # 새 파일명: 뚝딱비서_v0.0.6.exe 형태로 버전 고정
        new_filename = f"뚝딱비서_{info.tag_name}.exe"

        self.update_apply_btn.configure(state="disabled")
        self.check_update_btn.configure(state="disabled")
        self.update_bar.pack(fill="x", pady=(6, 0))
        self.update_bar["value"] = 0

        def worker():
            import tempfile
            new_exe = Path(tempfile.gettempdir()) / "_ddukddak_update_new.exe"

            def on_progress(done, total):
                if total:
                    pct = min(100, int(done * 100 / total))
                else:
                    pct = 0
                self.win.after(0, lambda p=pct, d=done, t=total:
                    self._update_progress(p, d, t))

            try:
                updater.download_update(info.asset_url, new_exe, on_progress)
            except Exception as e:
                self.win.after(0, lambda err=str(e): self._on_update_failed(err))
                return

            # 교체 + 재시작 (새 파일명으로 저장)
            try:
                updater.apply_update_and_restart(
                    current_exe, new_exe, new_filename=new_filename,
                )
            except Exception as e:
                self.win.after(0, lambda err=str(e): self._on_update_failed(err))
                return

            # PS 헬퍼 초기화 여유 + 사용자 피드백 표시 후 프로세스 즉시 kill.
            # sys.exit(0) 는 tkinter after 콜백 안에서 SystemExit 를 Tcl 이 먹어서
            # 프로세스가 안 죽음 (2026-04-20 실측). os._exit 로 C 레벨 즉시 종료.
            self.win.after(0, lambda: self.update_status_var.set(
                "업데이트 적용 중 — 잠시 후 자동 재시작합니다..."))
            self.win.after(2000, lambda: os._exit(0))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: int, downloaded: int, total: int):
        from core import updater
        self.update_bar["value"] = pct
        self.update_status_var.set(
            f"다운로드 중 {pct}% "
            f"({updater.human_size(downloaded)} / {updater.human_size(total) if total else '?'})"
        )

    def _on_update_failed(self, err: str):
        self.update_apply_btn.configure(state="normal")
        self.check_update_btn.configure(state="normal")
        self.update_bar.pack_forget()
        self.update_status_var.set(f"업데이트 실패: {err[:200]}")
        self.update_status_label.configure(foreground="red")

    # ── 저장/취소 ──

    def _save(self):
        if self._installing:
            messagebox.showinfo("설치 중", "설치가 진행 중입니다.",
                                parent=self.win)
            return

        if not _check_claude_cli():
            if not messagebox.askyesno("CLI 미설치",
                "Claude AI 엔진이 설치되지 않았습니다.\n"
                "1단계 '자동 설치'를 먼저 진행하시겠습니까?",
                parent=self.win):
                return
            self._auto_install()
            return

        self.result = {
            "mode": "cli",
            "model": "sonnet",
        }
        _save_config(self.result)
        self.win.destroy()

    def _cancel(self):
        self.win.destroy()


# ── 메인 앱 ──

class DdukddakApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"뚝딱비서 v{__version__} — 한글 문서 AI 어시스턴트")
        self.root.geometry("950x850")
        self.root.minsize(750, 650)

        self.work_dir = DEFAULT_WORK_DIR
        self.result_queue: queue.Queue = queue.Queue()
        self.is_processing = False
        # 대화 이력 — --continue 플래그가 CLI 레벨 세션 맥락을 이어가주지만
        # 앱은 history 를 별도로 유지해 session_cache 기록 + 턴 수 카운트에 사용.
        self.history: list[dict] = []
        self.current_process: subprocess.Popen | None = None  # 중단 버튼 타겟
        self._user_aborted = False  # 사용자가 중단 눌렀는지
        self._spinner_idx = 0
        self._spinner_after_id = None
        # 번들 assets(core/, rhwp_bridge/) 해제 1회 플래그 — 매 _call_claude
        # 마다 copytree 하는 I/O 오버헤드 방지 + AV 반복 스캔 회피.
        self._assets_prepared: set[str] = set()

        self.config = _load_config()
        self.system_prompt = self._load_system_prompt()

        self._build_ui()
        self._setup_drag_and_drop()
        self._poll_queue()

        if not self.config.get("mode"):
            self.root.after(100, self._show_setup)

    # v0.0.25: 토대 skill 모듈 합성 순서 (frontmatter priority 큰 값 우선,
    # 파일명 알파벳 정렬과 다를 수 있어서 명시적 순서). Phase 6+ 의 trigger
    # 기반 skill (xlsx_*, hwp_*, pdf_*) 은 런타임에 Claude 가 Read 하므로
    # 여기 포함 X.
    _HARNESS_FOUNDATION_SKILLS = (
        "_invariants.md",
        "_index.md",
        "_session.md",
        "_output_contract.md",
        "_loop_guard.md",
    )

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        """YAML frontmatter (--- ... ---) 제거. 없거나 형식 어긋나면 원본."""
        if not text.startswith("---"):
            return text
        end = text.find("\n---", 3)
        if end == -1:
            return text
        nl = text.find("\n", end + 4)
        if nl == -1:
            return ""
        return text[nl + 1:].lstrip()

    def _load_system_prompt(self) -> str:
        """base 프롬프트 + markdown harness 토대 skill 모듈 합성.

        v0.0.25 부터: pentong_system_prompt.txt 뒤에 prompts/skills/_*.md
        (always_load 토대 모듈 5개) 를 순서대로 append. frontmatter 는 제거하고
        본문만 합쳐서 Claude 에 전달. 합성 결과가 곧 _ensure_system_prompt_file
        에서 디스크로 보장되어 --append-system-prompt-file 로 CLI 에 주입된다.
        """
        parts: list[str] = []
        try:
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                parts.append(f.read())
        except FileNotFoundError:
            parts.append("당신은 한글(HWP) 문서 편집 전문 AI 어시스턴트입니다.")

        if os.path.isdir(SKILLS_DIR):
            for name in self._HARNESS_FOUNDATION_SKILLS:
                path = os.path.join(SKILLS_DIR, name)
                if not os.path.isfile(path):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError:
                    continue
                stripped = self._strip_frontmatter(body)
                parts.append(
                    f"\n\n---\n# (markdown harness skill: {name[:-3]})\n\n{stripped}"
                )

        return "\n".join(parts)

    def _build_ui(self):
        # 상단 바
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(10, 0))

        ttk.Label(top, text="작업 폴더:").pack(side="left")
        self.dir_var = tk.StringVar(value=self.work_dir)
        ttk.Entry(top, textvariable=self.dir_var, width=50).pack(side="left", padx=4)
        ttk.Button(top, text="변경", command=self._change_dir).pack(side="left", padx=(0, 5))
        ttk.Button(top, text="대화 초기화", command=self._clear).pack(side="left", padx=(0, 5))
        ttk.Button(top, text="설정", command=self._show_setup).pack(side="left")

        self.status_var = tk.StringVar(value="준비")
        self.status_label = ttk.Label(top, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side="right")

        self.conn_var = tk.StringVar()
        self.conn_label = ttk.Label(top, textvariable=self.conn_var, font=("맑은 고딕", 9))
        self.conn_label.pack(side="right", padx=10)
        self._update_conn_status()

        # 양식 선택 바
        tpl_frame = ttk.Frame(self.root)
        tpl_frame.pack(fill="x", padx=10, pady=(6, 0))

        ttk.Label(tpl_frame, text="양식:").pack(side="left")
        self.template_var = tk.StringVar(value="없음 (자유 형식)")
        self.template_combo = ttk.Combobox(
            tpl_frame, textvariable=self.template_var,
            state="readonly", width=45,
        )
        self.template_combo.pack(side="left", padx=4)
        ttk.Button(tpl_frame, text="새로고침", command=lambda: self._refresh_templates(confirm=True)).pack(side="left", padx=(0, 4))
        ttk.Button(tpl_frame, text="양식 폴더 지정", command=self._open_templates_dir).pack(side="left")

        self._refresh_templates()

        # 채팅 영역
        chat_frame = ttk.LabelFrame(self.root, text="대화")
        chat_frame.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self.chat = scrolledtext.ScrolledText(
            chat_frame, wrap="word", state="disabled",
            font=("맑은 고딕", 11), spacing3=5, padx=10, pady=10,
        )
        self.chat.pack(fill="both", expand=True)

        self.chat.tag_configure("user", foreground="#0066cc", font=("맑은 고딕", 11, "bold"))
        self.chat.tag_configure("ai", foreground="#222222")
        self.chat.tag_configure("info", foreground="#888888", font=("맑은 고딕", 9))
        self.chat.tag_configure("cost", foreground="#aa6600", font=("Consolas", 9))
        self.chat.tag_configure("tool", foreground="#cc6600", font=("Consolas", 10))
        self.chat.tag_configure("progress", foreground="#4A90D9", font=("맑은 고딕", 10))
        self.chat.tag_configure("error", foreground="#cc0000", font=("맑은 고딕", 10))
        self.chat.tag_configure("file", foreground="#6B4C9A", font=("Consolas", 10, "italic"))

        # 입력 영역
        inp_frame = ttk.LabelFrame(self.root, text="메시지 입력 (Enter: 전송 / Shift+Enter: 줄바꿈 / 파일 드래그 가능)")
        inp_frame.pack(fill="x", padx=10, pady=(4, 10))
        inp_frame.columnconfigure(0, weight=1)

        self.input_box = tk.Text(
            inp_frame, height=3, wrap="word",
            font=("맑은 고딕", 12), bg="#FFFFF0",
            relief="solid", borderwidth=1,
        )
        self.input_box.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        self.input_box.bind("<Return>", self._on_enter)
        self.input_box.bind("<Shift-Return>", lambda e: None)

        # 파일 첨부 버튼
        self.attach_btn = tk.Button(
            inp_frame, text="📎", command=self._attach_file,
            font=("Segoe UI Emoji", 14), width=3, height=2,
            relief="flat", bg="#F0F0F0",
        )
        self.attach_btn.grid(row=0, column=1, sticky="ns", pady=6)

        self.send_btn = tk.Button(
            inp_frame, text="보내기\n(Enter)", command=self._send,
            font=("맑은 고딕", 11, "bold"), bg="#4A90D9", fg="white",
            width=8, height=2, relief="raised",
        )
        self.send_btn.grid(row=0, column=2, sticky="ns", padx=(0, 4), pady=6)

        # 중단(비상정지) — 작업 중일 때만 활성화
        self.stop_btn = tk.Button(
            inp_frame, text="중단", command=self._stop,
            font=("맑은 고딕", 11, "bold"), bg="#D94A4A", fg="white",
            width=6, height=2, relief="raised", state="disabled",
        )
        self.stop_btn.grid(row=0, column=3, sticky="ns", padx=(0, 8), pady=6)

        self.input_box.focus_set()

        # 환영 메시지
        self._append("info",
            "뚝딱비서에 오신 것을 환영합니다.\n"
            "한글(HWP) 문서와 엑셀 파일을 AI가 도와드립니다.\n\n"
            "사용법:\n"
            '  - 파일을 채팅창에 드래그하거나 📎 버튼으로 첨부\n'
            '  - "이 파일에서 컴퓨터공학과 섹션 읽어줘"\n'
            '  - "양식에 학과 정보 채워줘"\n'
        )

        if not self.config.get("mode"):
            self._append("info", "먼저 설정을 완료해주세요. (상단 '설정' 버튼)")

    # ── 드래그 앤 드롭 ──

    def _setup_drag_and_drop(self):
        """파일 드래그 앤 드롭 설정."""
        try:
            import windnd
            # 입력창에 드롭
            windnd.hook_dropfiles(self.input_box, func=self._on_files_dropped)
            # 채팅창에도 드롭 가능
            windnd.hook_dropfiles(self.chat, func=self._on_files_dropped)
        except ImportError:
            pass  # windnd 없으면 드래그 앤 드롭 비활성화 (파일 첨부 버튼은 동작)

    def _on_files_dropped(self, files):
        """파일이 드롭되었을 때 입력창에 경로를 삽입."""
        for f in files:
            # windnd는 bytes로 전달
            if isinstance(f, bytes):
                try:
                    path = f.decode("utf-8")
                except UnicodeDecodeError:
                    path = f.decode("cp949", errors="replace")
            else:
                path = str(f)

            # 경로를 큰따옴표로 감싸서 삽입
            self.input_box.insert("end", f' "{path}" ')

        self.input_box.focus_set()
        # 드롭 알림
        count = len(files)
        self._append("file", f"파일 {count}개 첨부됨 — 메시지와 함께 전송하세요.")

    def _attach_file(self):
        """파일 선택 다이얼로그로 파일 첨부."""
        files = filedialog.askopenfilenames(
            title="파일 첨부",
            initialdir=self.work_dir,
            filetypes=[
                ("모든 파일", "*.*"),
                ("한글 파일", "*.hwp *.hwpx"),
                ("엑셀 파일", "*.xlsx *.xls"),
                ("텍스트 파일", "*.txt *.csv"),
            ],
        )
        if files:
            for path in files:
                self.input_box.insert("end", f' "{path}" ')
            self.input_box.focus_set()
            self._append("file", f"파일 {len(files)}개 첨부됨")

    def _update_conn_status(self):
        if _check_claude_cli():
            self.conn_var.set("연결됨")
            self.conn_label.configure(foreground="green")
        else:
            self.conn_var.set("미연결 — 설정 필요")
            self.conn_label.configure(foreground="red")

    # ── 채팅 표시 ──

    def _append(self, tag, text):
        self.chat.configure(state="normal")
        prefix = {
            "user": "\n나: ", "ai": "\nAI: ", "info": "\n",
            "cost": "\n  ", "tool": "\n  ", "progress": "\n  ",
            "error": "\n❌ ", "file": "\n📎 ",
        }.get(tag, "\n")
        self.chat.insert("end", prefix, tag)
        self.chat.insert("end", text + "\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    # ── v0.0.25: verdict / verify_report 카드 렌더 ──
    #
    # Claude 응답 본문 시작에 YAML frontmatter 가 있으면 카드 형태로 변환.
    # spec 의 verdict frontmatter (max_attempts 위반 시) 와 verify_report
    # frontmatter (산출물 검증) 두 가지 처리. 그 외는 원본 그대로 출력.

    _VERDICT_CATEGORY_HEADER = {
        "external_blocker": "🔧 사용자 행동 필요",
        "system_limit": "🚫 미지원 기능",
        "unclear_intent": "❓ 명확화 필요",
    }

    def _render_ai_response(self, text: str) -> None:
        """AI 응답을 채팅창에 표시. frontmatter 검출 시 카드 분기."""
        if not text:
            return
        parsed = self._extract_frontmatter(text)
        if parsed is None:
            self._append("ai", text)
            return
        fm, rest = parsed

        if fm.get("verdict") == "stop":
            self._append("info", self._format_verdict_card(fm))
            if rest:
                self._append("ai", rest)
            return
        if fm.get("report") == "verify":
            self._append("info", self._format_verify_report_card(fm))
            if rest:
                self._append("ai", rest)
            return

        # 알 수 없는 frontmatter — 본문만 출력
        self._append("ai", rest or text)

    @staticmethod
    def _extract_frontmatter(text: str):
        """본문 시작의 YAML frontmatter 검출.

        지원 형태:
          ---\n<yaml>\n---\n<rest>
          ```yaml\n<yaml>\n```\n<rest>
        Returns: (frontmatter_dict, rest_text) 또는 None.
        """
        s = text.strip()
        if s.startswith("```yaml") or s.startswith("```YAML"):
            close = s.find("```", 7)
            if close == -1:
                return None
            yaml_block = s[7:close]
            rest = s[close + 3:].lstrip("\n").strip()
        elif s.startswith("---"):
            close = s.find("\n---", 3)
            if close == -1:
                return None
            yaml_block = s[3:close]
            rest = s[close + 4:].lstrip("\n").strip()
        else:
            return None
        try:
            fm = DdukddakApp._parse_minimal_yaml(yaml_block)
        except Exception:
            return None
        if not isinstance(fm, dict):
            return None
        return fm, rest

    @staticmethod
    def _parse_minimal_yaml(text: str) -> dict:
        """verdict / verify_report frontmatter 만 처리하는 미니 YAML 파서.

        지원: scalar (key: value), list of dicts (`- key: value`),
        multiline | block. PyYAML 의존성 회피용. 일반 YAML 미지원 — 우리
        spec 형식만 동작.
        """
        result: dict = {}
        lines = text.splitlines()
        i = 0
        n = len(lines)

        def _strip_quotes(v: str) -> str:
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                return v[1:-1]
            return v

        def _coerce(v: str):
            v = _strip_quotes(v)
            if v == "true":
                return True
            if v == "false":
                return False
            if v == "null" or v == "":
                return None
            try:
                return int(v)
            except ValueError:
                pass
            try:
                return float(v)
            except ValueError:
                pass
            return v

        while i < n:
            raw = lines[i]
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                i += 1
                continue

            # top-level key: ...
            if not line.startswith(" "):
                if ":" not in line:
                    i += 1
                    continue
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()

                # multiline | block
                if value == "|":
                    i += 1
                    block_lines: list[str] = []
                    base_indent: int | None = None
                    while i < n:
                        nxt = lines[i]
                        if not nxt.strip():
                            block_lines.append("")
                            i += 1
                            continue
                        stripped = nxt.lstrip(" ")
                        indent = len(nxt) - len(stripped)
                        if indent == 0:
                            break
                        if base_indent is None:
                            base_indent = indent
                        if indent < base_indent:
                            break
                        block_lines.append(nxt[base_indent:].rstrip())
                        i += 1
                    result[key] = "\n".join(block_lines).strip("\n")
                    continue

                # list (next non-empty line starts with `-`)
                if value == "":
                    j = i + 1
                    items: list = []
                    while j < n:
                        nxt = lines[j]
                        if not nxt.strip():
                            j += 1
                            continue
                        if not nxt.startswith(" "):
                            break
                        stripped = nxt.lstrip(" ")
                        if not stripped.startswith("- "):
                            break
                        # list item
                        item_first = stripped[2:].strip()
                        item_dict: dict = {}
                        if item_first and ":" in item_first:
                            k1, _, v1 = item_first.partition(":")
                            item_dict[k1.strip()] = _coerce(v1.strip())
                        elif item_first:
                            items.append(_coerce(item_first))
                            j += 1
                            continue
                        # 후속 들여쓰기 줄들 (같은 list item 의 추가 키)
                        item_indent = len(nxt) - len(nxt.lstrip(" "))
                        j += 1
                        while j < n:
                            sub = lines[j]
                            if not sub.strip():
                                j += 1
                                continue
                            sub_stripped = sub.lstrip(" ")
                            sub_indent = len(sub) - len(sub_stripped)
                            if sub_indent <= item_indent:
                                break
                            if sub_stripped.startswith("- "):
                                break
                            if ":" in sub_stripped:
                                k2, _, v2 = sub_stripped.partition(":")
                                item_dict[k2.strip()] = _coerce(v2.strip())
                            j += 1
                        items.append(item_dict)
                    if items:
                        result[key] = items
                        i = j
                        continue
                    # 빈 키 (다음에 list 도, scalar 도 없음) — None 으로
                    result[key] = None
                    i += 1
                    continue

                # scalar
                result[key] = _coerce(value)
                i += 1
                continue

            i += 1
        return result

    def _format_verdict_card(self, fm: dict) -> str:
        category = str(fm.get("category") or "")
        header = self._VERDICT_CATEGORY_HEADER.get(category, "⏸ 작업 멈춤")

        attempted = fm.get("attempted") or []
        step_lines: list[str] = []
        if isinstance(attempted, list):
            for idx, step in enumerate(attempted, 1):
                if not isinstance(step, dict):
                    continue
                result = str(step.get("result") or "")
                mark = "✅" if result == "ok" else "❌"
                sid = step.get("step") or f"step{idx}"
                detail = step.get("detail") or ""
                if detail:
                    step_lines.append(f"  {mark} {idx}. {sid} — {detail}")
                else:
                    step_lines.append(f"  {mark} {idx}. {sid}")

        user_action = str(fm.get("user_action") or "").strip()
        last_error = str(fm.get("last_error") or "").strip()

        lines: list[str] = []
        bar = "─" * 50
        lines.append(bar)
        lines.append("⏸ 작업 멈춤")
        lines.append("")
        lines.append(header)
        if step_lines:
            lines.append("")
            lines.extend(step_lines)
        if user_action:
            lines.append("")
            lines.append(user_action)
        if last_error and not user_action:
            lines.append("")
            lines.append(f"  (참고: {last_error})")
        lines.append(bar)
        return "\n".join(lines)

    def _format_verify_report_card(self, fm: dict) -> str:
        skill = fm.get("skill") or "?"
        verdict = fm.get("verdict") or "?"
        output_file = fm.get("output_file") or ""
        checks = fm.get("checks") or []
        check_lines: list[str] = []
        if isinstance(checks, list):
            for c in checks:
                if not isinstance(c, dict):
                    continue
                name = c.get("name") or "?"
                expected = c.get("expected", "")
                actual = c.get("actual", "")
                passed = c.get("pass") is True
                mark = "✅" if passed else "❌"
                check_lines.append(
                    f"  {mark} {name} — 기대 {expected} / 실측 {actual}"
                )

        overall = "✅" if verdict == "pass" else "❌"
        bar = "─" * 50
        lines: list[str] = [bar, f"{overall} 검증 리포트 ({skill})", ""]
        if check_lines:
            lines.extend(check_lines)
            lines.append("")
        if output_file:
            lines.append(f"  결과 파일: {output_file}")
            lines.append("")
        lines.append(bar)
        return "\n".join(lines)

    # ── 스피너 ──

    def _start_spinner(self):
        self._spinner_idx = 0
        self._tick_spinner()

    def _tick_spinner(self):
        if not self.is_processing:
            return
        frames = ["작업 중 .", "작업 중 ..", "작업 중 ...", "작업 중    "]
        self.status_var.set(frames[self._spinner_idx % len(frames)])
        self._spinner_idx += 1
        self._spinner_after_id = self.root.after(400, self._tick_spinner)

    def _stop_spinner(self):
        if self._spinner_after_id:
            self.root.after_cancel(self._spinner_after_id)
            self._spinner_after_id = None
        self.status_var.set("준비")

    # ── 양식 관리 ──

    def _refresh_templates(self, confirm: bool = False):
        if confirm:
            if not messagebox.askyesno("양식 새로고침",
                "양식 목록을 새로고침하시겠습니까?\n현재 선택한 양식이 초기화됩니다."):
                return
        choices = ["없음 (자유 형식)"]
        if os.path.isdir(TEMPLATES_DIR):
            for f in sorted(os.listdir(TEMPLATES_DIR)):
                if f.lower().endswith((".hwp", ".hwpx", ".xlsx", ".docx", ".txt")):
                    choices.append(f)
        self.template_combo["values"] = choices
        self.template_var.set(choices[0])

    def _open_templates_dir(self):
        """양식 폴더 지정 — 폴더를 선택하면 양식 폴더로 설정."""
        global TEMPLATES_DIR
        d = filedialog.askdirectory(
            title="양식 폴더 선택",
            initialdir=TEMPLATES_DIR if os.path.isdir(TEMPLATES_DIR) else self.work_dir,
        )
        if d:
            TEMPLATES_DIR = d
            self._refresh_templates()
            self._append("info", f"양식 폴더 변경: {d}")

    def _get_template_prompt(self) -> str:
        selected = self.template_var.get()
        if selected == "없음 (자유 형식)" or not selected:
            return ""
        template_path = os.path.join(TEMPLATES_DIR, selected)
        if not os.path.exists(template_path):
            return ""
        return (
            f'\n\n[양식 지정] 작업 시 다음 양식 파일을 참고하세요: "{template_path}"\n'
            f"이 양식의 구조와 서식을 그대로 따라서 결과물을 만들어주세요. "
            f"양식 파일을 먼저 읽고 구조를 파악한 뒤 작업하세요."
        )

    # ── 설정 ──

    def _show_setup(self):
        wizard = SetupWizard(self.root)
        self.root.wait_window(wizard.win)
        if wizard.result:
            self.config = wizard.result
            # 설치 직후 PATH/CLI 경로 즉시 갱신 (재시작 불필요)
            global CLAUDE_CMD
            from core.setup_helper import _refresh_path, _find_claude
            _refresh_path()
            found = _find_claude()
            if found:
                CLAUDE_CMD = found
            self._update_conn_status()
            self._append("info", "설정 완료! 이제 채팅으로 작업을 시작하세요.")

    # ── 이벤트 ──

    def _change_dir(self):
        initial = self.work_dir if os.path.isdir(self.work_dir) else os.path.expanduser("~")
        d = filedialog.askdirectory(initialdir=initial)
        if d:
            if not os.path.isdir(d):
                self._append("error",
                    f"선택한 경로가 유효한 디렉터리가 아닙니다:\n  {d}")
                return
            self.work_dir = d
            self.dir_var.set(d)
            self.history = []
            self._reset_session_cache()
            self._append("info", f"작업 폴더 변경: {d}")

    def _clear(self):
        if not messagebox.askyesno("대화 초기화",
            "대화 내용을 모두 삭제하시겠습니까?\n이전 대화는 복구할 수 없습니다."):
            return
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.history = []
        self._reset_session_cache()
        self._append("info", "대화 초기화됨")

    def _on_enter(self, event):
        if not (event.state & 1):
            self._send()
            return "break"

    def _send(self):
        if self.is_processing:
            return

        if not _check_claude_cli():
            self._append("error", "Claude가 설치되지 않았습니다. 상단 '설정' 버튼을 눌러 설치하세요.")
            return

        text = self.input_box.get("1.0", "end").strip()
        if not text:
            return

        self.input_box.delete("1.0", "end")
        self._append("user", text)

        self.is_processing = True
        self._user_aborted = False
        self.send_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._start_spinner()

        threading.Thread(target=self._call_claude, args=(text,), daemon=True).start()

    def _stop(self):
        """비상 정지 — 실행 중인 Claude CLI 서브프로세스를 강제 종료."""
        if not self.is_processing or self.current_process is None:
            return
        self._user_aborted = True
        try:
            self.current_process.terminate()
            try:
                self.current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
        except (OSError, ValueError):
            pass
        # 자식 프로세스 트리 전체 종료
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)],
                capture_output=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError, AttributeError):
            pass
        self._append("error", "작업이 중단되었습니다 (사용자 요청).")
        # _call_claude 의 finally 가 'done' 을 큐에 넣어 상태 복구

    # ── Claude Code CLI 호출 ──

    def _reset_session_cache(self) -> None:
        """대화 초기화 / 작업 폴더 변경 시 세션 캐시 파일을 비운다."""
        try:
            if os.path.exists(SESSION_CACHE_FILE):
                os.remove(SESSION_CACHE_FILE)
        except OSError:
            pass

    def _seed_session_cache_if_empty(self) -> None:
        """세션 캐시가 없으면 기본 시드 파일 생성.

        새 PC 에서 .ddukddak/current_session.md 가 비어있으면 Claude 가
        맥락 복원 시 읽을 내용이 0 → BUG-002 완화. 뚝딱비서 자체 배경을
        시드로 넣어서 Claude 가 앱 정체 / 권한 / 도구 사용법을 즉시 파악.
        """
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.exists(SESSION_CACHE_FILE):
                return
            with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write("# 뚝딱비서 대화 맥락 캐시\n\n")
                f.write(
                    "이 파일은 뚝딱비서 앱이 매 턴 끝에 자동으로 append 합니다.\n"
                    "Claude 가 시스템 프롬프트의 이력이 부족할 때 Read 로 이 파일을\n"
                    "열어 대화 맥락을 복원합니다. self-managed memory.\n\n"
                )
                f.write("## 앱 환경 기본 정보 (시드)\n\n")
                f.write(
                    "- 이 앱은 **뚝딱비서** — 엑셀·한글(HWP) 파일 AI 편집 어시스턴트.\n"
                    "- 환경은 **`--dangerously-skip-permissions`** sandbox — 권한 사전 승인됨.\n"
                    "  사용자에게 '권한이 필요합니다' / '승인해주세요' 묻지 말 것.\n"
                    "- HWP 처리는 **`core.hwp_*`** 모듈만 사용 (내부 rhwp WASM). COM 금지.\n"
                    "- 엑셀 처리는 **`core.excel_*`** 모듈만 사용 (openpyxl / xlrd). COM 금지.\n"
                    "- 표 추출은 `core.hwp_reader.list_tables`, `extract_table`, `read_tables`.\n\n"
                )
                f.write("---\n")
        except OSError:
            pass

    def _append_to_session_cache(self, user_msg: str, assistant_msg: str) -> None:
        """턴 완료 후 대화 내용을 캐시 파일에 append.

        Claude 가 시스템 프롬프트의 이력 섹션을 놓쳤을 때 스스로 Read 도구로
        이 파일을 열어 맥락을 복원할 수 있게 해준다. self-managed memory.
        """
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            is_new = not os.path.exists(SESSION_CACHE_FILE)
            if is_new:
                self._seed_session_cache_if_empty()
            with open(SESSION_CACHE_FILE, "a", encoding="utf-8") as f:
                turn_num = (len(self.history) // 2)
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n## 턴 {turn_num} — {ts}\n\n")
                f.write(f"### 사용자\n{user_msg}\n\n")
                f.write(f"### 어시스턴트\n{assistant_msg}\n\n")
                f.write("---\n")
        except OSError:
            pass

    def _ensure_system_prompt_file(self) -> str:
        """합성된 시스템 프롬프트를 사용자 홈 디렉토리에 저장하고 경로 반환.

        v0.0.25 부터: base (pentong_system_prompt.txt) + markdown harness 토대
        skill 모듈 5개를 합성한 결과를 저장. 합성은 self.system_prompt 에 이미
        담겨 있으므로 그걸 그대로 디스크에 쓴다. PyInstaller exe 내부 경로
        (_MEIPASS)는 외부 프로세스가 못 읽으므로 사용자 홈에 복사 필수.

        맥락 유지는 Claude CLI 의 `--continue` 플래그가 cwd 기반으로 처리.
        """
        stable_path = os.path.join(CONFIG_DIR, "system_prompt.txt")
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            content = self.system_prompt or ""
            if not content:
                # 안전 fallback — 합성 실패 시 base 만이라도
                with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as src:
                    content = src.read()
            with open(stable_path, "w", encoding="utf-8") as dst:
                dst.write(content)
            return stable_path
        except Exception:
            return SYSTEM_PROMPT_FILE

    # HWP preflight (win32com 기반 COM 차단 로직) 은 v0.0.17 에서 폐기됨.
    # core/hwp_*.py 가 @rhwp/core (WASM) 로 전환되어 COM 의존성 0 — 한컴 OCX
    # 미등록 PC 에서도 정상 동작. 관련 메서드 (_prompt_mentions_hwp,
    # _needs_hwp_com, _preflight_hwp_check) 와 토큰 리스트 4종 제거됨.

    def _ensure_core_modules(self) -> str:
        """번들된 core/ 를 사용자 홈에 풀어, 외부 python 서브프로세스에서
        `from core.xxx import ...` 로 import 가능하게 한다.

        Returns:
            PYTHONPATH 에 추가할 루트 경로 (core/ 의 부모). 실패 시 빈 문자열.

        PyInstaller exe 에 `_MEIPASS/core/` 가 들어있지만 exe 가 끝나면
        _MEIPASS 는 사라져 외부 python 이 접근 못하므로 영구 폴더에 복사.

        이 앱 프로세스 당 1회만 실행. `_assets_prepared` set 으로 재호출 가드.
        """
        dst_dir = os.path.join(CONFIG_DIR, "core")
        if "core" in self._assets_prepared and os.path.isdir(dst_dir):
            return CONFIG_DIR
        try:
            src_dir = _resource_path("core")
            if not os.path.isdir(src_dir):
                return ""
            os.makedirs(CONFIG_DIR, exist_ok=True)
            # 이전 복사본 제거 — 업데이트된 exe 로 교체했을 때 stale 방지
            if os.path.isdir(dst_dir):
                shutil.rmtree(dst_dir, ignore_errors=True)
            shutil.copytree(src_dir, dst_dir,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            self._assets_prepared.add("core")
            return CONFIG_DIR
        except Exception:
            # 개발 모드(frozen=False)면 현재 소스 트리의 부모를 그냥 쓴다
            if not getattr(sys, 'frozen', False):
                return os.path.dirname(os.path.abspath(__file__))
            return ""

    def _ensure_rhwp_bridge(self) -> str:
        """번들된 rhwp_bridge/ 를 사용자 홈에 풀어, Node.js 서브프로세스가
        @rhwp/core WASM 으로 HWP 처리 가능하게 한다.

        Returns:
            ~/.ddukddak/rhwp_bridge/rhwp_bridge.js 경로. 실패 시 빈 문자열.

        앱 프로세스 당 1회만 copytree. 매 _call_claude 마다 I/O 반복 방지.
        """
        dst_bridge_js = os.path.join(CONFIG_DIR, "rhwp_bridge", "rhwp_bridge.js")
        if "rhwp_bridge" in self._assets_prepared and os.path.isfile(dst_bridge_js):
            return dst_bridge_js
        try:
            src_dir = _resource_path("rhwp_bridge")
            if not os.path.isdir(src_dir):
                # 개발 모드면 소스 트리에서 직접 사용
                if not getattr(sys, 'frozen', False):
                    dev_bridge = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "rhwp_bridge", "rhwp_bridge.js",
                    )
                    return dev_bridge if os.path.isfile(dev_bridge) else ""
                return ""
            os.makedirs(CONFIG_DIR, exist_ok=True)
            dst_dir = os.path.join(CONFIG_DIR, "rhwp_bridge")
            if os.path.isdir(dst_dir):
                shutil.rmtree(dst_dir, ignore_errors=True)
            shutil.copytree(src_dir, dst_dir)
            self._assets_prepared.add("rhwp_bridge")
            return dst_bridge_js if os.path.isfile(dst_bridge_js) else ""
        except Exception:
            if not getattr(sys, 'frozen', False):
                dev_bridge = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "rhwp_bridge", "rhwp_bridge.js",
                )
                return dev_bridge if os.path.isfile(dev_bridge) else ""
            return ""

    def _find_claude_cmd(self) -> str:
        """최신 PATH 기준으로 Claude CLI 경로를 찾는다."""
        from core.setup_helper import _find_claude, _refresh_path
        _refresh_path()
        found = _find_claude()
        if found:
            return found
        return CLAUDE_CMD

    # ── Claude CLI 호출 — subprocess(-p) + stream-json 파싱 ──
    # (v0.0.14 ~ v0.0.17 의 claude-agent-sdk 대화형 세션 방식은 Control request
    # timeout 이 일부 환경에서 반복 발생해 v0.0.18 에서 롤백. 단순 `-p` 호출로
    # 복귀. 세션 맥락은 `--continue` 플래그로 CLI 가 cwd 기준으로 유지.)

    def _emit_tool_use_dict(self, tool_name: str, tool_input: dict) -> None:
        """stream-json 의 assistant.tool_use 블록을 UI progress 로 변환."""
        if not isinstance(tool_input, dict):
            tool_input = {}
        if tool_name == "Bash":
            cmd_text = str(tool_input.get("command", ""))[:200]
            self.result_queue.put(("tool", f"[실행] {cmd_text}"))
        elif tool_name == "Read":
            fname = os.path.basename(str(tool_input.get("file_path", ""))) or "?"
            self.result_queue.put(("tool", f"[읽기] {fname}"))
        elif tool_name == "Write":
            fname = os.path.basename(str(tool_input.get("file_path", ""))) or "?"
            self.result_queue.put(("tool", f"[파일 생성] {fname}"))
        elif tool_name == "Edit":
            fname = os.path.basename(str(tool_input.get("file_path", ""))) or "?"
            self.result_queue.put(("tool", f"[편집] {fname}"))
        elif tool_name == "Glob":
            pattern = str(tool_input.get("pattern", ""))
            self.result_queue.put(("tool", f"[파일 검색] {pattern}"))
        elif tool_name == "Grep":
            pattern = str(tool_input.get("pattern", ""))[:80]
            self.result_queue.put(("tool", f"[내용 검색] {pattern}"))
        else:
            self.result_queue.put(("tool", f"[{tool_name}]"))

    # hesitation 감지용 패턴 — Claude 가 첫 도구 호출 전 자발적으로 권한
    # 확인 자연어로 끝내는 케이스. 이 키워드 + 도구 호출 0 + 첫 턴이면
    # "세션 완전 리셋 후 동일 prompt 재전송" 전략으로 자동 복구.
    _HESITATION_MARKERS = (
        # 권한 묻기 (미준수 사례 1)
        "권한 승인", "권한이 필요", "권한을 허용", "권한을 승인",
        "승인해 주", "승인해주", "허용해 주", "허용해주",
        "approval", "permission", "requires approval",
        "I need permission", "please approve", "allow me to",
        # v0.0.25: 세션 미참조 (미준수 사례 2)
        "이전 대화 이력이 없", "이전 대화가 없", "맥락이 없", "맥락을 알 수 없",
        "어떤 파일을 말씀하시는지 모르", "어떤 작업을 말씀하시는지 모르",
        "처음부터 다시 알려", "다시 한 번 알려",
    )

    def _call_claude(self, prompt: str, _hesitation_retry: bool = False):
        """사용자 메시지를 Claude CLI 로 전달하고 stream-json 응답을 파싱.

        _hesitation_retry: 재귀 호출 플래그. 첫 턴 hesitation 감지 시 세션을
        리셋하고 같은 prompt 로 한 번 더 이 함수를 호출. 무한루프 방지용 True.
        """
        full_prompt = prompt
        final_result_text = ""
        tool_use_count = 0  # hesitation 판정용 — 이 턴에서 실제 도구 호출 수
        was_first_turn = len(self.history) == 0  # 재시도 후 변질되므로 미리 저장

        # work_dir 이 유효한 디렉터리인지 사전 체크 — Popen 의 cwd 인자가
        # 존재하지 않거나 파일이면 WinError 267 "디렉터리 이름이 올바르지 않습니다"
        # 로 실패. 그전에 명시적 에러로 사용자 안내.
        if not os.path.isdir(self.work_dir):
            self.result_queue.put(("error",
                f"작업 폴더가 유효한 디렉터리가 아닙니다:\n  {self.work_dir}\n\n"
                "상단 '작업 폴더 변경' 버튼으로 올바른 폴더를 다시 선택해주세요.\n"
                "(폴더가 삭제/이름 변경됐거나 네트워크 드라이브 연결 해제 가능성)"))
            self.result_queue.put(("done", None))
            return

        try:
            template_hint = self._get_template_prompt()
            full_prompt = prompt + template_hint

            # 시스템 프롬프트 / core PYTHONPATH / rhwp bridge 준비
            prompt_file = self._ensure_system_prompt_file()
            core_pythonpath = self._ensure_core_modules()
            bridge_js = self._ensure_rhwp_bridge()
            claude_cmd = self._find_claude_cmd()

            cmd = [
                claude_cmd,
                "-p", full_prompt,
                "--verbose",
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--model", "haiku",
                "--append-system-prompt-file", prompt_file,
                "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
                "--add-dir", CONFIG_DIR,
                "--dangerously-skip-permissions",
            ]
            # 첫 턴은 --continue 없이 (새 세션 시작). 이후 턴은 cwd 기반으로 이어감.
            if self.history:
                cmd.append("--continue")

            self.result_queue.put(("progress",
                f"Claude에게 전송 중... (이력 {len(self.history)//2}턴)"))

            env = os.environ.copy()
            from core.setup_helper import _refresh_path, _find_python
            _refresh_path()

            # PATH 세팅: (1) WindowsApps shim 제거 — Microsoft Store 의 Python
            # Install Manager 리다이렉트 차단, (2) 실제 python 디렉토리를 최상위
            # prepend — `python` 명령이 번들/시스템 python 에 바로 매핑.
            raw_path = os.environ.get("PATH", "")
            path_parts: list[str] = []
            for p in raw_path.split(os.pathsep):
                p_norm = p.rstrip("\\/").lower()
                if p_norm.endswith("microsoft\\windowsapps") or p_norm.endswith("microsoft/windowsapps"):
                    continue
                if p.strip():
                    path_parts.append(p)
            python_exe = _find_python()
            if python_exe:
                python_dir = os.path.dirname(python_exe)
                path_parts = [p for p in path_parts if p.rstrip("\\/").lower() != python_dir.rstrip("\\/").lower()]
                path_parts.insert(0, python_dir)
            env["PATH"] = os.pathsep.join(path_parts)

            env["DDUKDDAK_SESSION_CACHE"] = SESSION_CACHE_FILE
            if bridge_js:
                env["DDUKDDAK_BRIDGE_JS"] = bridge_js
            if core_pythonpath:
                existing = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = (
                    core_pythonpath + os.pathsep + existing
                    if existing else core_pythonpath
                )

            # v0.0.25: Google Drive 가 zip 다운로드 시 한글 폴더명을 NFD (자모
            # 분리) 로 저장하면 claude CLI (claude.cmd → node) 가 NFD cwd 를
            # 처리 못 해 silent fail (rc=0, stdout/stderr 모두 비어있음).
            # 실측: cmd /c cd 는 NFD cwd 잘 받지만 claude CLI 는 못 받음.
            # 호스트 단에서 우회 불가 (\\?\ prefix 도 cmd 가 거부, GetShortPath
            # NameW 도 NFD path 는 인식 못 함). 사용자가 GUI 로 폴더 rename
            # 해서 NFC 로 정규화하는 게 유일한 해결.
            #
            # _resolve_actual_path 는 GUI 의 NFC↔실제 NFD 표기 매칭만 수행 —
            # 일반 한글 폴더 (NFC) 는 변경 없음, NFD 만 실제 entry 표기로 정정.
            cwd_for_popen = _resolve_actual_path(self.work_dir)
            # NFD component 감지 시 사용자에게 명확한 우회 안내 후 중단.
            _has_nfd = any(
                part and part != unicodedata.normalize('NFC', part)
                for part in cwd_for_popen.replace('/', os.sep).split(os.sep)
            )
            if _has_nfd:
                self.result_queue.put(("error",
                    "작업 폴더 이름에 NFD (한글 자모 분리) 표기가 포함되어 있어\n"
                    "claude CLI 가 silent fail 합니다 (알려진 버그).\n"
                    "원인: Google Drive 가 zip 다운로드 시 macOS 스타일 NFD 로 저장.\n\n"
                    "해결 (5초): 탐색기에서 해당 폴더 우클릭 →\n"
                    "  '이름 바꾸기' → 같은 이름 그대로 다시 입력 후 Enter.\n"
                    "  (Windows GUI rename 이 NFC 로 정규화해 저장합니다.)\n\n"
                    "그 후 작업 폴더를 다시 선택하면 정상 동작합니다."))
                self.result_queue.put(("done", None))
                return
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd_for_popen,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=_CREATE_NO_WINDOW,
            )
            self.current_process = process

            start_time = time.time()
            got_result = False
            raw_stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            def _read_stderr():
                for line in process.stderr:
                    stderr_lines.append(line)
            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                raw_stdout_lines.append(line[:500])

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "result":
                    got_result = True
                    result_text = msg.get("result", "")
                    cost = msg.get("total_cost_usd", 0)
                    turns = msg.get("num_turns", 0)
                    duration = msg.get("duration_ms", 0)
                    if result_text:
                        final_result_text = result_text
                    # v0.0.25: hesitation 의심 응답은 사용자 chat 에 박지 않고
                    # 재시도 분기로 보냄. Q2(a) "재시도 사용자에게 안 보이게".
                    is_hesitation_candidate = (
                        was_first_turn
                        and not _hesitation_retry
                        and tool_use_count == 0
                        and result_text
                        and any(m.lower() in result_text.lower()
                                for m in self._HESITATION_MARKERS)
                    )
                    if not is_hesitation_candidate:
                        self.result_queue.put(("ai", result_text))
                        self.result_queue.put(("cost",
                            f"[{turns}턴 | {duration/1000:.1f}초 | ${cost:.4f}]"))
                elif msg_type == "assistant":
                    content = msg.get("message", {}).get("content", [])
                    for block in content:
                        btype = block.get("type", "")
                        if btype == "tool_use":
                            tool_use_count += 1
                            self._emit_tool_use_dict(
                                block.get("name", "?"),
                                block.get("input", {}) or {},
                            )
                        elif btype == "text":
                            text_chunk = (block.get("text") or "").strip()
                            if text_chunk:
                                elapsed = int(time.time() - start_time)
                                self.result_queue.put(("progress",
                                    f"({elapsed}초) {text_chunk[:200]}"))
                elif msg_type == "stream_event":
                    event = msg.get("event", {}) or {}
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {}) or {}
                        if delta.get("type") == "text_delta":
                            piece = (delta.get("text") or "").strip()
                            if piece and len(piece) >= 3:
                                elapsed = int(time.time() - start_time)
                                self.result_queue.put(("progress",
                                    f"({elapsed}초) …{piece[:150]}"))

            process.wait()
            stderr_thread.join(timeout=3)
            full_stderr = "".join(stderr_lines).strip()

            if not got_result:
                # stream-json 이 안 왔으면 plain-text fallback
                plain_text = ""
                for raw in raw_stdout_lines:
                    try:
                        json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        if raw.strip():
                            plain_text += raw.strip() + "\n"
                plain_text = plain_text.strip()

                if plain_text and process.returncode == 0:
                    self.result_queue.put(("ai", plain_text))
                    final_result_text = plain_text
                elif process.returncode != 0 and full_stderr:
                    err = full_stderr[:500]
                    if any(k in err.lower() for k in ("auth", "login", "sign")):
                        self.result_queue.put(("error",
                            "Claude 로그인이 필요합니다.\n설정에서 '로그인하기'를 진행하세요."))
                    elif any(k in err.lower() for k in ("not found", "enoent")):
                        self.result_queue.put(("error",
                            f"Claude CLI 실행 오류:\n{err}\n\n"
                            "설정에서 '자동 설치'를 다시 시도하세요."))
                    else:
                        self.result_queue.put(("error", f"Claude 오류:\n{err}"))
                else:
                    # v0.0.25: silent fail 진단 강화. raw stdout/stderr 첫 부분
                    # 을 디스크에 보존해 다음 진단에 활용. UI 에는 짧게만.
                    try:
                        log_dir = os.path.join(CONFIG_DIR, "logs")
                        os.makedirs(log_dir, exist_ok=True)
                        log_path = os.path.join(log_dir, "last_silent_fail.log")
                        with open(log_path, "w", encoding="utf-8") as fh:
                            fh.write(f"[timestamp] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                            fh.write(f"[returncode] {process.returncode}\n")
                            fh.write(f"[work_dir (raw from GUI)] {self.work_dir!r}\n")
                            fh.write(f"[work_dir isdir] {os.path.isdir(self.work_dir)}\n")
                            fh.write(f"[step1 _resolved (NFC↔NFD)] {_resolved!r}\n")
                            fh.write(f"[step1 isdir] {os.path.isdir(_resolved)}\n")
                            fh.write(f"[step2 cwd_for_popen (short)] {cwd_for_popen!r}\n")
                            fh.write(f"[step2 isdir] {os.path.isdir(cwd_for_popen)}\n")
                            fh.write(f"[step1 != work_dir] {self.work_dir != _resolved}\n")
                            fh.write(f"[step2 != step1] {_resolved != cwd_for_popen}\n")
                            fh.write(f"[claude_cmd] {claude_cmd!r}\n")
                            fh.write(f"[claude_cmd exists] {os.path.isfile(claude_cmd)}\n")
                            fh.write(f"[prompt_file] {prompt_file!r}\n")
                            fh.write(f"[prompt_file exists] {os.path.isfile(prompt_file)}\n")
                            fh.write(f"[full_prompt length] {len(full_prompt)} chars\n")
                            fh.write(f"[env PATH first 500] {env.get('PATH', '')[:500]}\n\n")
                            fh.write(f"[cmd] {' '.join(repr(c) for c in cmd)}\n\n")
                            fh.write("=== stderr (first 2000 chars) ===\n")
                            fh.write((full_stderr or "<empty>")[:2000])
                            fh.write("\n\n=== stdout raw lines (first 30) ===\n")
                            for ln in raw_stdout_lines[:30]:
                                fh.write(ln + "\n")
                        log_hint = f"\n진단 로그: {log_path}"
                    except Exception:
                        log_hint = ""
                    self.result_queue.put(("error",
                        f"응답 파싱 실패. 종료코드: {process.returncode}\n"
                        f"stderr 길이: {len(full_stderr or '')}, stdout 라인: {len(raw_stdout_lines)}"
                        f"{log_hint}\n"
                        "설정에서 로그인 상태를 확인하거나 위 로그 파일을 보고해 주세요."))

        except FileNotFoundError as e:
            if not self._user_aborted:
                self.result_queue.put(("error",
                    f"Claude를 찾을 수 없습니다: {e}\n"
                    "설정에서 설치를 진행하세요."))
        except Exception as e:
            if not self._user_aborted:
                # traceback 마지막 몇 줄을 에러에 포함 — 사용자/개발자가 어느
                # 라인에서 났는지 즉시 판별 가능 (BUG-007 대응).
                import traceback as _tb
                tb_lines = _tb.format_exc().splitlines()
                # 마지막 File .../... + 직전 traceback 단계 5줄 정도만
                tb_tail = "\n".join(tb_lines[-6:]) if tb_lines else ""
                self.result_queue.put(("error",
                    f"오류: {type(e).__name__}: {e}\n\n"
                    f"[진단용 traceback]\n{tb_tail}"))

        # ─── hesitation 자동 재시도 ───
        # 조건: (첫 턴) + (도구 호출 0 개) + (응답에 권한 확인 자연어 포함)
        # + (이미 재시도가 아님). 조건 만족 시 세션을 리셋하고 동일 prompt 로
        # 한 번 더 시도. "대화 초기화 + 재입력" 을 자동화한 것 — 사용자 실증
        # 성공 패턴. 맥락을 완전히 지워서 Claude 의 "이전 hesitation 응답" 이
        # 프롬프트에 안 남게 → 새 주사위.
        if (was_first_turn
                and not _hesitation_retry
                and not self._user_aborted
                and tool_use_count == 0
                and final_result_text
                and any(m.lower() in final_result_text.lower() for m in self._HESITATION_MARKERS)):
            # v0.0.25: Q2(a) — 재시도는 사용자에게 안 보이게. 기존 info 안내
            # 메시지 (chat 에 노출됨) 제거. UI 는 "처리 중..." 스피너만 표시.
            # 세션 완전 리셋 — 사용자가 "대화 초기화" 버튼 누른 것과 동일
            self.history = []
            self._reset_session_cache()
            self._seed_session_cache_if_empty()
            # 재귀 1회 호출. 재시도 경로가 history/session_cache/done 모두
            # 처리하므로 여기선 cleanup 건너뛰고 return.
            self._call_claude(prompt, _hesitation_retry=True)
            return

        # cleanup (정상 경로 + 에러 경로 공통)
        if final_result_text and not self._user_aborted:
            self.history.append({"role": "user", "content": full_prompt})
            self.history.append({"role": "assistant", "content": final_result_text})
            self._append_to_session_cache(full_prompt, final_result_text)
        self.current_process = None
        self.result_queue.put(("done", None))

    # ── Queue 폴링 ──

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.result_queue.get_nowait()
                if msg_type == "done":
                    self.is_processing = False
                    self.send_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self._stop_spinner()
                elif msg_type == "ai":
                    # v0.0.25: AI 응답에 verdict / verify_report frontmatter
                    # 가 있으면 카드로 분기 렌더.
                    self._render_ai_response(data)
                else:
                    self._append(msg_type, data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _prepare_bundled_assets(self) -> None:
        """앱 시작 시 번들된 core/, rhwp_bridge/ 를 사용자 홈에 풀어둠.

        _call_claude 첫 호출에서 기다리지 않도록 백그라운드 스레드에서 미리.
        실패 시 UI 에 info/error 로 명시 — BUG-004 대응 (조용한 실패 방지).
        """
        issues: list[str] = []
        try:
            core_dir = self._ensure_core_modules()
            # 새 PC 에서 실패 감지 — frozen exe 인데 빈 문자열이면 번들 해제 실패
            if getattr(sys, 'frozen', False) and not core_dir:
                issues.append("core 모듈 해제 실패")
            elif not os.path.isdir(os.path.join(CONFIG_DIR, "core")):
                if getattr(sys, 'frozen', False):
                    issues.append(f"core 디렉토리 누락: {os.path.join(CONFIG_DIR, 'core')}")
        except Exception as e:
            issues.append(f"core 모듈 해제 오류: {type(e).__name__}: {e}")
        try:
            bridge_js = self._ensure_rhwp_bridge()
            if getattr(sys, 'frozen', False) and (not bridge_js or not os.path.isfile(bridge_js)):
                issues.append(f"rhwp_bridge.js 누락: {bridge_js or '(경로 없음)'}")
        except Exception as e:
            issues.append(f"rhwp_bridge 해제 오류: {type(e).__name__}: {e}")
        try:
            self._seed_session_cache_if_empty()
        except Exception:
            pass

        if issues:
            msg = (
                "⚠️ 뚝딱비서 초기화 경고\n"
                + "\n".join(f"  - {i}" for i in issues)
                + "\n\nHWP 관련 작업이 실패할 수 있습니다. 설정 창에서 '자동 설치'를 "
                  "다시 실행하거나 exe 재설치를 권장합니다."
            )
            self.result_queue.put(("error", msg))

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # 번들 assets 자동 풀기 (새 PC 에서도 첫 메시지 전에 준비 완료).
        threading.Thread(
            target=self._prepare_bundled_assets,
            daemon=True,
            name="BundleSetup",
        ).start()
        self.root.mainloop()

    def _on_close(self):
        """윈도우 닫기."""
        try:
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    app = DdukddakApp()
    app.run()
