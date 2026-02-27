# Hybrid PDF Parser & Image Context Enrichment

This guide explains how to use the hybrid PDF parser and image context enrichment features added to the ingestion pipeline.

## What it does

The hybrid parser reduces Azure Document Intelligence (DI) costs by processing digitally-created PDF pages locally with PyMuPDF, only sending scanned pages to DI. It also extracts images from digital PDFs (closing a gap where the local PDF parser produced zero images), and enriches all extracted images with structural context metadata.

### Features

- **Per-page triage**: Each PDF page is analyzed — digital pages are processed locally, scanned pages go to DI
- **Local image extraction**: Images are extracted from digital PDFs using PyMuPDF (no DI needed)
- **Image context enrichment**: Images get metadata about where they appear:
  - `context_title` — slide title (PPTX) or nearest heading (DOCX)
  - `context_text` — full text of the page/slide the image is on
  - `alt_text` — author-provided alt text from the document
  - `source_document_summary` — LLM-generated 1-2 sentence summary of the entire document
- **Search index fields**: New searchable fields in the index enable queries like "images from the presentation about X"

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_HYBRID_PDF_PARSER` | `false` | Set to `true` to enable the hybrid parser for PDFs. When disabled, the existing behavior is preserved (DI or local parser based on `USE_LOCAL_PDF_PARSER`). |
| `USE_DOCUMENT_SUMMARY` | `false` | Set to `true` to generate a per-document summary using the chat model. Reuses the existing `AZURE_OPENAI_CHATGPT_MODEL` — no additional model deployment needed. |
| `USE_LOCAL_PDF_PARSER` | `false` | Takes priority over `USE_HYBRID_PDF_PARSER`. When `true`, uses the basic local PyPDF parser (no images, no DI). |

**Priority**: `USE_LOCAL_PDF_PARSER` > `USE_HYBRID_PDF_PARSER` > Document Intelligence (default)

## How to run

### Prerequisites

1. You have the project set up with `azd` and an active Azure environment (`azd env select <your-env>`)
2. You're logged into Azure (`azd auth login`)
3. The Python virtual environment exists (`.venv/`)

### Option 1: Using the prepdocs script (recommended)

Set the environment variables in your `azd` environment, then run the standard ingestion script:

```bash
# Enable hybrid parser and document summaries
azd env set USE_HYBRID_PDF_PARSER true
azd env set USE_DOCUMENT_SUMMARY true

# Run ingestion on all files in data/
./scripts/prepdocs.sh

# Or run on specific files
./scripts/prepdocs.sh --verbose
```

### Option 2: Running prepdocs.py directly

If you want more control, run the Python script directly. The script reads from `.azure/<env-name>/.env` via `load_azd_env()`, but you can also export variables manually:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Set the hybrid parser flags (these supplement the existing azd env vars)
export USE_HYBRID_PDF_PARSER=true
export USE_DOCUMENT_SUMMARY=true

# Run on specific files
python app/backend/prepdocs.py './data/*.pdf' --verbose

# Or on a single file
python app/backend/prepdocs.py './data/employee_handbook.pdf' --verbose
```

### Option 3: Azure Functions (cloud ingestion)

If you use the cloud ingestion pipeline (`USE_CLOUD_INGESTION=true`), set the variable in the Azure Functions app settings:

```bash
azd env set USE_HYBRID_PDF_PARSER true
azd up  # redeploys functions with the new setting
```

Note: `USE_DOCUMENT_SUMMARY` is not yet supported in the cloud ingestion pipeline (the Functions process pages across separate calls). The image context fields (`context_title`, `context_text`, `alt_text`) do flow through the Functions pipeline.

## What to look for in the output

With `--verbose`, the hybrid parser logs how pages were routed:

```
Document 'employee_handbook.pdf': 45 pages local, 0 pages DI
Extracted 12 images from employee_handbook.pdf
Generated document summary for 'employee_handbook.pdf': This document is an employee handbook...
```

For documents with scanned pages, you'll see the split:

```
Document 'mixed_report.pdf': 180 pages local, 20 pages DI
Sending 20 scanned pages (of 200 total) to Document Intelligence for 'mixed_report.pdf'
```

## How the per-page triage works

For each page in a PDF, the parser checks:

1. **Dominant image check**: If the page has very little text (< 50 characters) AND a single image covers more than 50% of the page area, it's classified as scanned
2. **Minimum text check**: If the page has fewer than 50 characters of extractable text, it's classified as scanned
3. Otherwise, the page is classified as digital and processed locally

Only the scanned pages are sent to DI (as a sub-PDF), minimizing the per-page billing.

## Search index changes

The following fields are added to the search index:

**Image subfields** (inside the `images` complex type):
- `context_title` — searchable
- `context_text` — searchable
- `alt_text` — searchable
- `source_document_summary` — searchable

**Top-level field**:
- `sourceDocumentSummary` — searchable

Existing indexes are automatically migrated (the `sourceDocumentSummary` field is added on next run). Existing documents will have `null` for the new fields until re-indexed.

## Running the tests

```bash
source .venv/bin/activate

# All hybrid parser tests
python -m pytest tests/test_hybrid_pdfparser.py -v

# Office image context tests
python -m pytest tests/test_officeimageextractor.py -v

# Document summary tests
python -m pytest tests/test_document_summary.py -v

# Integration tests
python -m pytest tests/test_hybrid_integration.py -v

# All tests at once
python -m pytest tests/test_hybrid_pdfparser.py tests/test_officeimageextractor.py tests/test_document_summary.py tests/test_hybrid_integration.py tests/test_pdfparser.py tests/test_prepdocslib_filestrategy.py tests/test_page.py -v
```

## Cost implications

- **Digital PDFs**: Zero DI cost. All processing is local using PyMuPDF.
- **Mixed PDFs**: Only scanned pages are billed by DI. A 200-page document with 20 scanned pages costs 10x less than sending the full document to DI.
- **Document summaries**: One LLM call per document (~3000 chars input, ~50 tokens output). Negligible cost using the same `gpt-4o-mini` model already deployed for chat.
- **No additional Azure resources needed**: Uses existing OpenAI deployment and storage.
