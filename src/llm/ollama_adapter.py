"""
Ollama LLM Client - 새 인터페이스 어댑터
기존 OllamaClient를 LLMClient 인터페이스에 맞춤.
"""
import json
import time
import logging
from typing import Optional, Dict, Any, List
import httpx

from src.llm.llm_client import LLMClient, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OllamaLLMClient(LLMClient):
    """Ollama LLMClient 구현"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 30.0,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client
    
    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
    
    def generate(self, request: LLMRequest) -> LLMResponse:
        """텍스트 생성"""
        start_time = time.time()
        
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }
        
        if request.system_prompt:
            payload["system"] = request.system_prompt
        
        if request.json_mode:
            payload["format"] = "json"
        
        response = self.client.post(
            f"{self.base_url}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        
        result = response.json()
        latency_ms = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=result.get("response", ""),
            model=self.model,
            input_tokens=result.get("prompt_eval_count", 0),
            output_tokens=result.get("eval_count", 0),
            latency_ms=latency_ms,
            raw_response=result,
        )
    
    def generate_json(self, request: LLMRequest) -> Dict[str, Any]:
        """JSON 생성"""
        request.json_mode = True
        response = self.generate(request)
        
        content = response.content.strip()
        
        # ```json ... ``` 제거
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        return json.loads(content)
    
    def health_check(self) -> bool:
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_model_name(self) -> str:
        return self.model


class MockLLMClient(LLMClient):
    """테스트용 Mock LLM Client"""
    
    def __init__(self, default_response: str = "Mock response"):
        self.default_response = default_response
        self._responses: List[str] = []
        self._call_count = 0
    
    def set_responses(self, responses: List[str]) -> None:
        """순차적으로 반환할 응답 설정"""
        self._responses = responses
    
    def generate(self, request: LLMRequest) -> LLMResponse:
        self._call_count += 1
        
        if self._responses:
            content = self._responses.pop(0)
        else:
            content = self.default_response
        
        return LLMResponse(
            content=content,
            model="mock",
            input_tokens=len(request.prompt.split()),
            output_tokens=len(content.split()),
            latency_ms=10.0,
        )
    
    def generate_json(self, request: LLMRequest) -> Dict[str, Any]:
        response = self.generate(request)
        return json.loads(response.content)
    
    def health_check(self) -> bool:
        return True
    
    def get_model_name(self) -> str:
        return "mock"
    
    @property
    def call_count(self) -> int:
        return self._call_count
