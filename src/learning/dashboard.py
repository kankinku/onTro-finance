"""
Learning Dashboard
"학습 상태를 확인하고 리뷰하기 쉽게 만드는 장치"

역할: **Read Only** - 상태 변경 없음
- 조회만 담당
- Trainer/Deployment/Logs를 조회해 Summary 생성
- 상태 변경은 Deployment가 담당

포함: Version Dashboard, Training Run Registry, Quality Reports
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from src.learning.models import QualityReport

logger = logging.getLogger(__name__)


class LearningDashboard:
    """
    Learning Dashboard - 학습 상태 모니터링
    
    Read Only 모듈
    - 어떠한 상태도 바꾸지 않음
    - 상태 변경은 Deployment가 담당
    """
    
    def __init__(
        self, dataset_builder=None, goldset_manager=None,
        trainer=None, policy_learner=None, deployment=None,
        domain=None, personal=None,
    ):
        self.dataset_builder = dataset_builder
        self.goldset_manager = goldset_manager
        self.trainer = trainer
        self.policy_learner = policy_learner
        self.deployment = deployment
        self.domain = domain
        self.personal = personal
        self._reports: List[QualityReport] = []
    
    def get_version_dashboard(self) -> Dict:
        """현재 온라인 상태"""
        active_bundle = self.deployment.get_active_bundle() if self.deployment else None
        return {
            "active_bundle": active_bundle.version if active_bundle else None,
            "student1": active_bundle.student1_version if active_bundle else None,
            "student2": active_bundle.student2_version if active_bundle else None,
            "sign_validator": active_bundle.sign_validator_version if active_bundle else None,
            "semantic_validator": active_bundle.semantic_validator_version if active_bundle else None,
            "policy": active_bundle.policy_version if active_bundle else None,
            "deployed_at": active_bundle.deployed_at.isoformat() if active_bundle and active_bundle.deployed_at else None,
        }
    
    def get_training_registry(self, limit: int = 10) -> List[Dict]:
        """Training Run 목록"""
        if not self.trainer:
            return []
        return self.trainer.list_runs()[:limit]
    
    def generate_domain_quality_report(self) -> QualityReport:
        """Domain KG 품질 리포트"""
        metrics = {"total_relations": 0, "avg_conf": 0, "drift_candidates": 0}
        highlights, warnings = [], []
        
        if self.domain:
            relations = self.domain.get_all_relations()
            metrics["total_relations"] = len(relations)
            if relations:
                metrics["avg_conf"] = sum(r.domain_conf for r in relations.values()) / len(relations)
                drift = sum(1 for r in relations.values() if r.drift_flag)
                metrics["drift_candidates"] = drift
                if drift > 5:
                    warnings.append(f"Drift 후보 {drift}개 발견")
        
        report = QualityReport(
            report_type="domain",
            period_start=datetime.now() - timedelta(days=7),
            period_end=datetime.now(),
            metrics=metrics, highlights=highlights, warnings=warnings,
        )
        self._reports.append(report)
        return report
    
    def generate_personal_quality_report(self) -> QualityReport:
        """Personal KG 품질 리포트"""
        metrics = {"total_relations": 0, "strong": 0, "weak": 0}
        
        if self.personal:
            stats = self.personal.get_stats()
            metrics["total_relations"] = stats.get("total_relations", 0)
            metrics["strong"] = stats.get("labels", {}).get("strong", 0)
            metrics["weak"] = stats.get("labels", {}).get("weak", 0)
        
        report = QualityReport(
            report_type="personal",
            period_start=datetime.now() - timedelta(days=7),
            period_end=datetime.now(),
            metrics=metrics,
        )
        self._reports.append(report)
        return report
    
    def get_summary(self) -> Dict:
        """전체 요약"""
        return {
            "version": self.get_version_dashboard(),
            "datasets": self.dataset_builder.get_stats() if self.dataset_builder else {},
            "goldsets": self.goldset_manager.get_stats() if self.goldset_manager else {},
            "training": self.trainer.get_stats() if self.trainer else {},
            "policies": self.policy_learner.get_stats() if self.policy_learner else {},
            "deployment": self.deployment.get_stats() if self.deployment else {},
        }
