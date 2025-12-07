"""
DEPRECATED: 이 파일은 하위 호환성을 위해 유지됩니다.
새 코드는 config.settings를 직접 import하세요.

from config.settings import settings
"""
# Backward compatibility: re-export from new location
from config.settings import settings

__all__ = ["settings"]
