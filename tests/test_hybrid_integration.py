"""End-to-end integration tests for the hybrid PDF parser pipeline.

These tests exercise the full local pipeline from parse_file() through to
Section output, verifying that HybridPdfParser, text splitting, image
extraction with context, and document summary generation all work together.
"""

import io
import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from prepdocslib.fileprocessor import FileProcessor
from prepdocslib.filestrategy import parse_file
from prepdocslib.listfilestrategy import File
from prepdocslib.page import Page
from prepdocslib.pdfparser import HYBRID_CONTEXT_TEXT_MAX_CHARS, HybridPdfParser, LocalPdfParser
from prepdocslib.textsplitter import SentenceTextSplitter

TEST_DATA_DIR = pathlib.Path(__file__).parent / "test-data"
FINANCIAL_PDF = TEST_DATA_DIR / "Financial Market Analysis Report 2023.pdf"
FIGURE_PDF = TEST_DATA_DIR / "Simple Figure.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_from_real_pdf(pdf_path: pathlib.Path) -> File:
    """Create a File object backed by a real PDF on disk."""
    with open(pdf_path, "rb") as f:
        content = io.BytesIO(f.read())
    content.name = pdf_path.name
    return File(content=content)


def _make_mock_summary_client(summary_text: str = "A financial analysis report about market trends.") -> AsyncMock:
    """Create a mock AsyncOpenAI client that returns a canned summary."""
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = summary_text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


def _hybrid_file_processors() -> dict[str, FileProcessor]:
    """Build file processors dict with HybridPdfParser for .pdf files."""
    return {
        ".pdf": FileProcessor(HybridPdfParser(), SentenceTextSplitter()),
    }


def _local_file_processors() -> dict[str, FileProcessor]:
    """Build file processors dict with LocalPdfParser for .pdf files."""
    return {
        ".pdf": FileProcessor(LocalPdfParser(), SentenceTextSplitter()),
    }


# ---------------------------------------------------------------------------
# Test 1: Full pipeline test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_pdf_full_pipeline(monkeypatch):
    """Parse a real multi-page PDF through parse_file with HybridPdfParser
    and verify sections are returned with content."""

    file = _make_file_from_real_pdf(FINANCIAL_PDF)
    file_processors = _hybrid_file_processors()

    # Mock process_page_image to avoid blob/network calls
    async def mock_process_page_image(**kwargs):
        return kwargs["image"]

    monkeypatch.setattr("prepdocslib.filestrategy.process_page_image", mock_process_page_image)

    sections = await parse_file(
        file,
        file_processors,
        category=None,
        blob_manager=None,
        image_embeddings_client=None,
        figure_processor=None,
    )

    # Verify sections are returned
    assert len(sections) > 0, "Expected at least one section from the PDF"

    # Verify all sections have content
    for i, section in enumerate(sections):
        assert section.chunk.text.strip(), f"Section {i} has empty text"

    # Collect all pages produced by the parser to verify all pages have text
    parser = file_processors[".pdf"].parser
    file2 = _make_file_from_real_pdf(FINANCIAL_PDF)
    pages: list[Page] = [page async for page in parser.parse(file2.content)]
    assert len(pages) > 0, "Expected pages from the PDF"
    for page in pages:
        assert len(page.text.strip()) > 0, f"Page {page.page_num} has no text"


# ---------------------------------------------------------------------------
# Test 2: Image context verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_pdf_images_have_context():
    """Parse Simple Figure.pdf through HybridPdfParser and verify
    extracted images have context_text populated."""

    parser = HybridPdfParser()
    file = _make_file_from_real_pdf(FIGURE_PDF)

    pages: list[Page] = [page async for page in parser.parse(file.content)]
    all_images = [img for page in pages for img in page.images]

    assert len(all_images) > 0, "Expected at least one image from Simple Figure.pdf"

    for img in all_images:
        assert img.context_text is not None, f"Image {img.figure_id} has no context_text"
        assert len(img.context_text) > 0, f"Image {img.figure_id} has empty context_text"
        assert len(img.context_text) <= HYBRID_CONTEXT_TEXT_MAX_CHARS, (
            f"Image {img.figure_id} context_text exceeds {HYBRID_CONTEXT_TEXT_MAX_CHARS} chars: "
            f"got {len(img.context_text)}"
        )


