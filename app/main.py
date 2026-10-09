from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import get_settings

app = FastAPI(title="CV Tailor")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    mode = "demo mode" if get_settings().demo_mode else "live mode"
    return f"<h1>CV Tailor</h1><p>Running in {mode}.</p>"
