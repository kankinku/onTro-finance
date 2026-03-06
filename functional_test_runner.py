from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def _ensure_project_root() -> Path:
    project_root = _resource_path()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _print_banner() -> None:
    print("=" * 72)
    print("onTro-Finance One-Click Functional Test")
    print("=" * 72)


def _print_result(result: CheckResult) -> None:
    status = "[OK]" if result.ok else "[FAIL]"
    print(f"{status} {result.name}")
    if result.details:
        print(result.details)
    print("-" * 72)


def _set_runtime_env() -> None:
    os.environ["ONTRO_STORAGE_BACKEND"] = "inmemory"
    os.environ["ONTRO_COUNCIL_AUTO_ENABLED"] = "false"
    os.environ["ONTRO_LOAD_SAMPLE_DATA"] = "false"


def _run_pytest(project_root: Path) -> CheckResult:
    import pytest

    tests_path = project_root / "tests"
    exit_code = pytest.main([str(tests_path), "-q"])
    ok = exit_code == 0
    return CheckResult(
        name="Automated Test Suite",
        ok=ok,
        details=f"pytest exit code: {exit_code}",
    )


def _run_api_flow() -> tuple[CheckResult, dict[str, Any]]:
    from fastapi.testclient import TestClient

    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    import main

    try:
        main.reset_app_state()

        sample_text = "Higher policy rates continue to pressure long-duration growth equities."
        sample_question = "How do higher policy rates affect growth equities?"

        with TestClient(main.app) as client:
            health = client.get("/healthz")
            ingest = client.post(
                "/api/text/add-to-vectordb",
                json={
                    "text": sample_text,
                    "metadata": {
                        "doc_id": "exe-functional-test",
                        "source": "exe-functional-test",
                    },
                },
            )
            ask = client.post("/api/ask", json={"question": sample_question})
            status = client.get("/status")
    finally:
        logging.disable(previous_disable)

    health_payload = health.json()
    ingest_payload = ingest.json()
    ask_payload = ask.json()
    status_payload = status.json()

    checks = [
        health.status_code == 200,
        health_payload.get("ready") is True,
        ingest.status_code == 200,
        ingest_payload.get("status") == "success",
        int(ingest_payload.get("edge_count", 0)) >= 1,
        ask.status_code == 200,
        ask_payload.get("reasoning_used") is True,
        float(ask_payload.get("confidence", 0.0)) >= 0.5,
        status.status_code == 200,
        int(status_payload.get("ingested_docs", 0)) >= 1,
        int(status_payload.get("edge_count", 0)) >= 1,
    ]

    summary = {
        "health": health_payload,
        "ingest": ingest_payload,
        "ask": ask_payload,
        "status": status_payload,
    }

    details = "\n".join(
        [
            f"health.ready={health_payload.get('ready')}",
            f"ingest.edge_count={ingest_payload.get('edge_count')}",
            f"ask.confidence={ask_payload.get('confidence')}",
            f"ask.answer={ask_payload.get('answer')}",
            f"status.ingested_docs={status_payload.get('ingested_docs')}",
            f"status.edge_count={status_payload.get('edge_count')}",
        ]
    )

    return CheckResult(name="Functional API Flow", ok=all(checks), details=details), summary


def _write_report(project_root: Path, results: list[CheckResult], api_summary: dict[str, Any]) -> Path:
    if getattr(sys, "frozen", False):
        report_path = Path(sys.executable).resolve().parent / "functional_test_report.json"
    else:
        report_path = project_root / "functional_test_report.json"
    payload = {
        "results": [asdict(result) for result in results],
        "api_summary": api_summary,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def main_entry() -> int:
    _print_banner()
    project_root = _ensure_project_root()
    _set_runtime_env()

    results: list[CheckResult] = []
    api_summary: dict[str, Any] = {}

    try:
        pytest_result = _run_pytest(project_root)
        results.append(pytest_result)
        _print_result(pytest_result)

        api_result, api_summary = _run_api_flow()
        results.append(api_result)
        _print_result(api_result)

        report_path = _write_report(project_root, results, api_summary)
        print(f"[INFO] Report written to: {report_path}")

        overall_ok = all(result.ok for result in results)
        print("[OK] All checks passed." if overall_ok else "[FAIL] One or more checks failed.")
        return 0 if overall_ok else 1
    except Exception as exc:
        error_result = CheckResult(
            name="Launcher Error",
            ok=False,
            details=f"{exc}\n{traceback.format_exc()}",
        )
        results.append(error_result)
        _print_result(error_result)
        try:
            report_path = _write_report(project_root, results, api_summary)
            print(f"[INFO] Partial report written to: {report_path}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main_entry())
