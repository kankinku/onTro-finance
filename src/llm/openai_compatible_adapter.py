"""OpenAI-compatible LLM client backed by provider auth config."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Mapping, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

from src.llm.llm_client import LLMClient, LLMRequest, LLMResponse
from src.llm.provider_auth import ProviderAuthConfig, ProviderAuthManager

logger = logging.getLogger(__name__)


class OpenAICompatibleLLMClient(LLMClient):
    """LLMClient for OpenAI-compatible chat/completions providers."""

    def __init__(
        self,
        *,
        auth_config: ProviderAuthConfig,
        model: str,
        env: Optional[Mapping[str, str]] = None,
        api_key: Optional[str] = None,
    ):
        self.auth_config = auth_config
        self.model = model
        self._env = env
        self._api_key = api_key.strip() if api_key else None
        self._auth_manager = ProviderAuthManager()
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            if httpx is None:
                raise ImportError(
                    "httpx is required for OpenAICompatibleLLMClient (install httpx or disable LLM)"
                )
            self._client = httpx.Client(timeout=self.auth_config.timeout_seconds)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        response = self.client.post(
            self._chat_completions_url(),
            json=self._build_payload(request),
            headers=self._build_headers(),
        )
        response.raise_for_status()
        raw = response.json()
        latency_ms = (time.time() - start_time) * 1000
        content = self._extract_content(raw)
        usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
        return LLMResponse(
            content=content,
            model=str(raw.get("model") or self.model),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            raw_response=raw,
        )

    def generate_json(self, request: Any = None, **kwargs) -> Dict[str, Any]:
        if isinstance(request, LLMRequest):
            req_obj = request
        else:
            prompt = kwargs.pop("prompt", None)
            system_prompt = kwargs.pop("system_prompt", None)
            if prompt is None:
                raise ValueError("prompt is required for generate_json")
            req_obj = LLMRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=True,
                **kwargs,
            )
        req_obj.json_mode = True
        response = self.generate(req_obj)
        return self._parse_json_content(response.content)

    def health_check(self) -> bool:
        try:
            result = self._auth_manager.test_connection(
                self.auth_config,
                transport=_HttpxProviderHealthTransport(self.client),
                env=self._resolved_env(),
            )
            return result.success
        except Exception as exc:  # pragma: no cover - only happens in live environments
            logger.warning("OpenAI-compatible health check failed: %s", exc)
            return False

    def get_model_name(self) -> str:
        return self.model

    def _resolved_env(self) -> Dict[str, str]:
        env_map = dict(self._env or {})
        if self._api_key and self.auth_config.api_key_env and not env_map.get(self.auth_config.api_key_env):
            env_map[self.auth_config.api_key_env] = self._api_key
        return env_map

    def _build_headers(self) -> Dict[str, str]:
        headers = self._auth_manager.build_headers(self.auth_config, self._resolved_env())
        headers["Content-Type"] = "application/json"
        return headers

    def _build_payload(self, request: LLMRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _chat_completions_url(self) -> str:
        return f"{self.auth_config.base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _extract_content(raw: Dict[str, Any]) -> str:
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "OpenAI-compatible provider must return choices[0].message.content"
            ) from exc
        return str(content or "")

    @staticmethod
    def _parse_json_content(content: str) -> Dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```json"):
            normalized = normalized[7:]
        if normalized.startswith("```"):
            normalized = normalized[3:]
        if normalized.endswith("```"):
            normalized = normalized[:-3]
        return json.loads(normalized.strip())


class _HttpxProviderHealthTransport:
    def __init__(self, client: httpx.Client):
        self.client = client

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 10.0,
    ):
        from src.llm.provider_auth import ProviderConnectionResult, ProviderKind

        response = self.client.request(method=method, url=url, headers=headers, timeout=timeout_seconds)
        response_json: Optional[Dict[str, Any]] = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                response_json = payload
        except Exception:
            response_json = None
        return ProviderConnectionResult(
            provider=ProviderKind.OPENAI_GPT_SDK,
            success=response.status_code < 400,
            status_code=response.status_code,
            message="ok" if response.status_code < 400 else response.text[:200],
            checked_url=url,
            response_json=response_json,
        )
