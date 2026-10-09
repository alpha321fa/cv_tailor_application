import pytest

from app.models import CVData
from app.services.pdf_extract import PDFExtractionError, extract_text
from app.services.render import render_cv_pdf
from tests.conftest import make_encrypted_pdf


def test_extracts_text_from_sample_cv(sample_pdf):
    text = extract_text(sample_pdf)
    assert "Alex Morgan" in text
    assert "Northbridge Library Services" in text
    assert "Sep 2023" in text


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_edit_restricted_pdf_is_accepted(sample_pdf, algorithm):
    # "Encrypted" with an empty user password: opens fine, only editing is restricted.
    restricted = make_encrypted_pdf(sample_pdf, user_password="", algorithm=algorithm)
    assert "Alex Morgan" in extract_text(restricted)


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_password_protected_pdf_is_rejected(sample_pdf, algorithm):
    locked = make_encrypted_pdf(sample_pdf, user_password="secret", algorithm=algorithm)
    with pytest.raises(PDFExtractionError, match="password-protected"):
        extract_text(locked)


@pytest.mark.parametrize(
    "data",
    [b"", b"not a pdf at all", b"%PDF-1.4 but nothing else"],
    ids=["empty", "garbage", "header-only"],
)
def test_unreadable_files_raise_friendly_error(data):
    with pytest.raises(PDFExtractionError, match="couldn't be read"):
        extract_text(data)


def test_truncated_pdf_raises_friendly_error(sample_pdf):
    with pytest.raises(PDFExtractionError):
        extract_text(sample_pdf[: len(sample_pdf) // 2])


def test_pdf_with_almost_no_text_is_treated_as_scanned():
    # A valid PDF whose only text is a short name - like a scanned image with no text layer.
    nearly_empty = render_cv_pdf(CVData(name="A"))
    with pytest.raises(PDFExtractionError, match="scanned"):
        extract_text(nearly_empty)
