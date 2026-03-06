"""
L3. Student & Validator Trainer
Deterministic offline training metadata and evaluation.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.learning.models import (
    DatasetSnapshot,
    GoldSet,
    RunStatus,
    TrainingMetrics,
    TrainingRun,
)

logger = logging.getLogger(__name__)


class StudentValidatorTrainer:
    """Track training runs and evaluate datasets against goldsets deterministically."""

    def __init__(self):
        self._runs: Dict[str, TrainingRun] = {}
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
        base_version = self._current_versions.get(target, f"{target}_v1")
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
        logger.info("Created training run: %s for %s", run.run_id, target)
        return run

    def run_training(
        self,
        run_id: str,
        dataset: DatasetSnapshot,
        goldset: GoldSet,
    ) -> TrainingRun:
        run = self._runs.get(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        run.metrics_before = self._evaluate(dataset, goldset)
        logger.info("Training %s with %s samples", run.target, len(dataset.samples))
        run.metrics_after = self._evaluate(dataset, goldset)
        run.completed_at = datetime.now()
        run.status = RunStatus.PROPOSED
        return run

    def _evaluate(self, dataset: DatasetSnapshot, goldset: GoldSet) -> TrainingMetrics:
        dataset_labels = {
            (sample.text.strip(), sample.task_type.value): sample.labels
            for sample in dataset.samples
        }

        true_positive = 0
        false_negative = 0
        false_positive = 0

        for gold_sample in goldset.samples:
            key = (gold_sample.text.strip(), gold_sample.task_type.value)
            predicted = dataset_labels.get(key)
            if predicted is None:
                false_negative += 1
                continue

            if all(predicted.get(label_key) == label_value for label_key, label_value in gold_sample.gold_labels.items()):
                true_positive += 1
            else:
                false_negative += 1
                false_positive += 1

        matched_keys = {(sample.text.strip(), sample.task_type.value) for sample in goldset.samples}
        false_positive += len([key for key in dataset_labels if key not in matched_keys])

        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        f1 = (2 * precision * recall) / max(precision + recall, 1e-9)
        accuracy = true_positive / max(goldset.sample_count, 1)

        return TrainingMetrics(
            precision=precision,
            recall=recall,
            f1=f1,
            accuracy=accuracy,
            static_conflict_count=false_positive,
            drift_detection_rate=recall,
        )

    def get_run(self, run_id: str) -> Optional[TrainingRun]:
        return self._runs.get(run_id)

    def list_runs(
        self,
        target: Optional[str] = None,
        status: Optional[RunStatus] = None,
    ) -> List[Dict]:
        runs = list(self._runs.values())

        if target:
            runs = [run for run in runs if run.target == target]
        if status:
            runs = [run for run in runs if run.status == status]

        return [
            {
                "run_id": run.run_id,
                "target": run.target,
                "status": run.status.value,
                "dataset_version": run.dataset_version,
                "goldset_version": run.goldset_version,
                "base_version": run.base_model_version,
                "new_version": run.new_model_version,
                "f1_before": run.metrics_before.f1 if run.metrics_before else None,
                "f1_after": run.metrics_after.f1 if run.metrics_after else None,
                "started_at": run.started_at.isoformat(),
            }
            for run in runs
        ]

    def get_comparison(self, run_id: str) -> Optional[Dict]:
        run = self._runs.get(run_id)
        if not run or not run.metrics_before or not run.metrics_after:
            return None

        before = run.metrics_before
        after = run.metrics_after
        return {
            "run_id": run_id,
            "target": run.target,
            "metrics": {
                "precision": {"before": before.precision, "after": after.precision, "delta": after.precision - before.precision},
                "recall": {"before": before.recall, "after": after.recall, "delta": after.recall - before.recall},
                "f1": {"before": before.f1, "after": after.f1, "delta": after.f1 - before.f1},
                "accuracy": {"before": before.accuracy, "after": after.accuracy, "delta": after.accuracy - before.accuracy},
                "static_conflict": {
                    "before": before.static_conflict_count,
                    "after": after.static_conflict_count,
                    "delta": after.static_conflict_count - before.static_conflict_count,
                },
            },
        }

    def get_current_versions(self) -> Dict[str, str]:
        return self._current_versions.copy()

    def update_current_version(self, target: str, version: str):
        self._current_versions[target] = version

    def get_stats(self) -> Dict:
        status_counts = {}
        for run in self._runs.values():
            status_counts[run.status.value] = status_counts.get(run.status.value, 0) + 1

        return {
            "total_runs": len(self._runs),
            "status_distribution": status_counts,
            "current_versions": self._current_versions,
        }
