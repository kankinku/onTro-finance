"""
Centralized application settings.
"""
from functools import lru_cache
import os
from pathlib import Path
import sys

from pydantic import BaseModel, ConfigDict, Field
import yaml


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOADED = False


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def _iter_env_paths() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")

    candidates.append(Path.cwd() / ".env")
    candidates.append(_PROJECT_ROOT / ".env")

    ordered: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    return ordered


def load_project_env(force: bool = False) -> Path | None:
    global _ENV_LOADED

    if _ENV_LOADED and not force:
        for env_path in _iter_env_paths():
            if env_path.exists():
                return env_path
        return None

    loaded_path: Path | None = None
    for env_path in _iter_env_paths():
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, _parse_env_value(raw_value))

        loaded_path = env_path
        break

    _ENV_LOADED = True
    return loaded_path


load_project_env()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


class OllamaSettings(BaseModel):
    base_url: str = Field(default="http://localhost:11434")
    model_name: str = Field(default="llama3.2:latest")
    timeout: int = Field(default=120)
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=4096)


class ExtractionSettings(BaseModel):
    min_fragment_length: int = Field(default=10)
    max_fragment_length: int = Field(default=500)
    ner_confidence_threshold: float = Field(default=0.5)
    fuzzy_match_threshold: float = Field(default=0.8)
    relation_confidence_threshold: float = Field(default=0.5)


class StoreSettings(BaseModel):
    graph_db_path: str = Field(default="data/graph.db")
    document_db_path: str = Field(default="data/documents.db")
    vector_db_path: str = Field(default="data/vectors")
    domain_data_path: Path = Field(default=Path("data/domain"))
    raw_data_path: Path = Field(default=Path("data/raw"))
    personal_data_path: Path = Field(default=Path("data/personal"))
    learning_data_path: Path = Field(default=Path("data/learning"))


class RuntimeSettings(BaseModel):
    load_sample_data_on_startup: bool = Field(
        default_factory=lambda: _env_bool("ONTRO_LOAD_SAMPLE_DATA", False)
    )


class CouncilRuntimeSettings(BaseModel):
    auto_process_enabled: bool = Field(default_factory=lambda: _env_bool("ONTRO_COUNCIL_AUTO_ENABLED", True))
    poll_interval_seconds: float = Field(default=float(os.getenv("ONTRO_COUNCIL_POLL_SECONDS", "5")))


class CallbackSettings(BaseModel):
    enabled: bool = Field(default_factory=lambda: _env_bool("ONTRO_ENABLE_CALLBACKS", False))
    allowed_hosts: list[str] = Field(default_factory=lambda: _env_list("ONTRO_CALLBACK_ALLOWED_HOSTS"))
    allowed_schemes: list[str] = Field(
        default_factory=lambda: _env_list("ONTRO_CALLBACK_ALLOWED_SCHEMES", "https")
    )


class Settings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path = Field(default_factory=lambda: _PROJECT_ROOT)

    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)
    store: StoreSettings = Field(default_factory=StoreSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    council_runtime: CouncilRuntimeSettings = Field(default_factory=CouncilRuntimeSettings)
    callbacks: CallbackSettings = Field(default_factory=CallbackSettings)

    entity_types_path: str = Field(default="config/entity_types.yaml")
    relation_types_path: str = Field(default="config/relation_types.yaml")
    alias_dictionary_path: str = Field(default="config/alias_dictionary.yaml")
    validation_schema_path: str = Field(default="config/validation_schema.yaml")
    static_domain_path: str = Field(default="config/static_domain.yaml")
    council_path: str = Field(default="config/council.yaml")
    council_members_path: str = Field(default="config/council_members.yaml")

    def get_config_path(self, config_name: str) -> Path:
        config_map = {
            "entity_types": self.entity_types_path,
            "relation_types": self.relation_types_path,
            "alias_dictionary": self.alias_dictionary_path,
            "validation_schema": self.validation_schema_path,
            "static_domain": self.static_domain_path,
            "council": self.council_path,
            "council_members": self.council_members_path,
        }
        return self.project_root / config_map.get(config_name, config_name)

    def load_yaml_config(self, config_name: str) -> dict:
        config_path = self.get_config_path(config_name)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def normalize_paths(self) -> "Settings":
        if not Path(self.store.graph_db_path).is_absolute():
            self.store.graph_db_path = str(self.project_root / self.store.graph_db_path)
        if not Path(self.store.document_db_path).is_absolute():
            self.store.document_db_path = str(self.project_root / self.store.document_db_path)
        if not Path(self.store.vector_db_path).is_absolute():
            self.store.vector_db_path = str(self.project_root / self.store.vector_db_path)

        if not self.store.domain_data_path.is_absolute():
            self.store.domain_data_path = self.project_root / self.store.domain_data_path
        if not self.store.raw_data_path.is_absolute():
            self.store.raw_data_path = self.project_root / self.store.raw_data_path
        if not self.store.personal_data_path.is_absolute():
            self.store.personal_data_path = self.project_root / self.store.personal_data_path
        if not self.store.learning_data_path.is_absolute():
            self.store.learning_data_path = self.project_root / self.store.learning_data_path

        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings().normalize_paths()
