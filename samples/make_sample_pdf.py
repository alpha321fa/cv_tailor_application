"""Regenerate samples/sample_cv.pdf from samples/sample_cv.json.

Run from the repo root:  python -m samples.make_sample_pdf
"""

from pathlib import Path

from app.models import CVData
from app.services.render import render_cv_pdf

HERE = Path(__file__).resolve().parent


def main() -> None:
    cv = CVData.model_validate_json((HERE / "sample_cv.json").read_text(encoding="utf-8"))
    out = HERE / "sample_cv.pdf"
    out.write_bytes(render_cv_pdf(cv))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
