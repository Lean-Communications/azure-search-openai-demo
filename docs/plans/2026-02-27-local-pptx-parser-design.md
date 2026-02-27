# LocalPptxParser Design

**Date**: 2026-02-27
**Branch**: custom-extraction-expl
**Status**: Approved

## Problem

PPTX files currently require Azure Document Intelligence for text extraction. This is unnecessary — presentations have simple, structured content that `python-pptx` can parse locally. DI adds cost and a hard dependency for a straightforward format.

## Decision Summary

- **Approach B**: Thin `LocalPptxParser` class that uses `python-pptx` for text extraction and delegates image extraction to the existing `_extract_pptx_images()` in `officeimageextractor.py`.
- **Default behavior**: Local parsing is the default for PPTX. No env var needed to enable it. DI is no longer used for PPTX.
- **Content extracted per slide**: Visible shape text (title as `#` heading), tables as pipe-delimited rows, speaker notes after a `---` separator.
- **Images**: Integrated into `Page` objects by the parser, using the existing `_extract_pptx_images()` function. No duplication of filtering, dedup, alt text, or context logic.

## Design

### LocalPptxParser class (`pdfparser.py`)

New `Parser` subclass alongside `LocalDocxParser`. Each slide yields one `Page`.

**Text extraction per slide:**
1. Slide title → `# Title` (markdown heading)
2. Other shapes with text frames → plain text, one per line
3. Tables → pipe-delimited rows (matches `LocalDocxParser` table format)
4. Speaker notes → appended after `\n---\nNotes: ` separator

**Image integration:**
1. Parse all slides into `Page` objects first (text only)
2. Call `_extract_pptx_images(content_bytes, filename)` to get `ImageOnPage` list
3. Merge images into pages by matching `image.page_num` to `page.page_num` (both are slide index)
4. Append image placeholders to page text
5. Yield pages with images attached

### Pipeline wiring (`servicesetup.py`)

Replace the DI-dependent PPTX registration:

```python
# Before:
if doc_int_parser is not None:
    file_processors.update({".pptx": FileProcessor(doc_int_parser, ...)})

# After:
pptx_parser = LocalPptxParser()
file_processors.update({".pptx": FileProcessor(pptx_parser, sentence_text_splitter)})
```

PPTX is decoupled from `.xlsx`, `.png`, `.jpg`, etc. which remain DI-only.

## Scope

### Changed files
1. `app/backend/prepdocslib/pdfparser.py` — add `LocalPptxParser` class (~50 lines)
2. `app/backend/prepdocslib/servicesetup.py` — change PPTX routing (~5 lines)
3. `tests/test_local_pptxparser.py` — new test file

### Not changed
- `officeimageextractor.py` — reused as-is
- `filestrategy.py` — already handles Pages with images
- `searchmanager.py` — index schema already has all needed fields
- Embedding/indexing pipeline — unchanged
- Azure Functions — have their own PPTX path
- No new environment variables
