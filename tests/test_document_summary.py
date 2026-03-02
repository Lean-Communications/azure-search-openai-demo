from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prepdocslib.filestrategy import (
    SUMMARY_INPUT_MAX_CHARS,
    SUMMARY_MAX_TOKENS,
    _generate_document_summary,
    parse_file,
)
from prepdocslib.page import ImageOnPage, Page


def _make_mock_openai_client(summary_text="This is a summary of the document."):
    """Create a mock AsyncOpenAI client that returns a summary."""
    mock_client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = summary_text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


def _make_pages_with_images(texts, images_per_page=0):
    """Create a list of Page objects with optional images."""
    pages = []
    offset = 0
    for i, text in enumerate(texts):
        page = Page(page_num=i, offset=offset, text=text)
        for j in range(images_per_page):
            image = ImageOnPage(
                bytes=b"fake_image",
                bbox=(0, 0, 100, 100),
                page_num=i,
                figure_id=f"fig_{i}_{j}",
                filename=f"image_{i}_{j}.png",
                placeholder=f'<figure id="fig_{i}_{j}"></figure>',
            )
            page.images.append(image)
        pages.append(page)
        offset += len(text)
    return pages


@pytest.mark.asyncio
async def test_generate_summary_success():
    """Mock AsyncOpenAI client, verify summary is returned."""
    pages = _make_pages_with_images(["Hello world, this is page one.", "Page two content here."])
    client = _make_mock_openai_client("A document about greetings and content.")

    result = await _generate_document_summary(pages, client, "gpt-4o-mini", "test.pdf")

    assert result == "A document about greetings and content."
    client.chat.completions.create.assert_awaited_once()
    call_kwargs = client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs.kwargs["max_tokens"] == SUMMARY_MAX_TOKENS
    assert call_kwargs.kwargs["temperature"] == 0.0
    messages = call_kwargs.kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Summarize" in messages[0]["content"]


@pytest.mark.asyncio
async def test_generate_summary_failure_returns_none():
    """Mock client that raises, verify None returned."""
    pages = _make_pages_with_images(["Some text here."])
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    result = await _generate_document_summary(pages, client, "gpt-4o-mini", "test.pdf")

    assert result is None


@pytest.mark.asyncio
async def test_generate_summary_empty_pages():
    """Empty pages list returns None."""
    client = _make_mock_openai_client()

    # Empty list
    result = await _generate_document_summary([], client, "gpt-4o-mini", "test.pdf")
    assert result is None
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_summary_whitespace_only_pages():
    """Pages with only whitespace text return None."""
    pages = _make_pages_with_images(["   ", "\n", "\t"])
    client = _make_mock_openai_client()

    result = await _generate_document_summary(pages, client, "gpt-4o-mini", "test.pdf")

    assert result is None
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_summary_stamped_on_images(monkeypatch):
    """After parse_file with summary client, images have source_document_summary."""
    # Create mock file
    mock_file = MagicMock()
    mock_file.filename.return_value = "test.pdf"
    mock_file.file_extension.return_value = ".pdf"
    mock_file.content = BytesIO(b"test content")

    # Create pages with images
    pages = _make_pages_with_images(["Page text about financial markets."], images_per_page=2)

    # Create mock parser
    mock_parser = MagicMock()

    async def mock_parse(content):
        for page in pages:
            yield page

    mock_parser.parse = mock_parse

    mock_splitter = MagicMock()
    mock_processor = MagicMock()
    mock_processor.parser = mock_parser
    mock_processor.splitter = mock_splitter

    # Mock process_text
    monkeypatch.setattr("prepdocslib.filestrategy.process_text", lambda pages, file, splitter, category: [])

    # Mock process_page_image
    async def mock_process_page_image(**kwargs):
        return kwargs["image"]

    monkeypatch.setattr("prepdocslib.filestrategy.process_page_image", mock_process_page_image)

    # Create mock summary client
    summary_client = _make_mock_openai_client("Financial markets overview document.")

    sections = await parse_file(
        mock_file,
        {".pdf": mock_processor},
        category=None,
        blob_manager=MagicMock(),
        image_embeddings_client=None,
        figure_processor=MagicMock(),
        user_oid=None,
        summary_client=summary_client,
        summary_model="gpt-4o-mini",
    )

    # Verify images have the summary stamped
    for page in pages:
        for image in page.images:
            assert image.source_document_summary == "Financial markets overview document."


@pytest.mark.asyncio
async def test_summary_text_truncation():
    """Verify only first SUMMARY_INPUT_MAX_CHARS chars are sent to the model."""
    # Create pages with text that exceeds the limit
    long_text = "A" * 2000
    pages = _make_pages_with_images([long_text, long_text, long_text])

    client = _make_mock_openai_client("Summary of a long document.")

    result = await _generate_document_summary(pages, client, "gpt-4o-mini", "test.pdf")

    assert result == "Summary of a long document."

    # Verify the text sent to the model is truncated
    call_kwargs = client.chat.completions.create.call_args
    user_content = call_kwargs.kwargs["messages"][1]["content"]
    # The total text should not exceed SUMMARY_INPUT_MAX_CHARS (3000)
    # plus spaces used to join parts
    # Page 1: 2000 chars, Page 2: 1000 chars (remaining), Page 3: skipped
    assert len(user_content) <= SUMMARY_INPUT_MAX_CHARS + 10  # small margin for join spaces


@pytest.mark.asyncio
async def test_parse_file_without_summary_client(monkeypatch):
    """parse_file with no summary_client -> images have None source_document_summary."""
    # Create mock file
    mock_file = MagicMock()
    mock_file.filename.return_value = "test.pdf"
    mock_file.file_extension.return_value = ".pdf"
    mock_file.content = BytesIO(b"test content")

    # Create pages with images
    pages = _make_pages_with_images(["Page text here."], images_per_page=1)

    # Create mock parser
    mock_parser = MagicMock()

    async def mock_parse(content):
        for page in pages:
            yield page

    mock_parser.parse = mock_parse

    mock_splitter = MagicMock()
    mock_processor = MagicMock()
    mock_processor.parser = mock_parser
    mock_processor.splitter = mock_splitter

    # Mock process_text
    monkeypatch.setattr("prepdocslib.filestrategy.process_text", lambda pages, file, splitter, category: [])

    # Mock process_page_image
    async def mock_process_page_image(**kwargs):
        return kwargs["image"]

    monkeypatch.setattr("prepdocslib.filestrategy.process_page_image", mock_process_page_image)

    sections = await parse_file(
        mock_file,
        {".pdf": mock_processor},
        category=None,
        blob_manager=MagicMock(),
        image_embeddings_client=None,
        figure_processor=MagicMock(),
        user_oid=None,
        # No summary_client or summary_model provided
    )

    # Verify images do NOT have a summary
    for page in pages:
        for image in page.images:
            assert image.source_document_summary is None
