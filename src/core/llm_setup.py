"""
DEPRECATED: 이 파일은 하위 호환성을 위해 유지됩니다.
새 코드는 src.services.llm_service를 직접 import하세요.

from src.services.llm_service import llm_service
"""
# Backward compatibility: re-export from new location
from src.services.llm_service import llm_service

def check_and_pull_ollama_model():
    """DEPRECATED: Use llm_service.check_and_pull_model() instead"""
    return llm_service.check_and_pull_model()

__all__ = ["check_and_pull_ollama_model"]
