"""Inference-capable provider adapters for council automation."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

from src.llm.provider_auth import ProviderAuthConfig, ProviderAuthManager, ProviderKind


@dataclass
class ProviderInferenceRequest:
    model_name: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2


@dataclass
class ProviderInferenceResponse:
    content: str
    raw_response: Optional[Dict[str, Any]] = None


class InferenceTransport(ABC):
    @abstractmethod
    def post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        ...


class HttpxInferenceTransport(InferenceTransport):
    def post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for provider inference")

        response = httpx.post(url, json=payload, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()


class ProviderInferenceManager:
    """Small adapter layer on top of ProviderAuthConfig for live council prompts.

    Non-Ollama providers are expected to expose an OpenAI-compatible
    ``/chat/completions`` interface.
    """

    def __init__(self, auth_manager: Optional[ProviderAuthManager] = None):
        self.auth_manager = auth_manager or ProviderAuthManager()

    def infer(
        self,
        config: ProviderAuthConfig,
        request: ProviderInferenceRequest,
        transport: Optional[InferenceTransport] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> ProviderInferenceResponse:
        env_map = env or {}
        missing_env = self.auth_manager.missing_env_vars(config, env_map)
        if missing_env:
            raise RuntimeError(f"Missing credentials: {', '.join(missing_env)}")

        transport = transport or HttpxInferenceTransport()
        headers = self.auth_manager.build_headers(config, env_map)

        if config.provider == ProviderKind.OLLAMA:
            payload = {
                "model": request.model_name,
                "prompt": request.user_prompt,
                "system": request.system_prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": request.temperature,
                },
            }
            url = f"{config.base_url.rstrip('/')}/api/generate"
            raw = transport.post_json(url=url, payload=payload, headers=headers, timeout_seconds=config.timeout_seconds)
            return ProviderInferenceResponse(content=raw.get("response", ""), raw_response=raw)

        # Current scope intentionally treats non-Ollama providers as OpenAI-compatible.
        payload = {
            "model": request.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
        }
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        raw = transport.post_json(url=url, payload=payload, headers=headers, timeout_seconds=config.timeout_seconds)
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Provider '{config.provider.value}' must return an OpenAI-compatible "
                "/chat/completions response with choices[0].message.content"
            ) from exc
        return ProviderInferenceResponse(content=content, raw_response=raw)

    @staticmethod
    def parse_json_content(response: ProviderInferenceResponse) -> Dict[str, Any]:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())
