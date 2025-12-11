"""
Static Domain Guard Module
"이 엣지가 절대 불변 지식인 Static Domain과 충돌하는가?"

Static Domain:
- 경제학 기본 법칙
- 금리-채권가격 역관계
- 수요공급 법칙
등 절대 변경 불가능한 규칙
"""
import logging
from typing import Dict, Any, Optional, List

from src.domain.models import DomainCandidate, StaticGuardResult, DomainAction
from config.settings import get_settings

logger = logging.getLogger(__name__)


class StaticDomainGuard:
    """
    Static Domain Guard Module
    Static Domain과의 충돌 검사
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._static_rules = self._load_static_rules()
        self._rules_map = self._build_rules_map()
    
    def _load_static_rules(self) -> List[Dict[str, Any]]:
        """Static rules 로드"""
        try:
            data = self.settings.load_yaml_config("static_domain")
            return data.get("static_rules", [])
        except FileNotFoundError:
            logger.warning("Static domain config not found")
            return []
    
    def _build_rules_map(self) -> Dict[tuple, Dict[str, Any]]:
        """(head, tail) -> rule 맵 생성"""
        rules_map = {}
        for rule in self._static_rules:
            head = rule.get("head")
            tail = rule.get("tail")
            if head and tail:
                rules_map[(head, tail)] = rule
        return rules_map
    
    def check(self, candidate: DomainCandidate) -> StaticGuardResult:
        """
        Static Domain 충돌 검사
        
        Args:
            candidate: Domain Candidate
        
        Returns:
            StaticGuardResult
        """
        head_id = candidate.head_canonical_id
        tail_id = candidate.tail_canonical_id
        
        # Static rule 조회
        static_rule = self._rules_map.get((head_id, tail_id))
        
        if static_rule is None:
            # Static Domain에 해당 관계 없음 → 통과
            return StaticGuardResult(
                candidate_id=candidate.candidate_id,
                static_pass=True,
                static_conflict=False,
                action=DomainAction.CREATE_NEW,
            )
        
        # Static rule 존재 → 비교
        static_polarity = static_rule.get("polarity")
        static_relation = static_rule.get("relation")
        static_certainty = static_rule.get("certainty", 1.0)
        
        # Polarity 비교
        if static_polarity and candidate.polarity != "unknown":
            if candidate.polarity != static_polarity:
                # 충돌!
                logger.warning(
                    f"Static conflict: {candidate.candidate_id} "
                    f"expected {static_polarity}, got {candidate.polarity}"
                )
                return StaticGuardResult(
                    candidate_id=candidate.candidate_id,
                    static_pass=False,
                    static_conflict=True,
                    action=DomainAction.REJECT_TO_PERSONAL,
                    conflict_rule_id=static_rule.get("rule_id"),
                    expected_polarity=static_polarity,
                    actual_polarity=candidate.polarity,
                    conflict_reason=f"Polarity conflict with static rule: {static_rule.get('description', '')}",
                )
        
        # Relation type 비교 (엄격)
        if static_relation and candidate.relation_type != static_relation:
            # Static에서 정의된 관계 타입과 다름
            # 이건 더 유연하게 처리 (Affect vs Cause는 허용 가능한 경우도 있음)
            if static_certainty >= 0.95:
                # 높은 확실성의 규칙에서만 타입 충돌 체크
                logger.debug(
                    f"Relation type mismatch but allowing: "
                    f"static={static_relation}, candidate={candidate.relation_type}"
                )
        
        # 일치 → Static evidence 강화
        logger.info(f"Static match: {candidate.candidate_id} matches rule {static_rule.get('rule_id')}")
        return StaticGuardResult(
            candidate_id=candidate.candidate_id,
            static_pass=True,
            static_conflict=False,
            action=DomainAction.STRENGTHEN_STATIC,
            conflict_rule_id=static_rule.get("rule_id"),
            expected_polarity=static_polarity,
            actual_polarity=candidate.polarity,
        )
    
    def get_static_rule(self, head_id: str, tail_id: str) -> Optional[Dict[str, Any]]:
        """특정 관계의 Static rule 조회"""
        return self._rules_map.get((head_id, tail_id))
    
    def is_static_relation(self, head_id: str, tail_id: str) -> bool:
        """Static 관계 여부 확인"""
        return (head_id, tail_id) in self._rules_map
