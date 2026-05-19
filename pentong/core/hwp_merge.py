"""한글(HWP/HWPX) 파일 취합 — rhwp 기반 텍스트 수준 병합.

v0.0.19 까지는 win32com (한컴 COM) 으로 InsertFile 액션을 연쇄 호출했으나,
v0.0.20 부터 COM 의존 완전 제거. 첫 파일을 base 로 열고 이후 파일들의
문단 텍스트를 append 하는 방식으로 rhwp bridge 를 통해 단순 병합.

한계:
- 서식·표·이미지는 병합되지 않고 텍스트만 연결됨. 완전 서식 병합은 rhwp
  엔진 레벨의 Document merge API 필요 — 업스트림 이슈로 남김.
- 복잡한 레이아웃 병합이 필요하면 사용자가 별도 작업 권장.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .hwp_reader import read_all_paragraphs
from .hwp_insert import insert_paragraphs


def merge_hwp_files(
    input_paths: list[Path],
    output_path: Path,
    insert_page_break: bool = True,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    """여러 HWP/HWPX 파일을 하나의 문서로 취합한다.

    Args:
        input_paths: 취합할 HWP/HWPX 파일 경로 목록.
        output_path: 저장할 출력 파일 경로 (.hwp 또는 .hwpx — rhwp 제약상
            HWPX 로 자동 폴백될 수 있음).
        insert_page_break: 파일 사이에 구분 문단 삽입 여부 (rhwp 레벨에선
            실제 페이지 나누기가 아닌 빈 구분 라인으로 처리).
        progress_cb: (현재_인덱스, 전체_수, 현재_파일명) 콜백.

    Returns:
        {"output_path": str, "merged_count": int}
    """
    if not input_paths:
        raise ValueError("취합할 파일을 하나 이상 선택하세요.")
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")

    total = len(input_paths)

    # 1. 첫 파일을 base 로 사용 → output_path 에 복사 후 여기에 이어붙임
    import shutil
    if progress_cb:
        progress_cb(1, total, input_paths[0].name)
    # 첫 파일의 확장자에 맞춰 저장 (rhwp 가 HWP 저장 못하면 insert_paragraphs
    # 단계에서 HWPX 로 폴백)
    shutil.copy2(input_paths[0], output_path)

    # 2. 나머지 파일들의 문단을 읽어 순차적으로 output_path 에 append
    for idx, src_path in enumerate(input_paths[1:], start=2):
        if progress_cb:
            progress_cb(idx, total, src_path.name)
        paragraphs = read_all_paragraphs(src_path)
        # 구분자 삽입 + 파일명 헤더
        chunks: list[str] = []
        if insert_page_break:
            chunks.append("")  # 빈 줄 구분
            chunks.append(f"═══ {src_path.stem} ═══")
            chunks.append("")
        chunks.extend(paragraphs)
        result = insert_paragraphs(
            output_path,
            chunks,
            output_path=output_path,
            position="end",
        )
        # insert_paragraphs 가 HWPX 폴백 시 경로 바뀔 수 있음
        actual = Path(result.get("output_path", str(output_path)))
        if actual != output_path:
            output_path = actual

    return {
        "output_path": str(output_path),
        "merged_count": total,
    }
