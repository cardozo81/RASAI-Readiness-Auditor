from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _doc(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_interactive_console_documents_current_ai_credential_management() -> None:
    text = _doc("docs/INTERACTIVE_CONSOLE.md")

    assert "providers sem credencial continuam configuráveis" in text
    assert "S. Setar/alterar Key na sessão" in text
    assert "P. Persistir/remover Key no Windows/User" in text
    assert "L. Limpar Key somente da sessão" in text
    assert "X. Excluir Key da sessão e do Windows/User" in text
    assert "A. Habilitar/desabilitar no AUTO sem apagar a Key" in text
    assert "U. Usar este provider nesta auditoria" in text
    assert "recalcula imediatamente a capability" in text


def test_interactive_console_documents_non_admin_user_scope() -> None:
    text = _doc("docs/INTERACTIVE_CONSOLE.md")

    assert "HKEY_CURRENT_USER\\Environment" in text
    assert "não exige PowerShell ou `.ps1` executado como Administrador" in text
    assert "não modifica Windows/Machine" in text
    assert "Windows/Machine não é administrado automaticamente pelo RASAi" in text


def test_auto_documentation_matches_dynamic_provider_registry() -> None:
    console = _doc("docs/INTERACTIVE_CONSOLE.md")
    configuration = _doc("docs/CONFIGURATION.md")

    assert "não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo" in console
    assert "provider_registry" in console
    assert "`AI=auto` **não é uma cadeia fixa OpenAI → DeepSeek → MiMo**" in configuration
    assert "A cadeia `AUTO` permanece:" not in console
    assert "explicit-only enquanto sua qualificação" not in console


def test_reporting_glossary_keeps_established_concepts_in_english() -> None:
    text = _doc("docs/specification/11_REPORTING_LANGUAGE_GLOSSARY.md")

    expected = {
        "`DISCOVERY_ACCESS` | Discovery & Crawler Access",
        "`INDEXABILITY` | Indexability",
        "`CONTENT_EXTRACTABILITY` | Rendering & Extractability",
        "`SEMANTIC_STRUCTURE` | Semantic Structure",
        "`ENTITY_CLARITY` | Entity Clarity",
        "`STRUCTURED_DATA` | Structured Data",
        "`ANSWERABILITY` | Answerability",
        "`CITATION_READINESS` | Citation Readiness",
        "`EVIDENCE_TRUST` | Evidence & Trust",
        "`INTENT_COVERAGE` | Intent Coverage",
        "`CONTENT_VALUE` | Content Value",
    }
    for fragment in expected:
        assert fragment in text

    assert "Indexability | Capacidade de Indexação" not in text
    assert "Structured Data | Dados Estruturados" not in text
    assert "Citation Readiness | Preparação para Citação" not in text


def test_report_guide_documents_current_scope_and_multi_url_behavior() -> None:
    text = _doc("docs/REPORT_GUIDE.md")

    assert "crawling-discovery.html" in text
    assert "Domínio e descoberta; recursos ORIGIN" in text
    assert "Com uma única URL, o layout permanece simples e linear." in text
    assert "duas ou mais URLs distintas" in text
    assert "context.html" in text
    assert "não devem ser replicados por URL em Mobile, Desktop ou `context.html`" in text
