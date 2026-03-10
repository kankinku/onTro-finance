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
from src.learning.event_store import LearningEventStore
from src.learning.offline_runner import _build_dataset, _evaluate_dataset


class TestDatasetBuilder:
    def test_build_dataset(self):
        builder = TrainingDatasetBuilder()
        builder.add_validation_log({"edge_id": "E1", "semantic_tag": "sem_wrong"})

        dataset = builder.build_dataset(TaskType.SEMANTIC_VALIDATION)
        assert dataset.sample_count >= 0
        assert dataset.frozen == True

    def test_build_relation_dataset_from_council_logs(self):
        builder = TrainingDatasetBuilder()
        builder.add_council_log(
            {
                "candidate_id": "rc_001",
                "chunk_id": "chunk_01",
                "citation_text": "Higher policy rates pressure growth stocks.",
                "head_entity_id": "Policy_Rate",
                "tail_entity_id": "Growth_Stocks",
                "final_relation_type": "pressures",
                "final_polarity": "negative",
                "final_confidence": 0.82,
                "status": "COUNCIL_APPROVED",
                "source_document_id": "doc_001",
                "council_case_id": "case_001",
            }
        )
        builder.add_council_log(
            {
                "candidate_id": "rc_auto_001",
                "chunk_id": "chunk_02",
                "citation_text": "Falling oil supports airlines.",
                "head_entity_id": "Oil",
                "tail_entity_id": "Airlines",
                "final_relation_type": "supports",
                "final_polarity": "positive",
                "final_confidence": 0.9,
                "status": "AUTO_APPROVED",
                "source_document_id": "doc_002",
            }
        )

        dataset = builder.build_dataset(
            TaskType.RELATION, include_domain=False, include_personal=False, include_logs=False
        )

        assert dataset.sample_count == 2
        assert dataset.samples[0].source == DataSource.COUNCIL_REVIEW
        assert dataset.samples[0].labels["council_reviewed"] is True
        assert dataset.samples[0].metadata["source_document_id"] == "doc_001"
        assert dataset.provenance_summary["unique_source_documents"] == 2
        assert dataset.provenance_summary["council_reviewed_samples"] == 1
        assert dataset.provenance_summary["auto_approved_samples"] == 1


class TestGoldsetManager:
    def test_create_goldset(self):
        manager = TeacherGoldsetManager()

        from src.learning.models import GoldSample

        samples = [
            GoldSample(
                text="금리가 오르면 주가가 떨어진다",
                task_type=TaskType.RELATION,
                gold_labels={"head": "금리", "tail": "주가", "sign": "-"},
            )
        ]

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
        assert base is not None

        new = learner.create_policy_variant(base.version, ees_adj={"domain": 0.05})
        assert new.ees_weights["domain"] > base.ees_weights["domain"]


class TestDeploymentManager:
    def test_deployment_flow(self):
        manager = ReviewDeploymentManager()

        bundle = manager.create_bundle("s1_v1", "s2_v1", "sign_v1", "sem_v1", "pol_v1")
        assert bundle.status == RunStatus.PROPOSED

        manager.review_bundle(bundle.version, approved=True)
        assert manager._bundles[bundle.version].status == RunStatus.REVIEWED

        manager.deploy_bundle(bundle.version)
        active_bundle = manager.get_active_bundle()
        assert active_bundle is not None
        assert active_bundle.version == bundle.version


class TestDashboard:
    def test_summary(self):
        dashboard = LearningDashboard()
        summary = dashboard.get_summary()
        assert "version" in summary


class TestLearningEventStore:
    def test_append_and_count(self, tmp_path):
        store = LearningEventStore(tmp_path)
        store.append("validation", {"edge_id": "E1"})
        store.append("query", {"question": "What moves gold?"})

        assert store.count("validation") == 1
        assert store.counts()["query"] == 1

    def test_counts_include_ingest_events(self, tmp_path):
        store = LearningEventStore(tmp_path)
        store.append("ingest", {"doc_id": "doc_001"})

        assert store.count("ingest") == 1
        assert store.counts()["ingest"] == 1

    def test_upsert_document_persists_and_replaces_by_doc_id(self, tmp_path):
        store = LearningEventStore(tmp_path)

        first = store.upsert_document(
            {"doc_id": "doc_001", "title": "Macro Note", "source_type": "research_note"}
        )
        second = store.upsert_document(
            {
                "doc_id": "doc_001",
                "title": "Updated Macro Note",
                "source_type": "research_note",
                "edge_count": 3,
            }
        )

        assert store.document_count() == 1
        assert store.counts()["documents"] == 1
        assert first["doc_id"] == "doc_001"
        assert second["title"] == "Updated Macro Note"
        stored = store.get_document("doc_001")
        assert stored is not None
        assert stored["edge_count"] == 3

    def test_read_ignores_corrupted_final_jsonl_line_and_quarantines_it(self, tmp_path):
        store = LearningEventStore(tmp_path)
        event_path = store._event_path("validation")
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_path.write_text(
            '{"event_type": "validation", "edge_id": "E1"}\n{"event_type": "validation", "edge_id": ',
            encoding="utf-8",
        )

        rows = store.read("validation")

        assert len(rows) == 1
        assert rows[0]["edge_id"] == "E1"
        quarantine = event_path.with_suffix(event_path.suffix + ".corrupt")
        assert quarantine.exists()

    def test_replace_documents_uses_atomic_rewrite(self, tmp_path):
        store = LearningEventStore(tmp_path)
        store.replace_documents(
            [
                {"doc_id": "doc_001", "title": "One"},
                {"doc_id": "doc_002", "title": "Two"},
            ]
        )

        rows = store.read_documents()

        assert [row["doc_id"] for row in rows] == ["doc_001", "doc_002"]


