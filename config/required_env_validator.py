"""Runtime environment validation for production-safe startup."""

from __future__ import annotations

import os
from typing import Any


def validate_required_runtime_env(config: dict[str, Any] | None = None) -> None:
    config = config or {}
    storage_config = config.get("storage", {}) if isinstance(config, dict) else {}
    backend = os.environ.get("ONTRO_STORAGE_BACKEND") or storage_config.get("backend") or "neo4j"

    missing: list[str] = []
    if backend == "neo4j":
        if not _env_or_config("ONTRO_NEO4J_URI", storage_config.get("neo4j", {}).get("uri")):
            missing.append("ONTRO_NEO4J_URI")
        if not (
            _env_or_config("ONTRO_NEO4J_USER", storage_config.get("neo4j", {}).get("user"))
            or os.environ.get("ONTRO_NEO4J_USERNAME")
        ):
            missing.append("ONTRO_NEO4J_USER")
        if not _env_or_config(
            "ONTRO_NEO4J_PASSWORD", storage_config.get("neo4j", {}).get("password")
        ):
            missing.append("ONTRO_NEO4J_PASSWORD")
    if missing:
        raise ValueError(
            "Missing required runtime environment variables for "
            f"backend '{backend}': {', '.join(missing)}"
        )


def summarize_runtime_env(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    storage_config = config.get("storage", {}) if isinstance(config, dict) else {}
    backend = os.environ.get("ONTRO_STORAGE_BACKEND") or storage_config.get("backend") or "neo4j"
    loaded_env_names = sorted(
        name
        for name in (
            "ONTRO_STORAGE_BACKEND",
            "ONTRO_NEO4J_URI",
            "ONTRO_NEO4J_USER",
            "ONTRO_NEO4J_USERNAME",
            "ONTRO_NEO4J_DATABASE",
            "ONTRO_COUNCIL_AUTO_ENABLED",
            "ONTRO_LOAD_SAMPLE_DATA",
            "ONTRO_ENABLE_CALLBACKS",
            "ONTRO_API_KEY",
            "ONTRO_RATE_LIMIT_PER_MINUTE",
            "ONTRO_AUDIT_LOG",
            "OPENAI_API_KEY",
        )
        if os.environ.get(name)
    )
    return {
        "storage_backend": backend,
        "council_auto_enabled": os.environ.get("ONTRO_COUNCIL_AUTO_ENABLED", "true"),
        "load_sample_data": os.environ.get("ONTRO_LOAD_SAMPLE_DATA", "false"),
        "callbacks_enabled": os.environ.get("ONTRO_ENABLE_CALLBACKS", "false"),
        "loaded_env_names": loaded_env_names,
    }


def _env_or_config(name: str, configured_value: Any) -> str:
    value = os.environ.get(name)
    if value:
        return value
    if configured_value is None:
        return ""
    return str(configured_value).strip()
