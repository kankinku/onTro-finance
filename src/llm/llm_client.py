"""
LLM Client - 추상 인터페이스
모든 LLM 호출은 이 인터페이스를 통해서만.
Retry / Timeout / Cost logging / 캐싱 / 모델 스위칭 책임.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LLMRequest:
    """LLM 요청"""
    prompt: str
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    json_mode: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 응답"""
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    raw_response: Optional[Dict] = None
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMError:
    """LLM 에러"""
    error_type: str  # timeout, rate_limit, auth, network, parse, unknown
    message: str
    retryable: bool
    raw_error: Optional[Exception] = None


class LLMClient(ABC):
    """LLM Client 추상 인터페이스"""
    
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """텍스트 생성"""
        ...
    
    @abstractmethod
    def generate_json(self, request: LLMRequest) -> Dict[str, Any]:
        """JSON 형식 생성 (파싱 포함)"""
        ...
    
    @abstractmethod
    def health_check(self) -> bool:
        """연결 상태 확인"""
        ...
    
    @abstractmethod
    def get_model_name(self) -> str:
        """현재 모델명"""
        ...
    
    def close(self) -> None:
        """리소스 정리"""
        pass
