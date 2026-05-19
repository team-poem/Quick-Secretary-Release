"""뚝딱비서 사전 요구사항 자동 설치 도우미.

Git, Node.js, Claude Code CLI 자동 감지 및 설치를 담당한다.

핵심 이슈:
  - MSI/EXE 설치 시 관리자 권한(UAC) 팝업이 떠야 함 → CREATE_NO_WINDOW 사용 금지
  - 설치 후 현재 프로세스의 PATH가 자동 갱신 안 됨 → 수동 PATH 추가 필요
  - npm 경로를 PATH가 아닌 절대경로로 호출해야 확실함
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import tempfile
from pathlib import Path
from typing import Callable

# Python 다운로드 URL (Windows x64, 3.12 LTS — 안정성 우선)
PYTHON_EXE_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
PYTHON_EXE_FILENAME = "python-3.12.10-amd64.exe"

# Python 기본 설치 경로들
PYTHON_DEFAULT_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312"),
    os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Python312"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python313"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python314"),
]

# 뚝딱비서가 필요한 pip 패키지
# xlrd: 구버전 .xls 읽기용 (전체지원자.xls 같은 파일). openpyxl 은 .xlsx 만 됨.
REQUIRED_PIP_PACKAGES = ["pywin32", "openpyxl", "xlrd"]

# Git 다운로드 URL (Windows x64)
GIT_EXE_URL = "https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/Git-2.49.0-64-bit.exe"
GIT_EXE_FILENAME = "Git-2.49.0-64-bit.exe"

# Git 기본 설치 경로
GIT_DEFAULT_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Git", "cmd")

# Node.js LTS 다운로드 URL (Windows x64 msi)
NODE_MSI_URL = "https://nodejs.org/dist/v22.16.0/node-v22.16.0-x64.msi"
NODE_MSI_FILENAME = "node-v22.16.0-x64.msi"

# Node.js 기본 설치 경로
NODE_DEFAULT_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "nodejs")

# npm 전역 설치 경로 (Windows)
NPM_GLOBAL_DIR = os.path.join(os.environ.get("APPDATA", ""), "npm")

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _refresh_path():
    """설치 후 현재 프로세스의 PATH에 Python/Git/Node.js/npm 경로를 추가한다."""
    paths_to_add = [GIT_DEFAULT_DIR, NODE_DEFAULT_DIR, NPM_GLOBAL_DIR]
    # Python 경로 추가 (Scripts 포함 — pip용)
    for pd in PYTHON_DEFAULT_DIRS:
        paths_to_add.append(pd)
        paths_to_add.append(os.path.join(pd, "Scripts"))

    current_path = os.environ.get("PATH", "")
    for p in paths_to_add:
        if os.path.isdir(p) and p not in current_path:
            os.environ["PATH"] = p + os.pathsep + current_path
            current_path = os.environ["PATH"]


def _find_npm() -> str | None:
    """npm.cmd의 절대 경로를 찾는다."""
    candidates = [
        os.path.join(NODE_DEFAULT_DIR, "npm.cmd"),
        os.path.join(NODE_DEFAULT_DIR, "npm"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "nodejs", "npm.cmd"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    # PATH에서 찾기
    try:
        result = subprocess.run(
            ["where", "npm.cmd"] if sys.platform == "win32" else ["which", "npm"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _find_claude() -> str | None:
    """claude.cmd의 절대 경로를 찾는다."""
    candidates = [
        os.path.join(NPM_GLOBAL_DIR, "claude.cmd"),
        os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    # PATH에서 찾기
    try:
        result = subprocess.run(
            ["where", "claude.cmd"] if sys.platform == "win32" else ["which", "claude"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _find_python() -> str | None:
    """시스템 Python 실행 파일 경로를 찾는다."""
    # 절대경로로 확인
    for pd in PYTHON_DEFAULT_DIRS:
        exe = os.path.join(pd, "python.exe")
        if os.path.exists(exe):
            return exe
    # PATH에서 확인
    try:
        result = subprocess.run(
            ["where", "python.exe"] if sys.platform == "win32" else ["which", "python3"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            # 앱스토어 python 제외 (WindowsApps)
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and "WindowsApps" not in line:
                    return line
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def check_python() -> dict:
    """Python 설치 여부 확인."""
    _refresh_path()

    python_exe = _find_python()
    if python_exe:
        try:
            result = subprocess.run(
                [python_exe, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                return {"installed": True, "version": version, "path": python_exe}
        except (subprocess.TimeoutExpired, OSError):
            pass

    return {"installed": False, "version": None, "path": None}


# pip 패키지명 → import 확인용 모듈명 매핑
_PIP_IMPORT_MAP = {
    "pywin32": "win32com.client",
    "openpyxl": "openpyxl",
    "xlrd": "xlrd",
}


def check_pip_packages(python_exe: str | None = None) -> dict:
    """필수 pip 패키지 설치 여부 확인."""
    if not python_exe:
        info = check_python()
        if not info["installed"]:
            return {"all_installed": False, "missing": REQUIRED_PIP_PACKAGES}
        python_exe = info["path"]

    missing = []
    for pkg in REQUIRED_PIP_PACKAGES:
        import_name = _PIP_IMPORT_MAP.get(pkg, pkg)
        try:
            result = subprocess.run(
                [python_exe, "-c", f"import {import_name}"],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                missing.append(pkg)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            missing.append(pkg)

    return {"all_installed": len(missing) == 0, "missing": missing}


def check_git() -> dict:
    """Git 설치 여부 확인."""
    _refresh_path()

    # 절대경로로 먼저 확인
    git_exe = os.path.join(GIT_DEFAULT_DIR, "git.exe")
    if os.path.exists(git_exe):
        try:
            result = subprocess.run(
                [git_exe, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"installed": True, "version": result.stdout.strip(), "path": git_exe}
        except (subprocess.TimeoutExpired, OSError):
            pass

    # PATH에서 확인
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return {"installed": True, "version": result.stdout.strip(), "path": "git"}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"installed": False, "version": None, "path": None}


def check_nodejs() -> dict:
    """Node.js 설치 여부 확인."""
    _refresh_path()

    # 절대경로로 먼저 확인
    node_exe = os.path.join(NODE_DEFAULT_DIR, "node.exe")
    if os.path.exists(node_exe):
        try:
            result = subprocess.run(
                [node_exe, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"installed": True, "version": result.stdout.strip(), "path": node_exe}
        except (subprocess.TimeoutExpired, OSError):
            pass

    # PATH에서 확인
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return {"installed": True, "version": result.stdout.strip(), "path": "node"}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"installed": False, "version": None, "path": None}


def check_claude_cli() -> dict:
    """Claude Code CLI 설치 여부 확인."""
    _refresh_path()

    # 절대경로로 먼저 확인
    claude_cmd = _find_claude()
    if claude_cmd:
        try:
            result = subprocess.run(
                [claude_cmd, "--version"],
                capture_output=True, text=True, timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"installed": True, "version": result.stdout.strip(), "path": claude_cmd}
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    # PATH에서 확인
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return {"installed": True, "version": result.stdout.strip(), "path": "claude"}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"installed": False, "version": None, "path": None}


def check_hwp() -> dict:
    """한컴 한글 설치 여부 확인."""
    try:
        import winreg
        for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for sub in ["SOFTWARE\\HNC\\HWP", "SOFTWARE\\WOW6432Node\\HNC\\Hwp"]:
                try:
                    key = winreg.OpenKey(root_key, sub)
                    path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    return {"installed": True, "path": path}
                except (FileNotFoundError, OSError):
                    continue
    except ImportError:
        pass

    try:
        import win32com.client
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        hwp.Quit()
        return {"installed": True, "path": "(COM 확인)"}
    except Exception:
        pass

    return {"installed": False, "path": None}


def check_all() -> dict:
    """모든 요구사항 상태를 한 번에 확인."""
    nodejs = check_nodejs()
    claude_cli = check_claude_cli()
    hwp = check_hwp()
    return {
        "nodejs": nodejs,
        "claude_cli": claude_cli,
        "hwp": hwp,
        "all_ready": nodejs["installed"] and claude_cli["installed"],
    }


def download_python(
    progress_cb: Callable[[str], None] | None = None,
) -> Path:
    """Python 설치 파일을 다운로드한다."""
    download_dir = Path(tempfile.gettempdir()) / "ddukddak_setup"
    download_dir.mkdir(parents=True, exist_ok=True)
    exe_path = download_dir / PYTHON_EXE_FILENAME

    if exe_path.exists() and exe_path.stat().st_size > 20_000_000:
        if progress_cb:
            progress_cb("Python 설치 파일 이미 다운로드됨")
        return exe_path

    if progress_cb:
        progress_cb("Python 다운로드 중... (약 27MB)")

    def _reporthook(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            downloaded = block_num * block_size
            pct = min(100, int(downloaded / total_size * 100))
            progress_cb(f"Python 다운로드 중... {pct}%")

    urllib.request.urlretrieve(PYTHON_EXE_URL, str(exe_path), _reporthook)

    if progress_cb:
        progress_cb("Python 다운로드 완료")
    return exe_path


def install_python(
    exe_path: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """Python을 자동 설치한다. PATH에 자동 추가."""
    if progress_cb:
        progress_cb("Python 설치 중... (관리자 권한 팝업이 뜰 수 있습니다)")

    try:
        # /passive: 진행 바만 표시, PrependPath=1: PATH에 추가
        result = subprocess.run(
            [str(exe_path), "/passive", "InstallAllUsers=0",
             "PrependPath=1", "Include_pip=1", "Include_launcher=1"],
            timeout=300,
        )

        if result.returncode == 0:
            _refresh_path()
            time.sleep(3)

            py_check = check_python()
            if py_check["installed"]:
                if progress_cb:
                    progress_cb(f"Python 설치 완료! ({py_check['version']})")
                return True
            else:
                # PATH 강제 추가
                for pd in PYTHON_DEFAULT_DIRS:
                    if os.path.exists(os.path.join(pd, "python.exe")):
                        os.environ["PATH"] = pd + os.pathsep + os.environ.get("PATH", "")
                        break
                time.sleep(1)
                py_check = check_python()
                if py_check["installed"]:
                    if progress_cb:
                        progress_cb(f"Python 설치 완료! ({py_check['version']})")
                    return True
                if progress_cb:
                    progress_cb("Python 설치는 됐지만 PATH 인식 실패. 앱을 재시작해주세요.")
                return True
        else:
            if progress_cb:
                progress_cb(f"Python 설치 실패 (코드: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        if progress_cb:
            progress_cb("Python 설치 시간 초과 (5분)")
        return False
    except OSError as e:
        if progress_cb:
            progress_cb(f"Python 설치 오류: {e}")
        return False


def install_pip_packages(
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """필수 pip 패키지를 설치한다."""
    py_info = check_python()
    if not py_info["installed"]:
        if progress_cb:
            progress_cb("Python이 설치되지 않아 패키지 설치 불가")
        return False

    python_exe = py_info["path"]
    pkg_check = check_pip_packages(python_exe)
    missing = pkg_check["missing"]

    if not missing:
        if progress_cb:
            progress_cb("필수 패키지 모두 설치됨")
        return True

    if progress_cb:
        progress_cb(f"패키지 설치 중: {', '.join(missing)}")

    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "install"] + missing + ["--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            if progress_cb:
                progress_cb("패키지 설치 완료!")
            return True
        else:
            if progress_cb:
                progress_cb(f"패키지 설치 실패: {result.stderr[:200]}")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        if progress_cb:
            progress_cb(f"패키지 설치 오류: {e}")
        return False


def download_git(
    progress_cb: Callable[[str], None] | None = None,
) -> Path:
    """Git 설치 파일을 다운로드한다."""
    download_dir = Path(tempfile.gettempdir()) / "ddukddak_setup"
    download_dir.mkdir(parents=True, exist_ok=True)
    exe_path = download_dir / GIT_EXE_FILENAME

    if exe_path.exists() and exe_path.stat().st_size > 30_000_000:
        if progress_cb:
            progress_cb("Git 설치 파일 이미 다운로드됨")
        return exe_path

    if progress_cb:
        progress_cb("Git 다운로드 중... (약 65MB)")

    def _reporthook(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            downloaded = block_num * block_size
            pct = min(100, int(downloaded / total_size * 100))
            progress_cb(f"Git 다운로드 중... {pct}%")

    urllib.request.urlretrieve(GIT_EXE_URL, str(exe_path), _reporthook)

    if progress_cb:
        progress_cb("Git 다운로드 완료")

    return exe_path


def install_git(
    exe_path: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """Git을 자동(Silent) 설치한다."""
    if progress_cb:
        progress_cb("Git 설치 중... (관리자 권한 팝업이 뜰 수 있습니다)")

    try:
        # /VERYSILENT: UI 없이 설치, /NORESTART: 재시작 안 함
        result = subprocess.run(
            [str(exe_path), "/VERYSILENT", "/NORESTART", "/NOCANCEL",
             "/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            timeout=300,
        )

        if result.returncode == 0:
            _refresh_path()
            time.sleep(2)

            git_check = check_git()
            if git_check["installed"]:
                if progress_cb:
                    progress_cb(f"Git 설치 완료! ({git_check['version']})")
                return True
            else:
                os.environ["PATH"] = GIT_DEFAULT_DIR + os.pathsep + os.environ.get("PATH", "")
                time.sleep(2)
                git_check = check_git()
                if git_check["installed"]:
                    if progress_cb:
                        progress_cb(f"Git 설치 완료! ({git_check['version']})")
                    return True
                if progress_cb:
                    progress_cb("Git 설치는 됐지만 PATH 인식 실패. 앱을 재시작해주세요.")
                return True
        else:
            if progress_cb:
                progress_cb(f"Git 설치 실패 (코드: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        if progress_cb:
            progress_cb("Git 설치 시간 초과 (5분)")
        return False
    except OSError as e:
        if progress_cb:
            progress_cb(f"Git 설치 오류: {e}")
        return False


def download_nodejs(
    progress_cb: Callable[[str], None] | None = None,
) -> Path:
    """Node.js MSI 설치 파일을 다운로드한다."""
    download_dir = Path(tempfile.gettempdir()) / "ddukddak_setup"
    download_dir.mkdir(parents=True, exist_ok=True)
    msi_path = download_dir / NODE_MSI_FILENAME

    # 이미 다운로드 되어있으면 스킵
    if msi_path.exists() and msi_path.stat().st_size > 10_000_000:
        if progress_cb:
            progress_cb("Node.js 설치 파일 이미 다운로드됨")
        return msi_path

    if progress_cb:
        progress_cb("Node.js 다운로드 중... (약 30MB)")

    def _reporthook(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            downloaded = block_num * block_size
            pct = min(100, int(downloaded / total_size * 100))
            progress_cb(f"Node.js 다운로드 중... {pct}%")

    urllib.request.urlretrieve(NODE_MSI_URL, str(msi_path), _reporthook)

    if progress_cb:
        progress_cb("Node.js 다운로드 완료")

    return msi_path


def install_nodejs(
    msi_path: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """Node.js MSI를 설치한다. UAC 팝업이 뜬다."""
    if progress_cb:
        progress_cb("Node.js 설치 중... (관리자 권한 팝업이 뜰 수 있습니다)")

    try:
        # 중요: CREATE_NO_WINDOW를 쓰지 않아야 UAC 팝업이 정상 표시됨
        result = subprocess.run(
            ["msiexec", "/i", str(msi_path), "/passive", "/norestart"],
            timeout=300,
        )

        if result.returncode == 0:
            # PATH 갱신: 설치 직후 현재 프로세스에 반영
            _refresh_path()
            time.sleep(2)  # 파일시스템 안정화 대기

            # 설치 확인
            node_check = check_nodejs()
            if node_check["installed"]:
                if progress_cb:
                    progress_cb(f"Node.js 설치 완료! ({node_check['version']})")
                return True
            else:
                if progress_cb:
                    progress_cb("Node.js MSI 완료했으나 node 실행 확인 실���. 재시도...")
                # PATH를 한 번 더 강제 추가
                os.environ["PATH"] = NODE_DEFAULT_DIR + os.pathsep + os.environ.get("PATH", "")
                time.sleep(2)
                node_check = check_nodejs()
                if node_check["installed"]:
                    if progress_cb:
                        progress_cb(f"Node.js 설치 완료! ({node_check['version']})")
                    return True
                if progress_cb:
                    progress_cb("Node.js 설치는 됐지만 PATH 인식 실패. 앱을 재시작해주세요.")
                return True  # MSI 자체는 ���공했으므로 True 반환
        else:
            if progress_cb:
                progress_cb(f"Node.js 설치 실패 (코드: {result.returncode}). 관리자 권한을 확인하세요.")
            return False

    except subprocess.TimeoutExpired:
        if progress_cb:
            progress_cb("Node.js 설치 시간 초과 (5분)")
        return False
    except OSError as e:
        if progress_cb:
            progress_cb(f"Node.js 설치 오류: {e}")
        return False


def install_claude_cli(
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """npm으로 Claude Code CLI를 전역 설치한다."""
    if progress_cb:
        progress_cb("Claude Code CLI 설치 중... (1~2분 소요)")

    # PATH 갱신
    _refresh_path()

    # npm 절대경로 찾기
    npm_cmd = _find_npm()
    if not npm_cmd:
        if progress_cb:
            progress_cb("npm을 찾을 수 없습니다. Node.js가 제대로 설치되었는지 확인하세요.")
        return False

    if progress_cb:
        progress_cb(f"npm 찾음: {npm_cmd}\nClaude Code CLI 설치 중...")

    try:
        result = subprocess.run(
            [npm_cmd, "install", "-g", "@anthropic-ai/claude-code"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300,
            # npm은 콘솔 없이 실행 가능
            creationflags=_CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            # PATH 갱신
            _refresh_path()
            time.sleep(2)

            cli_check = check_claude_cli()
            if cli_check["installed"]:
                if progress_cb:
                    progress_cb(f"Claude Code CLI 설치 완료! ({cli_check['version']})")
                return True
            else:
                # npm global bin이 PATH에 없을 수 있음
                os.environ["PATH"] = NPM_GLOBAL_DIR + os.pathsep + os.environ.get("PATH", "")
                time.sleep(1)
                cli_check = check_claude_cli()
                if cli_check["installed"]:
                    if progress_cb:
                        progress_cb(f"Claude Code CLI 설치 완료! ({cli_check['version']})")
                    return True
                if progress_cb:
                    progress_cb("CLI 설치는 됐으나 경로 인식 실패. 앱을 재시작해주세요.")
                return True  # npm install 자체는 성공
        else:
            stderr = result.stderr.strip()[:300] if result.stderr else "알 수 없는 오류"
            if progress_cb:
                progress_cb(f"CLI 설치 실패: {stderr}")
            return False

    except FileNotFoundError:
        if progress_cb:
            progress_cb(f"npm 실행 실패: {npm_cmd} 을 찾을 수 없습니다.")
        return False
    except subprocess.TimeoutExpired:
        if progress_cb:
            progress_cb("CLI 설치 시간 초과 (5분)")
        return False
    except OSError as e:
        if progress_cb:
            progress_cb(f"CLI 설치 오류: {e}")
        return False


def check_powershell_execution_policy() -> dict:
    """현재 사용자 PowerShell 실행 정책을 확인한다."""
    if sys.platform != "win32":
        return {"ok": True, "policy": "N/A"}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-ExecutionPolicy -Scope CurrentUser"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        policy = (result.stdout or "").strip()
        # Restricted, AllSigned 는 claude.ps1 차단됨
        ok = policy.lower() in ("remotesigned", "unrestricted", "bypass")
        return {"ok": ok, "policy": policy or "Undefined"}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "policy": f"확인 실패: {e}"}


def set_powershell_execution_policy(
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """PowerShell 실행 정책을 RemoteSigned(CurrentUser)로 설정한다.

    claude.ps1 같은 npm 글로벌 PS 스크립트가 차단되는 문제를 해결한다.
    CurrentUser 범위라서 관리자 권한이 필요 없다.
    """
    if sys.platform != "win32":
        return True

    info = check_powershell_execution_policy()
    if info["ok"]:
        if progress_cb:
            progress_cb(f"PowerShell 정책 OK ({info['policy']})")
        return True

    if progress_cb:
        progress_cb(f"PowerShell 정책 변경 중... (현재: {info['policy']} → RemoteSigned)")

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        # Set-ExecutionPolicy는 상위 스코프(Group Policy/Process)가 우선될 때
        # stderr에 경고를 내보내며 returncode != 0이 될 수 있다. 실제 적용 여부는
        # returncode가 아니라 검증 결과로 판단해야 한다.
        verify = check_powershell_execution_policy()
        if verify["ok"]:
            if progress_cb:
                progress_cb(f"PowerShell 정책 설정 완료 ({verify['policy']})")
            return True
        err = (result.stderr or "").strip()[:200]
        if progress_cb:
            progress_cb(f"PowerShell 정책 설정 실패 (현재: {verify['policy']}): {err}")
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        if progress_cb:
            progress_cb(f"PowerShell 정책 설정 오류: {e}")
        return False


def install_all(
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Python + Git + Node.js + Claude CLI + pip 패키지를 순차적으로 설치한다."""
    result = {"python_ok": False, "pip_ok": False, "git_ok": False,
              "nodejs_ok": False, "claude_cli_ok": False,
              "ps_policy_ok": False, "success": False}

    # 0. PowerShell 실행 정책 먼저 풀어둔다 (claude.ps1 차단 방지)
    result["ps_policy_ok"] = set_powershell_execution_policy(progress_cb)

    # 1. Python 확인/설치
    py_info = check_python()
    if py_info["installed"]:
        if progress_cb:
            progress_cb(f"Python 이미 설치됨 ({py_info['version']})")
        result["python_ok"] = True
    else:
        if progress_cb:
            progress_cb("Python 다운로드 시작...")
        try:
            exe_path = download_python(progress_cb)
            result["python_ok"] = install_python(exe_path, progress_cb)
        except Exception as e:
            if progress_cb:
                progress_cb(f"Python 설치 실패: {e}")
            result["python_ok"] = False

    if not result["python_ok"]:
        if progress_cb:
            progress_cb("Python 설치에 실패했습니다. 다시 시도하세요.")
        return result

    # 2. pip 패키지 (pywin32, openpyxl) 설치
    result["pip_ok"] = install_pip_packages(progress_cb)

    # 3. Git 확인/설치
    git_info = check_git()
    if git_info["installed"]:
        if progress_cb:
            progress_cb(f"Git 이미 설치됨 ({git_info['version']})")
        result["git_ok"] = True
    else:
        if progress_cb:
            progress_cb("Git 다운로드 시작...")
        try:
            exe_path = download_git(progress_cb)
            result["git_ok"] = install_git(exe_path, progress_cb)
        except Exception as e:
            if progress_cb:
                progress_cb(f"Git 설치 실패: {e}")
            result["git_ok"] = False

    if not result["git_ok"]:
        if progress_cb:
            progress_cb("Git 설치에 실패했습니다. 다시 시도하세요.")
        return result

    # 4. Node.js 확인/설치
    node_info = check_nodejs()
    if node_info["installed"]:
        if progress_cb:
            progress_cb(f"Node.js 이미 설치됨 ({node_info['version']})")
        result["nodejs_ok"] = True
    else:
        if progress_cb:
            progress_cb("Node.js 다운로드 시작...")
        try:
            msi_path = download_nodejs(progress_cb)
            result["nodejs_ok"] = install_nodejs(msi_path, progress_cb)
        except Exception as e:
            if progress_cb:
                progress_cb(f"Node.js 설치 실패: {e}")
            result["nodejs_ok"] = False

    if not result["nodejs_ok"]:
        if progress_cb:
            progress_cb("Node.js 설치에 실패했습니다. 다시 시도��세요.")
        return result

    # 5. Claude CLI 확인/설치
    cli_info = check_claude_cli()
    if cli_info["installed"]:
        if progress_cb:
            progress_cb(f"Claude CLI 이미 설치됨 ({cli_info['version']})")
        result["claude_cli_ok"] = True
    else:
        result["claude_cli_ok"] = install_claude_cli(progress_cb)

    result["success"] = (result["python_ok"] and result["git_ok"]
                         and result["nodejs_ok"] and result["claude_cli_ok"])

    if result["success"] and progress_cb:
        progress_cb("모두 설치 완료!")
    elif not result["claude_cli_ok"] and progress_cb:
        progress_cb("Claude CLI 설치 실패. '자동 설치'를 다시 눌러주세요.")

    return result
