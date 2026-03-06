"""Provider authentication and connection testing for multi-model council members."""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Mapping, Optional

from pydantic import BaseModel, Field
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class ProviderKind(str, Enum):
    OLLAMA = "ollama"
    OPENAI_GPT_SDK = "openai_gpt_sdk"
    GITHUB_COPILOT_OAUTH_APP = "github_copilot_oauth_app"


class AuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH_APP = "oauth_app"


class ProviderAuthConfig(BaseModel):
    provider: ProviderKind
    auth_type: AuthType
    base_url: str
    healthcheck_path: str = "/health"
    api_key_env: Optional[str] = None
    access_token_env: Optional[str] = None
    client_id_env: Optional[str] = None
    client_secret_env: Optional[str] = None
    timeout_seconds: float = Field(default=10.0, gt=0.0)


class ProviderConnectionResult(BaseModel):
    provider: ProviderKind
    success: bool
    status_code: Optional[int] = None
    error_type: Optional[str] = None
    message: str = ""
    checked_url: Optional[str] = None
    missing_env: List[str] = Field(default_factory=list)


class ConnectionTransport(ABC):
    @abstractmethod
    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 10.0,
    ) -> ProviderConnectionResult:
        ...


class HttpxConnectionTransport(ConnectionTransport):
    """Default HTTP transport for live provider connectivity checks."""

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 10.0,
    ) -> ProviderConnectionResult:
        if httpx is None:
            return ProviderConnectionResult(
                provider=ProviderKind.OLLAMA,
                success=False,
                error_type="missing_dependency",
                message="httpx is required for live connection tests",
                checked_url=url,
            )

        try:
            response = httpx.request(method=method, url=url, headers=headers, timeout=timeout_seconds)
            return ProviderConnectionResult(
                provider=ProviderKind.OLLAMA,
                success=response.status_code < 400,
                status_code=response.status_code,
                message="ok" if response.status_code < 400 else response.text[:200],
                checked_url=url,
            )
        except Exception as exc:  # pragma: no cover - exercised only in live environments
            return ProviderConnectionResult(
                provider=ProviderKind.OLLAMA,
                success=False,
                error_type="transport_error",
                message=str(exc),
                checked_url=url,
            )


class ProviderAuthManager:
    """Validate auth config, resolve credentials, and test provider connectivity."""

    def validate_config(self, config: ProviderAuthConfig) -> List[str]:
        errors: List[str] = []

        if config.auth_type == AuthType.API_KEY and not config.api_key_env:
            errors.append("api_key_env_required")

        if config.auth_type == AuthType.OAUTH_APP:
            if not config.access_token_env:
                errors.append("access_token_env_required")
            if not config.client_id_env:
                errors.append("client_id_env_required")
            if not config.client_secret_env:
                errors.append("client_secret_env_required")

        return errors

    def required_env_vars(self, config: ProviderAuthConfig) -> List[str]:
        env_vars: List[str] = []

        if config.auth_type == AuthType.API_KEY and config.api_key_env:
            env_vars.append(config.api_key_env)

        if config.auth_type == AuthType.OAUTH_APP:
            for key in [config.access_token_env, config.client_id_env, config.client_secret_env]:
                if key:
                    env_vars.append(key)

        return env_vars

    def missing_env_vars(
        self,
        config: ProviderAuthConfig,
        env: Optional[Mapping[str, str]] = None,
    ) -> List[str]:
        env_map = env or {}
        return [key for key in self.required_env_vars(config) if not env_map.get(key)]

    def build_headers(
        self,
        config: ProviderAuthConfig,
        env: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, str]:
        env_map = env or {}
        headers: Dict[str, str] = {}

        if config.auth_type == AuthType.API_KEY and config.api_key_env:
            headers["Authorization"] = f"Bearer {env_map[config.api_key_env]}"

        if config.auth_type == AuthType.OAUTH_APP and config.access_token_env:
            headers["Authorization"] = f"Bearer {env_map[config.access_token_env]}"

        return headers

    def test_connection(
        self,
        config: ProviderAuthConfig,
        transport: ConnectionTransport,
        env: Optional[Mapping[str, str]] = None,
    ) -> ProviderConnectionResult:
        config_errors = self.validate_config(config)
        if config_errors:
            return ProviderConnectionResult(
                provider=config.provider,
                success=False,
                error_type="invalid_config",
                message=",".join(config_errors),
            )

        env_map = env or {}
        missing_env = self.missing_env_vars(config, env_map)
        if missing_env:
            return ProviderConnectionResult(
                provider=config.provider,
                success=False,
                error_type="missing_credentials",
                message="missing required environment variables",
                missing_env=missing_env,
            )

        base_url = config.base_url.rstrip("/")
        health_path = config.healthcheck_path if config.healthcheck_path.startswith("/") else f"/{config.healthcheck_path}"
        url = f"{base_url}{health_path}"

        result = transport.request(
            method="GET",
            url=url,
            headers=self.build_headers(config, env_map),
            timeout_seconds=config.timeout_seconds,
        )
        result.provider = config.provider
        result.checked_url = url
        return result
