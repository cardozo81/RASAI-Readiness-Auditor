from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

from rasai.recommendation_governance import (
    ACCEPTED,
    AUDITOR_INTERNAL,
    EXTERNAL_PROVIDER,
    INFORMATIONAL,
    REJECTED,
    TARGET_SITE,
    VERIFY_DECIDE,
    classify_candidate,
    evaluate_recommendations,
)


def _database(root: Path) -> Path:
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            INSERT INTO audits VALUES ('AUD-1');
            CREATE TABLE jsonld_remediation_suggestions(
                suggestion_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                page_id TEXT,
                snapshot_id TEXT,
                device TEXT,
                status TEXT,
                existing_types TEXT,
                proposed_json TEXT,
                improvements TEXT,
                evidence_ids TEXT,
                created_at TEXT
            );
            CREATE TABLE request_remediation_groups(
                group_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                family TEXT,
                party_scope TEXT,
                title TEXT,
                occurrence_count INTEGER,
                problem_count INTEGER,
                affected_sample_count INTEGER,
                total_sample_count INTEGER,
                recurrence_ratio REAL,
                recurrence_class TEXT,
                source_catalogs_json TEXT,
                resource_urls_json TEXT,
                http_statuses_json TEXT,
                error_types_json TEXT,
                observed_impacts_json TEXT,
                potential_impacts_json TEXT,
                public_reference_label TEXT,
                public_reference_url TEXT,
                evidence_fingerprint TEXT,
                updated_at TEXT
            );
            CREATE TABLE request_remediation_ai(
                group_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                evidence_fingerprint TEXT,
                provider TEXT,
                model TEXT,
                status TEXT,
                title TEXT,
                solution TEXT,
                technical_detail TEXT,
                example TEXT,
                verification TEXT,
                confidence REAL,
                effort TEXT,
                reason TEXT,
                updated_at TEXT
            );
            CREATE TABLE request_remediation_evidence(
                evidence_id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                audit_id TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    return database


def test_jsonld_absent_cannot_be_described_as_fixing_existing_jsonld() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO jsonld_remediation_suggestions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "J1", "AUD-1", "P1", "S1", "MOBILE", "SUGGESTED", "[]", None,
                    json.dumps(["Corrigir JSON-LD existente"], ensure_ascii=False),
                    json.dumps(["EV-JSONLD-ABSENT"]), "2026-09-17T12:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        rows = evaluate_recommendations(database, "AUD-1")
        row = next(item for item in rows if item["source_id"] == "J1")
        assert row["target_class"] == TARGET_SITE
        assert row["decision"] == REJECTED
        assert row["rejection_reason"] == "JSONLD_ABSENT_EXISTING_CONFLICT"
        assert row["conflict_group"] == "JSONLD_EXISTENCE"


def test_jsonld_absent_with_unproven_entity_requires_decision() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO jsonld_remediation_suggestions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "J2", "AUD-1", "P1", "S1", "MOBILE", "SUGGESTED", "[]",
                    json.dumps({"@context": "https://schema.org", "@type": "Organization"}),
                    json.dumps(["Criar JSON-LD para a organização"], ensure_ascii=False),
                    json.dumps(["EV-JSONLD-ABSENT"]), "2026-09-17T12:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        rows = evaluate_recommendations(database, "AUD-1")
        row = next(item for item in rows if item["source_id"] == "J2")
        assert row["target_class"] == TARGET_SITE
        assert row["decision"] == VERIFY_DECIDE
        assert row["rejection_reason"] == "JSONLD_CONTENT_OR_ENTITY_NOT_PROVEN"
        assert row["conflict_group"] == "JSONLD_CONTENT_SUPPORT"


def test_jsonld_webpage_baseline_with_persisted_evidence_is_accepted() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "JSONLD",
        {
            "status": "MISSING_PROPOSED",
            "existing_types": "[]",
            "proposed_json": json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "url": "https://example.test/pagina",
                    "name": "Título observado",
                }
            ),
            "evidence_ids": json.dumps(["EV-MAIN-CONTENT", "EV-META-TITLE"]),
        },
    )
    assert target == TARGET_SITE
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None


def test_canonical_absence_requires_preferred_url_decision() -> None:
    target, decision, reason, conflict, rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-013",
            "observed_value": json.dumps({"canonicals": []}),
            "title": "Adicionar canonical autorreferente para /seguro-de-vida",
            "description": "Implementar canonical autorreferente.",
        },
    )
    assert target == TARGET_SITE
    assert decision == VERIFY_DECIDE
    assert reason == "CANONICAL_PREFERRED_URL_NOT_PROVEN"
    assert conflict == "CANONICAL_TARGET_DECISION"
    assert "não comprova qual URL" in rationale


