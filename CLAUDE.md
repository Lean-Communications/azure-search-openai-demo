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
- `chat_history/` — CosmosDB chat history storage
- Served via Gunicorn + Uvicorn worker

### Azure Functions (`app/functions/`)
Cloud ingestion pipeline functions. Each bundles a copy of `prepdocslib` — run `python scripts/copy_prepdocslib.py` after modifying the library.

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

## Upgrading Backend Dependencies
```bash
cd app/backend && uv pip compile requirements.in -o requirements.txt --python-version 3.10 --upgrade-package <package-name>
```
