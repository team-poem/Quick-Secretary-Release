"""QR 코드 생성 코어 테스트."""

from __future__ import annotations

import pytest

from core.qrcode_gen import (
    QROptions,
    batch_generate_qr,
    generate_qr_image,
    save_qr_png,
    save_qr_svg,
)


# ---------------------------------------------------------------------------
# 빈 입력 처리
# ---------------------------------------------------------------------------

def test_generate_qr_image_empty_raises() -> None:
    with pytest.raises(ValueError, match="텍스트를 입력하세요"):
        generate_qr_image("")


def test_generate_qr_image_whitespace_raises() -> None:
    with pytest.raises(ValueError):
        generate_qr_image("   ")


def test_batch_generate_qr_empty_raises() -> None:
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            batch_generate_qr([], pathlib.Path(d))


def test_batch_generate_qr_all_whitespace_raises() -> None:
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            batch_generate_qr(["  ", "\t"], pathlib.Path(d))


# ---------------------------------------------------------------------------
# 한글 텍스트 QR 생성
# ---------------------------------------------------------------------------

def test_generate_qr_image_korean() -> None:
    img = generate_qr_image("안녕하세요 한글 테스트")
    assert img is not None
    w, h = img.size
    assert w == h == 300  # 기본 크기


def test_save_qr_png_korean(tmp_path) -> None:
    out = tmp_path / "kr.png"
    save_qr_png("한글 QR 코드 테스트", out)
    assert out.exists()
    assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# 긴 텍스트 (URL) QR 생성
# ---------------------------------------------------------------------------

def test_generate_qr_image_long_url() -> None:
    url = "https://example.com/path?query=한글파라미터&foo=bar&baz=qux" * 3
    img = generate_qr_image(url)
    assert img is not None


def test_save_qr_png_long_url(tmp_path) -> None:
    url = "https://example.com/" + "a" * 200
    out = tmp_path / "url.png"
    save_qr_png(url, out)
    assert out.exists()


# ---------------------------------------------------------------------------
# 옵션 — 크기 / 색상
# ---------------------------------------------------------------------------

def test_generate_qr_image_custom_size() -> None:
    opts = QROptions(size=100)
    img = generate_qr_image("test", opts)
    assert img.size == (100, 100)


def test_generate_qr_image_custom_colors() -> None:
    opts = QROptions(fg_color="#ffffff", bg_color="#000000")
    img = generate_qr_image("inverted", opts)
    assert img is not None


# ---------------------------------------------------------------------------
# SVG 저장
# ---------------------------------------------------------------------------

def test_save_qr_svg(tmp_path) -> None:
    out = tmp_path / "test.svg"
    save_qr_svg("SVG 테스트", out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "<svg" in content.lower() or "svg" in content.lower()


# ---------------------------------------------------------------------------
# 일괄 생성
# ---------------------------------------------------------------------------

def test_batch_generate_qr_png(tmp_path) -> None:
    lines = ["첫 번째 QR", "두 번째 QR", "https://example.com"]
    results = batch_generate_qr(lines, tmp_path, fmt="PNG")
    assert len(results) == 3
    for p in results:
        assert p.suffix == ".png"
        assert p.exists()


def test_batch_generate_qr_svg(tmp_path) -> None:
    lines = ["SVG QR 1", "SVG QR 2"]
    results = batch_generate_qr(lines, tmp_path, fmt="SVG")
    assert len(results) == 2
    for p in results:
        assert p.suffix == ".svg"
        assert p.exists()


def test_batch_generate_qr_skips_empty_lines(tmp_path) -> None:
    lines = ["유효한 텍스트", "", "  ", "또 다른 텍스트"]
    results = batch_generate_qr(lines, tmp_path)
    assert len(results) == 2
