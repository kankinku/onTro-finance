"""
설정 관리 모듈
원칙 2: 선택값 및 설정값 분리 (Configuration Separation)
모든 상수, 파라미터는 코드에 직접 쓰지 않고 여기서 관리
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
from pydantic import BaseModel, Field
import yaml


class OllamaSettings(BaseModel):
    """Ollama LLM 설정"""
    base_url: str = Field(default="http://localhost:11434")
    model_name: str = Field(default="llama3.2:latest")
    timeout: int = Field(default=120)
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=4096)


class ExtractionSettings(BaseModel):
    """Extraction Sector 설정"""
    # Fragment Extraction
    min_fragment_length: int = Field(default=10, description="최소 fragment 길이")
    max_fragment_length: int = Field(default=500, description="최대 fragment 길이")
    
    # NER (Student1)
    ner_confidence_threshold: float = Field(default=0.5, description="NER 최소 신뢰도 (recall 우선이므로 낮게)")
    
    # Entity Resolution
    fuzzy_match_threshold: float = Field(default=0.8, description="Fuzzy match 임계값")
    
    # Relation Extraction (Student2)
    relation_confidence_threshold: float = Field(default=0.5, description="관계 추출 최소 신뢰도")


class StoreSettings(BaseModel):
    """저장소 설정"""
    graph_db_path: str = Field(default="data/graph.db")
    document_db_path: str = Field(default="data/documents.db")
    vector_db_path: str = Field(default="data/vectors")
    
    # Data Separation Paths
    domain_data_path: Path = Field(default=Path("data/domain"))
    raw_data_path: Path = Field(default=Path("data/raw"))
    personal_data_path: Path = Field(default=Path("data/personal"))


class Settings(BaseModel):
    """전체 설정 (One Source of Truth)"""
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)
    store: StoreSettings = Field(default_factory=StoreSettings)
    
    # Config 파일 경로
    entity_types_path: str = Field(default="config/entity_types.yaml")
    relation_types_path: str = Field(default="config/relation_types.yaml")
    alias_dictionary_path: str = Field(default="config/alias_dictionary.yaml")
    validation_schema_path: str = Field(default="config/validation_schema.yaml")
    static_domain_path: str = Field(default="config/static_domain.yaml")
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_config_path(self, config_name: str) -> Path:
        """설정 파일 전체 경로 반환"""
        config_map = {
            "entity_types": self.entity_types_path,
            "relation_types": self.relation_types_path,
            "alias_dictionary": self.alias_dictionary_path,
            "validation_schema": self.validation_schema_path,
            "static_domain": self.static_domain_path,
        }
        return self.project_root / config_map.get(config_name, config_name)
    
    def load_yaml_config(self, config_name: str) -> dict:
        """YAML 설정 파일 로드"""
        config_path = self.get_config_path(config_name)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


@lru_cache()
def get_settings() -> Settings:
    """싱글톤 설정 인스턴스 반환"""
    return Settings()
