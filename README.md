# CV Tailor

*AI-generated README, except for the improvements section.*

A small web app that tailors your CV to a specific job. Upload your CV as a PDF, paste a job description, and get back a PDF of the same CV, reworded and reordered to fit that role, without inventing any experience.

## What I built and why

Tailoring a CV to every application helps, but doing it by hand is slow and asking a chatbot often produces a CV full of skills you don't have. I wanted a tool that does the tedious part while sticking to my real experience:

- **Input:** your CV (PDF) and a job description (pasted text).
- **Processing:** an LLM rewrites the profile summary, reorders and rewords bullet points and skills by relevance to the job, and uses the job's terminology only where the CV already supports it. It's told never to add employers, dates, numbers or skills that aren't in the original.
- **Output:** an on-screen preview and a clean, ATS-friendly PDF to download.

## How to run it

Requires **Python 3.10+** (the minimum the dependencies support). Developed and tested on Python 3.13, Windows 11.

```bash
git clone <this repo>
cd cv_tailor_application

python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate

pip install -r requirements.txt
```

### Option A: demo mode (no API key, no sign-up)

Just run it:

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000. With no API key set, the app runs in **demo mode**: every request returns a pre-made tailored version of the sample CV, so you can click through the whole flow, including the PDF download, without any network calls. Try it with `samples/sample_cv.pdf` and the text in `samples/sample_job_description.txt`.

### Option B: real tailoring (free OpenRouter key)

1. Create a free account and key at https://openrouter.ai/keys (no payment needed).
2. Copy `.env.example` to `.env` and fill in the key:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
3. Run `uvicorn app.main:app --reload` and open http://localhost:8000.

A request takes roughly 20-60 seconds on the free models. Settings are read once at startup, so **restart the server after editing `.env`** (`--reload` only watches Python files).

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

The tests run fully offline: the LLM is replaced with a fake, so no API key or network is needed.

## How it works

```
PDF upload ──► pypdf extracts text ──► LLM (OpenRouter) returns tailored CV as JSON
                                              │
                                   validated against CVData (Pydantic)
                                              │
                     ┌────────────────────────┴────────────────────────┐
              HTML preview (htmx)                          PDF (Jinja template → xhtml2pdf)
```

1. **Upload** (`app/main.py`, `POST /tailor`): checks the job description isn't empty or too long, the file is at most 5 MB, and the file really is a PDF (by its `%PDF-` header, not its name).
2. **Text extraction** (`app/services/pdf_extract.py`): pypdf reads the PDF's text layer. Password-protected and scanned (image-only) PDFs get a clear error message; edit-restricted PDFs are accepted.
3. **Tailoring** (`app/services/tailor.py`, `app/prompts/tailor_system.md`): one LLM call with the CV text and job description. The system prompt sets strict "never invent" rules and includes a JSON Schema **generated from the Pydantic model**, so the prompt and the validation can't drift apart. The CV and job description are wrapped in tags and treated as data, to reduce prompt injection from a job advert.
4. **Validation**: the reply is cut down to the outermost `{...}` (models sometimes add code fences or chatter) and validated into `CVData` (`app/models.py`).
5. **Preview and download**: the result is shown as an htmx partial. The tailored CV travels back in a hidden form field to `POST /download`, which renders it to PDF. The server is **stateless**: no database, no sessions.

### Design decisions

| Decision | Why |
|---|---|
| **FastAPI + Jinja + htmx** | All Python, no JavaScript build step. htmx swaps server-rendered HTML fragments into the page. |
| **OpenRouter free models** | Free to run. The Claude/OpenAI APIs have no free tier. OpenRouter uses the OpenAI-compatible API, so switching to a paid model is one line in `.env`. |
| **Fallback models** | Free models share capacity between all users and are often busy (HTTP 429). OpenRouter tries backup models in order (`LLM_FALLBACK_MODELS`). |
| **One LLM call, JSON output** | Structured output means the PDF layout is controlled by a template, not by the model. One call keeps within free-tier rate limits. |
| **xhtml2pdf** | Pure Python, installs with pip on Windows. WeasyPrint needs native GTK libraries; Playwright needs a ~150 MB browser. Trade-off: limited CSS (no flexbox), so the template uses tables. |
| **Bundled DejaVu Sans font** | The built-in PDF fonts can't draw characters like Ł or →. |
| **`LLMClient` protocol + `FakeLLM`** | The rest of the app doesn't care which LLM it talks to. The same fake powers demo mode and the tests. |

