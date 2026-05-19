"""HWP 찾아바꾸기 — @rhwp/core (Rust + WASM) 기반.

v0.0.14 까지는 win32com AllReplace 패턴. v0.0.17~ 부터 rhwp bridge 로 이관.
COM 의존 제거, 한컴 OCX 미등록 PC 에서도 동작.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .hwp_reader import _call_bridge


def find_and_replace(
    filepath: Path,
    find_str: str,
    replace_str: str,
    output_path: Path | None = None,
    ignore_case: bool = False,
    whole_word: bool = False,  # rhwp 레벨에선 아직 미지원 (호환성 위해 인자만)
) -> dict:
    """HWP 파일에서 텍스트를 찾아 바꾼다.

    Args:
        filepath: 대상 HWP/HWPX 파일 경로.
        find_str: 찾을 문자열.
        replace_str: 바꿀 문자열.
        output_path: 저장 경로. None 이면 원본_수정본.hwp 로 자동 생성.
        ignore_case: 대소문자 무시 (현재는 인자만 받고 동작 안 함 — rhwp replaceText 는 case-sensitive).
        whole_word: 온전한 단어만 매칭 (아직 미구현).

    Returns:
        {"output_path": str, "find_str": str, "replace_str": str, "replaced_count": int}
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    if not find_str:
        raise ValueError("찾을 문자열이 비어있습니다.")

    if output_path is None:
        output_path = filepath.parent / f"{filepath.stem}_수정본{filepath.suffix}"

    data = _call_bridge("find_and_replace", filepath, {
        "find": find_str,
        "replace": replace_str,
        "save_path": str(output_path.resolve()),
        "ignore_case": ignore_case,
    })
    return {
        "output_path": data.get("saved_to", str(output_path)),
        "find_str": find_str,
        "replace_str": replace_str,
        "replaced_count": int(data.get("replaced_count", 0)),
        "fallback": data.get("fallback"),  # HWP 저장 실패 시 hwpx 로 자동 변환됐을 수도
    }


def batch_replace(
    filepath: Path,
    replacements: list[tuple[str, str]],
    output_path: Path | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    """여러 개의 찾아바꾸기를 한 번에 수행."""
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    if not replacements:
        raise ValueError("치환 목록이 비어있습니다.")

    if output_path is None:
        output_path = filepath.parent / f"{filepath.stem}_수정본{filepath.suffix}"

    pairs = [[find_s, replace_s] for find_s, replace_s in replacements if find_s]
    data = _call_bridge("batch_replace", filepath, {
        "pairs": pairs,
        "save_path": str(output_path.resolve()),
    })

    if progress_cb:
        total = len(pairs)
        for idx, item in enumerate(data.get("per_pair", [])):
            progress_cb(idx + 1, total, item.get("find", ""))

    return {
        "output_path": data.get("saved_to", str(output_path)),
        "total_replacements": int(data.get("total_replaced", 0)),
        "per_pair": data.get("per_pair", []),
        "fallback": data.get("fallback"),
    }


def find_text(
    filepath: Path,
    find_str: str,
    ignore_case: bool = False,
) -> bool:
    """HWP 파일에 특정 텍스트가 존재하는지 확인."""
    from .hwp_reader import read_full_text
    full = read_full_text(filepath)
    if ignore_case:
        return find_str.lower() in full.lower()
    return find_str in full
