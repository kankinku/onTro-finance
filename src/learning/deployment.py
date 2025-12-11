"""
L5. Review & Deployment Manager
"학습 결과를 실제 시스템에 반영할지 말지 최종 컨트롤"

역할: **Write 전용** - ConfigBundle 상태 전이 담당
- PROPOSED -> REVIEWED -> DEPLOYED / ROLLED_BACK
- DB에 상태 쓰기
- 조회는 Dashboard가 담당

규칙: 모든 변경은 Proposal -> Review -> Apply 구조
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime

from src.learning.models import ConfigBundle, TrainingRun, RunStatus

logger = logging.getLogger(__name__)


class ReviewDeploymentManager:
    """
    L5. Review & Deployment Manager
    
    Write 전용 모듈
    - 상태 전이: PROPOSED -> REVIEWED -> DEPLOYED / ROLLED_BACK
    - 조회는 Dashboard가 담당
    """
    
    def __init__(self):
        self._bundles: Dict[str, ConfigBundle] = {}
        self._active_bundle: Optional[str] = None
        self._deployment_history: List[Dict] = []
    
    def create_bundle(
        self, student1_v: str, student2_v: str,
        sign_v: str, semantic_v: str, policy_v: str, schema_v: str = "schema_v1",
    ) -> ConfigBundle:
        version = f"bundle_v{len(self._bundles) + 1}"
        bundle = ConfigBundle(
            version=version,
            student1_version=student1_v, student2_version=student2_v,
            sign_validator_version=sign_v, semantic_validator_version=semantic_v,
            policy_version=policy_v, schema_version=schema_v,
        )
        self._bundles[version] = bundle
        logger.info(f"Created bundle: {version}")
        return bundle
    
    def review_bundle(self, version: str, approved: bool, notes: str = "", reviewer: str = "human") -> bool:
        bundle = self._bundles.get(version)
        if not bundle:
            return False
        bundle.status = RunStatus.REVIEWED if approved else RunStatus.ROLLED_BACK
        bundle.review_notes = notes
        logger.info(f"Bundle {version} reviewed: approved={approved}")
        return True
    
    def deploy_bundle(self, version: str) -> bool:
        bundle = self._bundles.get(version)
        if not bundle or bundle.status != RunStatus.REVIEWED:
            return False
        
        if self._active_bundle:
            old = self._bundles.get(self._active_bundle)
            if old:
                old.status = RunStatus.ROLLED_BACK
        
        bundle.status = RunStatus.DEPLOYED
        bundle.deployed_at = datetime.now()
        self._active_bundle = version
        
        self._deployment_history.append({
            "version": version, "deployed_at": datetime.now().isoformat(),
            "previous": self._active_bundle,
        })
        logger.info(f"Deployed bundle: {version}")
        return True
    
    def rollback(self, to_version: str) -> bool:
        if to_version not in self._bundles:
            return False
        
        current = self._bundles.get(self._active_bundle)
        if current:
            current.status = RunStatus.ROLLED_BACK
        
        self._bundles[to_version].status = RunStatus.DEPLOYED
        self._active_bundle = to_version
        logger.info(f"Rolled back to: {to_version}")
        return True
    
    def get_active_bundle(self) -> Optional[ConfigBundle]:
        return self._bundles.get(self._active_bundle) if self._active_bundle else None
    
    def list_bundles(self) -> List[Dict]:
        return [
            {"version": b.version, "status": b.status.value,
             "deployed_at": b.deployed_at.isoformat() if b.deployed_at else None}
            for b in self._bundles.values()
        ]
    
    def get_stats(self) -> Dict:
        return {"total": len(self._bundles), "active": self._active_bundle,
                "deployments": len(self._deployment_history)}
