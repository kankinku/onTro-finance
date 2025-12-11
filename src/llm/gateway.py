"""
LLM Gateway
단일 진입점. Retry / Timeout / Logging / Fallback 처리.
"""
import json
import time
import logging
from typing import Any, Dict, List, Optional, Callable
from functools import wraps

from src.llm.llm_client import LLMClient, LLMRequest, LLMResponse, LLMError

logger = logging.getLogger(__name__)


class LLMGateway:
    """
    LLM Gateway - 단일 진입점
    
    책임:
    - Retry with exponential backoff
    - Timeout 처리
    - Cost/Token logging
    - 캐싱 (선택)
    - Fallback (primary -> secondary)
    """
    
    def __init__(
        self,
        primary_client: LLMClient,
        fallback_client: Optional[LLMClient] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        enable_cache: bool = False,
    ):
        self.primary = primary_client
        self.fallback = fallback_client
        self.max_retries = max_retries
        self.base_delay = base_delay
        
        # 캐시 (simple in-memory)
        self._cache: Dict[str, LLMResponse] = {}
        self._enable_cache = enable_cache
        
        # 통계
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "primary_success": 0,
            "fallback_success": 0,
            "total_failures": 0,
            "total_tokens": 0,
            "total_latency_ms": 0,
        }
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
        metadata: Optional[Dict] = None,
    ) -> LLMResponse:
        """LLM 호출 (retry + fallback 포함)"""
        request = LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            metadata=metadata or {},
        )
        
        self._stats["total_requests"] += 1
        
        # 캐시 확인
        cache_key = self._make_cache_key(request)
        if self._enable_cache and cache_key in self._cache:
            self._stats["cache_hits"] += 1
            response = self._cache[cache_key]
            response.cached = True
            return response
        
        # Primary 시도
        response, error = self._try_with_retry(self.primary, request)
        
        if response:
            self._stats["primary_success"] += 1
            self._update_stats(response)
            if self._enable_cache:
                self._cache[cache_key] = response
            return response
        
        # Fallback 시도
        if self.fallback and error and error.retryable:
            logger.warning(f"Primary failed, trying fallback: {error.message}")
            response, error = self._try_with_retry(self.fallback, request)
            
            if response:
                self._stats["fallback_success"] += 1
                self._update_stats(response)
                return response
        
        # 최종 실패
        self._stats["total_failures"] += 1
        raise LLMGatewayError(
            f"LLM call failed after retries: {error.message if error else 'unknown'}"
        )
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """JSON 생성 (파싱 포함)"""
        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            metadata=metadata,
        )
        
        try:
            # JSON 파싱
            content = response.content.strip()
            
            # ```json ... ``` 제거
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3]
            
            return json.loads(content)
        
        except json.JSONDecodeError as e:
            raise LLMGatewayError(f"JSON parse error: {e}")
    
    def _try_with_retry(
        self,
        client: LLMClient,
        request: LLMRequest,
    ) -> tuple:
        """Retry with exponential backoff"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = client.generate(request)
                return response, None
            
            except Exception as e:
                error = self._classify_error(e)
                last_error = error
                
                if not error.retryable:
                    logger.error(f"Non-retryable error: {error.message}")
                    break
                
                delay = self.base_delay * (2 ** attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{self.max_retries} after {delay}s: {error.message}"
                )
                time.sleep(delay)
        
        return None, last_error
    
    def _classify_error(self, e: Exception) -> LLMError:
        """에러 분류"""
        error_str = str(e).lower()
        
        if "timeout" in error_str:
            return LLMError("timeout", str(e), retryable=True, raw_error=e)
        elif "rate" in error_str or "429" in error_str:
            return LLMError("rate_limit", str(e), retryable=True, raw_error=e)
        elif "auth" in error_str or "401" in error_str or "403" in error_str:
            return LLMError("auth", str(e), retryable=False, raw_error=e)
        elif "connection" in error_str or "network" in error_str:
            return LLMError("network", str(e), retryable=True, raw_error=e)
        else:
            return LLMError("unknown", str(e), retryable=True, raw_error=e)
    
    def _make_cache_key(self, request: LLMRequest) -> str:
        """캐시 키 생성"""
        return f"{request.prompt}::{request.system_prompt}::{request.temperature}"
    
    def _update_stats(self, response: LLMResponse) -> None:
        """통계 업데이트"""
        self._stats["total_tokens"] += response.total_tokens
        self._stats["total_latency_ms"] += response.latency_ms
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()
    
    def health_check(self) -> bool:
        """헬스체크"""
        return self.primary.health_check()
    
    def close(self) -> None:
        """리소스 정리"""
        self.primary.close()
        if self.fallback:
            self.fallback.close()


class LLMGatewayError(Exception):
    """LLM Gateway 에러"""
    pass
