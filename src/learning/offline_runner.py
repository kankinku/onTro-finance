"""Offline dataset export, evaluation, and bundle creation for the learning loop."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from config.settings import get_settings
from src.bootstrap import get_domain_kg_adapter, get_personal_kg_adapter, reset_all
from src.learning.dataset_builder import TrainingDatasetBuilder
from src.learning.deployment import ReviewDeploymentManager
from src.learning.evaluation import evaluate_dataset_against_goldset
from src.learning.event_store import LearningEventStore, dump_json, load_json
from src.learning.models import DatasetSnapshot, GoldSet, TaskType, TrainingMetrics

logger = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _get_event_store() -> LearningEventStore:
    return LearningEventStore(get_settings().store.learning_data_path)


def _build_dataset(task_type: TaskType) -> DatasetSnapshot:
    try:
        domain = get_domain_kg_adapter()
    except (RuntimeError, ValueError, OSError) as exc:
        logger.warning("Skipping domain adapter during offline dataset build: %s", exc)
        domain = None

    try:
        personal = get_personal_kg_adapter()
    except (RuntimeError, ValueError, OSError) as exc:
        logger.warning("Skipping personal adapter during offline dataset build: %s", exc)
        personal = None

    store = _get_event_store()
    builder = TrainingDatasetBuilder(domain=domain, personal=personal)

    for item in store.read("validation"):
        builder.add_validation_log(item)
    for item in store.read("council_candidate"):
        builder.add_council_log(item)
    for item in store.read("council_final"):
        builder.add_council_log(item)
    for item in store.read("query"):
        builder.add_query_log(item)

    return builder.build_dataset(task_type=task_type)


def _evaluate_dataset(dataset: DatasetSnapshot, goldset: GoldSet) -> TrainingMetrics:
    return evaluate_dataset_against_goldset(dataset, goldset)


def export_dataset(task_type: TaskType, output: str | None) -> Path:
    dataset = _build_dataset(task_type)
    store = _get_event_store()
    filename = output or f"{_utc_timestamp()}-{task_type.value}.json"
    path = store.snapshot_path(filename)
    dump_json(path, dataset.model_dump(mode="json"))
    return path


def evaluate_dataset(snapshot_path: str, goldset_path: str) -> Path:
    snapshot = DatasetSnapshot.model_validate(load_json(Path(snapshot_path)))
    goldset = GoldSet.model_validate(load_json(Path(goldset_path)))
    metrics = _evaluate_dataset(snapshot, goldset)

    store = _get_event_store()
    path = store.snapshot_path(f"evaluation-{_utc_timestamp()}.json")
    dump_json(
        path,
        {
            "dataset_id": snapshot.dataset_id,
            "dataset_version": snapshot.version,
            "goldset_id": goldset.goldset_id,
            "goldset_version": goldset.version,
            "dataset_summary": {
                "sample_count": snapshot.sample_count,
                "source_distribution": snapshot.source_distribution,
                "provenance_summary": snapshot.provenance_summary,
            },
            "metrics": metrics.model_dump(mode="json"),
        },
    )
    return path


def create_bundle(
    student1: str, student2: str, sign_validator: str, semantic_validator: str, policy: str
) -> Path:
    manager = ReviewDeploymentManager()
    bundle = manager.create_bundle(student1, student2, sign_validator, semantic_validator, policy)
    manager.review_bundle(bundle.version, approved=True, notes="Created by offline runner")

    store = _get_event_store()
    path = store.bundle_path(f"{bundle.version}.json")
    active_bundle = manager.get_active_bundle()
    dump_json(
        path,
        active_bundle.model_dump(mode="json") if active_bundle else bundle.model_dump(mode="json"),
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline learning loop runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export-dataset")
    export_parser.add_argument(
        "--task", default=TaskType.RELATION.value, choices=[item.value for item in TaskType]
    )
    export_parser.add_argument("--output", default=None)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--snapshot", required=True)
    evaluate_parser.add_argument("--goldset", required=True)

    bundle_parser = subparsers.add_parser("create-bundle")
    bundle_parser.add_argument("--student1", required=True)
    bundle_parser.add_argument("--student2", required=True)
    bundle_parser.add_argument("--sign-validator", required=True)
    bundle_parser.add_argument("--semantic-validator", required=True)
    bundle_parser.add_argument("--policy", required=True)

    args = parser.parse_args()

    try:
        if args.command == "export-dataset":
            path = export_dataset(TaskType(args.task), args.output)
        elif args.command == "evaluate":
            path = evaluate_dataset(args.snapshot, args.goldset)
        else:
            path = create_bundle(
                student1=args.student1,
                student2=args.student2,
                sign_validator=args.sign_validator,
                semantic_validator=args.semantic_validator,
                policy=args.policy,
            )
        print(path)
        return 0
    finally:
        reset_all()


if __name__ == "__main__":
    raise SystemExit(main())
