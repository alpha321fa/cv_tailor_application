from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

# Below this many characters we assume the PDF is a scanned image with no
# text layer. A real CV has far more text than this.
MIN_TEXT_CHARS = 100


class PDFExtractionError(Exception):
    """Raised when a PDF can't be turned into usable text. The message is shown to the user."""


def extract_text(pdf_bytes: bytes) -> str:
    # Note: we don't check reader.is_encrypted up front. Many exported PDFs are
    # "encrypted" only to restrict editing and open with an empty password,
    # which pypdf tries automatically. Only a real open-password fails, and
    # that surfaces as FileNotDecryptedError when the pages are read.
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except FileNotDecryptedError as exc:
        raise PDFExtractionError("This PDF is password-protected. Please upload an unlocked copy.") from exc
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        # Malformed PDFs can fail deep inside pypdf with assorted error types.
        raise PDFExtractionError("This file couldn't be read as a PDF.") from exc

    text = "\n".join(pages).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise PDFExtractionError(
            "Couldn't find enough text in this PDF. It may be a scanned image - "
            "please upload a PDF exported from Word, Google Docs or similar."
        )
    return text
