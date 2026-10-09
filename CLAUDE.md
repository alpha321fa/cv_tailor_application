# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CV Tailor: a FastAPI + Jinja + htmx web app. The user uploads a CV (PDF) and pastes a job description. A free OpenRouter LLM rewrites and reorders the CV for that job, and the app returns an on-screen preview and a downloadable PDF. The core product rule is **never invent facts**: employers, titles, dates, numbers and skills must come from the source CV. The rules live in `app/prompts/tailor_system.md`.

## Commands

The project uses a local `.venv` (Python 3.13 on Windows; dependencies need 3.10+). Run commands from the repo root.

```bash
python -m venv .venv && .venv\Scripts\Activate.ps1   # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt                  # app + pytest/httpx/ruff (versions pinned with ==)

uvicorn app.main:app --reload                        # http://localhost:8000
pytest                                               # full suite, offline
pytest tests/test_api.py::test_download_round_trip   # a single test
pytest -k "too-large"                                # parametrized case by id
ruff check .                                         # lint (ruff 0.16 default rules, no config)
python -m samples.make_sample_pdf                    # regenerate samples/sample_cv.pdf from sample_cv.json
```

`pyproject.toml` only configures pytest (`pythonpath = ["."]`, so tests can `import app`).

## Architecture

**Request flow** (`app/main.py`):
1. `POST /tailor` validates the input. The PDF check uses its `%PDF-` magic bytes, not the filename.
2. `extract_text` reads the PDF, `tailor_cv` makes **one** LLM call, and the reply becomes a `CVData` (`app/models.py`).
3. The response is the htmx partial `partials/result.html`.
4. The tailored CV is put into a hidden form field as JSON. The "Download PDF" button is a normal (non-htmx) form post to `POST /download`, which re-validates the JSON and renders the PDF. **The server is stateless**: no DB or sessions. Keep it that way unless deliberately changing the design.

**LLM layer** (`app/services/llm.py`):
- Everything depends on the `LLMClient` protocol (`complete(system, user) -> str`).
- `OpenRouterClient` uses the `openai` SDK with OpenRouter's `base_url`. It sends `response_format=json_object`, plus OpenRouter-specific fallbacks via `extra_body={"models": [main, *fallbacks]}`. It records `last_model_used`, which the result page displays.
- It maps SDK exceptions to `LLMError`, whose messages are shown to users.
- `FakeLLM` returns canned replies and records `calls`. It is used for **demo mode** (when `OPENROUTER_API_KEY` is empty, `build_llm` returns `FakeLLM` loaded with `app/demo/demo_tailored_cv.json`) and for tests.
- Free model IDs change over time. Defaults are in `app/config.py` and can be overridden with `LLM_MODEL` / `LLM_FALLBACK_MODELS` (comma-separated).

**Prompt/schema coupling** (`app/services/tailor.py`):
- `SYSTEM_PROMPT` is built at import time by inserting `CVData.model_json_schema()` into the `{schema}` placeholder. It uses `str.replace`, not `.format()`, because the text contains literal braces.
- Changing `CVData` therefore changes the prompt automatically. The PDF/preview template and `app/demo/demo_tailored_cv.json` may also need updating.
- `parse_cv_json` cuts the reply to the outermost `{...}`, which handles code fences and chatter, then validates with Pydantic.

**Error handling convention:**
- Service modules raise their own exception types with user-facing messages: `PDFExtractionError`, `LLMError`, `TailoringError`, `PDFRenderError`.
- Routes map these to status codes: 400 bad input, 413 too large, 422 unreadable or oversized PDF text, 502 LLM/AI failure.
- htmx 2 doesn't swap 4xx/5xx responses by default. `base.html` overrides `responseHandling` with a `<meta name="htmx-config">` tag so error partials still display.
- Form fields are declared optional (`= None` / `= ""`) on purpose, so missing fields get the app's friendly error partial instead of FastAPI's automatic JSON 422.
- Non-htmx routes (`/download`) return the full `error_page.html` (`error_response(..., full_page=True)`).

**Templates/PDF:**
- `partials/cv_content.html` is the single CV body markup, included by both `cv_pdf.html` (xhtml2pdf) and the on-screen preview.
- xhtml2pdf supports only limited CSS: no flexbox or grid, so the layout uses tables. Fonts are the bundled DejaVu Sans in `app/fonts/`, embedded with `@font-face` using a forward-slash path (`FONT_DIR`), because the built-in Helvetica can't draw characters like Ł or →.
- Web pages and the PDF share one Jinja environment (`render.jinja_env`) with autoescaping on. CV text comes from users and the LLM, so never mark it `|safe`.

**PDF extraction** (`app/services/pdf_extract.py`): don't reject on `reader.is_encrypted`. Edit-restricted PDFs are "encrypted" but open with an empty password, which pypdf tries automatically. Only `FileNotDecryptedError` means a real password is needed. `cryptography` is a direct dependency so AES-encrypted PDFs work.

**Config** (`app/config.py`):
- `get_settings()` is `lru_cache`d, so `.env` is read once at startup. Restart the server after editing it; `--reload` only watches `.py` files.
- In `.env`, an empty `LLM_MODEL=` would override the default with `""`. That's why it's commented out in `.env.example`.

## Conventions

- Use FastAPI's `Annotated[...]` dependency style (`SettingsDep`, `LLMDep` in `main.py`). The older `x: T = Depends(...)` form trips ruff's B008.
- `/tailor` is a sync `def` on purpose. The LLM call blocks for up to a minute, and FastAPI runs sync endpoints in a thread pool.
- Tests must never hit the network or read the real `.env`:
  - The `client` fixture in `tests/conftest.py` overrides `get_settings` (with `Settings(_env_file=None, openrouter_api_key="")`) and `get_llm` (with `FakeLLM`) through `app.dependency_overrides`.
  - `OpenRouterClient` tests monkeypatch `client._client.chat.completions.create`.
  - Encrypted test PDFs are generated in the tests with `make_encrypted_pdf`.
- `samples/` holds a **fictional** CV and job description. Never commit a real CV.
- The README documents limitations and future work ("What I'd improve with more time"). Keep it in sync when adding features or removing a listed limitation, including the test count it states.
