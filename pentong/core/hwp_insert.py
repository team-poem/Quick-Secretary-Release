"""HWP 텍스트 삽입 — @rhwp/core (Rust + WASM) 기반.

v0.0.14 까지는 win32com InsertText + BreakPara. v0.0.17~ 부터 rhwp bridge.
"""

from __future__ import annotations

from pathlib import Path

from .hwp_reader import _call_bridge


def insert_text_at_end(
    filepath: Path,
    text: str,
    output_path: Path | None = None,
    new_paragraph: bool = True,  # 현재 rhwp bridge 는 단일 insertText — 문단 분리 처리는 bridge 내부
) -> dict:
    """문서 끝에 텍스트를 삽입한다."""
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    if output_path is None:
        output_path = filepath.parent / f"{filepath.stem}_수정본{filepath.suffix}"

    data = _call_bridge("insert_text_at_end", filepath, {
        "text": ("\n" + text) if new_paragraph else text,
        "save_path": str(output_path.resolve()),
    })
    return {
        "output_path": data.get("saved_to", str(output_path)),
        "inserted_length": len(text),
        "inserted_at": data.get("inserted_at"),
        "fallback": data.get("fallback"),
    }


def insert_text_at_beginning(
    filepath: Path,
    text: str,
    output_path: Path | None = None,
) -> dict:
    """문서 처음에 텍스트를 삽입한다."""
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    if output_path is None:
        output_path = filepath.parent / f"{filepath.stem}_수정본{filepath.suffix}"

    data = _call_bridge("insert_text_at_beginning", filepath, {
        "text": text + "\n",  # 기존 내용과 분리
        "save_path": str(output_path.resolve()),
    })
    return {
        "output_path": data.get("saved_to", str(output_path)),
        "inserted_length": len(text),
        "inserted_at": data.get("inserted_at"),
        "fallback": data.get("fallback"),
    }


def insert_paragraphs(
    filepath: Path,
    paragraphs: list[str],
    output_path: Path | None = None,
    position: str = "end",
) -> dict:
    """여러 문단을 한 번에 삽입한다.

    Args:
        position: "end" 또는 "begin".
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
    if not paragraphs:
        raise ValueError("삽입할 문단이 비어있습니다.")
    if output_path is None:
        output_path = filepath.parent / f"{filepath.stem}_수정본{filepath.suffix}"

    # bridge 는 "end" / "beginning" 사용
    pos = "beginning" if position in ("begin", "beginning") else "end"
    data = _call_bridge("insert_paragraphs", filepath, {
        "paragraphs": paragraphs,
        "position": pos,
        "save_path": str(output_path.resolve()),
    })
    return {
        "output_path": data.get("saved_to", str(output_path)),
        "inserted_paragraphs": int(data.get("count", len(paragraphs))),
        "fallback": data.get("fallback"),
    }