# ---------------------------------------------------------------------------
# Test 3: DI routing test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_pdf_no_di_for_digital():
    """Parse a digital PDF with a mock DI parser and verify
    that the DI parser is never called (all pages processed locally)."""

    di_parse_called = False

    async def _spy_parse(content):
        nonlocal di_parse_called
        di_parse_called = True
        return
        yield  # pragma: no cover - make it an async generator

    mock_di_parser = MagicMock()
    mock_di_parser.parse = _spy_parse

    parser = HybridPdfParser(di_parser=mock_di_parser)
    file = _make_file_from_real_pdf(FINANCIAL_PDF)

    pages: list[Page] = [page async for page in parser.parse(file.content)]

    # DI should not have been invoked for a digital PDF
    assert not di_parse_called, "DI parser was called but PDF is fully digital"

    # All pages should have been processed locally
    assert len(pages) > 0, "Expected pages from the PDF"
    for page in pages:
        assert len(page.text.strip()) > 0, f"Page {page.page_num} has no text (was it dropped?)"


# ---------------------------------------------------------------------------
# Test 4: Summary generation end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_integration(monkeypatch):
    """Parse a PDF through parse_file with a mock summary client and verify
    that source_document_summary is stamped on images and the client was
    called with text from the document."""

    summary_text = "A financial analysis report about market trends."
    mock_summary_client = _make_mock_summary_client(summary_text)

    file = _make_file_from_real_pdf(FIGURE_PDF)
    file_processors = _hybrid_file_processors()

    # Mock process_page_image to avoid blob/network calls
    async def mock_process_page_image(**kwargs):
        return kwargs["image"]

    monkeypatch.setattr("prepdocslib.filestrategy.process_page_image", mock_process_page_image)

    sections = await parse_file(
        file,
        file_processors,
        category=None,
        blob_manager=None,
        image_embeddings_client=None,
        figure_processor=None,
        summary_client=mock_summary_client,
        summary_model="gpt-4o-mini",
    )

    # Verify the mock client was called
    mock_summary_client.chat.completions.create.assert_awaited_once()

    # Verify the client was called with text from the document
    call_kwargs = mock_summary_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs["messages"]
    user_content = messages[1]["content"]
    assert len(user_content) > 0, "Expected non-empty text sent to summary model"

    # Re-parse to check images have summary stamped
    # (parse_file already stamps them; verify by re-parsing and manually checking)
    parser = file_processors[".pdf"].parser
    file2 = _make_file_from_real_pdf(FIGURE_PDF)
    pages: list[Page] = [page async for page in parser.parse(file2.content)]
    all_images = [img for page in pages for img in page.images]

    if all_images:
        # The images from the original parse_file call should have been stamped.
        # We need to look at sections to confirm the stamps actually happened.
        # Since sections were built from the parsed pages, verify through sections.
        images_in_sections = [img for section in sections for img in section.chunk.images]
        for img in images_in_sections:
            assert img.source_document_summary == summary_text, (
                f"Image {img.figure_id} missing summary stamp: got {img.source_document_summary!r}"
            )


# ---------------------------------------------------------------------------
# Test 5: Fallback test with LocalPdfParser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_file_without_hybrid_parser(monkeypatch):
    """Verify parse_file works normally with LocalPdfParser (no regression)."""

    file = _make_file_from_real_pdf(FINANCIAL_PDF)
    file_processors = _local_file_processors()

    # Mock process_page_image to avoid blob/network calls
    async def mock_process_page_image(**kwargs):
        return kwargs["image"]

    monkeypatch.setattr("prepdocslib.filestrategy.process_page_image", mock_process_page_image)

    sections = await parse_file(
        file,
        file_processors,
        category=None,
        blob_manager=None,
        image_embeddings_client=None,
        figure_processor=None,
    )

    # Verify sections are returned
    assert len(sections) > 0, "Expected at least one section from the PDF with LocalPdfParser"

    # Verify all sections have content
    for i, section in enumerate(sections):
        assert section.chunk.text.strip(), f"Section {i} has empty text with LocalPdfParser"
