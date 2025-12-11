"""Learning Layer 테스트"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.learning.models import TaskType, RunStatus, DataSource
from src.learning.dataset_builder import TrainingDatasetBuilder
from src.learning.goldset_manager import TeacherGoldsetManager
from src.learning.trainer import StudentValidatorTrainer
from src.learning.policy_learner import PolicyWeightLearner
from src.learning.deployment import ReviewDeploymentManager
from src.learning.dashboard import LearningDashboard


class TestDatasetBuilder:
    def test_build_dataset(self):
        builder = TrainingDatasetBuilder()
        builder.add_validation_log({"edge_id": "E1", "semantic_tag": "sem_wrong"})
        
        dataset = builder.build_dataset(TaskType.SEMANTIC_VALIDATION)
        assert dataset.sample_count >= 0
        assert dataset.frozen == True


class TestGoldsetManager:
    def test_create_goldset(self):
        manager = TeacherGoldsetManager()
        
        from src.learning.models import GoldSample
        samples = [GoldSample(
            text="금리가 오르면 주가가 떨어진다",
            task_type=TaskType.RELATION,
            gold_labels={"head": "금리", "tail": "주가", "sign": "-"},
        )]
        
        goldset = manager.create_goldset(TaskType.RELATION, samples)
        assert goldset.sample_count == 1
        assert manager.set_active_goldset(goldset.version) == True


class TestTrainer:
    def test_create_run(self):
        trainer = StudentValidatorTrainer()
        
        from src.learning.models import DatasetSnapshot, GoldSet
        dataset = DatasetSnapshot(version="ds_v1", task_type=TaskType.NER)
        goldset = GoldSet(version="gold_v1", task_type=TaskType.NER)
        
        run = trainer.create_run("student1", dataset, goldset)
        assert run.status == RunStatus.PROPOSED
        assert run.target == "student1"


class TestPolicyLearner:
    def test_create_variant(self):
        learner = PolicyWeightLearner()
        base = learner.get_active_policy()
        
        new = learner.create_policy_variant(
            base.version, ees_adj={"domain": 0.05}
        )
        assert new.ees_weights["domain"] > base.ees_weights["domain"]


class TestDeploymentManager:
    def test_deployment_flow(self):
        manager = ReviewDeploymentManager()
        
        bundle = manager.create_bundle(
            "s1_v1", "s2_v1", "sign_v1", "sem_v1", "pol_v1"
        )
        assert bundle.status == RunStatus.PROPOSED
        
        manager.review_bundle(bundle.version, approved=True)
        assert manager._bundles[bundle.version].status == RunStatus.REVIEWED
        
        manager.deploy_bundle(bundle.version)
        assert manager.get_active_bundle().version == bundle.version


class TestDashboard:
    def test_summary(self):
        dashboard = LearningDashboard()
        summary = dashboard.get_summary()
        assert "version" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
