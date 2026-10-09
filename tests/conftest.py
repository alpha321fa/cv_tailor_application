from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.config import Settings, get_settings
from app.main import app, get_llm
from app.services.llm import DEMO_RESPONSE_PATH, FakeLLM

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture
def sample_pdf() -> bytes:
    return (SAMPLES_DIR / "sample_cv.pdf").read_bytes()


@pytest.fixture
def sample_job_description() -> str:
    return (SAMPLES_DIR / "sample_job_description.txt").read_text(encoding="utf-8")


@pytest.fixture
def demo_json() -> str:
    return DEMO_RESPONSE_PATH.read_text(encoding="utf-8")


def make_encrypted_pdf(pdf_bytes: bytes, user_password: str, algorithm: str) -> bytes:
    """Encrypt a PDF. An empty user_password gives an edit-restricted PDF that opens without a password."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf_bytes)))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm=algorithm)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def fake_llm(demo_json: str) -> FakeLLM:
    return FakeLLM([demo_json])


@pytest.fixture
def client(fake_llm: FakeLLM):
    """A TestClient that never touches the network or the real .env file."""
    # _env_file=None and an explicit empty key: ignore any real .env / environment variable.
    settings = Settings(_env_file=None, openrouter_api_key="")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm] = lambda: fake_llm
    yield TestClient(app)
    app.dependency_overrides.clear()
