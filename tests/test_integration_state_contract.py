from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from rasai import integration_state_contract as state_contract
from rasai.integration_state_refinements import install as install_refinements


ROOT = Path(__file__).resolve().parents[1]
install_refinements()


def test_public_integration_states_distinguish_disabled_configuration_and_failure() -> None:
    assert state_contract.public_integration_state("DISABLED") == "Desabilitado / não solicitado"
    assert state_contract.public_integration_state("NOT_CONFIGURED") == "Não configurado"
    assert state_contract.public_integration_state("SUCCESS") == "Executado com sucesso"
    assert state_contract.public_integration_state("PARTIAL") == "Executado parcialmente"
    assert state_contract.public_integration_state("NO_DATA") == "Executado sem dado utilizável"
    assert state_contract.public_integration_state("ERROR") == "Falhou / indisponível"


def test_technical_ai_notice_is_explicit_when_disabled_or_not_configured() -> None:
    disabled = state_contract._m24_ai_notice({
        "run": {"ai_enabled": 0, "ai_state": "DISABLED"},
        "ai": {"state": "DISABLED", "reason": "DEFAULT_OFF"},
        "attempts": [],
    })
    assert "desabilitada nesta execução" in disabled
    assert "Nenhuma chamada era esperada" in disabled
    assert "não é erro do website" in disabled
    assert "data-integration-state='technical-ai'" in disabled
    assert "data-integration-state='m24-technical-ai'" not in disabled

    missing = state_contract._m24_ai_notice({
        "run": {"ai_enabled": 1, "ai_state": "NOT_CONFIGURED"},
        "ai": {"state": "NOT_CONFIGURED", "reason": "AI_NOT_CONFIGURED_FOR_M24"},
        "attempts": [],
    })
    assert "sem provider/credencial/configuração utilizável" in missing
    assert "Nenhum resultado de IA foi coletado" in missing
    assert "AI_NOT_CONFIGURED_FOR_M24" in missing


def test_content_remediation_no_safe_suggestion_is_not_provider_failure() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            """CREATE TABLE content_remediation_runs(
                audit_id TEXT PRIMARY KEY, enabled INTEGER, status TEXT,
                eligible_findings INTEGER, reason TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO content_remediation_runs VALUES (?,?,?,?,?)",
            ("AUD-1", 1, "NO_SAFE_SUGGESTIONS", 3, "all responses rejected by safety contract"),
        )
        coverage = state_contract._content_ai_coverage(
            connection,
            "AUD-1",
            lambda component, requested, status, reason: (component, requested, status, reason),
        )
        assert coverage is not None
        assert coverage[2] == "SEM SAÍDA SEGURA"
        assert "não é, por si só, falha do provider" in coverage[3]
    finally:
        connection.close()


def test_observability_attempt_ledger_persists_failure_reason_without_touching_audit_db() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        audit_db = workspace / "audit.db"
        connection = sqlite3.connect(audit_db)
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('immutable-source')")
        connection.commit()
        connection.close()

        attempt_id = state_contract.record_observability_attempt(
            workspace,
            operation="gsc-search",
            source_type="GOOGLE_SEARCH_CONSOLE",
            status="NOT_CONFIGURED",
            reason="Google Search Console OAuth bearer token not configured",
            metadata={"exit_code": 2},
        )
        assert attempt_id and attempt_id.startswith("INT-")
        sidecar = sqlite3.connect(workspace / "observability.db")
        sidecar.row_factory = sqlite3.Row
        try:
            row = sidecar.execute("SELECT * FROM integration_attempts").fetchone()
            assert row is not None
            assert row["operation"] == "gsc-search"
            assert row["status"] == "NOT_CONFIGURED"
            assert "not configured" in row["reason"]
        finally:
            sidecar.close()

        source = sqlite3.connect(audit_db)
        try:
            assert source.execute("SELECT value FROM sentinel").fetchone()[0] == "immutable-source"
        finally:
            source.close()


def test_observability_report_explains_no_attempt_and_failed_attempt() -> None:
    empty = state_contract._observability_state_section([])
    assert "Nenhuma tentativa persistida" in empty
    assert "não representa falha da fonte" in empty

    rendered = state_contract._observability_state_section([
        {
            "operation": "crux-history",
            "source_type": "CRUX_HISTORY_API",
            "status": "ERROR",
            "reason": "HTTP 503",
            "attempted_at": "2026-09-11T00:00:00+00:00",
        }
    ])
    assert "Falhou / indisponível" in rendered
    assert "HTTP 503" in rendered
    assert "não a qualidade do website" in rendered


def test_documentation_defines_universal_integration_state_contract() -> None:
    document = (ROOT / "docs/REPORT_PRESENTATION_CONTRACT.md").read_text(encoding="utf-8")
    for expected in (
        "Estado universal de integrações e coletas opcionais",
        "Desabilitado / não solicitado",
        "Não configurado",
        "Executado com sucesso",
        "Executado parcialmente",
        "Executado sem dado utilizável",
        "Falhou / indisponível",
        "desabilitado não é erro",
        "não configurado não é falha do website",
        "Search Intelligence/SERP",
        "Search & AI Observability",
        "Observed Generative Visibility",
    ):
        assert expected in document
