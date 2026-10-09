from app.models import CVData, Education, Experience
from app.services.pdf_extract import extract_text
from app.services.render import render_cv_html, render_cv_pdf


def test_renders_a_pdf_that_round_trips(demo_json):
    cv = CVData.model_validate_json(demo_json)
    pdf = render_cv_pdf(cv)
    assert pdf.startswith(b"%PDF-")
    text = extract_text(pdf)
    assert "Alex Morgan" in text
    assert "Northbridge Library Services" in text


def test_html_in_cv_content_is_escaped():
    html = render_cv_html(CVData(name="<script>alert(1)</script>", summary="5 < 6 & 7 > 3"))
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html
    assert "5 &lt; 6 &amp; 7 &gt; 3" in html


def test_missing_company_and_institution_leave_no_stray_separator():
    cv = CVData(
        name="A",
        experience=[Experience(title="Freelance Web Developer")],
        education=[Education(degree="Self-taught")],
    )
    html = render_cv_html(cv)
    assert "<b>Freelance Web Developer</b></td>" in html
    assert "<b>Self-taught</b></td>" in html


def test_non_latin_characters_render():
    # Helvetica can't draw these - the bundled DejaVu font can. Check they survive into the PDF text.
    pdf = render_cv_pdf(CVData(name="Łukasz Wójcik", summary="Built APIs → shipped ✓ " + "padding " * 20))
    text = extract_text(pdf)
    assert "Łukasz Wójcik" in text
    assert "→" in text
