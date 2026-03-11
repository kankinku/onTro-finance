"""Tests for the OpenAI-compatible LLM adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.llm.llm_client import LLMRequest
from src.llm.openai_compatible_adapter import OpenAICompatibleLLMClient
from src.llm.provider_auth import AuthType, ProviderAuthConfig, ProviderKind


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self):
        self.calls: list[Dict[str, Any]] = []

    def post(self, url: str, json: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers or {}})
        return _FakeResponse(
            {
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }
        )

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        return _FakeResponse({"data": [{"id": "gpt-4o-mini"}]})

    def close(self) -> None:
        return None


def _config() -> ProviderAuthConfig:
    return ProviderAuthConfig(
        provider=ProviderKind.OPENAI_GPT_SDK,
        auth_type=AuthType.API_KEY,
        base_url="https://api.openai.com/v1",
        healthcheck_path="/models",
        api_key_env="OPENAI_API_KEY",
        timeout_seconds=30.0,
    )


def test_generate_uses_chat_completions_and_bearer_auth():
    client = OpenAICompatibleLLMClient(auth_config=_config(), model="gpt-4o-mini", env={"OPENAI_API_KEY": "sk-test"})
    fake_http = _FakeClient()
    client._client = fake_http

    response = client.generate(
        LLMRequest(prompt="Summarize risk", system_prompt="You are a finance analyst", max_tokens=300)
    )

    assert response.content == '{"answer":"ok"}'
    assert response.input_tokens == 12
    assert response.output_tokens == 5
    assert fake_http.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert fake_http.calls[0]["headers"]["Authorization"] == "Bearer sk-test"
    assert fake_http.calls[0]["json"]["messages"][0]["role"] == "system"


def test_health_check_uses_models_endpoint_with_same_auth():
    client = OpenAICompatibleLLMClient(auth_config=_config(), model="gpt-4o-mini", env={"OPENAI_API_KEY": "sk-test"})
    fake_http = _FakeClient()
    client._client = fake_http

    assert client.health_check() is True
    assert fake_http.calls[0]["method"] == "GET"
    assert fake_http.calls[0]["url"] == "https://api.openai.com/v1/models"
    assert fake_http.calls[0]["headers"]["Authorization"] == "Bearer sk-test"
