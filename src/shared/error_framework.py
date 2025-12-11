"""
Exception Framework
구조화된 예외 처리 시스템.

계층:
- OntologyError (base)
  - StorageError (저장소)
  - LLMError (LLM 호출)
  - ValidationError (검증)
  - ExtractionError (추출)
  - ReasoningError (추론)
  - ConfigError (설정)
"""
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import traceback
import logging

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """에러 심각도"""
    LOW = "low"           # 로그만, 계속 진행
    MEDIUM = "medium"     # 부분 실패, fallback 시도
    HIGH = "high"         # 작업 실패, 롤백 필요
    CRITICAL = "critical" # 시스템 중단 필요


class ErrorCategory(Enum):
    """에러 카테고리"""
    STORAGE = "storage"
    LLM = "llm"
    VALIDATION = "validation"
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    CONFIG = "config"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """에러 컨텍스트"""
    module: str
    operation: str
    input_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class OntologyError(Exception):
    """Base Exception for Ontology System"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        retryable: bool = False,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.retryable = retryable
        self.context = context
        self.cause = cause
        self.timestamp = datetime.now()
        
        # 로깅
        self._log()
    
    def _log(self) -> None:
        """에러 로깅"""
        log_data = {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "retryable": self.retryable,
        }
        
        if self.context:
            log_data["module"] = self.context.module
            log_data["operation"] = self.context.operation
        
        if self.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"CRITICAL ERROR: {log_data}")
        elif self.severity == ErrorSeverity.HIGH:
            logger.error(f"ERROR: {log_data}")
        elif self.severity == ErrorSeverity.MEDIUM:
            logger.warning(f"WARNING: {log_data}")
        else:
            logger.info(f"INFO: {log_data}")
    
    def to_dict(self) -> Dict[str, Any]:
        """직렬화"""
        result = {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "timestamp": self.timestamp.isoformat(),
        }
        
        if self.context:
            result["context"] = {
                "module": self.context.module,
                "operation": self.context.operation,
            }
        
        if self.cause:
            result["cause"] = str(self.cause)
        
        return result


class StorageError(OntologyError):
    """저장소 관련 에러"""
    
    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        entity_id: Optional[str] = None,
        **kwargs
    ):
        context = ErrorContext(
            module="storage",
            operation=operation,
            extra={"entity_id": entity_id} if entity_id else {},
        )
        super().__init__(
            message=message,
            category=ErrorCategory.STORAGE,
            severity=kwargs.get("severity", ErrorSeverity.HIGH),
            retryable=kwargs.get("retryable", True),
            context=context,
            cause=kwargs.get("cause"),
        )


class LLMServiceError(OntologyError):
    """LLM 호출 관련 에러"""
    
    def __init__(
        self,
        message: str,
        model: str = "unknown",
        prompt_preview: Optional[str] = None,
        **kwargs
    ):
        context = ErrorContext(
            module="llm",
            operation="generate",
            extra={
                "model": model,
                "prompt_preview": prompt_preview[:100] if prompt_preview else None,
            },
        )
        super().__init__(
            message=message,
            category=ErrorCategory.LLM,
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            retryable=kwargs.get("retryable", True),
            context=context,
            cause=kwargs.get("cause"),
        )


class ValidationError(OntologyError):
    """검증 관련 에러"""
    
    def __init__(
        self,
        message: str,
        validator: str = "unknown",
        edge_id: Optional[str] = None,
        reasons: Optional[List[str]] = None,
        **kwargs
    ):
        context = ErrorContext(
            module="validation",
            operation=validator,
            extra={
                "edge_id": edge_id,
                "reasons": reasons or [],
            },
        )
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=kwargs.get("severity", ErrorSeverity.LOW),
            retryable=False,
            context=context,
        )


class ExtractionError(OntologyError):
    """추출 관련 에러"""
    
    def __init__(
        self,
        message: str,
        extractor: str = "unknown",
        text_preview: Optional[str] = None,
        **kwargs
    ):
        context = ErrorContext(
            module="extraction",
            operation=extractor,
            extra={"text_preview": text_preview[:100] if text_preview else None},
        )
        super().__init__(
            message=message,
            category=ErrorCategory.EXTRACTION,
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            retryable=False,
            context=context,
        )


class ReasoningError(OntologyError):
    """추론 관련 에러"""
    
    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        step: str = "unknown",
        **kwargs
    ):
        context = ErrorContext(
            module="reasoning",
            operation=step,
            extra={"query": query},
        )
        super().__init__(
            message=message,
            category=ErrorCategory.REASONING,
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            retryable=False,
            context=context,
        )


class ConfigError(OntologyError):
    """설정 관련 에러"""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        **kwargs
    ):
        context = ErrorContext(
            module="config",
            operation="load",
            extra={"config_key": config_key},
        )
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIG,
            severity=ErrorSeverity.CRITICAL,
            retryable=False,
            context=context,
        )


# ==============================================================================
# Error Handler / Registry
# ==============================================================================

class ErrorRegistry:
    """에러 레지스트리 - 에러 수집 및 분석용"""
    
    def __init__(self, max_size: int = 1000):
        self._errors: List[Dict] = []
        self._max_size = max_size
    
    def record(self, error: OntologyError) -> None:
        """에러 기록"""
        if len(self._errors) >= self._max_size:
            self._errors.pop(0)  # FIFO
        self._errors.append(error.to_dict())
    
    def get_recent(self, count: int = 10) -> List[Dict]:
        """최근 에러"""
        return self._errors[-count:]
    
    def get_by_category(self, category: ErrorCategory) -> List[Dict]:
        """카테고리별 에러"""
        return [e for e in self._errors if e["category"] == category.value]
    
    def get_stats(self) -> Dict[str, Any]:
        """통계"""
        stats = {
            "total": len(self._errors),
            "by_category": {},
            "by_severity": {},
        }
        
        for e in self._errors:
            cat = e["category"]
            sev = e["severity"]
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1
        
        return stats
    
    def clear(self) -> None:
        """초기화"""
        self._errors.clear()


# 싱글톤
_error_registry = ErrorRegistry()


def get_error_registry() -> ErrorRegistry:
    return _error_registry
