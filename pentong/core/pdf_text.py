"""PDF ↔ 텍스트 변환 로직.

PDF→텍스트: PyMuPDF(fitz)로 페이지별 텍스트 추출.
텍스트→PDF: reportlab으로 한글 폰트를 지원하는 PDF 생성.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

try:
    import fitz  # type: ignore[import]  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    fitz = None  # type: ignore[assignment]
    _HAS_FITZ = False

try:
    from reportlab.pdfgen import canvas as _rl_canvas  # type: ignore[import]
    from reportlab.lib.pagesizes import A4  # type: ignore[import]
    from reportlab.pdfbase import pdfmetrics  # type: ignore[import]
    from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import]
    _HAS_REPORTLAB = True
except ImportError:
    _rl_canvas = None  # type: ignore[assignment]
    A4 = None  # type: ignore[assignment]
    pdfmetrics = None  # type: ignore[assignment]
    TTFont = None  # type: ignore[assignment]
    _HAS_REPORTLAB = False


# ---------------------------------------------------------------------------
# PDF → 텍스트
# ---------------------------------------------------------------------------

def extract_text_from_pdf(
    pdf_path: Path,
    progress_cb: Callable[[int, int], None] | None = None,
) -> str:
    """PDF 파일에서 텍스트를 추출한다.

    Args:
        pdf_path: 입력 PDF 파일 경로.
        progress_cb: (현재_페이지, 전체_페이지) 형태의 콜백. 생략 가능.

    Returns:
        추출된 텍스트 문자열. 텍스트가 없으면 빈 문자열.

    Raises:
        ImportError: PyMuPDF가 설치되지 않았을 때.
        FileNotFoundError: 파일이 존재하지 않을 때.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {pdf_path}")
    if not _HAS_FITZ or fitz is None:
        raise ImportError("PyMuPDF가 설치되지 않았습니다. 'pip install pymupdf'로 설치하세요.")

    doc = fitz.open(str(pdf_path))
    try:
        total = len(doc)
        parts: list[str] = []
        for i, page in enumerate(doc, start=1):
            if progress_cb:
                progress_cb(i, total)
            text = page.get_text()
            parts.append(text)
        return "\n".join(parts)
    finally:
        doc.close()


def batch_extract_pdfs(
    pdf_paths: list[Path],
    output_dir: Path,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """여러 PDF 파일을 일괄 텍스트 추출하여 .txt 파일로 저장한다.

    Args:
        pdf_paths: PDF 파일 경로 목록.
        output_dir: 추출된 .txt 파일들을 저장할 디렉토리.
        progress_cb: (현재_인덱스, 전체_수, 현재_파일명) 형태의 콜백.

    Returns:
        생성된 .txt 파일 경로 목록.

    Raises:
        ValueError: pdf_paths가 비어 있을 때.
    """
    if not pdf_paths:
        raise ValueError("변환할 PDF 파일을 하나 이상 선택하세요.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    total = len(pdf_paths)

    for idx, pdf_path in enumerate(pdf_paths, start=1):
        if progress_cb:
            progress_cb(idx, total, pdf_path.name)

        text = extract_text_from_pdf(pdf_path)
        out_path = output_dir / (pdf_path.stem + ".txt")
        out_path.write_text(text, encoding="utf-8")
        results.append(out_path)

    return results


# ---------------------------------------------------------------------------
# 텍스트 → PDF
# ---------------------------------------------------------------------------

_FONT_NAME = "Korean"
_FONT_SIZE = 11
_LINE_HEIGHT = 16
_MARGIN = 60
_REGISTERED_FONTS: set[str] = set()


def _register_korean_font(font_path: Path | None) -> str:
    """한글 폰트를 reportlab에 등록하고 폰트 이름을 반환한다."""
    if not _HAS_REPORTLAB or pdfmetrics is None or TTFont is None:
        raise ImportError("reportlab이 설치되지 않았습니다. 'pip install reportlab'으로 설치하세요.")

    if font_path and font_path.exists():
        key = str(font_path)
        if key not in _REGISTERED_FONTS:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
            _REGISTERED_FONTS.add(key)
        return _FONT_NAME

    # 시스템 기본 한글 폰트 탐색
    candidates = [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/gulim.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            key = str(candidate)
            if key not in _REGISTERED_FONTS:
                pdfmetrics.registerFont(TTFont(_FONT_NAME, str(candidate)))
                _REGISTERED_FONTS.add(key)
            return _FONT_NAME

    # 한글 폰트 없으면 Helvetica 사용 (한글 깨질 수 있음)
    return "Helvetica"


def convert_text_to_pdf(
    text_path: Path,
    output_path: Path,
    font_path: Path | None = None,
) -> None:
    """텍스트 파일을 PDF로 변환한다.

    Args:
        text_path: 입력 .txt 파일 경로.
        output_path: 저장할 .pdf 파일 경로.
        font_path: 사용할 TTF 폰트 파일 경로. 생략 시 시스템 한글 폰트 자동 탐색.

    Raises:
        ImportError: reportlab이 설치되지 않았을 때.
        FileNotFoundError: text_path가 존재하지 않을 때.
    """
    if not text_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {text_path}")
    if not _HAS_REPORTLAB or _rl_canvas is None or A4 is None:
        raise ImportError("reportlab이 설치되지 않았습니다. 'pip install reportlab'으로 설치하세요.")

    font_name = _register_korean_font(font_path)
    text = text_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    page_w, page_h = A4
    usable_h = page_h - _MARGIN * 2
    lines_per_page = int(usable_h // _LINE_HEIGHT)

    c = _rl_canvas.Canvas(str(output_path), pagesize=A4)
    c.setFont(font_name, _FONT_SIZE)

    y = page_h - _MARGIN
    for i, line in enumerate(lines):
        if i > 0 and i % lines_per_page == 0:
            c.showPage()
            c.setFont(font_name, _FONT_SIZE)
            y = page_h - _MARGIN

        c.drawString(_MARGIN, y, line)
        y -= _LINE_HEIGHT

    c.save()


def batch_convert_texts_to_pdf(
    text_paths: list[Path],
    output_dir: Path,
    font_path: Path | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """여러 텍스트 파일을 일괄 PDF로 변환한다.

    Args:
        text_paths: .txt 파일 경로 목록.
        output_dir: 생성된 PDF를 저장할 디렉토리.
        font_path: 한글 폰트 경로. 생략 시 자동 탐색.
        progress_cb: (현재_인덱스, 전체_수, 현재_파일명) 형태의 콜백.

    Returns:
        생성된 .pdf 파일 경로 목록.

    Raises:
        ValueError: text_paths가 비어 있을 때.
    """
    if not text_paths:
        raise ValueError("변환할 텍스트 파일을 하나 이상 선택하세요.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    total = len(text_paths)

    for idx, text_path in enumerate(text_paths, start=1):
        if progress_cb:
            progress_cb(idx, total, text_path.name)

        out_path = output_dir / (text_path.stem + ".pdf")
        convert_text_to_pdf(text_path, out_path, font_path=font_path)
        results.append(out_path)

    return results
