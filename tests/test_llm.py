from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import Settings
from app.services.llm import FakeLLM, LLMError, OpenRouterClient, build_llm


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{"openrouter_api_key": "", **overrides})


def test_no_api_key_means_demo_mode():
    settings = make_settings()
    assert settings.demo_mode
    assert isinstance(build_llm(settings), FakeLLM)


def test_api_key_gives_real_client():
    settings = make_settings(openrouter_api_key="sk-test")
    assert not settings.demo_mode
    assert isinstance(build_llm(settings), OpenRouterClient)


def test_fallback_models_parsed_from_comma_separated_string():
    settings = make_settings(llm_fallback_models=" model-a:free , ,model-b:free ")
    assert settings.fallback_models == ["model-a:free", "model-b:free"]


def test_fake_llm_repeats_last_response():
    llm = FakeLLM(["first", "second"])
    assert [llm.complete("s", "u") for _ in range(3)] == ["first", "second", "second"]


# --- OpenRouterClient, with the OpenAI SDK call replaced so no network is used ---


def client_with_fake_create(monkeypatch, create) -> OpenRouterClient:
    client = OpenRouterClient("sk-test", "main-model", "https://example.invalid", timeout=5, fallback_models=["backup"])
    monkeypatch.setattr(client._client.chat.completions, "create", create)
    return client


def fake_completion(content, model="backup"):
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_sends_fallback_models_and_records_which_answered(monkeypatch):
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return fake_completion('{"name": "A"}', model="backup")

    client = client_with_fake_create(monkeypatch, create)
    assert client.complete("system", "user") == '{"name": "A"}'
    assert seen["model"] == "main-model"
    assert seen["extra_body"] == {"models": ["main-model", "backup"]}
    assert seen["response_format"] == {"type": "json_object"}
    assert client.last_model_used == "backup"


def api_error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.invalid"))
    return cls("error", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (api_error(openai.RateLimitError, 429), "busy or rate-limited"),
        (api_error(openai.AuthenticationError, 401), "API key was rejected"),
        (api_error(openai.NotFoundError, 404), "wasn't found"),
        (api_error(openai.InternalServerError, 500), "HTTP 500"),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://example.invalid")), "too long"),
    ],
    ids=["rate-limit", "auth", "not-found", "server-error", "timeout"],
)
def test_api_errors_become_friendly_messages(monkeypatch, error, message):
    def create(**kwargs):
        raise error

    client = client_with_fake_create(monkeypatch, create)
    with pytest.raises(LLMError, match=message):
        client.complete("system", "user")


def test_empty_reply_is_an_error(monkeypatch):
    client = client_with_fake_create(monkeypatch, lambda **kwargs: fake_completion(None))
    with pytest.raises(LLMError, match="empty response"):
        client.complete("system", "user")
