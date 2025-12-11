"""
커스텀 예외 정의
원칙 3: 철저한 Error Handling - 에러는 정확한 실패 원인 전달
"""
from typing import Optional, Dict, Any


class BaseExtractionException(Exception):
    """Extraction Sector 기본 예외"""
    
    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = False,
    ):
        self.message = message
        self.details = details or {}
        self.recoverable = recoverable  # 복구 가능 여부
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """구조화된 에러 정보 반환 (로깅용)"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }


class ExtractionError(BaseExtractionException):
    """일반 추출 에러"""
    pass


class FragmentExtractionError(BaseExtractionException):
    """Fragment Extraction 실패"""
    
    def __init__(
        self,
        message: str,
        doc_id: Optional[str] = None,
        raw_text_preview: Optional[str] = None,
        **kwargs
    ):
        details = {
            "doc_id": doc_id,
            "raw_text_preview": raw_text_preview[:100] if raw_text_preview else None,
        }
        super().__init__(message, details, **kwargs)


class NERError(BaseExtractionException):
    """NER (Student1) 실패"""
    
    def __init__(
        self,
        message: str,
        fragment_id: Optional[str] = None,
        fragment_text: Optional[str] = None,
        **kwargs
    ):
        details = {
            "fragment_id": fragment_id,
            "fragment_text": fragment_text[:100] if fragment_text else None,
        }
        super().__init__(message, details, **kwargs)


class EntityResolutionError(BaseExtractionException):
    """Entity Resolution 실패"""
    
    def __init__(
        self,
        message: str,
        entity_id: Optional[str] = None,
        surface_text: Optional[str] = None,
        resolution_attempt: Optional[str] = None,
        **kwargs
    ):
        details = {
            "entity_id": entity_id,
            "surface_text": surface_text,
            "resolution_attempt": resolution_attempt,
        }
        super().__init__(message, details, **kwargs)


class RelationExtractionError(BaseExtractionException):
    """Relation Extraction (Student2) 실패"""
    
    def __init__(
        self,
        message: str,
        fragment_id: Optional[str] = None,
        entity_pair: Optional[tuple] = None,
        **kwargs
    ):
        details = {
            "fragment_id": fragment_id,
            "entity_pair": entity_pair,
        }
        super().__init__(message, details, **kwargs)


class LLMError(BaseExtractionException):
    """LLM 호출 실패"""
    
    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        prompt_preview: Optional[str] = None,
        response_preview: Optional[str] = None,
        **kwargs
    ):
        details = {
            "model_name": model_name,
            "prompt_preview": prompt_preview[:200] if prompt_preview else None,
            "response_preview": response_preview[:200] if response_preview else None,
        }
        super().__init__(message, details, **kwargs)


class ConfigError(BaseExtractionException):
    """설정 관련 에러"""
    
    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        missing_key: Optional[str] = None,
        **kwargs
    ):
        details = {
            "config_file": config_file,
            "missing_key": missing_key,
        }
        super().__init__(message, details, **kwargs)
