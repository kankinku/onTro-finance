"""CLI help and output tests for council inspection."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.council import cli
from src.council.member_registry import CouncilMemberDefinition, CouncilMemberRegistry
from src.council.models import CouncilRole
from src.llm.provider_auth import AuthType, ProviderAuthConfig, ProviderConnectionResult, ProviderKind


class _FakeService:
    def __init__(self):
        self.member_registry = CouncilMemberRegistry()
        self.member_registry.register(
            CouncilMemberDefinition(
                member_id="proposer-openai",
                role=CouncilRole.PROPOSER,
                provider=ProviderKind.OPENAI_GPT_SDK,
                model_name="gpt-4.1",
                auth=ProviderAuthConfig(
                    provider=ProviderKind.OPENAI_GPT_SDK,
                    auth_type=AuthType.API_KEY,
                    base_url="https://api.openai.com/v1",
                    api_key_env="OPENAI_API_KEY",
                ),
            )
        )
        self.member_registry.register(
            CouncilMemberDefinition(
                member_id="challenger-copilot",
                role=CouncilRole.CHALLENGER,
                provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
                auth=ProviderAuthConfig(
                    provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
                    auth_type=AuthType.OAUTH_APP,
                    base_url="https://copilot.example.internal",
                    access_token_env="TOKEN",
                    client_id_env="CLIENT_ID",
                    client_secret_env="CLIENT_SECRET",
                ),
            )
        )

    def refresh_member_availability(self, env=None):
        results = {
            "proposer-openai": ProviderConnectionResult(
                provider=ProviderKind.OPENAI_GPT_SDK,
                success=True,
                message="ok",
                checked_url="https://api.openai.com/v1/models",
                available_models=["gpt-4.1", "gpt-4o-mini"],
            ),
            "challenger-copilot": ProviderConnectionResult(
                provider=ProviderKind.GITHUB_COPILOT_OAUTH_APP,
                success=True,
                message="ok",
                checked_url="https://copilot.example.internal/models",
                available_models=["gpt-5", "claude-3.7-sonnet"],
            ),
        }
        self.member_registry.assign_models(results, enabled_only=True)
        return results


def test_help_mentions_model_assignment_rules():
    parser = cli.build_parser()
    help_text = parser.format_help()

    assert "model_name" in help_text
    assert "auto-assigned" in help_text
    assert "python -m src.council.cli models" in help_text


def test_members_command_prints_configured_members(capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: _FakeService())

    exit_code = cli.main(["members"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "proposer-openai" in output
    assert "challenger-copilot" in output
    assert "gpt-4.1" in output


def test_models_command_prints_effective_model_assignment_as_json(capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: _FakeService())

    exit_code = cli.main(["models", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert payload[0]["effective_model"] == "gpt-4.1"
    assert payload[1]["effective_model"] == "gpt-5"
