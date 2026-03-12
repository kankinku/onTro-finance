from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TypedDict, cast

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_QUESTIONS = [
    "How do higher policy rates affect growth stocks?",
    "What do higher oil prices mean for airlines?",
]


class SampleDocument(TypedDict):
    doc_id: str
    text: str
    source: str
    timestamp: str


class IngestSummary(TypedDict):
    doc_id: str
    edge_count: int


class QuestionSummary(TypedDict):
    question: str
    answer: str
    confidence: float


class DemoSummary(TypedDict):
    health: dict[str, object]
    status: dict[str, object]
    metrics_preview: str
    documents: list[IngestSummary]
    questions: list[QuestionSummary]
    total_edges: int


def load_sample_documents(limit: int | None = None) -> list[SampleDocument]:
    sample_path = Path(__file__).resolve().parents[1] / "data" / "samples" / "sample_documents.json"
    documents = cast(list[SampleDocument], json.loads(sample_path.read_text(encoding="utf-8")))
    return documents[:limit] if limit else documents


def run_demo(sample_limit: int = 4) -> DemoSummary:
    from config.settings import get_settings
    import main as app_main

    with tempfile.TemporaryDirectory(prefix="ontro-demo-") as temp_dir:
        os.environ["ONTRO_APP_HOME"] = temp_dir
        os.environ["ONTRO_STORAGE_BACKEND"] = "inmemory"
        os.environ["ONTRO_COUNCIL_AUTO_ENABLED"] = "false"
        os.environ["ONTRO_LOAD_SAMPLE_DATA"] = "false"
        os.environ["ONTRO_ENABLE_CALLBACKS"] = "false"
        get_settings.cache_clear()
        app_main.reset_app_state()

        documents = load_sample_documents(sample_limit)
        ingest_results: list[IngestSummary] = []
        answers: list[QuestionSummary] = []

        with TestClient(app_main.app) as client:
            health = cast(dict[str, object], client.get("/healthz").json())

            for doc in documents:
                response = client.post(
                    "/api/text/add-to-vectordb",
                    json={
                        "text": doc["text"],
                        "metadata": {
                            "doc_id": doc["doc_id"],
                            "title": doc["source"],
                            "source_type": "sample_demo",
                        },
                    },
                )
                payload = cast(dict[str, object], response.json())
                ingest_results.append(
                    {
                        "doc_id": str(payload.get("doc_id", "")),
                        "edge_count": int(cast(int | str, payload.get("edge_count", 0))),
                    }
                )

            status = cast(dict[str, object], client.get("/status").json())
            metrics_preview = client.get("/metrics").text

            for question in SAMPLE_QUESTIONS:
                response = client.post("/api/ask", json={"question": question})
                payload = cast(dict[str, object], response.json())
                answers.append(
                    {
                        "question": question,
                        "answer": str(payload.get("answer", "")),
                        "confidence": float(
                            cast(float | int | str, payload.get("confidence", 0.0))
                        ),
                    }
                )

        return {
            "health": health,
            "status": status,
            "metrics_preview": metrics_preview,
            "documents": ingest_results,
            "questions": answers,
            "total_edges": sum(item["edge_count"] for item in ingest_results),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the starter-friendly sample finance scenario."
    )
    _ = parser.add_argument("--sample-limit", type=int, default=4)
    _ = parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sample_limit = cast(int, args.sample_limit)
    as_json = cast(bool, args.json)
    summary = run_demo(sample_limit=sample_limit)
    if as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"health.ready={summary['health'].get('ready')}")
        print(f"status.ingested_docs={summary['status'].get('ingested_docs')}")
        print(f"total_edges={summary['total_edges']}")
        print(f"metrics.ready={'ontro_ready 1' in summary['metrics_preview']}")
        for item in summary["questions"]:
            print(f"Q: {item['question']}")
            print(f"A: {item['answer']}")
            print(f"confidence={item['confidence']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
