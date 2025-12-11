"""
L3. Student & Validator Trainer
"Student1/2 + Validator를 실제로 학습시키는 모듈"

학습 대상:
- Student1 (NER)
- Student2 (Relation Extraction)
- Sign Validator
- Semantic Validator

모든 학습은 run 단위로 기록됨
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.learning.models import (
    TrainingRun, TrainingMetrics, DatasetSnapshot, GoldSet, 
    TaskType, RunStatus
)

logger = logging.getLogger(__name__)


class StudentValidatorTrainer:
    """
    L3. Student & Validator Trainer
    모델 학습 및 평가
    """
    
    def __init__(self):
        # 학습 Run 저장
        self._runs: Dict[str, TrainingRun] = {}
        
        # 현재 모델 버전
        self._current_versions = {
            "student1": "student1_v1",
            "student2": "student2_v1",
            "sign_validator": "sign_validator_v1",
            "semantic_validator": "semantic_validator_v1",
        }
    
    def create_run(
        self,
        target: str,
        dataset: DatasetSnapshot,
        goldset: GoldSet,
        hyperparameters: Optional[Dict] = None,
    ) -> TrainingRun:
        """
        학습 Run 생성
        
        Args:
            target: 학습 대상 (student1, student2, ...)
            dataset: 학습 데이터셋
            goldset: 평가용 Gold Set
            hyperparameters: 하이퍼파라미터
        
        Returns:
            TrainingRun
        """
        base_version = self._current_versions.get(target, f"{target}_v1")
        
        # 새 버전 번호
        version_num = int(base_version.split("_v")[-1]) + 1
        new_version = f"{target}_v{version_num}"
        
        run = TrainingRun(
            target=target,
            dataset_version=dataset.version,
            goldset_version=goldset.version,
            hyperparameters=hyperparameters or {},
            base_model_version=base_version,
            new_model_version=new_version,
            status=RunStatus.PROPOSED,
        )
        
        self._runs[run.run_id] = run
        
        logger.info(f"Created training run: {run.run_id} for {target}")
        return run
    
    def run_training(
        self,
        run_id: str,
        dataset: DatasetSnapshot,
        goldset: GoldSet,
    ) -> TrainingRun:
        """
        학습 실행 (시뮬레이션)
        
        실제 구현에서는 여기서 모델 학습이 수행됨
        """
        run = self._runs.get(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        # Before 평가
        run.metrics_before = self._evaluate(run.target, goldset, run.base_model_version)
        
        # 학습 시뮬레이션 (실제로는 모델 학습)
        logger.info(f"Training {run.target} with {len(dataset.samples)} samples...")
        
        # After 평가 (개선된 것으로 시뮬레이션)
        run.metrics_after = self._simulate_improvement(run.metrics_before)
        
        run.completed_at = datetime.now()
        run.status = RunStatus.PROPOSED
        
        logger.info(
            f"Training complete: {run.run_id}, "
            f"F1: {run.metrics_before.f1:.3f} -> {run.metrics_after.f1:.3f}"
        )
        
        return run
    
    def _evaluate(
        self,
        target: str,
        goldset: GoldSet,
        model_version: str,
    ) -> TrainingMetrics:
        """
        Gold Set으로 평가 (시뮬레이션)
        """
        # 실제 구현에서는 모델 예측 후 Gold와 비교
        # 여기서는 시뮬레이션
        import random
        
        metrics = TrainingMetrics(
            precision=0.75 + random.uniform(0, 0.1),
            recall=0.70 + random.uniform(0, 0.1),
            f1=0.72 + random.uniform(0, 0.1),
            accuracy=0.78 + random.uniform(0, 0.1),
            static_conflict_count=random.randint(0, 10),
            drift_detection_rate=0.6 + random.uniform(0, 0.2),
        )
        
        return metrics
    
    def _simulate_improvement(self, before: TrainingMetrics) -> TrainingMetrics:
        """개선 시뮬레이션"""
        import random
        
        improvement = random.uniform(0.02, 0.08)
        
        return TrainingMetrics(
            precision=min(0.99, before.precision + improvement),
            recall=min(0.99, before.recall + improvement),
            f1=min(0.99, before.f1 + improvement),
            accuracy=min(0.99, before.accuracy + improvement),
            static_conflict_count=max(0, before.static_conflict_count - random.randint(1, 3)),
            drift_detection_rate=min(0.99, before.drift_detection_rate + improvement * 0.5),
        )
    
    def get_run(self, run_id: str) -> Optional[TrainingRun]:
        """Run 조회"""
        return self._runs.get(run_id)
    
    def list_runs(
        self,
        target: Optional[str] = None,
        status: Optional[RunStatus] = None,
    ) -> List[Dict]:
        """Run 목록"""
        runs = list(self._runs.values())
        
        if target:
            runs = [r for r in runs if r.target == target]
        if status:
            runs = [r for r in runs if r.status == status]
        
        return [
            {
                "run_id": r.run_id,
                "target": r.target,
                "status": r.status.value,
                "dataset_version": r.dataset_version,
                "goldset_version": r.goldset_version,
                "base_version": r.base_model_version,
                "new_version": r.new_model_version,
                "f1_before": r.metrics_before.f1 if r.metrics_before else None,
                "f1_after": r.metrics_after.f1 if r.metrics_after else None,
                "started_at": r.started_at.isoformat(),
            }
            for r in runs
        ]
    
    def get_comparison(self, run_id: str) -> Optional[Dict]:
        """Before/After 비교"""
        run = self._runs.get(run_id)
        if not run or not run.metrics_before or not run.metrics_after:
            return None
        
        before = run.metrics_before
        after = run.metrics_after
        
        return {
            "run_id": run_id,
            "target": run.target,
            "metrics": {
                "precision": {
                    "before": before.precision,
                    "after": after.precision,
                    "delta": after.precision - before.precision,
                },
                "recall": {
                    "before": before.recall,
                    "after": after.recall,
                    "delta": after.recall - before.recall,
                },
                "f1": {
                    "before": before.f1,
                    "after": after.f1,
                    "delta": after.f1 - before.f1,
                },
                "accuracy": {
                    "before": before.accuracy,
                    "after": after.accuracy,
                    "delta": after.accuracy - before.accuracy,
                },
                "static_conflict": {
                    "before": before.static_conflict_count,
                    "after": after.static_conflict_count,
                    "delta": after.static_conflict_count - before.static_conflict_count,
                },
            },
        }
    
    def get_current_versions(self) -> Dict[str, str]:
        """현재 모델 버전"""
        return self._current_versions.copy()
    
    def update_current_version(self, target: str, version: str):
        """현재 버전 업데이트 (deploy 시)"""
        self._current_versions[target] = version
    
    def get_stats(self) -> Dict:
        """통계"""
        status_counts = {}
        for r in self._runs.values():
            status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1
        
        return {
            "total_runs": len(self._runs),
            "status_distribution": status_counts,
            "current_versions": self._current_versions,
        }