class TestOfflineEvaluation:
    def test_evaluate_dataset_matches_goldset(self):
        from src.learning.models import DatasetSnapshot, GoldSample, GoldSet, TrainingSample

        dataset = DatasetSnapshot(
            version="ds_v1",
            task_type=TaskType.RELATION,
            samples=[
                TrainingSample(
                    text="Higher policy rates pressure growth stocks.",
                    task_type=TaskType.RELATION,
                    labels={"relation_type": "pressures", "sign": "negative"},
                    source=DataSource.COUNCIL_REVIEW,
                    label_confidence=0.9,
                )
            ],
            sample_count=1,
        )
        goldset = GoldSet(
            version="gold_v1",
            task_type=TaskType.RELATION,
            samples=[
                GoldSample(
                    text="Higher policy rates pressure growth stocks.",
                    task_type=TaskType.RELATION,
                    gold_labels={"relation_type": "pressures", "sign": "negative"},
                )
            ],
            sample_count=1,
        )

        metrics = _evaluate_dataset(dataset, goldset)

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.matched_samples == 1
        assert metrics.unexpected_samples == 0
        assert metrics.confusion_matrix == {
            "relation_type:pressures": {"relation_type:pressures": 1}
        }

    def test_evaluate_dataset_reports_mismatches_and_unexpected_predictions(self):
        from src.learning.models import DatasetSnapshot, GoldSample, GoldSet, TrainingSample

        dataset = DatasetSnapshot(
            version="ds_v1",
            task_type=TaskType.RELATION,
            samples=[
                TrainingSample(
                    text="Higher policy rates pressure growth stocks.",
                    task_type=TaskType.RELATION,
                    labels={"relation_type": "supports", "sign": "positive"},
                    source=DataSource.COUNCIL_REVIEW,
                    label_confidence=0.9,
                ),
                TrainingSample(
                    text="Oil supports airlines.",
                    task_type=TaskType.RELATION,
                    labels={"relation_type": "supports", "sign": "positive"},
                    source=DataSource.COUNCIL_REVIEW,
                    label_confidence=0.8,
                ),
            ],
            sample_count=2,
        )
        goldset = GoldSet(
            version="gold_v1",
            task_type=TaskType.RELATION,
            samples=[
                GoldSample(
                    text="Higher policy rates pressure growth stocks.",
                    task_type=TaskType.RELATION,
                    gold_labels={"relation_type": "pressures", "sign": "negative"},
                )
            ],
            sample_count=1,
        )

        metrics = _evaluate_dataset(dataset, goldset)

        assert metrics.matched_samples == 0
        assert metrics.unexpected_samples == 1
        assert metrics.static_conflict_count == 2
        assert any(item["error_type"] == "label_mismatch" for item in metrics.error_examples)
        assert any(item["error_type"] == "unexpected_prediction" for item in metrics.error_examples)

    def test_build_dataset_logs_expected_adapter_failures_and_degrades(self, monkeypatch, caplog):
        class DummyStore:
            def read(self, name):
                return []

        class DummyBuilder:
            def __init__(self, domain=None, personal=None):
                self.domain = domain
                self.personal = personal

            def add_validation_log(self, item):
                pass

            def add_council_log(self, item):
                pass

            def add_query_log(self, item):
                pass

            def build_dataset(self, task_type):
                from src.learning.models import DatasetSnapshot

                return DatasetSnapshot(version="ds_v1", task_type=task_type)

        monkeypatch.setattr(
            "src.learning.offline_runner.get_domain_kg_adapter",
            lambda: (_ for _ in ()).throw(RuntimeError("domain down")),
        )
        monkeypatch.setattr(
            "src.learning.offline_runner.get_personal_kg_adapter",
            lambda: (_ for _ in ()).throw(ValueError("personal down")),
        )
        monkeypatch.setattr("src.learning.offline_runner._get_event_store", lambda: DummyStore())
        monkeypatch.setattr("src.learning.offline_runner.TrainingDatasetBuilder", DummyBuilder)

        with caplog.at_level("WARNING"):
            snapshot = _build_dataset(TaskType.RELATION)

        assert snapshot.task_type == TaskType.RELATION
        assert "Skipping domain adapter during offline dataset build" in caplog.text
        assert "Skipping personal adapter during offline dataset build" in caplog.text

    def test_build_dataset_does_not_swallow_unexpected_adapter_failures(self, monkeypatch):
        monkeypatch.setattr(
            "src.learning.offline_runner.get_domain_kg_adapter",
            lambda: (_ for _ in ()).throw(TypeError("bug")),
        )

        with pytest.raises(TypeError, match="bug"):
            _build_dataset(TaskType.RELATION)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
