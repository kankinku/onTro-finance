"""
Path Reasoning Engine
"추출된 edge들을 연결하여 실제 영향 방향성과 크기를 계산"

핵심:
- Sign propagation: sign_A→B × sign_B→C = sign_A→C
- Path strength: Π W_i
- Multiple path aggregation: Σ(sign × weight)
"""
import logging
from typing import List, Optional

from src.reasoning.models import (
    FusedPath, PathReasoningResult, ReasoningResult, ReasoningDirection
)

logger = logging.getLogger(__name__)


class PathReasoningEngine:
    """
    Path Reasoning Engine
    경로 기반 인과 추론
    """
    
    def __init__(self):
        pass
    
    def reason(
        self,
        fused_paths: List[FusedPath],
        query_id: str,
    ) -> ReasoningResult:
        """
        경로들을 분석하여 최종 추론 결과 생성
        
        Args:
            fused_paths: 융합된 경로들
            query_id: 질문 ID
        
        Returns:
            ReasoningResult
        """
        if not fused_paths:
            return ReasoningResult(
                query_id=query_id,
                direction=ReasoningDirection.UNKNOWN,
                confidence=0.0,
            )
        
        # 각 경로 추론
        path_results = []
        for fused_path in fused_paths:
            result = self._reason_single_path(fused_path)
            path_results.append(result)
        
        # 다중 경로 집계
        final_result = self._aggregate_paths(path_results, query_id)
        
        logger.info(
            f"Reasoning complete: direction={final_result.direction.value}, "
            f"confidence={final_result.confidence:.3f}, paths={len(path_results)}"
        )
        
        return final_result
    
    def _reason_single_path(self, fused_path: FusedPath) -> PathReasoningResult:
        """단일 경로 추론"""
        edges = fused_path.fused_edges
        
        if not edges:
            return PathReasoningResult(
                path_id=fused_path.path_id,
                nodes=fused_path.nodes,
                node_names=fused_path.nodes,
                combined_sign="+",
                path_strength=0.0,
            )
        
        # Sign propagation
        combined_sign = "+"
        edge_signs = []
        edge_weights = []
        
        for edge in edges:
            edge_signs.append(edge.sign)
            edge_weights.append(edge.final_weight)
            
            # sign multiplication
            if edge.sign == "-":
                combined_sign = "-" if combined_sign == "+" else "+"
        
        # Path strength (multiplicative)
        path_strength = 1.0
        for w in edge_weights:
            path_strength *= max(w, 0.01)
        
        return PathReasoningResult(
            path_id=fused_path.path_id,
            nodes=fused_path.nodes,
            node_names=fused_path.nodes,
            combined_sign=combined_sign,
            path_strength=path_strength,
            edge_signs=edge_signs,
            edge_weights=edge_weights,
        )
    
    def _aggregate_paths(
        self,
        path_results: List[PathReasoningResult],
        query_id: str,
    ) -> ReasoningResult:
        """다중 경로 집계"""
        if not path_results:
            return ReasoningResult(
                query_id=query_id,
                direction=ReasoningDirection.UNKNOWN,
                confidence=0.0,
            )
        
        # Weighted sum of signs
        # sign_final = sign(Σ sign_path × W_path)
        positive_evidence = 0.0
        negative_evidence = 0.0
        
        for result in path_results:
            if result.combined_sign == "+":
                positive_evidence += result.path_strength
            else:
                negative_evidence += result.path_strength
        
        # 방향 결정
        total_evidence = positive_evidence + negative_evidence
        if total_evidence == 0:
            direction = ReasoningDirection.UNKNOWN
            confidence = 0.0
        else:
            net_evidence = positive_evidence - negative_evidence
            
            if net_evidence > 0.05:
                direction = ReasoningDirection.POSITIVE
            elif net_evidence < -0.05:
                direction = ReasoningDirection.NEGATIVE
            else:
                direction = ReasoningDirection.NEUTRAL
            
            # Confidence = |net| / total
            confidence = min(1.0, abs(net_evidence) / max(total_evidence, 0.01))
        
        # 가장 강한 경로
        strongest_path = max(path_results, key=lambda x: x.path_strength) if path_results else None
        
        # 충돌 경로 수
        conflicting = 0
        if positive_evidence > 0 and negative_evidence > 0:
            conflicting = sum(1 for r in path_results if r.combined_sign == "-")
        
        return ReasoningResult(
            query_id=query_id,
            direction=direction,
            confidence=confidence,
            paths_used=path_results,
            strongest_path=strongest_path,
            positive_evidence=positive_evidence,
            negative_evidence=negative_evidence,
            conflicting_paths=conflicting,
        )
