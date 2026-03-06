"""Provider auth and multi-member connection tests."""
import os
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.council.member_registry import CouncilMemberDefinition, CouncilMemberRegistry
from src.council.models import CouncilRole
from src.llm.provider_auth import (
    AuthType,
    ConnectionTransport,
    HttpxConnectionTransport,
    ProviderAuthConfig,
    ProviderAuthManager,
    ProviderConnectionResult,
    ProviderKind,
)


class FakeTransport(ConnectionTransport):
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.calls = []

    def request(self, method: str, url: str, headers=None, timeout_seconds: float = 10.0) -> ProviderConnectionResult:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "timeout_seconds": timeout_seconds,
            }
        )
        return ProviderConnectionResult(
            provider=ProviderKind.OPENAI_GPT_SDK,
            success=self.status_code < 400,
            status_code=self.status_code,
            message="ok" if self.status_code < 400 else "failed",
        )


class TestProviderAuthManager:
    def test_openai_gpt_sdk_auth_connection_success(self):
        manager = ProviderAuthManager()
        config = ProviderAuthConfig(
            provider=ProviderKind.OPENAI_GPT_SDK,
            auth_type=AuthType.API_KEY,
            base_url="https://api.openai.com/v1",
            healthcheck_path="/models",
            api_key_env="OPENAI_API_KEY",
        )
        transport = FakeTransport()

        result = manager.test_connection(
            config,
            transport=transport,
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.success is True
        assert result.checked_url == "https://api.openai.com/v1/models"
        assert transport.calls[0]["headers"]["Authorization"] == "Bearer sk-test"

    def test_openai_gpt_sdk_auth_missing_env_fails(self):
        manager = ProviderAuthManager()
        config = ProviderAuthConfig(
            provider=ProviderKind.OPENAI_GPT_SDK,
            auth_type=AuthType.API_KEY,
            base_url="https://api.openai.com/v1",
            healthcheck_path="/models",
            api_key_env="OPENAI_API_KEY",
        )
        transport = FakeTransport()

        result = manager.test_connection(config, transport=transport, env={})

        assert result.success is False
        assert result.error_type == "missing_credentials"
        assert result.missing_env == ["OPENAI_API_KEY"]
        assert transport.calls == []

    def test_github_copilot_oauth_app_connection_success(self):
        manager = ProviderAuthManager()
        config = ProviderAuthConfig(
            provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
            auth_type=AuthType.OAUTH_APP,
            base_url="https://copilot.example.internal",
            healthcheck_path="/models",
            access_token_env="GITHUB_COPILOT_ACCESS_TOKEN",
            client_id_env="GITHUB_COPILOT_CLIENT_ID",
            client_secret_env="GITHUB_COPILOT_CLIENT_SECRET",
        )
        transport = FakeTransport()

        result = manager.test_connection(
            config,
            transport=transport,
            env={
                "GITHUB_COPILOT_ACCESS_TOKEN": "ghu_test",
                "GITHUB_COPILOT_CLIENT_ID": "client-id",
                "GITHUB_COPILOT_CLIENT_SECRET": "client-secret",
            },
        )

        assert result.success is True
        assert result.checked_url == "https://copilot.example.internal/models"
        assert transport.calls[0]["headers"]["Authorization"] == "Bearer ghu_test"

    def test_github_copilot_oauth_app_missing_token_fails(self):
        manager = ProviderAuthManager()
        config = ProviderAuthConfig(
            provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
            auth_type=AuthType.OAUTH_APP,
            base_url="https://copilot.example.internal",
            healthcheck_path="/models",
            access_token_env="GITHUB_COPILOT_ACCESS_TOKEN",
            client_id_env="GITHUB_COPILOT_CLIENT_ID",
            client_secret_env="GITHUB_COPILOT_CLIENT_SECRET",
        )
        transport = FakeTransport()

        result = manager.test_connection(
            config,
            transport=transport,
            env={
                "GITHUB_COPILOT_CLIENT_ID": "client-id",
                "GITHUB_COPILOT_CLIENT_SECRET": "client-secret",
            },
        )

        assert result.success is False
        assert result.error_type == "missing_credentials"
        assert "GITHUB_COPILOT_ACCESS_TOKEN" in result.missing_env


class TestCouncilMemberRegistry:
    def test_registry_loads_members_from_config(self):
        registry = CouncilMemberRegistry()
        registry.load_from_config(
            {
                "members": [
                    {
                        "member_id": "proposer-openai",
                        "role": "proposer",
                        "provider": "openai_gpt_sdk",
                        "model_name": "gpt-4.1",
                        "auth": {
                            "auth_type": "api_key",
                            "base_url": "https://api.openai.com/v1",
                            "healthcheck_path": "/models",
                            "api_key_env": "OPENAI_API_KEY",
                        },
                    }
                ]
            }
        )

        member = registry.get("proposer-openai")
        assert member is not None
        assert member.provider == ProviderKind.OPENAI_GPT_SDK

    def test_registry_can_test_all_member_connections(self):
        registry = CouncilMemberRegistry()
        registry.register(
            CouncilMemberDefinition(
                member_id="proposer-openai",
                role=CouncilRole.PROPOSER,
                provider=ProviderKind.OPENAI_GPT_SDK,
                model_name="gpt-4.1",
                auth=ProviderAuthConfig(
                    provider=ProviderKind.OPENAI_GPT_SDK,
                    auth_type=AuthType.API_KEY,
                    base_url="https://api.openai.com/v1",
                    healthcheck_path="/models",
                    api_key_env="OPENAI_API_KEY",
                ),
            )
        )
        registry.register(
            CouncilMemberDefinition(
                member_id="challenger-copilot",
                role=CouncilRole.CHALLENGER,
                provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
                model_name="copilot-gpt",
                auth=ProviderAuthConfig(
                    provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
                    auth_type=AuthType.OAUTH_APP,
                    base_url="https://copilot.example.internal",
                    healthcheck_path="/models",
                    access_token_env="GITHUB_COPILOT_ACCESS_TOKEN",
                    client_id_env="GITHUB_COPILOT_CLIENT_ID",
                    client_secret_env="GITHUB_COPILOT_CLIENT_SECRET",
                ),
            )
        )
        transport = FakeTransport()

        results = registry.test_all_connections(
            transport=transport,
            env={
                "OPENAI_API_KEY": "sk-live",
                "GITHUB_COPILOT_ACCESS_TOKEN": "ghu-live",
                "GITHUB_COPILOT_CLIENT_ID": "client-id",
                "GITHUB_COPILOT_CLIENT_SECRET": "client-secret",
            },
        )

        assert set(results.keys()) == {"proposer-openai", "challenger-copilot"}
        assert all(result.success for result in results.values())
        assert len(transport.calls) == 2


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OPENAI_API_KEY")
def test_openai_live_connection_smoke():
    manager = ProviderAuthManager()
    config = ProviderAuthConfig(
        provider=ProviderKind.OPENAI_GPT_SDK,
        auth_type=AuthType.API_KEY,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        healthcheck_path=os.getenv("OPENAI_HEALTHCHECK_PATH", "/models"),
        api_key_env="OPENAI_API_KEY",
    )

    result = manager.test_connection(config, transport=HttpxConnectionTransport(), env=os.environ)
    assert result.success is True


@pytest.mark.skipif(
    not (
        os.getenv("GITHUB_COPILOT_ACCESS_TOKEN")
        and os.getenv("GITHUB_COPILOT_CLIENT_ID")
        and os.getenv("GITHUB_COPILOT_CLIENT_SECRET")
        and os.getenv("GITHUB_COPILOT_BASE_URL")
    ),
    reason="requires GitHub Copilot OAuth env vars",
)
def test_github_copilot_live_connection_smoke():
    manager = ProviderAuthManager()
    config = ProviderAuthConfig(
        provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
        auth_type=AuthType.OAUTH_APP,
        base_url=os.getenv("GITHUB_COPILOT_BASE_URL"),
        healthcheck_path=os.getenv("GITHUB_COPILOT_HEALTHCHECK_PATH", "/models"),
        access_token_env="GITHUB_COPILOT_ACCESS_TOKEN",
        client_id_env="GITHUB_COPILOT_CLIENT_ID",
        client_secret_env="GITHUB_COPILOT_CLIENT_SECRET",
    )

    result = manager.test_connection(config, transport=HttpxConnectionTransport(), env=os.environ)
    assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
