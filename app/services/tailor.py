import json
from pathlib import Path

from pydantic import ValidationError

from app.models import CVData
from app.services.llm import LLMClient

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "tailor_system.md"

# The schema is generated from the Pydantic model, so the prompt can never drift
# out of sync with what we validate against. str.replace rather than .format()
# because the prompt and the schema both contain literal braces.
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").replace(
    "{schema}", json.dumps(CVData.model_json_schema(), indent=1)
)


class TailoringError(Exception):
    """Raised when the LLM's reply can't be turned into a CV. The message is shown to the user."""


def build_user_message(cv_text: str, job_description: str) -> str:
    return f"<cv>\n{cv_text}\n</cv>\n\n<job_description>\n{job_description}\n</job_description>"


def parse_cv_json(raw: str) -> CVData:
    """Parse the model's reply into CVData, tolerating common formatting slips.

    Even in JSON mode some models wrap the JSON in ```json fences or add a
    sentence before/after it. Cutting to the outermost {...} handles both.
    Raises ValueError (incl. pydantic's ValidationError) if it still isn't valid.
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        raise ValueError("No JSON object found in the model's reply.")
    return CVData.model_validate_json(raw[start : end + 1])


def tailor_cv(llm: LLMClient, cv_text: str, job_description: str) -> CVData:
    raw = llm.complete(SYSTEM_PROMPT, build_user_message(cv_text, job_description))
    try:
        return parse_cv_json(raw)
    except (ValueError, ValidationError) as exc:
        raise TailoringError(
            "The AI returned its answer in an unexpected format. Please try again - "
            "free models are sometimes inconsistent."
        ) from exc
