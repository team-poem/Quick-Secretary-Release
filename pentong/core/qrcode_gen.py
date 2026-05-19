"""QR 코드 생성 로직.

qrcode + Pillow로 QR 코드를 생성한다.
PNG, SVG 저장과 일괄 생성을 지원한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import qrcode  # type: ignore[import]
    from qrcode.image.svg import SvgImage  # type: ignore[import]
    _HAS_QRCODE = True
except ImportError:
    qrcode = None  # type: ignore[assignment]
    SvgImage = None  # type: ignore[assignment]
    _HAS_QRCODE = False

try:
    from PIL import Image  # type: ignore[import]
    _HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False


@dataclass
class QROptions:
    """QR 코드 생성 옵션."""

    size: int = 300          # 출력 이미지 크기 (픽셀, PNG 전용)
    box_size: int = 10       # 각 QR 모듈 크기 (픽셀)
    border: int = 4          # QR 여백 (모듈 단위)
    fg_color: str = "#000000"  # 전경색 (hex)
    bg_color: str = "#ffffff"  # 배경색 (hex)
    error_correction: str = "M"  # L / M / Q / H


def _error_correction_level(level: str):  # type: ignore[return]
    """문자열을 qrcode 오류 정정 레벨 상수로 변환한다."""
    if not _HAS_QRCODE or qrcode is None:
        raise ImportError("qrcode가 설치되지 않았습니다. 'pip install qrcode[pil]'로 설치하세요.")
    mapping = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    return mapping.get(level.upper(), qrcode.constants.ERROR_CORRECT_M)


def generate_qr_image(text: str, options: QROptions | None = None):
    """텍스트로부터 QR 코드 PIL 이미지를 생성한다.

    Args:
        text: QR 코드로 인코딩할 문자열.
        options: 생성 옵션. None이면 기본값 사용.

    Returns:
        PIL.Image 객체.

    Raises:
        ImportError: qrcode 또는 Pillow가 설치되지 않았을 때.
        ValueError: text가 비어 있을 때.
    """
    if not text or not text.strip():
        raise ValueError("QR 코드로 변환할 텍스트를 입력하세요.")
    if not _HAS_QRCODE or qrcode is None:
        raise ImportError("qrcode가 설치되지 않았습니다. 'pip install qrcode[pil]'로 설치하세요.")
    if not _HAS_PIL or Image is None:
        raise ImportError("Pillow가 설치되지 않았습니다. 'pip install Pillow'로 설치하세요.")

    opts = options or QROptions()
    qr = qrcode.QRCode(
        error_correction=_error_correction_level(opts.error_correction),
        box_size=opts.box_size,
        border=opts.border,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color=opts.fg_color, back_color=opts.bg_color)
    pil_img = img.get_image()  # PIL.Image

    # 크기 조정
    if opts.size > 0:
        pil_img = pil_img.resize((opts.size, opts.size), Image.NEAREST)

    return pil_img


def save_qr_png(text: str, output_path: Path, options: QROptions | None = None) -> None:
    """QR 코드를 PNG 파일로 저장한다.

    Args:
        text: QR 코드로 인코딩할 문자열.
        output_path: 저장할 .png 파일 경로.
        options: 생성 옵션.

    Raises:
        ImportError: 필수 패키지가 없을 때.
        ValueError: text가 비어 있을 때.
    """
    img = generate_qr_image(text, options)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), format="PNG")


def save_qr_svg(text: str, output_path: Path, options: QROptions | None = None) -> None:
    """QR 코드를 SVG 파일로 저장한다.

    Args:
        text: QR 코드로 인코딩할 문자열.
        output_path: 저장할 .svg 파일 경로.
        options: 생성 옵션. 색상 옵션은 SVG에서 무시된다.

    Raises:
        ImportError: qrcode가 없을 때.
        ValueError: text가 비어 있을 때.
    """
    if not text or not text.strip():
        raise ValueError("QR 코드로 변환할 텍스트를 입력하세요.")
    if not _HAS_QRCODE or qrcode is None:
        raise ImportError("qrcode가 설치되지 않았습니다. 'pip install qrcode[pil]'로 설치하세요.")

    opts = options or QROptions()
    qr = qrcode.QRCode(
        error_correction=_error_correction_level(opts.error_correction),
        box_size=opts.box_size,
        border=opts.border,
        image_factory=SvgImage,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))


def batch_generate_qr(
    lines: list[str],
    output_dir: Path,
    fmt: str = "PNG",
    options: QROptions | None = None,
) -> list[Path]:
    """여러 텍스트 줄마다 QR 코드를 생성하여 파일로 저장한다.

    Args:
        lines: QR 코드로 변환할 텍스트 목록.
        output_dir: 생성된 파일을 저장할 디렉토리.
        fmt: 저장 형식 ("PNG" 또는 "SVG").
        options: 생성 옵션.

    Returns:
        생성된 파일 경로 목록.

    Raises:
        ValueError: lines가 비어 있거나 모든 줄이 공백일 때.
    """
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        raise ValueError("QR 코드로 변환할 텍스트를 하나 이상 입력하세요.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for idx, text in enumerate(non_empty, start=1):
        ext = fmt.lower()
        out_path = output_dir / f"qr_{idx:03d}.{ext}"
        if fmt.upper() == "SVG":
            save_qr_svg(text, out_path, options)
        else:
            save_qr_png(text, out_path, options)
        results.append(out_path)

    return results
