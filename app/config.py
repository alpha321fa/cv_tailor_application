from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"

    max_upload_bytes: int = 5 * 1024 * 1024
    max_job_description_chars: int = 15_000

    @property
    def demo_mode(self) -> bool:
        # No key means we can't call a real LLM, so fall back to canned output.
        return not self.openrouter_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
