"""LLM clients.

Everything else in the app depends only on the LLMClient protocol, so the real
OpenRouter client can be swapped for FakeLLM in tests and in demo mode.
"""

from pathlib import Path
from typing import Protocol

import openai
from openai import OpenAI

from app.config import Settings

DEMO_RESPONSE_PATH = Path(__file__).resolve().parent.parent / "demo" / "demo_tailored_cv.json"


class LLMError(Exception):
    """Raised when the LLM call fails. The message is shown to the user."""


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Send a system + user message and return the model's text reply."""
        ...


class OpenRouterClient:
    def __init__(
        self, api_key: str, model: str, base_url: str, timeout: float, fallback_models: list[str] | None = None
    ) -> None:
        # OpenRouter speaks the OpenAI API, so the official SDK works with a different base_url.
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)
        self._model = model
        self._fallback_models = fallback_models or []
        self.last_model_used: str | None = None  # which model actually answered (may be a fallback)

    def complete(self, system: str, user: str) -> str:
        extra_body = {}
        if self._fallback_models:
            # OpenRouter-specific: if a model errors (incl. rate limits), try the next one in order.
            extra_body["models"] = [self._model, *self._fallback_models]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # JSON mode. Providers that don't support it ignore it rather than
                # erroring, so the parser still has to cope with stray text.
                response_format={"type": "json_object"},
                temperature=0.3,  # low: we want faithful rewording, not creativity
                extra_body=extra_body,
            )
        except openai.RateLimitError as exc:
            # Free models share capacity across all OpenRouter users, so a 429 can
            # mean "busy right now" as well as "you've used your daily quota".
            raise LLMError(
                "The free AI models are busy or rate-limited right now. Wait a minute and try again. "
                "(Free models are shared between all users and also have a daily request limit.)"
            ) from exc
        except openai.AuthenticationError as exc:
            raise LLMError("The OpenRouter API key was rejected. Check OPENROUTER_API_KEY in your .env file.") from exc
        except openai.NotFoundError as exc:
            raise LLMError(
                f"The model '{self._model}' wasn't found. Free models change over time - "
                "set LLM_MODEL in .env to one listed at openrouter.ai/models."
            ) from exc
        except openai.APITimeoutError as exc:
            raise LLMError("The AI model took too long to respond. Please try again.") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Couldn't reach OpenRouter. Check your internet connection.") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"The AI service returned an error (HTTP {exc.status_code}). Please try again.") from exc

        self.last_model_used = response.model
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMError("The AI model returned an empty response. Please try again.")
        return content


class FakeLLM:
    """Returns canned responses in order, and records the calls it receives.

    Used for demo mode (no API key) and in tests, so neither needs the network.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        # Repeat the last response once the list runs out (demo mode has just one).
        return self._responses[min(len(self.calls), len(self._responses)) - 1]


def build_llm(settings: Settings) -> LLMClient:
    if settings.demo_mode:
        return FakeLLM([DEMO_RESPONSE_PATH.read_text(encoding="utf-8")])
    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        fallback_models=settings.fallback_models,
    )
