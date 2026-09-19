from __future__ import annotations

from rasai.observability.store import observability_database_path

def _obs_path(workspace: Path) -> Path:
    path = observability_database_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


from pathlib import Path
import sqlite3
import tempfile

from rasai import integration_state_contract as state_contract


def test_public_integration_states_distinguish_disabled_configuration_and_failure() -> None:
    assert state_contract.public_integration_state("DISABLED") == "Desabilitado / não solicitado"
    assert state_contract.public_integration_state("NOT_CONFIGURED") == "Não configurado"
    assert state_contract.public_integration_state("SUCCESS") == "Executado com sucesso"
    assert state_contract.public_integration_state("PARTIAL") == "Executado parcialmente"
    assert state_contract.public_integration_state("NO_DATA") == "Executado sem dado utilizável"
    assert state_contract.public_integration_state("ERROR") == "Falhou / indisponível"


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
        sidecar = sqlite3.connect(_obs_path(workspace))
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