### Project structure

```
app/
  main.py               routes: GET /, POST /tailor, POST /download
  config.py             settings from .env (pydantic-settings)
  models.py             CVData schema
  prompts/              the tailoring system prompt
  services/             pdf_extract, llm, tailor, render
  templates/            pages, htmx partials and the PDF template
  static/               CSS and a pinned copy of htmx
  fonts/                DejaVu Sans (+ licence)
  demo/                 canned response used in demo mode
samples/                fictional sample CV and job description
tests/                  pytest suite (offline)
```

### Dependencies

| Package | Used for |
|---|---|
| fastapi, uvicorn | web framework and server |
| jinja2 | HTML and PDF templates |
| python-multipart | file uploads (form parsing) |
| pydantic-settings | reading config from `.env` |
| pypdf (+ cryptography) | extracting text from PDFs, including AES-encrypted ones |
| openai | calling OpenRouter's OpenAI-compatible API |
| xhtml2pdf | rendering HTML to PDF |
| pytest, httpx, ruff | tests, the test client, linting (dev only) |

## Testing

54 tests in `tests/`, covering:

- **PDF extraction**: real, edit-restricted and password-protected PDFs (RC4 and AES-256), empty, garbage, truncated and near-empty "scanned" files.
- **LLM output parsing**: plain JSON, code-fenced, chatty replies, truncated JSON and schema violations.
- **LLM client**: fallback models are sent, the answering model is recorded, and each API error (rate limit, bad key, unknown model, timeout, server error) becomes a friendly message. The SDK call is replaced, so no network is used.
- **Rendering**: the PDF round-trips through text extraction, HTML in CV content is escaped (XSS), and non-Latin characters survive.
- **Routes**: the happy path, every input error with its status code (including CVs with an unreasonable amount of text), LLM failures (502) and the download round trip.

To check the tests actually catch bugs, I deliberately broke the code in six places (e.g. turning off HTML escaping, re-adding an old encryption bug) and confirmed the suite failed. One change didn't fail any test, which showed that a code-fence regex was redundant, so I removed it.

I also tested manually in the browser, and with real model calls checked that every employer, title, date, skill and number in the output appeared word for word in the original CV.

## Limitations

- **Always proofread the output.** The hard facts are kept, but the rewritten profile summary is free text, and models sometimes add vague claims ("strong communication skills") that the CV only loosely supports.
- **Scanned PDFs aren't supported** (no OCR), and complex layouts (multi-column CVs) may extract in a jumbled order.
- **Chinese, Japanese and Korean text** won't render in the PDF (the bundled font doesn't cover them).
- **Free models are slow and sometimes busy**, and have a daily request limit (50 a day without credits).
- **The output layout is a single fixed template**, not your original design.
- **Built for running locally, not public hosting.** There's no login or rate limiting, so if it were deployed publicly anyone could use up the owner's OpenRouter quota.

## Privacy

Your CV is sent to OpenRouter and on to whichever model provider serves the request. OpenRouter itself doesn't store prompts unless you opt in, but **by default it may route to providers that store prompts or train on them** (OpenRouter's `data_collection` preference defaults to `"allow"`). You can switch off those providers account-wide in your OpenRouter privacy settings (https://openrouter.ai/workspaces/default/settings). Note that this may leave fewer free models available. Don't upload a CV you aren't comfortable sharing with a third-party AI service.

The app itself stores nothing: there is no database or session, and uploads are processed in memory. (For files over 1 MB, the web framework briefly spools the upload to a temporary file, which is deleted after the request.)

## What I'd improve with more time

- The ability to create tailored cover letters.
- Add the option to import and export with docx file type.
- A verification check to see whether tailored CV is faithful to original CV and no new information was invented.
- The ability to add company information as context.

## Documentation

- [RESEARCH.md](RESEARCH.md): what I needed to learn and how I learned it.
- [AI.md](AI.md): how I used AI tools, where they were wrong, and how I checked their work.
