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

                # Map new prompt outputs to Fragment
                variables = get_val(["variables", "term_candidates", "terms", "Entities"], [])
                relation_kind = get_val(["relation_kind"], "CAUSAL")
                sign_val = get_val(["proportional_sign", "sign"], 1)
                strength_val = get_val(["strength"], 1.0)
                
                # Infer predicate for backward compatibility
                inferred_pred = "P_INCREASES" if sign_val > 0 else "P_DECREASES"

                fragment = Fragment(
                    fragment_id=f"F{str(idx).zfill(2)}",
                    text=get_val(["text", "Text"], ""),
                    fact=get_val(["fact", "Fact"], ""),
                    mechanism_text=get_val(["mechanism", "Mechanism", "mech"], ""),
                    condition_text=get_val(["condition", "Condition"], None),
                    outcome_text=get_val(["outcome", "Outcome"], ""),
                    term_candidates=variables,
                    mechanism_candidates=get_val(["mechanism_candidates", "mechanisms"], []),
                    predicate_candidate=get_val(["predicate_candidate", "predicate"], inferred_pred),
                    
                    # New Fields
                    relation_kind=relation_kind,
                    sign=sign_val,
                    strength=strength_val,
                    lag_days=get_val(["lag_days"], 0)
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
        You are a Specialized Financial Ontology Engineer.
        Your task is to extract structured causal relations from the input text into a rigorous JSON format.

        [Input Text]
        "{text}"
        
        [Extraction Rules]
        1. **Variables**: Identify the main variables (Entities). The first one is the Cause/Subject, the second is the Effect/Object.
        2. **Relation Kind**: Choose strictly from [CAUSAL, PROPORTIONAL, CORRELATED, STRUCTURAL].
           - CAUSAL: One event causes another.
           - PROPORTIONAL: Two variables move together (function relationship).
           - STRUCTURAL: One is part of another.
        3. **Sign (proportional_sign)**:
           - +1: Positive correlation (Both up or both down).
           - -1: Negative correlation (Inverse relationship).
        4. **Strength**: 0.0 to 1.0 (How strong is this link?).
        5. **Lag**: Estimated days for effect to materialize (0 if immediate).

        [Output Format (JSON List)]
        {{
            "fragments": [
                {{
                    "text": "Original sentence segment",
                    "variables": ["Subject Entity", "Object Entity"],
                    "relation_kind": "PROPORTIONAL",
                    "proportional_sign": -1,
                    "strength": 0.8,
                    "lag_days": 0,
                    "condition": "Condition context if any",
                    "mechanism": "Logical explanation"
                }}
            ]
        }}
        
        [Example]
        Input: "금리가 오르면 자산 가격은 필연적으로 하락 압력을 받는다."
        Output:
        {{
            "fragments": [
                {{
                    "text": "금리가 오르면 자산 가격은 필연적으로 하락 압력을 받는다",
                    "variables": ["금리", "자산 가격"],
                    "relation_kind": "PROPORTIONAL",
                    "proportional_sign": -1,
                    "strength": 0.9,
                    "lag_days": 30,
                    "condition": "필연적",
                    "mechanism": "할인율 상승에 따른 가치 하락"
                }}
            ]
        }}

        Answer in pure JSON.
        """

    def _mock_fallback(self, text: str) -> List[Fragment]:
        logger.warning("[M1] Using Mock Fallback.")
        
        # Scenario: SLR Regulation
        if "SLR" in text:
             return [Fragment(
                fragment_id="F99_MOCK",
                text=text,
                fact="Mock Fact for SLR",
                mechanism_text="SLR limits balance sheet expansion",
                outcome_text="Reduced Buying Power",
                term_candidates=["SLR 규제", "대차대조표"], # Subject, Object
                
                # Strong Ontology Fields
                relation_kind="CAUSAL",
                sign=-1, # DECREASES
                strength=0.9,
                lag_days=0
             )]
             
        # Generic Fallback
        return [Fragment(
            fragment_id=f"F_MOCK_GEN",
            text=text,
            fact=f"Analyzed fact from: {text[:20]}...",
            mechanism_text="Generic Mechanism",
            outcome_text="Predicted Outcome",
            term_candidates=["General Subject", "Generic Object"],
            
            # Strong Ontology Fields
            relation_kind="CORRELATED",
            sign=1,
            strength=0.5,
            lag_days=0
        )]
