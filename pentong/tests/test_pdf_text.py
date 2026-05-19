"""Tests for core/pdf_text.py."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# extract_text_from_pdf
# ---------------------------------------------------------------------------

class TestExtractTextFromPdf:
    def test_raises_when_pymupdf_missing(self, tmp_path):
        pdf = tmp_path / "dummy.pdf"
        pdf.write_bytes(b"")

        import core.pdf_text as module
        original = module._HAS_FITZ
        try:
            module._HAS_FITZ = False
            module.fitz = None
            from core.pdf_text import extract_text_from_pdf
            with pytest.raises(ImportError, match="PyMuPDF"):
                extract_text_from_pdf(pdf)
        finally:
            module._HAS_FITZ = original

    def test_raises_when_file_missing(self, tmp_path):
        from core.pdf_text import extract_text_from_pdf
        with pytest.raises(FileNotFoundError):
            extract_text_from_pdf(tmp_path / "nonexistent.pdf")

    def test_extracts_text_with_mock_fitz(self, tmp_path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"%PDF dummy")

        fake_page = MagicMock()
        fake_page.get_text.return_value = "안녕하세요"
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.close = MagicMock()

        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        import core.pdf_text as module
        original_fitz = module.fitz
        original_has = module._HAS_FITZ
        try:
            module.fitz = fake_fitz
            module._HAS_FITZ = True
            from core.pdf_text import extract_text_from_pdf
            result = extract_text_from_pdf(pdf)
            assert "안녕하세요" in result
        finally:
            module.fitz = original_fitz
            module._HAS_FITZ = original_has

    def test_empty_pdf_returns_empty_string(self, tmp_path):
        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"%PDF dummy")

        fake_page = MagicMock()
        fake_page.get_text.return_value = ""
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.close = MagicMock()

        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        import core.pdf_text as module
        original_fitz = module.fitz
        original_has = module._HAS_FITZ
        try:
            module.fitz = fake_fitz
            module._HAS_FITZ = True
            from core.pdf_text import extract_text_from_pdf
            result = extract_text_from_pdf(pdf)
            assert result.strip() == ""
        finally:
            module.fitz = original_fitz
            module._HAS_FITZ = original_has

    def test_image_only_pdf_returns_empty_string(self, tmp_path):
        """이미지 전용 PDF는 텍스트가 없으므로 빈 문자열을 반환한다."""
        pdf = tmp_path / "image_only.pdf"
        pdf.write_bytes(b"%PDF image")

        fake_page = MagicMock()
        fake_page.get_text.return_value = ""  # 이미지 전용 → 텍스트 없음
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page, fake_page]))
        fake_doc.__len__ = MagicMock(return_value=2)
        fake_doc.close = MagicMock()

        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        import core.pdf_text as module
        original_fitz = module.fitz
        original_has = module._HAS_FITZ
        try:
            module.fitz = fake_fitz
            module._HAS_FITZ = True
            from core.pdf_text import extract_text_from_pdf
            result = extract_text_from_pdf(pdf)
            assert result.strip() == ""
        finally:
            module.fitz = original_fitz
            module._HAS_FITZ = original_has

    def test_progress_callback_called(self, tmp_path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"%PDF dummy")

        fake_page = MagicMock()
        fake_page.get_text.return_value = "page text"
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page, fake_page]))
        fake_doc.__len__ = MagicMock(return_value=2)
        fake_doc.close = MagicMock()

        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        import core.pdf_text as module
        original_fitz = module.fitz
        original_has = module._HAS_FITZ
        try:
            module.fitz = fake_fitz
            module._HAS_FITZ = True
            from core.pdf_text import extract_text_from_pdf
            calls = []
            extract_text_from_pdf(pdf, progress_cb=lambda cur, tot: calls.append((cur, tot)))
            assert calls == [(1, 2), (2, 2)]
        finally:
            module.fitz = original_fitz
            module._HAS_FITZ = original_has


# ---------------------------------------------------------------------------
# batch_extract_pdfs
# ---------------------------------------------------------------------------

class TestBatchExtractPdfs:
    def test_raises_when_empty(self, tmp_path):
        from core.pdf_text import batch_extract_pdfs
        with pytest.raises(ValueError, match="하나 이상"):
            batch_extract_pdfs([], tmp_path)

    def test_creates_txt_files(self, tmp_path):
        pdf1 = tmp_path / "a.pdf"
        pdf2 = tmp_path / "b.pdf"
        pdf1.write_bytes(b"%PDF")
        pdf2.write_bytes(b"%PDF")

        out_dir = tmp_path / "out"

        fake_page = MagicMock()
        fake_page.get_text.return_value = "hello"
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.close = MagicMock()

        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        import core.pdf_text as module
        original_fitz = module.fitz
        original_has = module._HAS_FITZ
        try:
            module.fitz = fake_fitz
            module._HAS_FITZ = True
            from core.pdf_text import batch_extract_pdfs
            results = batch_extract_pdfs([pdf1, pdf2], out_dir)
            assert len(results) == 2
            assert all(r.suffix == ".txt" for r in results)
            assert all(r.exists() for r in results)
        finally:
            module.fitz = original_fitz
            module._HAS_FITZ = original_has


# ---------------------------------------------------------------------------
# convert_text_to_pdf / batch_convert_texts_to_pdf
# ---------------------------------------------------------------------------

class TestConvertTextToPdf:
    def test_raises_when_reportlab_missing(self, tmp_path):
        txt = tmp_path / "hello.txt"
        txt.write_text("hello", encoding="utf-8")
        out = tmp_path / "hello.pdf"

        import core.pdf_text as module
        original = module._HAS_REPORTLAB
        try:
            module._HAS_REPORTLAB = False
            module._rl_canvas = None
            from core.pdf_text import convert_text_to_pdf
            with pytest.raises(ImportError, match="reportlab"):
                convert_text_to_pdf(txt, out)
        finally:
            module._HAS_REPORTLAB = original

    def test_raises_when_file_missing(self, tmp_path):
        from core.pdf_text import convert_text_to_pdf
        with pytest.raises(FileNotFoundError):
            convert_text_to_pdf(tmp_path / "nonexistent.txt", tmp_path / "out.pdf")

    def test_batch_raises_when_empty(self, tmp_path):
        from core.pdf_text import batch_convert_texts_to_pdf
        with pytest.raises(ValueError, match="하나 이상"):
            batch_convert_texts_to_pdf([], tmp_path)
