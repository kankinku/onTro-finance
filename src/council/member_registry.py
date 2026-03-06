"""Registry for multi-provider council members."""
from typing import Dict, List, Mapping, Optional

from pydantic import BaseModel, Field

from src.council.models import CouncilRole
from src.llm.provider_auth import (
    ConnectionTransport,
    ProviderAuthConfig,
    ProviderAuthManager,
    ProviderConnectionResult,
    ProviderKind,
)


class CouncilMemberDefinition(BaseModel):
    member_id: str
    role: CouncilRole
    provider: ProviderKind
    model_name: str
    auth: ProviderAuthConfig
    enabled: bool = True
    metadata: Dict[str, str] = Field(default_factory=dict)


class CouncilMemberRegistry:
    """Manage council members and validate provider connectivity."""

    def __init__(self, auth_manager: Optional[ProviderAuthManager] = None):
        self.auth_manager = auth_manager or ProviderAuthManager()
        self._members: Dict[str, CouncilMemberDefinition] = {}

    def register(self, member: CouncilMemberDefinition) -> None:
        self._members[member.member_id] = member

    def load_from_config(self, config: Dict) -> None:
        for item in config.get("members", []):
            provider = ProviderKind(item["provider"])
            auth_payload = dict(item.get("auth", {}))
            member = CouncilMemberDefinition(
                member_id=item["member_id"],
                role=CouncilRole(item["role"]),
                provider=provider,
                model_name=item["model_name"],
                enabled=item.get("enabled", True),
                metadata=item.get("metadata", {}),
                auth=ProviderAuthConfig(
                    provider=provider,
                    **auth_payload,
                ),
            )
            self.register(member)

    def get(self, member_id: str) -> Optional[CouncilMemberDefinition]:
        return self._members.get(member_id)

    def list_members(self, enabled_only: bool = True) -> List[CouncilMemberDefinition]:
        members = list(self._members.values())
        if enabled_only:
            members = [member for member in members if member.enabled]
        return members

    def test_member_connection(
        self,
        member_id: str,
        transport: ConnectionTransport,
        env: Optional[Mapping[str, str]] = None,
    ) -> ProviderConnectionResult:
        member = self._members[member_id]
        return self.auth_manager.test_connection(member.auth, transport=transport, env=env)

    def test_all_connections(
        self,
        transport: ConnectionTransport,
        env: Optional[Mapping[str, str]] = None,
        enabled_only: bool = True,
    ) -> Dict[str, ProviderConnectionResult]:
        results: Dict[str, ProviderConnectionResult] = {}
        for member in self.list_members(enabled_only=enabled_only):
            results[member.member_id] = self.test_member_connection(member.member_id, transport=transport, env=env)
        return results
