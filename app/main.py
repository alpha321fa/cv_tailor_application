import re
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models import CVData
from app.services.llm import LLMClient, LLMError, build_llm
from app.services.pdf_extract import PDFExtractionError, extract_text
from app.services.render import PDFRenderError, jinja_env, render_cv_pdf
from app.services.tailor import TailoringError, tailor_cv

app = FastAPI(title="CV Tailor")
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
templates = Jinja2Templates(env=jinja_env)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm(settings: SettingsDep) -> LLMClient:
    # A FastAPI dependency, so tests can swap in a FakeLLM via app.dependency_overrides.
    return build_llm(settings)


LLMDep = Annotated[LLMClient, Depends(get_llm)]


def error_response(request: Request, message: str, status_code: int, full_page: bool = False) -> HTMLResponse:
    # htmx requests get just the error box to swap into the page; normal form posts need a whole page.
    template = "error_page.html" if full_page else "partials/error.html"
    return templates.TemplateResponse(request, template, {"message": message}, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, settings: SettingsDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "demo_mode": settings.demo_mode,
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            "max_jd_chars": settings.max_job_description_chars,
        },
    )


# A plain `def` (not `async def`): the LLM call blocks for up to a minute, and
# FastAPI runs sync endpoints in a thread pool so other requests aren't held up.
@app.post("/tailor", response_class=HTMLResponse)
def tailor(
    request: Request,
    settings: SettingsDep,
    llm: LLMDep,
    # Optional with defaults so a missing field gets our friendly error message
    # instead of FastAPI's automatic JSON 422 (which htmx would show as raw JSON).
    cv_file: Annotated[UploadFile | None, File()] = None,
    job_description: Annotated[str, Form()] = "",
) -> HTMLResponse:
    job_description = job_description.strip()
    if not job_description:
        return error_response(request, "Please paste a job description.", 400)
    if len(job_description) > settings.max_job_description_chars:
        return error_response(
            request, f"The job description is too long (max {settings.max_job_description_chars:,} characters).", 400
        )
    if cv_file is None or not cv_file.filename:
        return error_response(request, "Please choose your CV as a PDF file.", 400)

    # Read one byte past the limit so we can tell "exactly at the limit" from "over it".
    pdf_bytes = cv_file.file.read(settings.max_upload_bytes + 1)
    if len(pdf_bytes) > settings.max_upload_bytes:
        return error_response(request, f"That file is too large (max {settings.max_upload_bytes // (1024 * 1024)} MB).", 413)
    # Check the file's actual content: every PDF starts with "%PDF-". The filename
    # and the browser-supplied content type are easy to get wrong or fake.
    if not pdf_bytes.startswith(b"%PDF-"):
        return error_response(request, "That file isn't a PDF. Please upload your CV as a PDF.", 400)

    try:
        cv_text = extract_text(pdf_bytes)
        # A small PDF can still hold a huge amount of text, which would make a slow,
        # oversized prompt. Real CVs are a few thousand characters.
        if len(cv_text) > settings.max_cv_chars:
            return error_response(
                request,
                f"Your CV has an unusually large amount of text ({len(cv_text):,} characters, "
                f"max {settings.max_cv_chars:,}). Please upload just your CV.",
                422,
            )
        cv = tailor_cv(llm, cv_text, job_description)
    except PDFExtractionError as exc:
        return error_response(request, str(exc), 422)
    except (LLMError, TailoringError) as exc:
        # 502 Bad Gateway: the problem is with the upstream AI service, not the user's input.
        return error_response(request, str(exc), 502)

    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {"cv": cv, "cv_json": cv.model_dump_json(), "model_used": getattr(llm, "last_model_used", None)},
    )


@app.post("/download")
def download(request: Request, cv_json: Annotated[str, Form()] = "") -> Response:
    try:
        cv = CVData.model_validate_json(cv_json)
        pdf = render_cv_pdf(cv)
    except ValidationError:
        return error_response(
            request, "The CV data was missing or invalid. Please tailor your CV again.", 400, full_page=True
        )
    except PDFRenderError as exc:
        return error_response(request, str(exc), 500, full_page=True)

    # Keep the filename to safe ASCII characters for the Content-Disposition header.
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", cv.name).strip("_") or "tailored"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_CV.pdf"'},
    )
