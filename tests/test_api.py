import html
import re

import pytest

from app.main import app, get_llm
from app.services.llm import FakeLLM, LLMError


def pdf_upload(data: bytes, filename: str = "cv.pdf") -> dict:
    return {"cv_file": (filename, data, "application/pdf")}


def test_index_shows_form_and_demo_banner(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-post="/tailor"' in response.text
    assert "Demo mode" in response.text


def test_static_files_are_served(client):
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_tailor_happy_path(client, fake_llm, sample_pdf, sample_job_description):
    response = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": sample_job_description})

    assert response.status_code == 200
    assert "Your tailored CV" in response.text
    assert "Download PDF" in response.text
    # The extracted CV text and the job description both reached the LLM.
    _, user_message = fake_llm.calls[0]
    assert "Northbridge Library Services" in user_message
    assert "Junior Python Developer" in user_message


@pytest.mark.parametrize(
    ("files", "job_description", "status", "message"),
    [
        ("sample", "   ", 400, "paste a job description"),
        ("sample", "x" * 15_001, 400, "too long"),
        (None, "A job", 400, "choose your CV"),
        (b"hello, I am a text file", "A job", 400, "isn't a PDF"),
        (b"%PDF-" + b"0" * (5 * 1024 * 1024), "A job", 413, "too large"),
        ("truncated", "A job", 422, "couldn't be read"),
    ],
    ids=["blank-job", "job-too-long", "no-file", "not-a-pdf", "too-large", "corrupt-pdf"],
)
def test_tailor_rejects_bad_input(client, sample_pdf, files, job_description, status, message):
    if files == "sample":
        files = pdf_upload(sample_pdf)
    elif files == "truncated":
        files = pdf_upload(sample_pdf[:300])
    elif files is not None:
        files = pdf_upload(files)

    response = client.post("/tailor", files=files, data={"job_description": job_description})
    assert response.status_code == status
    assert message in html.unescape(response.text)


def test_llm_failure_shows_message_with_502(client, sample_pdf):
    class FailingLLM:
        def complete(self, system, user):
            raise LLMError("The free AI models are busy.")

    app.dependency_overrides[get_llm] = lambda: FailingLLM()
    response = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": "A job"})
    assert response.status_code == 502
    assert "The free AI models are busy." in response.text


def test_bad_llm_json_shows_message_with_502(client, sample_pdf):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(["not json"])
    response = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": "A job"})
    assert response.status_code == 502
    assert "unexpected format" in response.text


def test_cv_content_is_escaped_in_preview(client, sample_pdf):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(['{"name": "<script>alert(1)</script>"}'])
    response = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": "A job"})
    assert "<script>alert(1)" not in response.text
    assert "&lt;script&gt;" in response.text


def test_download_round_trip(client, sample_pdf, sample_job_description):
    result = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": sample_job_description})
    # Pull the tailored CV JSON out of the hidden form field, as the browser would submit it.
    cv_json = html.unescape(re.search(r'name="cv_json" value="([^"]*)"', result.text).group(1))

    response = client.post("/download", data={"cv_json": cv_json})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="Alex_Morgan_CV.pdf"'
    assert response.content.startswith(b"%PDF-")


@pytest.mark.parametrize("cv_json", ["", "{broken", '{"summary": "no name"}'], ids=["empty", "broken", "invalid"])
def test_download_rejects_bad_data(client, cv_json):
    response = client.post("/download", data={"cv_json": cv_json})
    assert response.status_code == 400
    assert "missing or invalid" in response.text
    # /download is a normal form post, not htmx, so the error must be a full page with a way back.
    assert "<html" in response.text
    assert 'href="/"' in response.text


def test_cv_with_too_much_text_is_rejected(client, fake_llm, monkeypatch, sample_pdf):
    # Stand in for a PDF that extracts to a huge amount of text.
    monkeypatch.setattr("app.main.extract_text", lambda pdf_bytes: "word " * 10_000)
    response = client.post("/tailor", files=pdf_upload(sample_pdf), data={"job_description": "A job"})
    assert response.status_code == 422
    assert "unusually large amount of text" in response.text
    assert fake_llm.calls == []  # never sent to the LLM
