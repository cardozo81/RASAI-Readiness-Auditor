from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_provider_docs_include_copilot_and_dynamic_auto_contract() -> None:
    for path in (
        "docs/CONFIGURATION.md",
        "docs/INTERACTIVE_CONSOLE.md",
        "docs/CLI_REFERENCE.md",
        "docs/COMPATIBILITY.md",
        "docs/specification/13_MODEL_ROUTING_POLICY.md",
        "docs/specification/18_MULTI_AI_PROVIDER_ROUTING.md",
    ):
        text = _text(path)
        assert "Copilot" in text, path
        assert "explicit-only" in text, path
        assert "provider_registry" in text, path

    assert "não é uma cadeia fixa OpenAI → DeepSeek → MiMo" in _text("docs/CONFIGURATION.md")
    assert "não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo" in _text("docs/INTERACTIVE_CONSOLE.md")


def test_installation_and_troubleshooting_document_copilot_sdk() -> None:
    installation = _text("docs/INSTALLATION.md")
    troubleshooting = _text("docs/TROUBLESHOOTING.md")

    for text in (installation, troubleshooting):
        assert 'python -m pip install -e ".[copilot]"' in text
        assert "COPILOT_GITHUB_TOKEN" in text


def test_search_provider_docs_cover_all_live_adapters() -> None:
    for path in ("docs/CONFIGURATION.md", "docs/CLI_REFERENCE.md", "docs/TROUBLESHOOTING.md"):
        text = _text(path)
        for provider in ("serpapi", "zenserp", "scrapingdog"):
            assert provider in text, (path, provider)
        assert "RASAI_ZENSERP_API_KEY" in text, path
        assert "RASAI_SCRAPINGDOG_API_KEY" in text, path


def test_shared_apdex_acquisition_is_documented_as_non_scoring() -> None:
    for path in ("docs/CONFIGURATION.md", "docs/CLI_REFERENCE.md", "docs/INTERACTIVE_CONSOLE.md"):
        text = _text(path)
        assert "RASAI_APDEX_ACQUISITION_MODE" in text, path
        assert "auto" in text and "isolated" in text, path
