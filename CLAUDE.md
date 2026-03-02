# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG (Retrieval Augmented Generation) chat application using Azure OpenAI and Azure AI Search. The `ui-migration` branch is migrating the frontend from Fluent UI / CSS Modules to **Tailwind CSS v4 + shadcn/ui**.

## Common Commands

### Frontend (from `app/frontend/`)
```bash
npm run dev          # Dev server at localhost:5173, proxies API to localhost:50505
npm run build        # TypeScript check + Vite build → outputs to app/backend/static/
npx prettier --check .   # Check formatting
npx prettier --write .   # Fix formatting
```

### Backend (activate `.venv` first with `source .venv/bin/activate`)
```bash
python -m quart --app app.app run --port 50505 --reload   # Run backend
ruff check .                    # Python lint
black --check .                 # Python format check
ty check                        # Python type checking (app code only, not tests)
```

### Testing (activate `.venv` first)
```bash
pytest -s -vv                                    # Run all tests
pytest -s -vv tests/test_app.py                  # Run specific test file
pytest -s -vv -k "test_name"                     # Run specific test by name
pytest --cov --cov-report=annotate:cov_annotate  # Coverage with annotated source
pytest --cov --cov-report=xml --cov-fail-under=90  # Coverage with 90% threshold
```
E2E tests require `npm run build` in `app/frontend/` first.

### Deployment
```bash
azd up          # Provision Azure resources + deploy all
azd provision   # Infrastructure only (Bicep)
azd deploy      # Application code only
```

## Architecture

### Frontend (`app/frontend/`)
- **React 18** + TypeScript 5.6 (strict mode), built with **Vite 6**
- **Tailwind CSS v4** via `@tailwindcss/vite` plugin (CSS-first config, no `tailwind.config.js`)
- **shadcn/ui** components in `src/components/ui/` (Radix UI primitives, lucide-react icons)
- Path alias: `@/` maps to `src/`
- Hash-based routing via React Router DOM 7
- i18next for i18n (9 languages in `src/locales/`)
- MSAL for Azure AD/Entra authentication
- Streaming responses via `ndjson-readablestream`
- Build output goes to `app/backend/static/` (served by the Python backend)
- Prettier config: 4-space tabs, 160 print width, no trailing commas

### Backend (`app/backend/`)
- **Python/Quart** (async ASGI framework), entry point in `app.py`
- `approaches/` — RAG strategies (chat with query rewriting + retrieval + generation)
- `prepdocslib/` — Document ingestion library (blob, search, parsing, embedding)
  - `pdfparser.py` — PDF/DOCX/PPTX parsers (`LocalPdfParser`, `LocalDocxParser`, `LocalPptxParser`, `HybridPdfParser`, `DocumentAnalysisParser`)
  - `officeimageextractor.py` — Image extraction from PPTX/DOCX with context metadata
  - `filestrategy.py` — Orchestrates parsing, summary generation, image processing, and indexing
  - `searchmanager.py` — Azure Search index creation, schema migration, and document upload
  - `embeddings.py` — Text embeddings (OpenAI) and image embeddings (Azure Vision)
- `chat_history/` — CosmosDB chat history storage
- Served via Gunicorn + Uvicorn worker

### Azure Functions (`app/functions/`)
Cloud ingestion pipeline functions. Each bundles a copy of `prepdocslib` — run `python scripts/copy_prepdocslib.py` after modifying the library.

### Document Ingestion Pipeline
The ingestion pipeline supports multiple document formats with format-specific parsers:

| Format | Parser | DI Required? | Images? |
|--------|--------|-------------|---------|
| PDF (digital) | `HybridPdfParser` / `LocalPdfParser` | No (local) | Yes (PyMuPDF) |
| PDF (scanned) | `HybridPdfParser` → `DocumentAnalysisParser` | Only scanned pages | Yes (DI figures) |
| PPTX | `LocalPptxParser` | No (local) | Yes (python-pptx) |
| DOCX | `LocalDocxParser` | No (local) | Yes (python-docx) |
| XLSX, PNG, JPG, etc. | `DocumentAnalysisParser` | Yes | Via DI |

**Environment variables for parsing:**
- `USE_HYBRID_PDF_PARSER=true` — Enable per-page triage for PDFs (digital pages local, scanned pages to DI)
- `USE_LOCAL_PDF_PARSER=true` — Force all PDFs to local parser (overrides hybrid)
- `USE_DOCUMENT_SUMMARY=true` — Generate per-document LLM summaries stamped on images

### Infrastructure (`infra/`)
Bicep templates for Azure resources. See `.github/instructions/bicep.instructions.md` for Bicep coding conventions.

## Key Patterns

### Adding a Developer Setting
1. `app/frontend/src/api/models.ts` — add to `ChatAppRequestOverrides`
2. `app/frontend/src/components/Settings/Settings.tsx` — add UI element
3. `app/frontend/src/locales/*/translation.json` — add translations for all 9 languages
4. `app/frontend/src/pages/chat/Chat.tsx` — wire up the setting
5. `app/backend/approaches/chatreadretrieveread.py` — retrieve from overrides
6. `app/backend/app.py` — add to `/config` route if needed

### Adding azd Environment Variables
1. `infra/main.parameters.json` — add parameter mapped to env var
2. `infra/main.bicep` — add Bicep parameter, add to `appEnvVariables`
3. `.azdo/pipelines/azure-dev.yml` and `.github/workflows/azure-dev.yml` — add under `env`

### shadcn/ui Components
Config in `app/frontend/components.json`. Style: default, baseColor: neutral, CSS variables enabled. Add new components via `npx shadcn@latest add <component>` from `app/frontend/`.

## Code Style

### Python
- **Ruff** for linting (rules: E, F, I, UP; ignores: E501, E701, UP045)
- **Black** for formatting (120 char line length)
- Target: Python 3.10
- Do NOT use single underscore prefix for "private" methods/variables
- Type hints enforced in app code but not in tests

### TypeScript/Frontend
- **Prettier** for formatting (config in `.prettierrc.json`)
- No ESLint currently configured
- Functional React components with hooks

## Testing Conventions
- **E2E**: Playwright via Python (`tests/e2e.py`) — tests UI in browser with mocked backend snapshots
- **Integration**: `tests/test_app.py` — API endpoints with mocked Azure services
- **Unit**: `tests/test_*.py` — individual functions/methods
- Use mocks from `tests/conftest.py`, prefer mocking at HTTP level
- Coverage threshold: 90% for both overall and diff coverage
- Run tests via `.venv/bin/pytest` (no `--timeout` flag — not installed)

### Ingestion pipeline tests
```bash
.venv/bin/pytest tests/test_local_pptxparser.py -v      # LocalPptxParser
.venv/bin/pytest tests/test_hybrid_pdfparser.py -v       # HybridPdfParser
.venv/bin/pytest tests/test_officeimageextractor.py -v   # Office image extraction
.venv/bin/pytest tests/test_document_summary.py -v       # Document summaries
.venv/bin/pytest tests/test_hybrid_integration.py -v     # End-to-end integration
.venv/bin/pytest tests/test_page.py -v                   # Page/ImageOnPage serialization
```

## Upgrading Backend Dependencies
```bash
cd app/backend && uv pip compile requirements.in -o requirements.txt --python-version 3.10 --upgrade-package <package-name>
```
