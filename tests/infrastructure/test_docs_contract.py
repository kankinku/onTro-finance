"""Documentation contract tests for public runtime behavior."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_readme_documents_actual_api_routes_and_env_names():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "POST /api/text/add-to-vectordb" in readme
    assert "POST /api/pdf/extract-and-embed" in readme
    assert "POST /api/ask" in readme
    assert "ONTRO_NEO4J_USER" in readme
    assert "ONTRO_NEO4J_USERNAME" in readme
    assert "deprecated" in readme.lower()


def test_tutorial_documents_default_runtime_and_provider_contract():
    tutorial = (PROJECT_ROOT / "docs" / "TUTORIAL_KO.md").read_text(encoding="utf-8")

    assert "ONTRO_COUNCIL_AUTO_ENABLED" in tutorial
    assert "OpenAI-compatible" in tutorial
    assert "/chat/completions" in tutorial
    assert "/api/generate" in tutorial


def test_docs_and_build_script_pin_supported_python_runtime():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    tutorial = (PROJECT_ROOT / "docs" / "TUTORIAL_KO.md").read_text(encoding="utf-8")
    build_script = (PROJECT_ROOT / "build_ops_console_exe.ps1").read_text(encoding="utf-8")

    assert "Python 3.11 또는 3.12" in readme
    assert "Python 3.11 또는 3.12" in tutorial
    assert "py -3.11 -m venv $BuildVenv" in build_script
