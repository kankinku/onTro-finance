"""
Edge Weight Fusion Engine (EES)
"Domain/Personal/Semantic/Validation 정보를 모두 합쳐 최종 관계 강도를 계산"

가중치 공식:
  W_D = domain_conf * (1 - decay) * semantic_score * evidence_bonus * gold_bonus
  W_P = PCS * personal_weight 
        (Domain 존재 시 * 0.3 감쇠)
  
  추가 반영 요소:
  - evidence_count 가중 (많을수록 bonus)
  - gold_flag 보너스 (Gold Set 검증된 관계)
  
  최종: W = W_D + W_P
  (Domain-Personal sign 충돌 시 -> Personal 무시)
"""
import logging
from typing import List, Dict, Optional

from src.reasoning.models import RetrievedPath, FusedEdge, FusedPath

logger = logging.getLogger(__name__)


# Semantic score 매핑
SEMANTIC_SCORES = {
    "sem_confident": 1.0,
    "sem_weak": 0.7,
    "sem_ambiguous": 0.4,
    "sem_spurious": 0.2,
    "sem_wrong": 0.1,
}


class EdgeWeightFusion:
    """
    Edge Weight Fusion Engine (EES)
    Domain + Personal 가중치 융합
    
    공식:
      W_D = domain_conf * (1 - decay) * semantic * evidence_bonus * gold_bonus
      W_P = PCS * personal_weight * personal_discount
      W = W_D + W_P (충돌 시 Domain만)
    """
    
    def __init__(
        self,
        domain_priority: float = 0.7,
        personal_discount: float = 0.3,
        decay_weight: float = 0.1,
        evidence_bonus_rate: float = 0.02,
        gold_bonus: float = 1.2,
    ):
        self.domain_priority = domain_priority
        self.personal_discount = personal_discount
        self.decay_weight = decay_weight
        self.evidence_bonus_rate = evidence_bonus_rate
        self.gold_bonus = gold_bonus
    
    def fuse_path(self, path: RetrievedPath) -> FusedPath:
        """경로의 모든 엣지 가중치 융합"""
        fused_edges = []
        
        for edge in path.edges:
            fused = self._fuse_edge(edge)
            fused_edges.append(fused)
        
        path_weight, path_sign = self._calculate_path_metrics(fused_edges)
        
        return FusedPath(
            path_id=path.path_id,
            nodes=path.nodes,
            fused_edges=fused_edges,
            path_weight=path_weight,
            path_sign=path_sign,
        )
    
    def _fuse_edge(self, edge: Dict) -> FusedEdge:
        """
        단일 엣지 가중치 융합
        
        W_D = domain_conf * (1 - decay) * semantic * evidence_bonus * gold_bonus
        W_P = PCS * personal_weight * discount
        """
        source = edge.get("source", "domain")
        
        domain_weight = 0.0
        domain_conf = 0.0
        decay_factor = 0.0
        semantic_score = 1.0
        evidence_bonus = 1.0
        gold_applied = False
        
        if source == "domain":
            domain_conf = edge.get("domain_conf", 0.5)
            decay_factor = edge.get("decay_factor", 0.0)
            semantic_tag = edge.get("semantic_tag", "sem_confident")
            semantic_score = SEMANTIC_SCORES.get(semantic_tag, 0.7)
            
            # Evidence count 보너스 (체감)
            evidence_count = edge.get("evidence_count", 1)
            evidence_bonus = 1.0 + min(0.2, self.evidence_bonus_rate * evidence_count)
            
            # Gold flag 보너스
            gold_flag = edge.get("gold_flag", False)
            if gold_flag:
                gold_applied = True
                evidence_bonus *= self.gold_bonus
            
            domain_weight = domain_conf * (1 - decay_factor) * semantic_score * evidence_bonus
        
        personal_weight = 0.0
        pcs_score = 0.0
        has_conflict = False
        
        if source == "personal":
            pcs_score = edge.get("pcs_score", 0.5)
            p_weight = edge.get("personal_weight", 0.5)
            
            personal_weight = pcs_score * p_weight
            
            if domain_weight > 0:
                personal_weight *= self.personal_discount
                has_conflict = True
        
        final_weight = domain_weight + personal_weight
        
        if has_conflict and domain_weight > 0:
            final_weight = domain_weight
        
        return FusedEdge(
            edge_id=edge.get("relation_id", ""),
            head_id=edge.get("head", ""),
            tail_id=edge.get("tail", ""),
            relation_type=edge.get("relation_type", "Affect"),
            sign=edge.get("sign", "+"),
            domain_weight=domain_weight,
            personal_weight=personal_weight,
            final_weight=final_weight,
            domain_conf=domain_conf,
            decay_factor=decay_factor,
            semantic_score=semantic_score,
            pcs_score=pcs_score,
            has_personal_conflict=has_conflict,
        )
    
    def _calculate_path_metrics(
        self,
        fused_edges: List[FusedEdge],
    ) -> tuple:
        """경로 전체 가중치와 sign 계산"""
        if not fused_edges:
            return 0.0, "+"
        
        path_weight = 1.0
        for edge in fused_edges:
            path_weight *= max(edge.final_weight, 0.01)
        
        path_sign = "+"
        for edge in fused_edges:
            if edge.sign == "-":
                path_sign = "-" if path_sign == "+" else "+"
        
        return path_weight, path_sign
    
    def fuse_multiple_paths(
        self,
        paths: List[RetrievedPath],
    ) -> List[FusedPath]:
        """여러 경로 융합"""
        return [self.fuse_path(p) for p in paths]