def test_canonical_specific_action_requires_prescription_to_match_proven_target() -> None:
    proven = {
        "rule_id": "BR-GEO-013",
        "observed_value": json.dumps(
            {
                "canonicals": [],
                "preferred_url": "https://example.test/preferida",
            }
        ),
    }
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            **proven,
            "title": "Definir canonical para https://example.test/preferida",
        },
    )
    assert target == TARGET_SITE
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None

    _target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            **proven,
            "title": "Definir canonical para https://example.test/outra",
        },
    )
    assert decision == VERIFY_DECIDE
    assert reason == "PRESCRIPTION_CONFLICTS_WITH_EVIDENCE"
    assert conflict == "CANONICAL_TARGET_DECISION"


def test_noindex_requires_deliberate_indexability_intent() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-012",
            "observed_value": json.dumps({"explicit_noindex": True}),
            "title": "Remover noindex para indexar a página",
        },
    )
    assert target == TARGET_SITE
    assert decision == VERIFY_DECIDE
    assert reason == "INDEXABILITY_INTENT_NOT_PROVEN"
    assert conflict == "INDEXABILITY_POLICY_DECISION"

    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-012",
            "observed_value": json.dumps(
                {
                    "explicit_noindex": True,
                    "intended_indexability": "INDEX",
                }
            ),
            "title": "Remover noindex para indexar a página",
        },
    )
    assert target == TARGET_SITE
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None


def test_redirect_target_requires_persisted_destination() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-008",
            "observed_value": json.dumps({"redirect_count": 4}),
            "title": "Redirecionar para https://example.test/destino",
        },
    )
    assert target == TARGET_SITE
    assert decision == VERIFY_DECIDE
    assert reason == "REDIRECT_TARGET_NOT_PROVEN"
    assert conflict == "REDIRECT_TARGET_DECISION"

    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-008",
            "observed_value": json.dumps(
                {
                    "redirect_count": 4,
                    "redirect_target": "https://example.test/destino",
                }
            ),
            "title": "Redirecionar para https://example.test/destino",
        },
    )
    assert target == TARGET_SITE
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None


def test_third_party_request_remediation_targets_external_provider() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO request_remediation_groups VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "REQG-1", "AUD-1", "RESOURCE_NOT_FOUND", "THIRD_PARTY", "Corrigir recurso externo ausente",
                    2, 1, 2, 5, 0.4, "Intermitente", '["CAT-07"]', '["https://cdn.example/x.js"]', '[404]',
                    '["REQUEST_FAILED"]', '["Experiência sintética"]', '["Experiência"]', "MDN", "https://example.invalid",
                    "fingerprint", "2026-09-17T12:00:00Z",
                ),
            )
            connection.execute(
                "INSERT INTO request_remediation_ai VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "REQG-1", "AUD-1", "fingerprint", "openai", "model", "SUCCESS",
                    "Revisar dependência externa", "Acionar o fornecedor/CDN", "Validar URL publicada", "", "Reexecutar",
                    0.9, "LOW", None, "2026-09-17T12:01:00Z",
                ),
            )
            connection.execute("INSERT INTO request_remediation_evidence VALUES ('REQE-1','REQG-1','AUD-1')")
            connection.commit()
        finally:
            connection.close()

        rows = evaluate_recommendations(database, "AUD-1")
        row = next(item for item in rows if item["source_id"] == "REQG-1")
        assert row["target_class"] == EXTERNAL_PROVIDER
        assert row["decision"] == ACCEPTED
        assert json.loads(row["source_evidence_json"]) == ["REQE-1"]


def test_auditor_internal_recommendation_is_not_a_client_action() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {"title": "Corrigir audit.db do RASAi", "description": "Ajustar persistência interna do auditor"},
    )
    assert target == AUDITOR_INTERNAL
    assert decision == REJECTED
    assert reason == "AUDITOR_INTERNAL_NOT_CLIENT_ACTION"
    assert conflict == "TARGET_SCOPE"

