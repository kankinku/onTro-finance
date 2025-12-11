"""
Conflict Analyzer (Domain Conflict Resolution)
"Dynamic Domain 내에서 sign/type이 충돌할 때 어떻게 해결할까?"

시간축: **Local conflict** (즉시 처리)
- 같은 relation에 sign/type 상충 evidence 발생 시
- 그때그때 분배/보류/Personal 이전 결정

충돌 유형:
1. Sign 충돌 (+/- 충돌)
2. 관계 타입 충돌
3. 조건부 충돌
4. 경로 기반 충돌
"""
import logging
from typing import Optional, List, Dict, Set
from collections import deque

from src.domain.models import (
    DomainCandidate,
    DynamicRelation,
    ConflictAnalysisResult,
    ConflictType,
    ConflictResolution,
)
from src.domain.dynamic_update import DynamicDomainUpdate

logger = logging.getLogger(__name__)


class ConflictAnalyzer:
    """
    Conflict Analyzer
    Domain 내 충돌 해결
    """
    
    def __init__(
        self,
        dynamic_domain: DynamicDomainUpdate,
        min_evidence_ratio: float = 3.0,
        path_depth_limit: int = 3,
    ):
        self.dynamic_domain = dynamic_domain
        self.min_evidence_ratio = min_evidence_ratio
        self.path_depth_limit = path_depth_limit
    
    def analyze(
        self,
        candidate: DomainCandidate,
        relation: DynamicRelation,
    ) -> ConflictAnalysisResult:
        """충돌 분석 및 해결"""
        direct_result = self._analyze_direct_conflict(candidate, relation)
        
        if direct_result.resolution != ConflictResolution.KEEP_EXISTING:
            path_consistent, inconsistent_path = self._check_path_consistency(
                candidate, relation
            )
            direct_result.path_consistent = path_consistent
            direct_result.inconsistent_path = inconsistent_path
            
            if not path_consistent:
                direct_result.conflict_type = ConflictType.PATH_CONFLICT
                direct_result.resolution = ConflictResolution.TO_PERSONAL
        
        if candidate.semantic_tag in ["sem_wrong", "sem_spurious"]:
            direct_result.resolution = ConflictResolution.TO_PERSONAL
        
        logger.info(
            f"Conflict analysis: {candidate.candidate_id} -> {direct_result.resolution.value}"
        )
        
        return direct_result
    
    def _analyze_direct_conflict(
        self,
        candidate: DomainCandidate,
        relation: DynamicRelation,
    ) -> ConflictAnalysisResult:
        """직접 관계 충돌 분석"""
        has_conflict = False
        conflict_type = None
        resolution = ConflictResolution.KEEP_EXISTING
        
        if candidate.polarity != relation.sign and candidate.polarity != "unknown":
            has_conflict = True
            conflict_type = ConflictType.SIGN_CONFLICT
            
            evidence_ratio = relation.evidence_count / max(candidate.freq_count, 1)
            
            if evidence_ratio >= self.min_evidence_ratio:
                resolution = ConflictResolution.TO_PERSONAL
            elif relation.domain_conf < 0.4:
                resolution = ConflictResolution.TO_DRIFT
            else:
                resolution = ConflictResolution.KEEP_EXISTING
        
        if candidate.relation_type != relation.relation_type:
            has_conflict = True
            conflict_type = ConflictType.TYPE_CONFLICT
            resolution = ConflictResolution.TO_PERSONAL
        
        return ConflictAnalysisResult(
            candidate_id=candidate.candidate_id,
            relation_id=relation.relation_id,
            has_conflict=has_conflict,
            conflict_type=conflict_type,
            resolution=resolution,
            existing_sign=relation.sign,
            new_sign=candidate.polarity,
            existing_evidence=relation.evidence_count,
            new_evidence=candidate.freq_count,
        )
    
    def _check_path_consistency(
        self,
        candidate: DomainCandidate,
        relation: DynamicRelation,
    ) -> tuple:
        """경로 기반 consistency 검사"""
        all_relations = self.dynamic_domain.get_all_relations()
        
        graph: Dict[str, List[tuple]] = {}
        for rel in all_relations.values():
            if rel.head_id not in graph:
                graph[rel.head_id] = []
            graph[rel.head_id].append((rel.tail_id, rel.sign, rel.relation_id))
        
        head = candidate.head_canonical_id
        tail = candidate.tail_canonical_id
        new_sign = candidate.polarity
        
        paths = self._find_paths(graph, head, tail)
        
        for path in paths:
            combined_sign = self._calculate_path_sign(path)
            
            if combined_sign and new_sign != "unknown":
                if combined_sign != new_sign:
                    path_ids = [p[2] for p in path]
                    return False, path_ids
        
        return True, None
    
    def _find_paths(
        self,
        graph: Dict[str, List[tuple]],
        start: str,
        end: str,
    ) -> List[List[tuple]]:
        """BFS로 경로 찾기"""
        if start == end:
            return []
        
        paths = []
        queue = deque([(start, [])])
        visited = {start}
        
        while queue:
            current, path = queue.popleft()
            
            if len(path) >= self.path_depth_limit:
                continue
            
            for target, sign, rel_id in graph.get(current, []):
                if target == end:
                    paths.append(path + [(current, target, rel_id, sign)])
                elif target not in visited:
                    visited.add(target)
                    queue.append((target, path + [(current, target, rel_id, sign)]))
        
        return paths
    
    def _calculate_path_sign(self, path: List[tuple]) -> Optional[str]:
        """경로의 combined sign 계산"""
        if not path:
            return None
        
        result = "+"
        for step in path:
            sign = step[3] if len(step) > 3 else "+"
            if sign == "-":
                result = "-" if result == "+" else "+"
            elif sign == "unknown":
                return None
        
        return result
