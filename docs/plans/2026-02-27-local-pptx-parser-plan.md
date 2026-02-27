# LocalPptxParser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local PPTX parser so presentations no longer require Azure Document Intelligence.

**Architecture:** `LocalPptxParser` uses `python-pptx` for text extraction and delegates to the existing `_extract_pptx_images()` for image handling. It yields `Page` objects with images already attached, matching the pattern used by `HybridPdfParser`.

**Tech Stack:** python-pptx (already a dependency), existing `officeimageextractor.py` image extraction.

---

### Task 1: Write failing test for basic slide text extraction

**Files:**
- Create: `tests/test_local_pptxparser.py`

**Step 1: Write the test file with basic text extraction tests**

```python
"""Tests for LocalPptxParser — local PPTX parsing without Document Intelligence."""

import io

import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches


def _make_large_test_png() -> bytes:
    """Create a noisy PNG that passes the 2 KB byte-size filter."""
    import random

    rng = random.Random(42)
    pixels = bytes([rng.randint(0, 255) for _ in range(200 * 200 * 3)])
    img = Image.frombytes("RGB", (200, 200), pixels)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_pptx(
    slides: list[dict] | None = None,
) -> bytes:
    """Build a PPTX in memory.

    Each dict in `slides` can have:
      - title: str | None
      - body: str | None
      - notes: str | None
      - include_picture: bool (default False)
      - table: list[list[str]] | None  (rows of cells)
    """
    prs = Presentation()
    if slides is None:
        slides = [{"title": "Slide 1", "body": "Hello world"}]

    for slide_spec in slides:
        slide_layout = prs.slide_layouts[1]  # Title + content
        slide = prs.slides.add_slide(slide_layout)

        title = slide_spec.get("title")
        if title and slide.shapes.title is not None:
            slide.shapes.title.text = title

        body = slide_spec.get("body")
        if body:
            txBox = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1))
            txBox.text_frame.text = body

        notes = slide_spec.get("notes")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

        if slide_spec.get("include_picture"):
            img_bytes = _make_large_test_png()
            slide.shapes.add_picture(io.BytesIO(img_bytes), Inches(1), Inches(3), Inches(2), Inches(2))

        table_data = slide_spec.get("table")
        if table_data:
            rows = len(table_data)
            cols = len(table_data[0]) if table_data else 0
            tbl = slide.shapes.add_table(rows, cols, Inches(1), Inches(4), Inches(6), Inches(2)).table
            for r_idx, row in enumerate(table_data):
                for c_idx, cell_text in enumerate(row):
                    tbl.cell(r_idx, c_idx).text = cell_text

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _parse_pptx_sync(pptx_bytes: bytes, filename: str = "test.pptx") -> list:
    """Helper to run the async parser synchronously."""
    import asyncio

    from prepdocslib.pdfparser import LocalPptxParser

    parser = LocalPptxParser()
    stream = io.BytesIO(pptx_bytes)
    stream.name = filename

    async def collect():
        return [page async for page in parser.parse(content=stream)]

    return asyncio.run(collect())


class TestLocalPptxParserText:
    def test_single_slide_title_and_body(self):
        """A single slide yields one Page with title as heading and body text."""
        pptx_bytes = _build_pptx([{"title": "My Title", "body": "Body content"}])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 1
        assert pages[0].page_num == 0
        assert "# My Title" in pages[0].text
        assert "Body content" in pages[0].text

    def test_multiple_slides(self):
        """Each slide becomes a separate Page with correct page_num."""
        pptx_bytes = _build_pptx([
            {"title": "First", "body": "A"},
            {"title": "Second", "body": "B"},
            {"title": "Third", "body": "C"},
        ])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 3
        assert pages[0].page_num == 0
        assert pages[1].page_num == 1
        assert pages[2].page_num == 2
        assert "# First" in pages[0].text
        assert "# Second" in pages[1].text
        assert "# Third" in pages[2].text

    def test_offsets_are_cumulative(self):
        """Page offsets accumulate across slides."""
        pptx_bytes = _build_pptx([
            {"title": "A", "body": "Hello"},
            {"title": "B", "body": "World"},
        ])
        pages = _parse_pptx_sync(pptx_bytes)

        assert pages[0].offset == 0
        assert pages[1].offset == len(pages[0].text)

    def test_speaker_notes(self):
        """Speaker notes are included after a separator."""
        pptx_bytes = _build_pptx([{"title": "Slide", "body": "Content", "notes": "My speaker notes"}])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 1
        assert "Notes:" in pages[0].text
        assert "My speaker notes" in pages[0].text

    def test_table_extraction(self):
        """Tables are rendered as pipe-delimited rows."""
        pptx_bytes = _build_pptx([{
            "title": "Data",
            "table": [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]],
        }])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 1
        assert "Name | Age" in pages[0].text
        assert "Alice | 30" in pages[0].text
        assert "Bob | 25" in pages[0].text

    def test_empty_slide(self):
        """A slide with no text still yields a Page (possibly empty text)."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout
        buf = io.BytesIO()
        prs.save(buf)

        pages = _parse_pptx_sync(buf.getvalue())
        assert len(pages) == 1
        assert pages[0].page_num == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -m pytest tests/test_local_pptxparser.py -v`
