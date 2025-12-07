"""
LLM Service
Ollama 기반 LLM 호출을 담당하는 서비스 레이어
"""
import requests
import subprocess
from typing import Optional, Dict, Any
from config.settings import settings
from config.constants import APIEndpoints
from src.core.logger import logger


class LLMService:
    """
    LLM 호출 및 관리 서비스
    - Ollama 모델 체크/풀
    - 텍스트 생성
    - 분석 기능
    """
    
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        
    def check_and_pull_model(self) -> bool:
        """
        Ollama 모델 존재 여부 확인 및 없으면 Pull
        Returns: 성공 여부
        """
        logger.info(f"[LLM] Checking Ollama model: {self.model}...")
        
        try:
            # 1. 로컬 모델 목록 확인
            res = requests.get(
                f"{self.base_url}{APIEndpoints.OLLAMA_TAGS}",
                timeout=5
            )
            if res.status_code != 200:
                logger.warning("[LLM] Ollama API not responding. Is 'ollama serve' running?")
                return False
            
            models = res.json().get('models', [])
            found = any(self.model in m.get('name', '') for m in models)
            
            if found:
                logger.info(f"[LLM] Model '{self.model}' found locally.")
                return True
                
        except requests.RequestException as e:
            logger.warning(f"[LLM] Connection to Ollama failed: {e}")
            return False
        
        # 2. 모델이 없으면 Pull
        logger.info(f"[LLM] Model '{self.model}' NOT found. Pulling...")
        return self._pull_model()
    
    def _pull_model(self) -> bool:
        """Ollama CLI로 모델 다운로드"""
        try:
            process = subprocess.Popen(
                ["ollama", "pull", self.model],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(f"[Ollama Pull] {output.strip()}")
                    
            if process.returncode == 0:
                logger.info(f"[LLM] Successfully pulled '{self.model}'.")
                return True
            else:
                logger.error(f"[LLM] Failed to pull model. Return code: {process.returncode}")
                return False
                
        except FileNotFoundError:
            logger.error("[LLM] 'ollama' command not found. Please install Ollama.")
            return False
        except Exception as e:
            logger.error(f"[LLM] Error during model pull: {e}")
            return False
    
    def generate(
        self, 
        prompt: str, 
        json_mode: bool = False,
        temperature: float = 0.7
    ) -> Optional[str]:
        """
        LLM 텍스트 생성
        
        Args:
            prompt: 프롬프트
            json_mode: JSON 형식 출력 강제
            temperature: 생성 다양성 (0.0 ~ 1.0)
            
        Returns:
            생성된 텍스트 또는 None (실패 시)
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature}
            }
            
            if json_mode:
                payload["format"] = "json"
            
            response = requests.post(
                f"{self.base_url}{APIEndpoints.OLLAMA_GENERATE}",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            generated_text = result.get("response", "")
            
            # Markdown 코드 블록 제거
            if generated_text.strip().startswith("```"):
                generated_text = generated_text.strip().strip("`").replace("json\n", "", 1)
            
            return generated_text
            
        except requests.RequestException as e:
            logger.error(f"[LLM] Generation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"[LLM] Unexpected error during generation: {e}")
            return None
    
    def analyze_market(self, market_data: Dict[str, Any]) -> str:
        """
        시장 데이터 분석 생성
        
        Args:
            market_data: 분석할 시장 데이터 딕셔너리
            
        Returns:
            분석 결과 텍스트
        """
        prompt = self._build_market_analysis_prompt(market_data)
        result = self.generate(prompt, json_mode=False, temperature=0.3)
        
        if not result:
            return "시장 분석을 생성하지 못했습니다. LLM 서비스 상태를 확인해주세요."
        
        return result
    
    def _build_market_analysis_prompt(self, data: Dict[str, Any]) -> str:
        """시장 분석용 프롬프트 빌드"""
        data_summary = "\n".join([
            f"- {k}: {v}" for k, v in data.items() if v is not None
        ])
        
        return f"""
        당신은 "Cynical Macro Strategist" 페르소나입니다.
        공식 발표를 의심하고, 자본 흐름의 구조적 모순을 집요하게 파헤칩니다.
        
        [현재 시장 데이터]
        {data_summary}
        
        [분석 규칙]
        1. 겉으로 드러나지 않는 리스크를 찾아라
        2. 데이터 간 불일치를 지적하라
        3. 향후 1-3개월 전망을 제시하라
        4. 한국어로 3-5개 핵심 포인트로 요약하라
        
        분석 결과:
        """


# Singleton Instance
llm_service = LLMService()
