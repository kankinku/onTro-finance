"""Shared dataset evaluation helpers for the learning loop."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from src.learning.models import DatasetSnapshot, GoldSet, TrainingMetrics


def evaluate_dataset_against_goldset(dataset: DatasetSnapshot, goldset: GoldSet) -> TrainingMetrics:
    matches: Dict[Tuple[str, str], Dict[str, Any]] = {
        (sample.text.strip(), sample.task_type.value): sample.labels for sample in dataset.samples
    }

    true_positive = 0
    false_negative = 0
    false_positive = 0
    matched_samples = 0
    missing_samples = 0
    error_examples = []
    confusion_matrix: Dict[str, Dict[str, int]] = {}

    for gold in goldset.samples:
        key = (gold.text.strip(), gold.task_type.value)
        predicted = matches.get(key)
        if predicted is None:
            false_negative += 1
            missing_samples += 1
            error_examples.append(
                {
                    "text": gold.text,
                    "task_type": gold.task_type.value,
                    "expected": gold.gold_labels,
                    "predicted": None,
                    "error_type": "missing_prediction",
                }
            )
            continue

        expected_label = _primary_label(gold.gold_labels)
        predicted_label = _primary_label(predicted)
        _increment_confusion(confusion_matrix, expected_label, predicted_label)

        if all(
            predicted.get(label_key) == label_value
            for label_key, label_value in gold.gold_labels.items()
        ):
            true_positive += 1
            matched_samples += 1
        else:
            false_negative += 1
            false_positive += 1
            error_examples.append(
                {
                    "text": gold.text,
                    "task_type": gold.task_type.value,
                    "expected": gold.gold_labels,
                    "predicted": predicted,
                    "error_type": "label_mismatch",
                }
            )

    matched_keys = {(gold.text.strip(), gold.task_type.value) for gold in goldset.samples}
    extra_keys = [key for key in matches if key not in matched_keys]
    false_positive += len(extra_keys)

    for text, task_type in extra_keys:
        error_examples.append(
            {
                "text": text,
                "task_type": task_type,
                "expected": None,
                "predicted": matches[(text, task_type)],
                "error_type": "unexpected_prediction",
            }
        )

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = (2 * precision * recall) / max(precision + recall, 1e-9)
    accuracy = true_positive / max(goldset.sample_count, 1)

    return TrainingMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=accuracy,
        confusion_matrix=confusion_matrix,
        matched_samples=matched_samples,
        missing_samples=missing_samples,
        unexpected_samples=len(extra_keys),
        error_examples=error_examples[:20],
        static_conflict_count=false_positive,
        drift_detection_rate=recall,
    )


def _primary_label(labels: Dict[str, Any]) -> str:
    for key in ("relation_type", "semantic_tag", "sign", "head"):
        value = labels.get(key)
        if value is not None:
            return f"{key}:{value}"
    if not labels:
        return "empty"
    first_key = sorted(labels.keys())[0]
    return f"{first_key}:{labels[first_key]}"


def _increment_confusion(
    confusion_matrix: Dict[str, Dict[str, int]], expected: str, predicted: str
) -> None:
    row = confusion_matrix.setdefault(expected, {})
    row[predicted] = row.get(predicted, 0) + 1
