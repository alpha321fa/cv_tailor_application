from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    # Free models come and go - check https://openrouter.ai/models?max_price=0
    llm_model: str = "google/gemma-4-31b-it:free"
    # Comma-separated. OpenRouter tries these in order if the main model errors
    # (e.g. a free model's shared capacity is exhausted). Empty = no fallbacks.
    llm_fallback_models: str = "nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-26b-a4b-it:free"
    llm_timeout_seconds: float = 90
    llm_base_url: str = "https://openrouter.ai/api/v1"

    max_upload_bytes: int = 5 * 1024 * 1024
    max_job_description_chars: int = 15_000
    max_cv_chars: int = 30_000  # extracted text; a typical CV is 3-8k characters

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]

    @property
    def demo_mode(self) -> bool:
        # No key means we can't call a real LLM, so fall back to canned output.
        return not self.openrouter_api_key


@lru_cache  # read .env once; restart the server after editing it
def get_settings() -> Settings:
    return Settings()
