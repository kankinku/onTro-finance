"""
Domain Pipeline - Refactored for Transaction
"""
import logging
from typing import List, Optional, Dict, Any

from src.bootstrap import get_transaction_manager
from src.storage.transaction_manager import Transaction
from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination
from src.domain.models import (
    DomainCandidate,
    DomainProcessResult,
    DomainAction,
    ConflictResolution,
)
from src.domain.intake import DomainCandidateIntake
from src.domain.static_guard import StaticDomainGuard
from src.domain.dynamic_update import DynamicDomainUpdate
from src.domain.conflict_analyzer import ConflictAnalyzer
from src.domain.drift_detector import DomainDriftDetector

logger = logging.getLogger(__name__)


class DomainPipeline:
    """
    Domain Sector 통합 파이프라인
    Transaction 적용
    
    Validation Passed Edge
        → Domain Candidate Intake
        → Static Domain Guard
        → Dynamic Domain Update (TX)
        → Conflict Analyzer
        → Drift Detector (TX)
    """
    
    def __init__(self):
        # 모듈 초기화 (자동으로 Adapter 연결됨)
        self.intake = DomainCandidateIntake()
        self.static_guard = StaticDomainGuard()
        self.dynamic_update = DynamicDomainUpdate()
        self.conflict_analyzer = ConflictAnalyzer(self.dynamic_update)
        self.drift_detector = DomainDriftDetector(self.dynamic_update)
        
        self.tx_manager = get_transaction_manager()
        
        # 통계
        self._stats = {
            "total": 0,
            "domain_accepted": 0,
            "personal_redirected": 0,
            "logged": 0,
            "static_matched": 0,
            "static_conflict": 0,
            "new_relations": 0,
            "updated_relations": 0,
            "conflicts_resolved": 0,
        }
        
        # Personal 후보 저장
        self._personal_candidates: List[DomainCandidate] = []
    
    def process(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
        tx: Optional[Transaction] = None,
    ) -> DomainProcessResult:
        """
        단일 Edge Domain 처리
        Args:
            tx: 트랜잭션 객체 (배치 처리 시 전달)
        """
        self._stats["total"] += 1
        
        # Step 1: Intake
        candidate = self.intake.process(edge, validation_result, resolved_entities)
        
        if candidate is None:
            if validation_result.destination == ValidationDestination.PERSONAL_CANDIDATE:
                self._stats["personal_redirected"] += 1
                return DomainProcessResult(candidate_id="", raw_edge_id=edge.raw_edge_id, final_destination="personal")
            else:
                self._stats["logged"] += 1
                return DomainProcessResult(candidate_id="", raw_edge_id=edge.raw_edge_id, final_destination="log")
        
        # Step 2: Static Guard
        static_result = self.static_guard.check(candidate)
        
        if static_result.static_conflict:
            self._stats["static_conflict"] += 1
            self._personal_candidates.append(candidate)
            return DomainProcessResult(
                candidate_id=candidate.candidate_id, raw_edge_id=edge.raw_edge_id, final_destination="personal",
                intake_result=candidate, static_result=static_result
            )
        
        if static_result.action == DomainAction.STRENGTHEN_STATIC:
            self._stats["static_matched"] += 1
        
        # Step 3: Dynamic Update (with TX)
        dynamic_result = self.dynamic_update.update(candidate, tx=tx)
        
        if dynamic_result.is_new:
            self._stats["new_relations"] += 1
        else:
            self._stats["updated_relations"] += 1
        
        # Step 4: Conflict Analysis
        conflict_result = None
        drift_result = None
        
        if dynamic_result.conflict_pending:
            relation = self.dynamic_update.get_relation(dynamic_result.relation_id)
            if relation:
                conflict_result = self.conflict_analyzer.analyze(candidate, relation)
                self._stats["conflicts_resolved"] += 1
                
                if conflict_result.resolution == ConflictResolution.TO_PERSONAL:
                    self._personal_candidates.append(candidate)
                    return DomainProcessResult(
                        candidate_id=candidate.candidate_id, raw_edge_id=edge.raw_edge_id, final_destination="personal",
                        intake_result=candidate, static_result=static_result,
                        dynamic_result=dynamic_result, conflict_result=conflict_result
                    )
                elif conflict_result.resolution == ConflictResolution.TO_DRIFT:
                    # Drift 감지 (with TX)
                    drift_result = self.drift_detector.detect(relation, tx=tx)
                    return DomainProcessResult(
                        candidate_id=candidate.candidate_id, raw_edge_id=edge.raw_edge_id, final_destination="domain",
                        intake_result=candidate, static_result=static_result,
                        dynamic_result=dynamic_result, conflict_result=conflict_result,
                        drift_result=drift_result, domain_relation_id=dynamic_result.relation_id
                    )
        
        self._stats["domain_accepted"] += 1
        
        return DomainProcessResult(
            candidate_id=candidate.candidate_id,
            raw_edge_id=edge.raw_edge_id,
            final_destination="domain",
            intake_result=candidate,
            static_result=static_result,
            dynamic_result=dynamic_result,
            conflict_result=conflict_result,
            drift_result=drift_result,
            domain_relation_id=dynamic_result.relation_id,
        )
    
    def process_batch(
        self,
        edges: List[RawEdge],
        validation_results: Dict[str, ValidationResult],
        resolved_entities: List[ResolvedEntity],
    ) -> List[DomainProcessResult]:
        """
        배치 처리 - 전체를 트랜잭션으로 묶음
        """
        results = []
        
        # 트랜잭션 시작
        with self.tx_manager.transaction() as tx:
            for edge in edges:
                v_result = validation_results.get(edge.raw_edge_id)
                if v_result and v_result.validation_passed:
                    result = self.process(edge, v_result, resolved_entities, tx=tx)
                    results.append(result)
        
        logger.info(f"Domain batch complete: {self._stats}")
        return results
    
    # ... stats methods ...
    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()
    
    def get_personal_candidates(self) -> List[DomainCandidate]:
        return self._personal_candidates.copy()
    
    def get_dynamic_domain(self) -> DynamicDomainUpdate:
        return self.dynamic_update
    
    def get_drift_candidates(self) -> Dict:
        return self.drift_detector.get_drift_candidates()
    
    def run_drift_scan(self):
        return self.drift_detector.scan_all_relations()
    
    def reset_stats(self):
        for key in self._stats:
            self._stats[key] = 0