def test_grouped_neutral_robots_absence_is_informational_not_client_action() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                """
                CREATE TABLE findings(
                    finding_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    observed_value TEXT,
                    evidence_ids TEXT
                );
                CREATE TABLE root_cause_analyses(
                    analysis_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    observed_value TEXT,
                    evidence_basis TEXT
                );
                CREATE TABLE remediation_groups(
                    group_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    affected_findings TEXT NOT NULL
                );
                CREATE TABLE recommendations(
                    recommendation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    finding_id TEXT,
                    remediation_group_id TEXT,
                    title TEXT,
                    description TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO findings VALUES (?,?,?,?,?)",
                (
                    "F-ROBOTS",
                    "AUD-1",
                    "BR-GEO-017",
                    json.dumps({"state": "ABSENT", "url": "https://example.test/robots.txt"}),
                    json.dumps(["EV-ROBOTS"]),
                ),
            )
            connection.execute(
                "INSERT INTO root_cause_analyses VALUES (?,?,?,?,?,?)",
                (
                    "RCA-ROBOTS",
                    "AUD-1",
                    "F-ROBOTS",
                    "BR-GEO-017",
                    json.dumps({"state": "ABSENT", "url": "https://example.test/robots.txt"}),
                    json.dumps(["EV-ROBOTS"]),
                ),
            )
            connection.execute(
                "INSERT INTO remediation_groups VALUES (?,?,?,?)",
                ("G-ROBOTS", "AUD-1", "BR-GEO-017", json.dumps(["F-ROBOTS"])),
            )
            connection.execute(
                "INSERT INTO recommendations VALUES (?,?,?,?,?,?)",
                (
                    "REC-ROBOTS",
                    "AUD-1",
                    None,
                    "G-ROBOTS",
                    "Corrigir robots.txt não interpretável",
                    "Ausência válida não deve ser tratada como defeito.",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        rows = evaluate_recommendations(database, "AUD-1")
        row = next(item for item in rows if item["source_id"] == "REC-ROBOTS")

        assert row["target_class"] == INFORMATIONAL
        assert row["decision"] == REJECTED
        assert row["rejection_reason"] == "DISCOVERY_NEUTRAL_STATE_HUMAN_DECISION"
        assert row["conflict_group"] == "DISCOVERY_RESOURCE_STATE"
        assert json.loads(row["source_evidence_json"]) == ["EV-ROBOTS"]


def test_known_neutral_discovery_states_are_informational() -> None:
    cases = (
        ("BR-GEO-003", {"sitemaps": [{"state": "ABSENT", "error": None}]}),
        ("BR-GEO-017", {"state": "ABSENT"}),
        ("BR-GEO-055", {"ai_verdict": "NEUTRAL", "resource": "SITEMAP"}),
        ("BR-GEO-056", {"ai_verdict": "NEUTRAL", "resource": "ROBOTS"}),
    )
    for rule_id, observed in cases:
        target, decision, reason, conflict, _rationale = classify_candidate(
            "DETERMINISTIC",
            {
                "rule_id": rule_id,
                "observed_value": json.dumps(observed),
                "title": f"Remediar {rule_id}",
            },
        )
        assert target == INFORMATIONAL
        assert decision == REJECTED
        assert reason == "DISCOVERY_NEUTRAL_STATE_HUMAN_DECISION"
        assert conflict == "DISCOVERY_RESOURCE_STATE"


def test_invalid_robots_state_remains_actionable() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DETERMINISTIC",
        {
            "rule_id": "BR-GEO-017",
            "observed_value": json.dumps({"state": "INVALID", "error": "syntax"}),
            "title": "Corrigir robots.txt inválido",
        },
    )

    assert target == TARGET_SITE
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None



def test_deep_analysis_reuses_deterministic_external_provider_ownership() -> None:
    target, decision, reason, conflict, rationale = classify_candidate(
        "DEEP_ANALYSIS",
        {
            "title": "Revisar dependência externa",
            "details_json": json.dumps({
                "target": {
                    "kind": "RESOURCE",
                    "ref": "PSR-1",
                    "owner_class": "EXTERNAL_PROVIDER",
                }
            }),
        },
    )
    assert target == EXTERNAL_PROVIDER
    assert decision == ACCEPTED
    assert reason is None
    assert conflict is None
    assert "determinístico" in rationale


def test_deep_analysis_does_not_promote_informational_target() -> None:
    target, decision, reason, conflict, _rationale = classify_candidate(
        "DEEP_ANALYSIS",
        {
            "title": "Revisar ownership",
            "details_json": json.dumps({
                "target": {
                    "kind": "SCRIPT",
                    "ref": "PSS-1",
                    "owner_class": "INFORMATIONAL",
                }
            }),
        },
    )
    assert target == INFORMATIONAL
    assert decision == REJECTED
    assert reason == "UNKNOWN_OWNERSHIP_INFORMATIONAL_ONLY"
    assert conflict == "TARGET_SCOPE"
