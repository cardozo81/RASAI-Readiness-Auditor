from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.catalog_report_assurance import (
    CATALOG_MATURITY_MIN,
    HIGH_ASSURANCE_MIN,
    _catalog_referential_integrity,
    _read_only_guard_present,
    _safe_output,
    assess_catalog,
    assurance_matrix_html,
    catalog_assurance_html,
)


def _body(extra: str = "") -> str:
    return (
        "<section><h2>Configuração efetiva</h2></section>"
        "<section><h2>Resultados</h2></section>"
        "<section><h2>Evidências</h2><p>Fonte materializada</p></section>"
        "<section><h2>Análise e interpretação</h2></section>"
        "<section><h2>Remediações</h2></section>"
        "<section><h2>Detalhes técnicos</h2></section>"
        + extra
    )


def _data(*, secret: bool = False):
    configuration = {
        "targets": ["https://example.test/"],
        "audit_catalog": {"selected": ["CAT-01"]},
    }
    if secret:
        configuration["api_key"] = "secret-value"
    return SimpleNamespace(
        audit_id="AUD-ASSURANCE",
        configuration=configuration,
        config_hash="same",
        computed_hash="same",
        selected={"CAT-01"},
        work_items=[],
    )


def _patch_catalog(monkeypatch) -> None:
    from rasai import catalog_report_catalog_state as state
    from rasai import catalog_report_page as page

    monkeypatch.setattr(
        page,
        "_catalog_status",
        lambda *_args: ("CONCLUÍDO", "good", "Resultado persistido e exposto."),
    )
    monkeypatch.setattr(
        page,
        "_configuration_rows",
        lambda *_args: [
            ("Incluído nesta auditoria", "Sim", "Plano congelado"),
            ("URL / alvo", "https://example.test/", "Plano congelado"),
            ("Uso de IA nesta capacidade", "Não se aplica", "Plano congelado"),
            ("Política de IA", "Não utiliza IA", "Catálogo"),
        ],
    )
    monkeypatch.setattr(
        page,
        "_catalog_sources",
        lambda *_args: [("sample", "Fonte materializada", 1)],
    )
    monkeypatch.setattr(state, "_catalog_source_specs", lambda _catalog_id: ())


