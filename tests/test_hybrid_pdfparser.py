import io
import logging
import pathlib
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from prepdocslib.page import Page
from prepdocslib.pdfparser import (
    HYBRID_CONTEXT_TEXT_MAX_CHARS,
    HybridPdfParser,
)

TEST_DATA_DIR = pathlib.Path(__file__).parent / "test-data"
REAL_PDF = TEST_DATA_DIR / "Financial Market Analysis Report 2023.pdf"
FIGURE_PDF = TEST_DATA_DIR / "Simple Figure.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_real_pdf_page(page_num: int = 0) -> tuple[pymupdf.Document, pymupdf.Page]:
    """Open the real test PDF and return (doc, page)."""
    doc = pymupdf.open(str(REAL_PDF))
    return doc, doc.load_page(page_num)


def _make_mock_page(
    text: str = "",
    page_rect: pymupdf.Rect | None = None,
    images: list | None = None,
    image_rects_by_xref: dict | None = None,
) -> MagicMock:
    """Build a mock pymupdf.Page with controllable text, rect, images."""
    mock_page = MagicMock(spec=pymupdf.Page)
    mock_page.get_text.return_value = text
    mock_page.rect = page_rect or pymupdf.Rect(0, 0, 612, 792)  # US Letter
    mock_page.get_images.return_value = images or []

    _rects_map = image_rects_by_xref or {}

    def _get_image_rects(xref):
        return _rects_map.get(xref, [])

    mock_page.get_image_rects = _get_image_rects
    return mock_page


# ---------------------------------------------------------------------------
# _page_needs_ocr tests
# ---------------------------------------------------------------------------


def test_page_needs_ocr_digital_page():
    """A real PDF page with substantial text should be classified as digital."""
    # Use page 1 (body page) which has more text than the title page
    doc, page = _open_real_pdf_page(1)
    parser = HybridPdfParser()
    assert parser._page_needs_ocr(page) is False
    doc.close()


def test_page_needs_ocr_scanned_signature():
    """Mock page with no text and a large image covering most of the page -> scanned."""
    page_rect = pymupdf.Rect(0, 0, 612, 792)
    # Single large image covering > 50% of the page
    big_img_rect = pymupdf.Rect(0, 0, 612, 600)  # ~75% coverage
    mock_page = _make_mock_page(
        text="",
        page_rect=page_rect,
        images=[(42, 0, 0, 0, 0, 0, 0, 0, "", "", 0)],  # xref=42
        image_rects_by_xref={42: [big_img_rect]},
    )

    parser = HybridPdfParser()
    assert parser._page_needs_ocr(mock_page) is True


def test_page_needs_ocr_small_image_with_no_text():
    """Mock page with minimal text and a tiny image -> True (too little text)."""
    page_rect = pymupdf.Rect(0, 0, 612, 792)
    # Small image (< 50% coverage)
    small_img_rect = pymupdf.Rect(10, 10, 50, 50)
    mock_page = _make_mock_page(
        text="Hi",
        page_rect=page_rect,
        images=[(7, 0, 0, 0, 0, 0, 0, 0, "", "", 0)],  # xref=7
        image_rects_by_xref={7: [small_img_rect]},
    )

    parser = HybridPdfParser()
    # Text length (2 chars) < HYBRID_OCR_MIN_TEXT_CHARS -> True via heuristic 2
    assert parser._page_needs_ocr(mock_page) is True


# ---------------------------------------------------------------------------
# Full parse tests (digital PDF, no DI needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_parser_digital_pdf():
    """Parsing a real digital PDF should produce pages with non-empty text."""
    parser = HybridPdfParser()
    with open(REAL_PDF, "rb") as f:
        content = io.BytesIO(f.read())
        content.name = "Financial Market Analysis Report 2023.pdf"

    pages: list[Page] = [page async for page in parser.parse(content)]

    assert len(pages) > 0
    # Every page should have some text
    for page in pages:
        assert len(page.text.strip()) > 0, f"Page {page.page_num} has no text"
    # Offsets should be monotonically non-decreasing
    for i in range(1, len(pages)):
        assert pages[i].offset >= pages[i - 1].offset


@pytest.mark.asyncio
async def test_hybrid_parser_extracts_images():
    """The parser should extract images from a PDF that contains embedded raster images."""
    parser = HybridPdfParser()
    with open(FIGURE_PDF, "rb") as f:
        content = io.BytesIO(f.read())
        content.name = "Simple Figure.pdf"

    pages: list[Page] = [page async for page in parser.parse(content)]
    all_images = [img for page in pages for img in page.images]

    # Simple Figure.pdf contains one embedded JPEG image
    assert len(all_images) > 0

    for img in all_images:
        assert img.figure_id.startswith("img_")
        assert len(img.bytes) > 0
        assert img.placeholder.startswith("<figure")
        assert img.mime_type.startswith("image/")


@pytest.mark.asyncio
async def test_hybrid_parser_populates_context_text():
    """Extracted images should have non-empty context_text from the source page."""
    parser = HybridPdfParser()
    with open(FIGURE_PDF, "rb") as f:
        content = io.BytesIO(f.read())
        content.name = "Simple Figure.pdf"

    pages: list[Page] = [page async for page in parser.parse(content)]
    all_images = [img for page in pages for img in page.images]

    assert len(all_images) > 0
    for img in all_images:
        assert img.context_text is not None
        assert len(img.context_text) > 0
        assert len(img.context_text) <= HYBRID_CONTEXT_TEXT_MAX_CHARS


@pytest.mark.asyncio
async def test_hybrid_parser_logs_page_routing(caplog):
    """Log output should contain the local/DI page routing summary."""
    parser = HybridPdfParser()
    with open(REAL_PDF, "rb") as f:
        content = io.BytesIO(f.read())
        content.name = "Financial Market Analysis Report 2023.pdf"

    with caplog.at_level(logging.INFO, logger="scripts"):
        _ = [page async for page in parser.parse(content)]

    assert any("pages local" in record.message for record in caplog.records), (
        f"Expected 'pages local' in log output, got: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_hybrid_parser_sends_only_scanned_pages_to_di():
    """When a PDF is fully digital, DI parser should never be called."""
    # Track whether DI parse was called
    di_parse_called = False

    async def _spy_parse(content):
        nonlocal di_parse_called
        di_parse_called = True
        return
        yield  # pragma: no cover - make it an async generator

    mock_di_parser = MagicMock()
    mock_di_parser.parse = _spy_parse

    parser = HybridPdfParser(di_parser=mock_di_parser)
    with open(REAL_PDF, "rb") as f:
        content = io.BytesIO(f.read())
        content.name = "Financial Market Analysis Report 2023.pdf"

    pages: list[Page] = [page async for page in parser.parse(content)]

    # The real PDF is digital, so DI should not have been invoked
    assert not di_parse_called, "DI parser was called but PDF is fully digital"
    assert len(pages) > 0
