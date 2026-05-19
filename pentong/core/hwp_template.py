"""HWP 양식 채우기 — win32com COM 자동화.

양식(템플릿) HWP 파일의 플레이스홀더를 탐지하고,
사본을 만든 뒤 AllReplace로 값을 채워넣는다.

플레이스홀더 규칙:
  - {{필드명}} 형식 (권장)
  - OOO, ○○○ 등 반복 문자 (한글 양식에서 흔함)
  - [필드명] 형식

한컴 한글이 설치된 Windows 환경에서만 동작한다.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

from .hwp_reader import read_all_paragraphs
from .hwp_replace import batch_replace


# 플레이스홀더 탐지 패턴들
PLACEHOLDER_PATTERNS = [
    r"\{\{(.+?)\}\}",          # {{필드명}}
    r"\[([가-힣a-zA-Z_]+)\]",  # [필드명]
    r"(O{3,})",                 # OOO (3개 이상)
    r"(○{3,})",                # ○○○ (3개 이상)
    r"(_{3,})",                 # ___ (3개 이상)
]


def detect_placeholders(filepath: Path) -> list[dict]:
    """양식 파일에서 플레이스홀더를 탐지한다.

    Returns:
        [
            {
                "placeholder": "{{학과명}}",  # 원본 텍스트
                "field_name": "학과명",        # 추출된 필드명
                "paragraph_index": 5,          # 위치
                "context": "학과명: {{학과명}}"  # 주변 텍스트
            },
            ...
        ]
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")

    paragraphs = read_all_paragraphs(filepath)
    results: list[dict] = []
    seen: set[str] = set()

    for para_idx, para in enumerate(paragraphs):
        for pattern in PLACEHOLDER_PATTERNS:
            for match in re.finditer(pattern, para):
                placeholder = match.group(0)
                if placeholder in seen:
                    continue
                seen.add(placeholder)

                field_name = match.group(1) if match.lastindex else placeholder
                results.append({
                    "placeholder": placeholder,
                    "field_name": field_name,
                    "paragraph_index": para_idx,
                    "context": para.strip()[:80],
                })

    return results


def fill_template(
    template_path: Path,
    field_values: dict[str, str],
    output_path: Path | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    """양식 파일의 플레이스홀더를 값으로 채워넣는다.

    Args:
        template_path: 양식 HWP 파일 경로.
        field_values: {플레이스홀더_또는_필드명: 채울_값} 딕셔너리.
            예: {"{{학과명}}": "컴퓨터공학과", "{{학과장}}": "홍길동"}
            또는: {"학과명": "컴퓨터공학과"} (자동으로 {{}} 래핑)
        output_path: 저장 경로. None이면 자동 생성.
        progress_cb: (현재, 전체, 필드명) 콜백.

    Returns:
        {"output_path": str, "filled_fields": int, "unfilled": list[str]}
    """
    if not template_path.exists():
        raise FileNotFoundError(f"양식 파일을 찾을 수 없습니다: {template_path}")

    if output_path is None:
        output_path = template_path.parent / f"{template_path.stem}_작성완료{template_path.suffix}"

    # 양식의 플레이스홀더 탐지
    placeholders = detect_placeholders(template_path)
    placeholder_set = {p["placeholder"] for p in placeholders}

    # 치환 목록 구성
    replacements: list[tuple[str, str]] = []
    filled_fields: list[str] = []

    for key, value in field_values.items():
        # key가 플레이스홀더 자체인 경우 ("{{학과명}}")
        if key in placeholder_set:
            replacements.append((key, value))
            filled_fields.append(key)
            continue

        # key가 필드명인 경우 ("학과명") → 매칭되는 플레이스홀더 찾기
        matched = False
        for p in placeholders:
            if p["field_name"] == key or key in p["placeholder"]:
                replacements.append((p["placeholder"], value))
                filled_fields.append(p["placeholder"])
                matched = True
                break

        # 그래도 못 찾으면 직접 텍스트 치환 시도
        if not matched:
            replacements.append((key, value))
            filled_fields.append(key)

    # 채우지 못한 플레이스홀더
    filled_set = set(filled_fields)
    unfilled = [p["placeholder"] for p in placeholders if p["placeholder"] not in filled_set]

    if not replacements:
        # 치환할 게 없어도 사본은 생성
        shutil.copy2(template_path, output_path)
        return {
            "output_path": str(output_path),
            "filled_fields": 0,
            "unfilled": [p["placeholder"] for p in placeholders],
        }

    result = batch_replace(template_path, replacements, output_path, progress_cb)

    return {
        "output_path": str(output_path),
        "filled_fields": len(filled_fields),
        "unfilled": unfilled,
    }


def get_template_summary(filepath: Path) -> dict:
    """양식 파일의 요약 정보를 반환한다.

    Returns:
        {
            "filepath": str,
            "placeholders": [...],
            "total_fields": int,
            "field_names": [str, ...],
        }
    """
    placeholders = detect_placeholders(filepath)
    return {
        "filepath": str(filepath),
        "placeholders": placeholders,
        "total_fields": len(placeholders),
        "field_names": [p["field_name"] for p in placeholders],
    }