Expected: FAIL with `ImportError` or `AttributeError` — `LocalPptxParser` does not exist yet.

**Step 3: Commit test file**

```bash
git add tests/test_local_pptxparser.py
git commit -m "test: add failing tests for LocalPptxParser text extraction"
```

---

### Task 2: Implement LocalPptxParser text extraction

**Files:**
- Modify: `app/backend/prepdocslib/pdfparser.py` (add class after `LocalDocxParser`, around line 122)

**Step 1: Add the LocalPptxParser class**

Add this class after `LocalDocxParser` (before `DocumentAnalysisParser`) in `pdfparser.py`:

```python
class LocalPptxParser(Parser):
    """
    Concrete parser backed by python-pptx that can parse PPTX files into pages.
    Each slide becomes one Page. Extracts visible text, tables, and speaker notes.
    Images are extracted using the officeimageextractor module.
    """

    async def parse(self, content: IO) -> AsyncGenerator[Page, None]:
        from pptx import Presentation

        doc_name = getattr(content, "name", "unknown")
        logger.info("Extracting text from '%s' using local PPTX parser (python-pptx)", doc_name)

        try:
            content.seek(0)
        except (OSError, io.UnsupportedOperation):
            pass
        content_bytes = content.read()
        prs = Presentation(io.BytesIO(content_bytes))

        # Phase 1: extract text into Pages
        pages: list[Page] = []
        offset = 0
        for slide_idx, slide in enumerate(prs.slides):
            text_parts: list[str] = []

            # Slide title as markdown heading
            if slide.shapes.title is not None:
                title_text = slide.shapes.title.text.strip()
                if title_text:
                    text_parts.append(f"# {title_text}")

            # Other shapes: text frames and tables
            for shape in slide.shapes:
                if shape == slide.shapes.title:
                    continue
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        text_parts.append(" | ".join(cells))
                elif shape.has_text_frame:
                    shape_text = shape.text_frame.text.strip()
                    if shape_text:
                        text_parts.append(shape_text)

            # Speaker notes
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    text_parts.append(f"\n---\nNotes: {notes_text}")

            page_text = "\n".join(p for p in text_parts if p)
            page = Page(page_num=slide_idx, offset=offset, text=page_text)
            pages.append(page)
            offset += len(page_text)

        # Phase 2: extract and merge images
        from .officeimageextractor import _extract_pptx_images

        images = _extract_pptx_images(content_bytes, doc_name)
        if images:
            logger.info("Extracted %d images from '%s'", len(images), doc_name)
            page_map = {p.page_num: p for p in pages}
            for image in images:
                target = page_map.get(image.page_num, pages[-1] if pages else None)
                if target is not None:
                    target.text = target.text.rstrip() + "\n" + image.placeholder
                    target.images.append(image)

        # Phase 3: yield pages
        for page in pages:
            yield page
```

Note: the `from pptx import Presentation` is a lazy import to match the pattern used in `officeimageextractor.py` and avoid import-time failures if python-pptx isn't installed.