def test_catalog_assurance_reaches_closure_targets_when_all_controls_pass(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(database, _data(), "CAT-01", _body())

    assert result["maturity"] >= CATALOG_MATURITY_MIN
    assert result["reliability"] >= HIGH_ASSURANCE_MIN
    assert result["integrity"] >= HIGH_ASSURANCE_MIN
    assert result["security"] >= HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is True
    html = catalog_assurance_html(result)
    assert "Maturidade estrutural" in html
    assert "ATENDE" in html


def test_secret_in_frozen_configuration_blocks_security_closure(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(database, _data(secret=True), "CAT-01", _body())

    assert result["security"] < HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "SEC_PERSISTED_CONFIG" in failed


def test_unsafe_external_link_blocks_security_closure(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(
        database,
        _data(),
        "CAT-01",
        _body("<a href='https://external.test/path'>externo</a>"),
    )

    assert result["security"] < HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "SEC_EXTERNAL_LINKS" in failed

def test_security_scanner_ignores_css_sk_classes_but_detects_credential_assignment() -> None:
    ok, failures = _safe_output("<div class='sk-header-content sk-button--loading'></div>")
    assert ok is True
    assert failures == []

    ok, failures = _safe_output("<pre>api_key='prod-value-93af'</pre>")
    assert ok is False
    assert any("credencial" in item for item in failures)


def test_catalog_referential_integrity_detects_audit_owned_fk_violation(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_catalog_state as state
    import sqlite3

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY);
            CREATE TABLE semantic_coherence_assessments(
                assessment_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id)
            );
            INSERT INTO audits VALUES('AUD-ASSURANCE');
            INSERT INTO page_snapshots VALUES('S1');
            INSERT INTO semantic_coherence_assessments
                VALUES('SCA-1','AUD-ASSURANCE','S1');
            """
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(
        state,
        "_catalog_source_specs",
        lambda _catalog_id: (("semantic_coherence_assessments", "Coerência semântica"),),
    )

    passed, detail = _catalog_referential_integrity(
        database,
        "AUD-ASSURANCE",
        "CAT-03",
    )

    assert passed is False
    assert "1 violação(ões)" in detail
    assert "semantic_coherence_assessments" in detail
    assert "snapshots" in detail


def test_referential_integrity_failure_reduces_integrity_axis(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)
    monkeypatch.setattr(
        assurance,
        "_catalog_referential_integrity",
        lambda *_args: (False, "1 violação de FK"),
    )

    result = assess_catalog(database, _data(), "CAT-01", _body())

    assert result["integrity"] < 100.0
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "INT_REFERENTIAL_INTEGRITY" in failed


def test_read_only_assurance_follows_materializer_wrapper_chain(monkeypatch) -> None:
    from rasai import catalog_report_site as site

    original = site.materialize_catalog_report_site

    def wrapper(*args, **kwargs):
        return original(*args, **kwargs)

    wrapper._rasai_original = original
    monkeypatch.setattr(site, "materialize_catalog_report_site", wrapper)

    passed, detail = _read_only_guard_present()
    assert passed is True
    assert "fingerprint" in detail


def test_transversal_secret_output_blocks_global_closure(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    monkeypatch.setattr(
        assurance,
        "assess_catalog",
        lambda _database, _data, catalog_id, _body: {
            "catalog_id": catalog_id,
            "selected": True,
            "functional_status": "CONCLUÍDO",
            "configurability": 100.0,
            "governance": 100.0,
            "exposure": 100.0,
            "reliability": 100.0,
            "integrity": 100.0,
            "security": 100.0,
            "maturity": 100.0,
            "high_assurance": 100.0,
            "closure_eligible": True,
            "checks": [],
        },
    )
    result = assurance.assess_catalogs(
        tmp_path / "audit.db",
        SimpleNamespace(),
        {"ai-integrations.html": "<pre>api_key='prod-value-93af'</pre>"},
    )
    assert result["global_output_security"]["passed"] is False
    assert "ai-integrations.html" in result["global_output_security"]["failures"]
    assert result["closure_eligible"] is False

def test_assurance_matrix_explains_each_axis_without_changing_columns() -> None:
    result = {
        "catalogs": [{
            "catalog_id": "CAT-01",
            "selected": True,
            "configurability": 100,
            "governance": 100,
            "exposure": 100,
            "reliability": 100,
            "integrity": 100,
            "security": 100,
            "maturity": 100,
            "closure_eligible": True,
        }],
        "global": {
            "configurability": 100,
            "governance": 100,
            "exposure": 100,
            "reliability": 100,
            "integrity": 100,
            "security": 100,
            "maturity": 100,
        },
        "global_output_security": {"passed": True, "failures": {}},
        "closure_eligible": True,
    }
    html = assurance_matrix_html(result)

    assert "Matriz de encerramento estrutural" in html
    assert "Como ler os eixos" in html
    for label in (
        "CAT",
        "Configurabilidade",
        "Governança",
        "Exposição",
        "Confiabilidade",
        "Integridade",
        "Segurança",
        "Maturidade",
        "Gate",
    ):
        assert f"<th>{label}</th>" in html
    assert "cobertura de controles" in html
    assert "probabilidade estatística" in html
    global_labels = (
        "Configurabilidade global",
        "Governança global",
        "Exposição global",
        "Confiabilidade global",
        "Integridade global",
        "Segurança global",
        "Maturidade global",
    )
    positions = [html.index(label) for label in global_labels]
    assert positions == sorted(positions)
    assert "Gates de encerramento:" in html
    assert "<small>Encerramento estrutural</small>" not in html

def test_internal_orchestration_failure_reduces_assurance_instead_of_showing_all_100(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)
    monkeypatch.setattr(assurance, "_applicable_config_markers", lambda *_args: ())

    data = _data()
    data.selected = {"CAT-09"}
    data.work_items = [{
        "component": "CONTENT_REMEDIATION_AI",
        "scope_key": "AUDIT",
        "status": "FAILED_RETRYABLE",
        "last_error_class": "ORCHESTRATION",
        "last_error_code": "CONTENT_REMEDIATION_EXECUTION_FAILURE",
    }]
    result = assess_catalog(database, data, "CAT-09", _body())

    assert result["governance"] < 100.0
    assert result["reliability"] < 100.0
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "GOV_INTERNAL_EXECUTION" in failed
    assert "REL_INTERNAL_EXECUTION" in failed


def test_missing_semantic_attempt_task_round_provenance_reduces_integrity(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    database = tmp_path / "audit.db"
    connection = __import__("sqlite3").connect(database)
    try:
        connection.execute(
            """CREATE TABLE ai_provider_attempts(
                audit_id TEXT,semantic_contract_version TEXT,
                operation TEXT,ai_task_id TEXT,ai_round_id TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?)",
            ("AUD-ASSURANCE", "M18-SEMANTIC-22-v1", None, None, None),
        )
        connection.commit()
    finally:
        connection.close()
    _patch_catalog(monkeypatch)
    monkeypatch.setattr(assurance, "_applicable_config_markers", lambda *_args: ())

    data = _data()
    data.selected = {"CAT-03"}
    result = assess_catalog(database, data, "CAT-03", _body())

    assert result["governance"] < 100.0
    assert result["integrity"] < 100.0
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "GOV_AI_ATTEMPT_PROVENANCE" in failed
    assert "INT_AI_ATTEMPT_PROVENANCE" in failed


def test_requested_not_executed_is_explicit_in_catalog_execution_label() -> None:
    from rasai.catalog_report_analysis import _technical_work_status

    assert _technical_work_status("REQUESTED_NOT_EXECUTED") == "Solicitado, não executado"

def test_truthfully_persisted_provider_contract_failure_is_not_misclassified_as_internal_gap(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)
    monkeypatch.setattr(assurance, "_applicable_config_markers", lambda *_args: ())

    data = _data()
    data.selected = {"CAT-09"}
    data.work_items = [{
        "component": "CONTENT_REMEDIATION_AI",
        "scope_key": "AUDIT",
        "status": "FAILED_RETRYABLE",
        "last_error_class": "AI_CONTRACT",
        "last_error_code": "PROVIDER_RESPONSE_CONTRACT_ERROR",
    }]
    result = assess_catalog(database, data, "CAT-09", _body())

    internal = {
        item["code"]: item["passed"]
        for item in result["checks"]
        if item["code"] in {"GOV_INTERNAL_EXECUTION", "REL_INTERNAL_EXECUTION"}
    }
    assert internal == {
        "GOV_INTERNAL_EXECUTION": True,
        "REL_INTERNAL_EXECUTION": True,
    }
