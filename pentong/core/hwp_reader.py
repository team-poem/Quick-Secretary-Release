"""HWP 문서 텍스트 읽기 — @rhwp/core (Rust + WASM) 기반.

v0.0.14 까지는 win32com (HWPFrame.HwpObject) 으로 읽었으나 한컴 OCX 등록된
PC 에서만 동작. v0.0.17~ 부터는 Node.js + @rhwp/core (WASM) 로 대체 — COM
의존 제거, 어떤 Windows PC 에서도 동작.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

# bridge 경로 탐색: 모듈 기준 상대 → env 변수 → 사용자 홈
_MODULE_DIR = Path(__file__).resolve().parent
_BRIDGE_JS_CANDIDATES = [
    _MODULE_DIR.parent / "rhwp_bridge" / "rhwp_bridge.js",
    Path(os.environ.get("DDUKDDAK_BRIDGE_JS", "")),
    Path(os.path.expanduser("~")) / ".ddukddak" / "rhwp_bridge" / "rhwp_bridge.js",
]

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def read_all_paragraphs(
    filepath: Path,
    progress_cb: Callable[[int, str], None] | None = None,
) -> list[str]:
    """HWP 파일의 모든 문단 텍스트를 리스트로 반환한다."""
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    data = _call_bridge("read_all_paragraphs", filepath)
    # bridge 가 [{section, paragraph, text}, ...] 리스트 반환
    rows = data if isinstance(data, list) else []
    paragraphs = [str(row.get("text", "")).strip() for row in rows]
    if progress_cb:
        for i in range(0, len(paragraphs), 100):
            preview = paragraphs[i][:30] if paragraphs[i] else ""
            progress_cb(i, preview)
    return paragraphs


def read_full_text(filepath: Path) -> str:
    """HWP 파일의 전체 텍스트를 하나의 문자열로 반환한다 (문단을 \\n 으로 연결)."""
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    text = _call_bridge("read_full_text", filepath)
    return str(text or "")


def read_paragraph_range(
    filepath: Path,
    start: int,
    end: int,
) -> list[str]:
    """특정 범위의 문단만 반환한다 (0부터, end 미포함)."""
    all_paras = read_all_paragraphs(filepath)
    return all_paras[start:end]


def search_paragraphs(
    filepath: Path,
    pattern: str,
    ignore_case: bool = True,
) -> list[tuple[int, str]]:
    """정규식 패턴에 매칭되는 문단들을 (인덱스, 텍스트) 로 반환."""
    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(pattern, flags)
    all_paras = read_all_paragraphs(filepath)
    return [(i, p) for i, p in enumerate(all_paras) if compiled.search(p)]


def list_tables(filepath: Path) -> list[dict]:
    """HWP 파일의 모든 표 위치/크기 목록을 반환한다.

    Returns:
        [
            {
                "index": 0,            # read_tables / extract_table 호출 시 참조용
                "section": 1,
                "paragraph": 2,
                "control": 0,
                "rows": 22,            # 행 수
                "cols": 4,             # 열 수
                "cells": 71,           # 병합 고려한 실 셀 수
            },
            ...
        ]
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    data = _call_bridge("list_tables", filepath)
    return data if isinstance(data, list) else []


def extract_table(
    filepath: Path,
    index: int | None = None,
    section: int | None = None,
    paragraph: int | None = None,
    control: int | None = None,
) -> dict:
    """특정 표 1개의 내용을 2D 리스트로 반환한다.

    index 하나로 지정하거나 (section, paragraph, control) 3개로 지정.
    index 는 list_tables 반환값의 순번.

    Returns:
        {
            "section": 1, "paragraph": 2, "control": 0,
            "rows": 22, "cols": 4,
            "data": [["년월", "일", "요 일", "학사내용"], ["3", "01", "토", "..."], ...],
            "cells": [{"row": 0, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "년월"}, ...]
        }
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    args: dict = {}
    if index is not None:
        args["index"] = index
    if section is not None and paragraph is not None and control is not None:
        args["section"] = section
        args["paragraph"] = paragraph
        args["control"] = control
    data = _call_bridge("extract_table", filepath, args)
    return data if isinstance(data, dict) else {}


def read_tables(filepath: Path) -> list[dict]:
    """파일의 모든 표 내용을 한 번에 반환한다.

    표가 많은 문서에선 오래 걸릴 수 있음. 특정 표만 필요하면 list_tables 로
    위치 확인 후 extract_table 로 개별 추출이 효율적.

    Returns:
        list_tables 결과와 동일한 필드 + "data": 2D 리스트.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    data = _call_bridge("read_tables", filepath)
    return data if isinstance(data, list) else []


def get_document_info(filepath: Path) -> dict:
    """문서의 기본 정보를 반환한다.

    Returns:
        {
            "filepath": str,
            "total_paragraphs": int,
            "total_chars": int,
            "non_empty_paragraphs": int,
            "sections": int,
            "page_count": int | None,
            "preview": str,  # 앞 5문단
        }
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    info_raw = _call_bridge("get_document_info", filepath)
    paragraphs = read_all_paragraphs(filepath)
    non_empty = [p for p in paragraphs if p.strip()]
    preview_lines = non_empty[:5]
    return {
        "filepath": str(filepath),
        "total_paragraphs": int(info_raw.get("total_paragraphs", len(paragraphs))),
        "total_chars": sum(len(p) for p in paragraphs),
        "non_empty_paragraphs": len(non_empty),
        "sections": int(info_raw.get("sections", 0)),
        "page_count": info_raw.get("page_count"),
        "preview": "\n".join(preview_lines),
    }


# ---------------------------------------------------------------------------
# 내부 구현 — rhwp bridge 호출
# ---------------------------------------------------------------------------

def _find_bridge_js() -> Path:
    for candidate in _BRIDGE_JS_CANDIDATES:
        if candidate and candidate.is_file():
            return candidate
    raise RuntimeError(
        "rhwp_bridge.js 를 찾을 수 없습니다.\n"
        f"검색 경로: {[str(p) for p in _BRIDGE_JS_CANDIDATES]}\n"
        "뚝딱비서 설치가 손상됐을 가능성. 설정에서 재설치를 시도하세요."
    )


def _call_bridge(operation: str, filepath: Path, args: dict | None = None):
    """Node.js 로 rhwp_bridge.js 를 호출하고 결과를 파싱."""
    bridge_js = _find_bridge_js()
    cmd = ["node", str(bridge_js), operation, str(filepath.resolve())]
    if args is not None:
        cmd.append(json.dumps(args, ensure_ascii=False))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "Node.js 가 설치되어 있지 않습니다. 뚝딱비서 설정 → 1단계에서 자동 설치하세요."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"HWP 파일 처리 시간이 초과되었습니다 (180초). 파일이 매우 크거나 손상됐을 수 있습니다."
        ) from e

    # bridge 는 stdout 에 {"ok":true,"data":...} 또는 {"ok":false,"error":"..."} 반환
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if not stdout:
        raise RuntimeError(
            f"rhwp bridge 가 응답하지 않았습니다 (rc={proc.returncode}).\n"
            f"stderr: {stderr[:500]}"
        )
    try:
        result = json.loads(stdout.splitlines()[-1])  # 마지막 JSON 라인
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"rhwp bridge 응답 파싱 실패: {e}\n"
            f"stdout: {stdout[:500]}\nstderr: {stderr[:500]}"
        )
    if not result.get("ok"):
        raise RuntimeError(
            f"rhwp bridge 오류 ({operation}): {result.get('error', '알 수 없음')}"
        )
    return result.get("data")
