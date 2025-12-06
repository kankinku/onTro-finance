from typing import List, Dict, Optional
import uuid
from src.schemas.base_models import Fragment, Term, ResolvedEntity

class EntityResolver:
    """
    [M2] Entity Resolver
    Responsibility: Map surface forms (text) to canonical Entity IDs (URIs).
    In a real system, this uses Vector Search (Embedding) + Fuzzy Matching.
    """

    def __init__(self):
        # Mock Knowledge Base (Ontology)
        # In production, this would be a connection to Neo4j or Vector DB
        self.kb_terms: Dict[str, Term] = {
            "slr 규제": Term(term_id="TERM_SLR_RULE", label="SLR 규제", aliases=["SLR", "Supplementary Leverage Ratio"]),
            "바젤3": Term(term_id="TERM_BASEL3", label="바젤 III", aliases=["Basel 3", "바젤III"]),
            "대차대조표": Term(term_id="TERM_BALANCE_SHEET_CAP", label="대차대조표", aliases=["B/S", "대차대조표 여력"]),
            "국채 수요": Term(term_id="TERM_TREASURY_DEMAND", label="국채 수요", aliases=["UST Demand", "국채 매수"]),
            "국채 매수 여력": Term(term_id="TERM_TREASURY_BUYING_POWER", label="국채 매수 여력", aliases=[]),
            
            # 거시경제 지표
            "기준금리": Term(term_id="TERM_BASE_RATE", label="기준금리", aliases=["Policy Rate", "Base Rate"]),
            "인플레이션": Term(term_id="TERM_INFLATION", label="인플레이션", aliases=["물가상승", "Inflation Rate"]),
            "환율": Term(term_id="TERM_EXCHANGE_RATE", label="환율", aliases=["FX Rate", "원달러 환율"]),
            "국채 금리": Term(term_id="TERM_TREASURY_YIELD", label="국채 금리", aliases=["Treasury Yield", "국채 수익률"]),
            "유동성": Term(term_id="TERM_LIQUIDITY", label="유동성", aliases=["Market Liquidity", "자금 사정"]),
            
            # 금융 규제 및 리스크
            "신용 스프레드": Term(term_id="TERM_CREDIT_SPREAD", label="신용 스프레드", aliases=["회사채 스프레드", "Credit Spread"]),
            "미국채": Term(term_id="TERM_UST", label="미국채", aliases=["UST", "U.S. Treasury"]),
            "LCR": Term(term_id="TERM_LCR", label="LCR", aliases=["Liquidity Coverage Ratio", "유동성 커버리지 비율"]),
            "BIS 비율": Term(term_id="TERM_BIS_RATIO", label="BIS 비율", aliases=["BIS Ratio", "BIS"]),
            
            # 시장 참여자
            "중앙은행": Term(term_id="NODE_CENTRAL_BANK", label="중앙은행", aliases=["Fed", "BOK", "한국은행"]),
            "시중은행": Term(term_id="NODE_COMMERCIAL_BANK", label="시중은행", aliases=["Commercial Bank", "은행권"]),
            "헤지펀드": Term(term_id="NODE_HEDGE_FUND", label="헤지펀드", aliases=["Hedge Fund"]),

            # 자산
            "자산 가격": Term(term_id="TERM_ASSET_PRICE", label="자산 가격", aliases=["주가", "부동산 가격"]),
            "회사채": Term(term_id="TERM_CORP_BOND", label="회사채", aliases=["Corporate Bond"])
        }

    def resolve(self, fragments: List[Fragment]) -> Dict[str, ResolvedEntity]:
        """
        Resolves all terms found in fragments.
        Returns a map: surface_text -> ResolvedEntity
        """
        resolution_map = {}

        for frag in fragments:
            # Resolve Term Candidates
            for surface in frag.term_candidates:
                if surface in resolution_map:
                    continue
                
                resolved = self._resolve_single_term(surface)
                resolution_map[surface] = resolved

            # We could also resolve Mechanism candidates here if they were treated as entities
            
        return resolution_map

    def _resolve_single_term(self, surface: str) -> ResolvedEntity:
        """
        Naive implementation of resolution logic.
        1. Exact match (normalized)
        2. Vector similarity (mocked)
        3. New Entity creation
        """
        normalized = surface.lower().strip()
        
        # 1. Check Mock KB
        if normalized in self.kb_terms:
            term = self.kb_terms[normalized]
            return ResolvedEntity(
                surface_form=surface,
                entity_id=term.term_id,
                entity_type="TERM",
                confidence=1.0
            )

        # 2. Fuzzy/Vector Match (Mocked)
        # For this demo, let's map "국채 매수 여력" in text to "국채 수요" or similar if needed. 
        # But let's assume if it's not in KB, it's a new candidate.
        
        # 3. Create New Candidate
        new_id = f"TERM_CAND_{uuid.uuid4().hex[:8].upper()}"
        return ResolvedEntity(
            surface_form=surface,
            entity_id=new_id,
            entity_type="TERM",
            confidence=0.5 # Low confidence for new terms
        )
