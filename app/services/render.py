from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa

from app.models import CVData

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "templates"
# Forward slashes so the path works inside a CSS url() on Windows too.
FONT_DIR = (APP_DIR / "fonts").as_posix()

# Autoescaping matters here: CV text comes from the user and the LLM, so a
# stray "<" must be rendered as text, not treated as HTML.
_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape())


class PDFRenderError(Exception):
    pass


def render_cv_html(cv: CVData) -> str:
    return _env.get_template("cv_pdf.html").render(cv=cv, font_dir=FONT_DIR)


def render_cv_pdf(cv: CVData) -> bytes:
    out = BytesIO()
    result = pisa.CreatePDF(src=render_cv_html(cv), dest=out)
    if result.err:
        raise PDFRenderError(f"xhtml2pdf reported {result.err} error(s) while rendering the CV.")
    return out.getvalue()
