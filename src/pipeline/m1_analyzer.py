import requests
import json
from typing import List
from src.schemas.base_models import Fragment
from src.core.config import settings
from src.core.logger import logger

class InputAnalyzer:
    """
    [M1] Input Analyzer (Ollama Integrated)
    Responsibility: Decompose natural language text into Fact/Mechanism/Condition/Outcome fragments.
    """
    
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        logger.info(f"[M1] Initialized with Ollama model: {self.model} at {self.base_url}")

    def analyze(self, text: str) -> List[Fragment]:
        """
        Calls local Ollama instance to analyze text.
        """
        if not text:
            return []

        prompt = self._build_prompt(text)
        
        try:
            # Call Ollama API
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json" # Ollama supports JSON mode
                },
                timeout=30 # longer timeout for LLM
            )
            response.raise_for_status()
            result_json = response.json()
            
            # Ollama returns 'response' key with the generated text
            generated_text = result_json.get("response", "")
            logger.debug(f"[M1] Raw LLM Output: {generated_text[:100]}...")
            
            # Clean potential Markdown backticks if Ollama outputs them despite 'format: json'
            if generated_text.strip().startswith("```"):
                generated_text = generated_text.strip().strip("`").replace("json\n", "", 1)
            
            parsed_data = json.loads(generated_text)
            
            # Convert to Pydantic Models
            fragments = []
            raw_fragments = parsed_data.get("fragments", [])
            # Fallback if top-level key is missing or named differently
            if not raw_fragments and isinstance(parsed_data, list):
                raw_fragments = parsed_data

            for idx, item in enumerate(raw_fragments):
                # Helper to get value case-insensitively
                def get_val(keys, default=None):
                    for k in keys:
                        if k in item: return item[k]
                    return default

                fragment = Fragment(
                    fragment_id=f"F{str(idx).zfill(2)}",
                    text=get_val(["text", "Text"], ""),
                    fact=get_val(["fact", "Fact"], ""),
                    mechanism_text=get_val(["mechanism", "Mechanism", "mech"], ""),
                    condition_text=get_val(["condition", "Condition"], None),
                    outcome_text=get_val(["outcome", "Outcome"], ""),
                    term_candidates=get_val(["term_candidates", "terms", "Entities"], []),
                    mechanism_candidates=get_val(["mechanism_candidates", "mechanisms"], []),
                    predicate_candidate=get_val(["predicate_candidate", "predicate"], None)
                )
                fragments.append(fragment)
            
            logger.info(f"[M1] Successfully extracted {len(fragments)} fragments.")
            return fragments

        except Exception as e:
            logger.error(f"[M1] LLM Analysis failed: {e}")
            # Fallback to Mock if LLM fails (for safety)
            return self._mock_fallback(text)

    def _build_prompt(self, text: str) -> str:
        return f"""
        You are a Financial Ontology Analyst.
        Analyze the following text and decompose it into structured fragments.
        If the input is in Korean, extract the values in Korean (except for predicated_candidate which should be English).

        Input Text: "{text}"
        
        Task:
        1. Extract the core Fact.
        2. Identify the Mechanism (how X affects Y).
        3. Identify any Conditions (time, market state).
        4. Identify the Outcome.
        5. List key Terms (Entities).
        6. Suggest a Predicate from [P_INCREASES, P_DECREASES, P_CAUSES, P_PREVENTS, P_CORR_POS, P_CORR_NEG].
        
        Example Output:
        {{
            "fragments": [
                {{
                    "text": "연말은 자금 수요가 늘어 금리를 상승시킨다.",
                    "fact": "연말 자금 수요 증가",
                    "mechanism": "수요 증가 -> 금리 상승 압력",
                    "condition": "연말 (Year-end)",
                    "outcome": "금리 상승",
                    "term_candidates": ["연말", "자금 수요", "금리"],
                    "mechanism_candidates": ["수요-공급 원리"],
                    "predicate_candidate": "P_INCREASES"
                }}
            ]
        }}

        Return ONLY valid JSON.
        """

    def _mock_fallback(self, text: str) -> List[Fragment]:
        logger.warning("[M1] Using Mock Fallback.")
        # ... (Old mock logic) ...
        # Simplified for brevity, returning empty or old mock
        if "SLR" in text:
             return [Fragment(
                fragment_id="F99_MOCK",
                text=text,
                fact="Mock Fact for SLR",
                mechanism_text="Mock Mechanism",
                outcome_text="Mock Outcome",
                term_candidates=["SLR 규제", "대차대조표"],
                mechanism_candidates=["Mock Mechanism"],
                predicate_candidate="P_DECREASES"
             )]
             
        # Generic Fallback for any other text
        return [Fragment(
            fragment_id=f"F_MOCK_GEN",
            text=text,
            fact=f"Analyzed fact from: {text[:20]}...",
            mechanism_text="Generic Mechanism (Ollama Unavailable)",
            outcome_text="Predicted Outcome",
            term_candidates=["Generic Term A", "Generic Term B"],
            mechanism_candidates=["Mechanism A -> B"],
            predicate_candidate="P_CAUSES"
        )]
