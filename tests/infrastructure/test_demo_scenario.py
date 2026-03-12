from typing import cast

from scripts.demo_scenario import DemoSummary, run_demo


def test_demo_scenario_runs_sample_ingest_and_questions():
    summary: DemoSummary = run_demo(sample_limit=4)

    assert summary["health"]["ready"] is True
    assert int(cast(int | str, summary["status"]["ingested_docs"])) >= 4
    assert summary["total_edges"] >= 3
    assert len(summary["questions"]) == 2
    assert all(item["answer"] for item in summary["questions"])
    assert "ontro_ready 1" in summary["metrics_preview"]
    assert "ontro_ingested_documents_total" in summary["metrics_preview"]
