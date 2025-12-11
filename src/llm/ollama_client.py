"""
Ollama LLM 클라이언트
원칙 4: 단일 책임 - LLM 호출만 담당
원칙 3: 철저한 Error Handling - 재시도 로직 포함
"""
import json
import logging
import time
from typing import Optional, Dict, Any, List
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

from config.settings import get_settings, OllamaSettings
from src.shared.exceptions import LLMError

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama API 클라이언트"""
    
    def __init__(self, settings: Optional[OllamaSettings] = None):
        self.settings = settings or get_settings().ollama
        self.base_url = self.settings.base_url
        self.model_name = self.settings.model_name
        self.timeout = self.settings.timeout
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        """Lazy initialization of HTTP client"""
        if httpx is None:
            raise ImportError("httpx is required for OllamaClient (install httpx or disable LLM)")
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client
    
    def close(self):
        """클라이언트 정리"""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        max_retries: int = 3,
    ) -> str:
        """
        텍스트 생성
        
        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            temperature: 생성 온도 (None이면 설정값 사용)
            max_tokens: 최대 토큰 수
            json_mode: JSON 출력 모드
            max_retries: 최대 재시도 횟수
        
        Returns:
            생성된 텍스트
        
        Raises:
            LLMError: LLM 호출 실패 시
        """
        temperature = temperature if temperature is not None else self.settings.temperature
        max_tokens = max_tokens or self.settings.max_tokens
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        if json_mode:
            payload["format"] = "json"
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                
                result = response.json()
                return result.get("response", "")
                
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"LLM timeout (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(f"LLM HTTP error: {e.response.status_code}")
                if e.response.status_code >= 500:
                    time.sleep(2 ** attempt)
                else:
                    break  # 4xx 에러는 재시도 안함
                    
            except Exception as e:
                last_error = e
                logger.error(f"LLM unexpected error: {e}")
                break
        
        raise LLMError(
            message=f"LLM generation failed after {max_retries} attempts",
            model_name=self.model_name,
            prompt_preview=prompt,
            details={"last_error": str(last_error)},
        )
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        JSON 형식으로 생성
        
        Returns:
            파싱된 JSON 딕셔너리
            
        Raises:
            LLMError: 생성 또는 JSON 파싱 실패 시
        """
        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=True,
            **kwargs
        )
        
        try:
            # JSON 블록 추출 시도
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()
            
            return json.loads(response)
            
        except json.JSONDecodeError as e:
            raise LLMError(
                message="Failed to parse LLM response as JSON",
                model_name=self.model_name,
                response_preview=response,
                details={"parse_error": str(e)},
            )
    
    def health_check(self) -> bool:
        """Ollama 서버 상태 확인"""
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> List[str]:
        """사용 가능한 모델 목록"""
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            return [m.get("name") for m in models]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
