"""Provider inference contract tests."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.llm.provider_auth import AuthType, ProviderAuthConfig, ProviderKind
from src.llm.provider_inference import (
    InferenceTransport,
    ProviderInferenceManager,
    ProviderInferenceRequest,
)


class FakeInferenceTransport(InferenceTransport):
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, payload, headers=None, timeout_seconds=10.0):
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def test_ollama_inference_uses_generate_endpoint():
    manager = ProviderInferenceManager()
    transport = FakeInferenceTransport({"response": json.dumps({"decision": "APPROVE"})})
    config = ProviderAuthConfig(
        provider=ProviderKind.OLLAMA,
        auth_type=AuthType.NONE,
        base_url="http://localhost:11434",
    )

    response = manager.infer(
        config=config,
        request=ProviderInferenceRequest(
            model_name="llama3.2",
            system_prompt="system",
            user_prompt="user",
        ),
        transport=transport,
        env={},
    )

    assert response.content == json.dumps({"decision": "APPROVE"})
    assert transport.calls[0]["url"].endswith("/api/generate")


def test_non_ollama_inference_uses_openai_compatible_chat_completions():
    manager = ProviderInferenceManager()
    transport = FakeInferenceTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"decision": "APPROVE", "confidence": 0.8}),
                    }
                }
            ]
        }
    )
    config = ProviderAuthConfig(
        provider=ProviderKind.OPENAI_GPT_SDK,
        auth_type=AuthType.API_KEY,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    )

    response = manager.infer(
        config=config,
        request=ProviderInferenceRequest(
            model_name="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
        ),
        transport=transport,
        env={"OPENAI_API_KEY": "sk-test"},
    )

    assert json.loads(response.content)["decision"] == "APPROVE"
    assert transport.calls[0]["url"].endswith("/chat/completions")
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_non_ollama_inference_fails_with_explicit_contract_error():
    manager = ProviderInferenceManager()
    transport = FakeInferenceTransport({"result": "not-openai-compatible"})
    config = ProviderAuthConfig(
        provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
        auth_type=AuthType.OAUTH_APP,
        base_url="https://copilot.example.internal",
        access_token_env="TOKEN",
        client_id_env="CLIENT_ID",
        client_secret_env="CLIENT_SECRET",
    )

    with pytest.raises(RuntimeError, match="OpenAI-compatible"):
        manager.infer(
            config=config,
            request=ProviderInferenceRequest(
                model_name="copilot-gpt",
                system_prompt="system",
                user_prompt="user",
            ),
            transport=transport,
            env={
                "TOKEN": "ghu-test",
                "CLIENT_ID": "client-id",
                "CLIENT_SECRET": "client-secret",
            },
        )
