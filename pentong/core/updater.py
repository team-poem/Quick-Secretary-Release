"""뚝딱비서 자동 업데이트 — GitHub Releases 기반.

공개 레포의 Releases API 를 익명 호출해 최신 버전 확인 + exe 다운로드 후
Windows self-replace 헬퍼 batch 로 재시작.

레포는 public 이어야 하며 토큰/인증 없이 동작한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

# 레포 좌표 — pentong_chat.py 에서 덮어쓸 수 있도록 모듈 전역
GITHUB_OWNER = "FirstNotFists"
GITHUB_REPO = "Quick-Secretary-Release"

_UA = "DdukddakBissu-Updater"

_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ── 데이터 클래스 ──

class UpdateInfo:
    """최신 릴리스 정보 요약."""

    def __init__(self, data: dict):
        self.tag_name: str = data.get("tag_name", "")
        self.name: str = data.get("name", "") or self.tag_name
        self.body: str = data.get("body", "") or ""
        self.published_at: str = data.get("published_at", "")
        self.html_url: str = data.get("html_url", "")

        # 첨부된 exe 파일 찾기 (exe 우선, 없으면 첫 번째 asset)
        self.asset_name: str | None = None
        self.asset_url: str | None = None
        self.asset_size: int = 0
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".exe"):
                self.asset_name = name
                self.asset_url = asset.get("browser_download_url")
                self.asset_size = asset.get("size", 0)
                break

    @property
    def version(self) -> str:
        """tag 에서 v 접두사 제거 (v0.0.1 → 0.0.1)."""
        return self.tag_name.lstrip("vV")

    @property
    def has_exe(self) -> bool:
        return bool(self.asset_url)


# ── 버전 비교 ──

def parse_version(v: str) -> tuple[int, ...]:
    """'0.0.1' / 'v0.0.1' / '1.2.3-rc1' → (0,0,1) / (1,2,3)."""
    v = v.strip().lstrip("vV")
    # '-' 또는 '+' 이후는 프리릴리스/빌드 메타데이터라 무시
    for sep in ("-", "+"):
        if sep in v:
            v = v.split(sep, 1)[0]
    parts = []
    for p in v.split("."):
        digits = "".join(c for c in p if c.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def is_newer(candidate: str, current: str) -> bool:
    """candidate 버전이 current 보다 높으면 True."""
    return parse_version(candidate) > parse_version(current)


# ── API 호출 ──

def _api_url(owner: str = GITHUB_OWNER, repo: str = GITHUB_REPO) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def fetch_latest_release(
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 10,
) -> UpdateInfo:
    """GitHub API 호출 — 최신 릴리스 반환.

    Raises:
        URLError / HTTPError / TimeoutError — 네트워크/API 오류
    """
    req = urllib.request.Request(
        _api_url(owner, repo),
        headers={
            "User-Agent": _UA,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return UpdateInfo(data)


def check_for_update(current_version: str) -> UpdateInfo | None:
    """새 버전이 있는지 확인.

    Returns:
        새 버전이 있으면 UpdateInfo, 없거나 네트워크 오류면 None.
    """
    try:
        info = fetch_latest_release()
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError, json.JSONDecodeError):
        return None

    if not info.tag_name or not info.has_exe:
        return None

    if is_newer(info.version, current_version):
        return info
    return None


# ── 다운로드 ──

def download_update(
    url: str,
    dest_path: Path,
    progress_cb: Callable[[int, int], None] | None = None,
    chunk_size: int = 64 * 1024,
    timeout: int = 60,
) -> None:
    """업데이트 exe 를 다운로드. 완료 시 dest_path 에 원자적으로 저장.

    Args:
        progress_cb: (downloaded_bytes, total_bytes) 콜백. total=0 이면 길이 미상.

    Raises:
        URLError / HTTPError — 다운로드 실패.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        downloaded = 0
        with open(tmp_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    try:
                        progress_cb(downloaded, total)
                    except Exception:
                        pass

    # 완료 후에만 실제 경로로 rename (부분 파일 남지 않게)
    os.replace(tmp_path, dest_path)


# ── Self-replace ──

def get_current_exe_path() -> Path | None:
    """PyInstaller frozen 모드일 때만 현재 exe 경로 반환.

    개발 모드(python pentong_chat.py) 에선 None.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def apply_update_and_restart(
    current_exe: Path,
    new_exe: Path,
    new_filename: str | None = None,
) -> None:
    """현재 exe 를 새 exe 로 교체 + 재시작.

    Windows 는 실행 중 exe 를 덮어쓸 수 없어 분리 프로세스 helper 로 처리:
      1. 현재 프로세스 종료 대기 (2초)
      2. 구버전을 .bak 로 옮김
      3. 새 exe 를 target 경로(현재 또는 new_filename)로 이동
      4. 새 exe 실행
      5. helper 자기 삭제

    **PowerShell 기반** — cmd batch 는 한글 경로에 `move` 실패가 잦음.
    PowerShell 의 Move-Item -LiteralPath 는 unicode 안전.

    Args:
        new_filename: 새 파일명 (예: "뚝딱비서_v0.0.6.exe"). None 이면 current 덮어씀.
            다른 이름이면 current 는 .bak 로 남고, 새 exe 가 별도 파일로 저장됨.

    이 함수 호출 후 호출자는 즉시 sys.exit() 로 현재 프로세스를 종료해야 함.
    """
    if sys.platform != "win32":
        raise NotImplementedError("현재는 Windows 만 지원합니다.")

    current_exe = current_exe.resolve()
    new_exe = new_exe.resolve()
    if new_filename:
        target_path = (current_exe.parent / new_filename).resolve()
    else:
        target_path = current_exe
    backup = current_exe.with_suffix(current_exe.suffix + ".bak")
    log_path = Path(tempfile.gettempdir()) / "_ddukddak_update.log"

    # PowerShell 문자열은 single quote 안에서 '' 로 escape.
    def _ps_quote(p: Path) -> str:
        return "'" + str(p).replace("'", "''") + "'"

    # 새 파일명이 기존과 다르면 rename 모드, 같으면 덮어쓰기 모드
    is_rename = target_path != current_exe

    ps_content = f"""$ErrorActionPreference = 'Stop'
$log = {_ps_quote(log_path)}
function Log($msg) {{
  Add-Content -Path $log -Value ("{{0}} {{1}}" -f (Get-Date -Format 'HH:mm:ss'), $msg) -Encoding UTF8
}}

try {{
  Log '업데이트 시작'
  Start-Sleep -Seconds 2
  $current = {_ps_quote(current_exe)}
  $target  = {_ps_quote(target_path)}
  $newExe  = {_ps_quote(new_exe)}
  $backup  = {_ps_quote(backup)}
  $isRename = {"$true" if is_rename else "$false"}

  if (Test-Path -LiteralPath $backup) {{
    Remove-Item -Force -LiteralPath $backup
    Log '이전 .bak 제거'
  }}

  # 현재 실행 exe 를 .bak 으로 (rename 모드에서도 원본을 보존할지 여부 선택 가능)
  Move-Item -Force -LiteralPath $current -Destination $backup
  Log '원본 -> .bak'

  # rename 모드: target 자리에 이미 파일이 있으면 제거 후 이동
  if ($isRename -and (Test-Path -LiteralPath $target)) {{
    Remove-Item -Force -LiteralPath $target
    Log "target 자리 기존 파일 제거: $target"
  }}

  Move-Item -Force -LiteralPath $newExe -Destination $target
  Log ('새 exe 배치 완료: ' + $target)

  $proc = Start-Process -FilePath $target -PassThru
  Log '새 버전 실행'

  # 새 버전이 2초 이상 살아있으면 업데이트 성공 간주 → .bak 안전망 제거.
  # 2초 내 종료 시 크래시 가능성이 높아 .bak 유지(수동 롤백용).
  Start-Sleep -Seconds 2
  try {{ $proc.Refresh() }} catch {{}}
  if (-not $proc.HasExited) {{
    Remove-Item -Force -LiteralPath $backup -ErrorAction SilentlyContinue
    Log '.bak 정리 완료'
  }} else {{
    Log '새 버전이 2초 내 종료됨 — .bak 유지(롤백용)'
  }}
}} catch {{
  Log ('실패: ' + $_)
  try {{
    if (Test-Path -LiteralPath $backup) {{
      Move-Item -Force -LiteralPath $backup -Destination $current
      Log '롤백 완료'
    }}
  }} catch {{
    Log ('롤백 실패: ' + $_)
  }}
  exit 1
}} finally {{
  Remove-Item -Force -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue
}}
"""

    ps_path = Path(tempfile.gettempdir()) / "_ddukddak_update.ps1"
    # PowerShell 스크립트는 UTF-8 with BOM 가 가장 안전 (codepage 이슈 회피)
    ps_path.write_bytes(b"\xef\xbb\xbf" + ps_content.encode("utf-8"))

    # Windows CreateProcess 플래그 조합 (2026-04-20 실측으로 확정):
    #  - DETACHED_PROCESS 는 이 환경에서 PowerShell 을 즉사시킴(프로세스 spawn
    #    직후 어떤 코드도 실행 못 하고 종료). stdin/out/err 전부 DEVNULL 이어도
    #    마찬가지. 이전 세션에서 "근본 수정"으로 기록됐었지만 재현 안 됨.
    #    → CREATE_NO_WINDOW 로 대체 (console 없이 PS 정상 초기화 확인).
    #  - CREATE_BREAKAWAY_FROM_JOB: Explorer 로 띄운 부모의 Job Object 에서
    #    자식을 빼내야 부모 exit 시에도 PS 가 살아남음.
    #  - CREATE_NEW_PROCESS_GROUP: 부모 Ctrl+Break 시그널 전파 차단.
    # stdin/stdout/stderr 은 DEVNULL — 핸들 없으면 PS 초기화 중 죽는다.
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-File", str(ps_path),
    ]
    base_flags = (
        subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP
    )
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)

    try:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=base_flags | breakaway,
            close_fds=False,
        )
    except OSError:
        # Job 이 breakaway 를 불허하면 플래그 없이 재시도 (최소한의 호환)
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=base_flags,
            close_fds=False,
        )


# ── 편의 함수 ──

def human_size(n_bytes: int) -> str:
    """바이트를 KB/MB 단위로."""
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 * 1024):.1f} MB"