**Step 2: Run the text extraction tests**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -m pytest tests/test_local_pptxparser.py -v`
Expected: All 6 tests in `TestLocalPptxParserText` PASS.

**Step 3: Commit**

```bash
git add app/backend/prepdocslib/pdfparser.py
git commit -m "feat: add LocalPptxParser for local PPTX text and image extraction"
```

---

### Task 3: Write and run image integration tests

**Files:**
- Modify: `tests/test_local_pptxparser.py` (add new test class)

**Step 1: Add image integration tests to the test file**

Append this class to `tests/test_local_pptxparser.py`:

```python
class TestLocalPptxParserImages:
    def test_images_attached_to_pages(self):
        """Slides with pictures have ImageOnPage objects attached."""
        pptx_bytes = _build_pptx([{"title": "Img Slide", "body": "Text", "include_picture": True}])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 1
        assert len(pages[0].images) >= 1
        img = pages[0].images[0]
        assert img.page_num == 0
        assert img.context_title == "Img Slide"
        assert len(img.bytes) > 0

    def test_image_placeholder_in_text(self):
        """Image placeholders are appended to the page text."""
        pptx_bytes = _build_pptx([{"title": "Pic", "body": "Words", "include_picture": True}])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 1
        assert "<figure" in pages[0].text

    def test_slide_without_image_has_no_images(self):
        """Slides without pictures have empty images list."""
        pptx_bytes = _build_pptx([
            {"title": "No Pic", "body": "Just text"},
            {"title": "Has Pic", "body": "With image", "include_picture": True},
        ])
        pages = _parse_pptx_sync(pptx_bytes)

        assert len(pages) == 2
        assert len(pages[0].images) == 0
        assert len(pages[1].images) >= 1
```

**Step 2: Run image integration tests**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -m pytest tests/test_local_pptxparser.py::TestLocalPptxParserImages -v`
Expected: All 3 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_local_pptxparser.py
git commit -m "test: add image integration tests for LocalPptxParser"
```

---

### Task 4: Wire LocalPptxParser into pipeline

**Files:**
- Modify: `app/backend/prepdocslib/servicesetup.py:22` (add import)
- Modify: `app/backend/prepdocslib/servicesetup.py:314-327` (change PPTX routing)

**Step 1: Add import**

In `servicesetup.py` line 22, change:
```python
from .pdfparser import DocumentAnalysisParser, HybridPdfParser, LocalDocxParser, LocalPdfParser
```
to:
```python
from .pdfparser import DocumentAnalysisParser, HybridPdfParser, LocalDocxParser, LocalPdfParser, LocalPptxParser
```

**Step 2: Change PPTX routing**

Replace the block at lines 314-327:
```python
    # These file formats require Document Intelligence
    if doc_int_parser is not None:
        file_processors.update(
            {
                ".pptx": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".xlsx": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".png": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".jpg": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".jpeg": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".tiff": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".bmp": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".heic": FileProcessor(doc_int_parser, sentence_text_splitter),
            }
        )
```

with:
```python
    # PPTX can be parsed locally (no DI needed)
    file_processors.update({".pptx": FileProcessor(LocalPptxParser(), sentence_text_splitter)})

    # These file formats require Document Intelligence
    if doc_int_parser is not None:
        file_processors.update(
            {
                ".xlsx": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".png": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".jpg": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".jpeg": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".tiff": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".bmp": FileProcessor(doc_int_parser, sentence_text_splitter),
                ".heic": FileProcessor(doc_int_parser, sentence_text_splitter),
            }
        )
```

**Step 3: Run all tests to verify nothing is broken**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -m pytest tests/test_local_pptxparser.py tests/test_officeimageextractor.py -v`
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add app/backend/prepdocslib/servicesetup.py
git commit -m "feat: wire LocalPptxParser as default PPTX parser, remove DI dependency"
```

---

### Task 5: Final verification — run full test suite

**Step 1: Run all project tests**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS, no regressions.

**Step 2: Verify no import errors**

Run: `cd /Users/kkw/Desktop/Astar/azure-search-openai-demo && python -c "from prepdocslib.pdfparser import LocalPptxParser; print('OK')"`
Expected: prints `OK`.

**Step 3: Commit any fixups if needed, otherwise done**
