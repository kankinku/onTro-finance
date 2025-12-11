"""
L4. Policy / Weight Learner
"EES, PCS, Threshold 등 시스템 파라미터를 데이터 기반으로 최적화"
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime

from src.learning.models import PolicyConfig

logger = logging.getLogger(__name__)


class PolicyWeightLearner:
    """L4. Policy / Weight Learner"""
    
    def __init__(self):
        self._policies: Dict[str, PolicyConfig] = {}
        self._active_policy: Optional[str] = None
        self._optimization_logs: List[Dict] = []
        self._create_default_policy()
    
    def _create_default_policy(self):
        default = PolicyConfig(version="policy_v1")
        self._policies[default.version] = default
        self._active_policy = default.version
        default.is_active = True
    
    def get_active_policy(self) -> Optional[PolicyConfig]:
        if self._active_policy:
            return self._policies.get(self._active_policy)
        return None
    
    def create_policy_variant(
        self, base_version: str,
        ees_adj: Optional[Dict[str, float]] = None,
        pcs_adj: Optional[Dict[str, float]] = None,
        thresh_adj: Optional[Dict[str, float]] = None,
    ) -> PolicyConfig:
        base = self._policies.get(base_version) or self.get_active_policy()
        version = f"policy_v{len(self._policies) + 1}"
        
        new_policy = PolicyConfig(version=version)
        new_policy.ees_weights = base.ees_weights.copy()
        new_policy.pcs_weights = base.pcs_weights.copy()
        new_policy.thresholds = base.thresholds.copy()
        
        if ees_adj:
            for k, delta in ees_adj.items():
                if k in new_policy.ees_weights:
                    new_policy.ees_weights[k] = max(0, min(1, new_policy.ees_weights[k] + delta))
        
        if pcs_adj:
            for k, delta in pcs_adj.items():
                if k in new_policy.pcs_weights:
                    new_policy.pcs_weights[k] = max(0, min(1, new_policy.pcs_weights[k] + delta))
        
        if thresh_adj:
            for k, delta in thresh_adj.items():
                if k in new_policy.thresholds:
                    new_policy.thresholds[k] = max(0, min(1, new_policy.thresholds[k] + delta))
        
        self._policies[version] = new_policy
        logger.info(f"Created policy variant: {version}")
        return new_policy
    
    def set_active_policy(self, version: str) -> bool:
        if version not in self._policies:
            return False
        for p in self._policies.values():
            p.is_active = False
        self._policies[version].is_active = True
        self._active_policy = version
        return True
    
    def compare_policies(self, v1: str, v2: str) -> Optional[Dict]:
        p1, p2 = self._policies.get(v1), self._policies.get(v2)
        if not p1 or not p2:
            return None
        return {
            "ees": {k: {"v1": p1.ees_weights.get(k), "v2": p2.ees_weights.get(k)} for k in p1.ees_weights},
            "pcs": {k: {"v1": p1.pcs_weights.get(k), "v2": p2.pcs_weights.get(k)} for k in p1.pcs_weights},
        }
    
    def list_policies(self) -> List[Dict]:
        return [{"version": p.version, "is_active": p.is_active} for p in self._policies.values()]
    
    def get_stats(self) -> Dict:
        return {"total": len(self._policies), "active": self._active_policy}
