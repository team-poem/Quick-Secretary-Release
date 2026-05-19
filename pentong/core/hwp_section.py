"""HWP 섹션 추출/교체 — win32com COM 자동화.

제목 패턴 기반으로 섹션 경계를 파악하고, 섹션 단위로 추출/교체한다.
대학 요람 같은 문서에서 "가. AI공학", "나. 컴퓨터공학" 등의 학과 섹션을 다룬다.

핵심: 커서 이동이 아닌 텍스트 기반(AllReplace)으로 교체한다.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .hwp_reader import read_all_paragraphs


@dataclass
class Section:
    """문서 내 하나의 섹션."""
    title: str
    start_index: int  # 제목 문단의 인덱스
    end_index: int     # 다음 섹션 시작 직전 인덱스 (미포함)
    paragraphs: list[str] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        """제목을 제외한 본문 텍스트."""
        return "\n".join(self.paragraphs[1:])

    @property
    def full_text(self) -> str:
        """제목 포함 전체 텍스트."""
        return "\n".join(self.paragraphs)

    @property
    def body_paragraphs(self) -> list[str]:
        """제목을 제외한 본문 문단 리스트."""
        return self.paragraphs[1:]


# 기본 섹션 제목 패턴 (대학 요람 기준)
# "가. ", "나. ", "1. ", "제1장 " 등
DEFAULT_SECTION_PATTERN = r"^(?:[가-힣]\.\s|[0-9]+\.\s|제[0-9]+[장절관]\s|[A-Z]+\.\s|[IVX]+\.\s)"


def detect_sections(
    filepath: Path,
    pattern: str | None = None,
    min_body_lines: int = 1,
) -> list[Section]:
    """HWP 파일에서 섹션들을 탐지한다.

    Args:
        filepath: HWP/HWPX 파일 경로.
        pattern: 섹션 제목을 판별할 정규식. None이면 기본 패턴 사용.
        min_body_lines: 섹션으로 인정할 최소 본문 문단 수.

    Returns:
        Section 리스트.
    """
    paragraphs = read_all_paragraphs(filepath)
    return _find_sections(paragraphs, pattern or DEFAULT_SECTION_PATTERN, min_body_lines)


def list_section_titles(
    filepath: Path,
    pattern: str | None = None,
) -> list[tuple[int, str]]:
    """섹션 제목만 빠르게 조회한다.

    Returns:
        [(문단_인덱스, 제목_텍스트), ...] 리스트.
    """
    sections = detect_sections(filepath, pattern, min_body_lines=0)
    return [(s.start_index, s.title) for s in sections]


def extract_section(
    filepath: Path,
    section_title: str,
    pattern: str | None = None,
) -> Section | None:
    """특정 제목의 섹션을 추출한다.

    Args:
        filepath: HWP/HWPX 파일 경로.
        section_title: 찾을 섹션 제목 (부분 매칭).
        pattern: 섹션 판별 정규식.

    Returns:
        매칭된 Section 객체. 없으면 None.
    """
    sections = detect_sections(filepath, pattern)
    for s in sections:
        if section_title in s.title:
            return s
    return None


def extract_section_to_file(
    filepath: Path,
    section_title: str,
    output_path: Path,
    pattern: str | None = None,
) -> Path | None:
    """특정 섹션을 별도 텍스트 파일로 추출한다.

    Returns:
        생성된 파일 경로. 섹션을 못 찾으면 None.
    """
    section = extract_section(filepath, section_title, pattern)
    if section is None:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(section.full_text, encoding="utf-8")
    return output_path


def replace_section(
    filepath: Path,
    section_title: str,
    new_content: str | Path,
    output_path: Path | None = None,
    pattern: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """마스터 문서에서 특정 섹션의 본문을 교체한다.

    AllReplace 기반: 기존 본문의 첫 번째 고유 문단을 찾아 전체 본문을 교체.

    Args:
        filepath: 마스터 HWP 파일 경로.
        section_title: 교체할 섹션의 제목 (부분 매칭).
        new_content: 새 본문 텍스트 (str) 또는 수정본 HWP 파일 경로 (Path).
        output_path: 저장 경로. None이면 자동 생성.
        pattern: 섹션 판별 정규식.
        progress_cb: 진행 상황 콜백.

    Returns:
        {"output_path": str, "section_title": str, "replaced": bool}
    """
    if not filepath.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")

    # 수정본이 파일이면 읽어오기
    if isinstance(new_content, Path):
        if not new_content.exists():
            raise FileNotFoundError(f"수정본 파일을 찾을 수 없습니다: {new_content}")
        new_section = extract_section(new_content, section_title, pattern)
        if new_section is None:
            # 수정본 전체를 새 내용으로 사용
            new_paragraphs = read_all_paragraphs(new_content)
            new_body = "\n".join(p for p in new_paragraphs if p.strip())
        else:
            new_body = new_section.body_text
    else:
        new_body = new_content

    # 마스터에서 기존 섹션 찾기
    section = extract_section(filepath, section_title, pattern)
    if section is None:
        return {
            "output_path": str(output_path or filepath),
            "section_title": section_title,
            "replaced": False,
            "error": f"섹션을 찾을 수 없습니다: {section_title}",
        }

    old_body = section.body_text
    if not old_body.strip():
        return {
            "output_path": str(output_path or filepath),
            "section_title": section_title,
            "replaced": False,
            "error": "기존 섹션 본문이 비어있습니다.",
        }

    if progress_cb:
        progress_cb(f"섹션 '{section.title}' 본문 교체 중...")

    # AllReplace로 교체
    from .hwp_replace import batch_replace

    # 본문을 문단 단위로 교체 — 고유한 문단을 찾아서 교체
    old_paras = [p for p in section.body_paragraphs if p.strip()]
    new_paras = [p for p in new_body.split("\n") if p.strip()]

    if not old_paras:
        return {
            "output_path": str(output_path or filepath),
            "section_title": section_title,
            "replaced": False,
            "error": "교체할 본문 문단이 없습니다.",
        }

    # 전략: 기존 본문의 각 문단을 순서대로 교체
    # 첫 번째 기존 문단 → 새 본문 전체, 나머지 기존 문단 → 빈 문자열
    replacements: list[tuple[str, str]] = []

    if len(old_paras) >= 1:
        # 첫 번째 기존 문단을 새 본문 전체로 교체
        replacements.append((old_paras[0], "\r".join(new_paras) if new_paras else ""))
        # 나머지 기존 문단은 삭제
        for old_p in old_paras[1:]:
            if old_p.strip() and old_p != old_paras[0]:
                replacements.append((old_p, ""))

    result = batch_replace(filepath, replacements, output_path)
    result["section_title"] = section.title
    result["replaced"] = True
    return result


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

def _find_sections(
    paragraphs: list[str],
    pattern: str,
    min_body_lines: int,
) -> list[Section]:
    """문단 리스트에서 섹션 경계를 파악한다."""
    compiled = re.compile(pattern)
    title_indices: list[int] = []

    for i, para in enumerate(paragraphs):
        if para.strip() and compiled.match(para.strip()):
            title_indices.append(i)

    if not title_indices:
        return []

    sections: list[Section] = []
    for idx, start in enumerate(title_indices):
        end = title_indices[idx + 1] if idx + 1 < len(title_indices) else len(paragraphs)
        paras = paragraphs[start:end]

        if len(paras) - 1 >= min_body_lines:  # -1 for title
            sections.append(Section(
                title=paragraphs[start].strip(),
                start_index=start,
                end_index=end,
                paragraphs=paras,
            ))

    return sections
