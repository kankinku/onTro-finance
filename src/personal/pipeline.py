"""
Personal Pipeline
전체 Personal Sector 워크플로우를 통합
"""
import logging
from typing import List, Optional, Dict

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination
from src.domain.models import DomainCandidate, DomainProcessResult
from src.domain.static_guard import StaticDomainGuard
from src.domain.dynamic_update import DynamicDomainUpdate
from src.personal.models import PersonalProcessResult, PersonalLabel
from src.personal.intake import PersonalCandidateIntake
from src.personal.pcs_classifier import PCSClassifier
from src.personal.pkg_update import PersonalKGUpdate
from src.personal.drift_promotion import PersonalDriftAnalyzer

logger = logging.getLogger(__name__)


class PersonalPipeline:
    """
    Personal Sector 통합 파이프라인
    
    Domain Rejected Edge
        → Personal Candidate Intake
        → PCS Classifier
        → Personal KG Update
        → Drift Analyzer
            → Domain Promotion (조건 충족 시)
    """
    
    def __init__(
        self,
        user_id: str = "default_user",
        static_guard: Optional[StaticDomainGuard] = None,
        dynamic_domain: Optional[DynamicDomainUpdate] = None,
    ):
        self.user_id = user_id
        
        # 모듈 초기화
        self.intake = PersonalCandidateIntake(user_id=user_id)
        self.pkg = PersonalKGUpdate()
        self.pcs = PCSClassifier(domain=dynamic_domain)
        self.drift_analyzer = PersonalDriftAnalyzer(
            pkg=self.pkg,
            static_guard=static_guard,
            dynamic_domain=dynamic_domain,
        )
        
        # 외부 연결
        self.static_guard = static_guard
        self.dynamic_domain = dynamic_domain
        
        # 통계
        self._stats = {
            "total": 0,
            "stored": 0,
            "strong_beliefs": 0,
            "weak_beliefs": 0,
            "noisy": 0,
            "promotion_candidates": 0,
        }
    
    def process_from_validation(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
    ) -> Optional[PersonalProcessResult]:
        """
        Validation에서 Personal로 직접 온 경우 처리
        """
        if validation_result.destination != ValidationDestination.PERSONAL_CANDIDATE:
            return None
        
        self._stats["total"] += 1
        
        # Intake
        candidate = self.intake.process_from_validation(
            edge, validation_result, resolved_entities
        )
        
        if not candidate:
            return None
        
        # PCS
        pcs_result = self.pcs.classify(candidate)
        
        # PKG Update
        relation_id, is_new = self.pkg.update(candidate, pcs_result)
        
        # 통계 업데이트
        self._update_stats(pcs_result.personal_label)
        
        # Drift 분석 (기존 관계인 경우)
        drift_result = None
        if not is_new:
            relation = self.pkg.get_relation(relation_id)
            if relation:
                drift_result = self.drift_analyzer.analyze(relation)
                if drift_result.is_promotion_candidate:
                    self._stats["promotion_candidates"] += 1
        
        return PersonalProcessResult(
            candidate_id=candidate.candidate_id,
            raw_edge_id=edge.raw_edge_id,
            stored_in_pkg=True,
            personal_weight=self._calculate_weight(pcs_result),
            personal_label=pcs_result.personal_label,
            intake_result=candidate,
            pcs_result=pcs_result,
            pkg_relation_id=relation_id,
            drift_result=drift_result,
            promotion_pending=drift_result.is_promotion_candidate if drift_result else False,
        )
    
    def process_from_domain_rejection(
        self,
        domain_candidate: DomainCandidate,
        domain_result: DomainProcessResult,
    ) -> PersonalProcessResult:
        """
        Domain에서 거부된 후보 처리
        """
        self._stats["total"] += 1
        
        # Intake
        candidate = self.intake.process_from_domain_rejection(
            domain_candidate, domain_result
        )
        
        # PCS
        pcs_result = self.pcs.classify(candidate)
        
        # PKG Update
        relation_id, is_new = self.pkg.update(candidate, pcs_result)
        
        # 통계 업데이트
        self._update_stats(pcs_result.personal_label)
        
        # Drift 분석
        drift_result = None
        relation = self.pkg.get_relation(relation_id)
        if relation:
            drift_result = self.drift_analyzer.analyze(relation)
            if drift_result.is_promotion_candidate:
                self._stats["promotion_candidates"] += 1
        
        return PersonalProcessResult(
            candidate_id=candidate.candidate_id,
            raw_edge_id=domain_candidate.raw_edge_id,
            stored_in_pkg=True,
            personal_weight=self._calculate_weight(pcs_result),
            personal_label=pcs_result.personal_label,
            intake_result=candidate,
            pcs_result=pcs_result,
            pkg_relation_id=relation_id,
            drift_result=drift_result,
            promotion_pending=drift_result.is_promotion_candidate if drift_result else False,
        )
    
    def _calculate_weight(self, pcs_result) -> float:
        """Weight 계산"""
        if pcs_result.personal_label == PersonalLabel.STRONG_BELIEF:
            return pcs_result.pcs_score
        elif pcs_result.personal_label == PersonalLabel.WEAK_BELIEF:
            return pcs_result.pcs_score * 0.5
        return pcs_result.pcs_score * 0.1
    
    def _update_stats(self, label: PersonalLabel):
        """통계 업데이트"""
        self._stats["stored"] += 1
        if label == PersonalLabel.STRONG_BELIEF:
            self._stats["strong_beliefs"] += 1
        elif label == PersonalLabel.WEAK_BELIEF:
            self._stats["weak_beliefs"] += 1
        else:
            self._stats["noisy"] += 1
    
    def run_drift_scan(self) -> Dict:
        """전체 Drift 스캔"""
        results = self.drift_analyzer.scan_all_relations()
        candidates = self.drift_analyzer.get_promotion_candidates()
        
        return {
            "scanned": len(results),
            "promotion_candidates": len(candidates),
            "candidates": [
                {
                    "relation_id": c.relation_id,
                    "head": c.head_name,
                    "tail": c.tail_name,
                    "pcs": c.pcs_score,
                    "occurrences": c.occurrence_count,
                }
                for c in candidates
            ],
        }
    
    def promote_candidates(self) -> int:
        """모든 승격 후보를 Domain으로 승격"""
        if not self.dynamic_domain:
            logger.warning("No dynamic domain connected, cannot promote")
            return 0
        
        candidates = self.drift_analyzer.get_promotion_candidates()
        promoted = 0
        
        for relation in candidates:
            if self.drift_analyzer.promote_to_domain(
                relation.relation_id, self.dynamic_domain
            ):
                promoted += 1
        
        logger.info(f"Promoted {promoted}/{len(candidates)} candidates to domain")
        return promoted
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        return {
            **self._stats,
            "pkg_stats": self.pkg.get_stats(),
            "pattern_stats": self.pcs.get_pattern_stats(),
        }
    
    def get_pkg(self) -> PersonalKGUpdate:
        """PKG 접근"""
        return self.pkg
    
    def reset_stats(self):
        """통계 초기화"""
        for key in self._stats:
            if isinstance(self._stats[key], int):
                self._stats[key] = 0
