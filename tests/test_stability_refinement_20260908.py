from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rasai.m24_ai import _resource_context_facts, _validate
from rasai.persistence import AuditWorkspace
from rasai.report_presentation import humanize_report_html


def test_priority_humanization_is_idempotent_and_uses_canonical_priority_names() -> None:
    html = "<table><tr><td>P1</td><td>P2</td><td>P3</td><td>P4</td></tr></table>"
    once = humanize_report_html(html)
    twice = humanize_report_html(once)
    assert once == twice
    assert "Muito alta (P1)" in once
    assert "Alta (P2)" in once
    assert "Média (P3)" in once
    assert "Baixa (P4)" in once
    assert "Alta (Alta" not in twice


def test_console_and_readiness_contract_explain_bounded_ai_and_scope_coverage() -> None:
    console = Path("src/rasai/console_cost.py").read_text(encoding="utf-8")
    readiness = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "BR-GEO-055/056" in console
    assert "sem peso extra nem bônus duplicado" in console
    assert "Scoring Coverage não é cobertura do domínio" in readiness
    assert "fronteira observada do crawl" in readiness
    assert "href='scoring.html'" in readiness
    assert "href='score-geo-004.html'" not in readiness


def test_resource_context_facts_expose_clean_robots_evidence_to_technical_ai(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    root.mkdir()
    db = root / "audit.db"
    connection = sqlite3.connect(db)
    try:
        connection.execute(
            "CREATE TABLE rule_executions (rule_execution_id TEXT, audit_id TEXT, rule_id TEXT, result TEXT, observed_value TEXT, evidence_ids TEXT)"
        )
        connection.executemany(
            "INSERT INTO rule_executions VALUES (?,?,?,?,?,?)",
            [
                ("R1", "AUD", "BR-GEO-017", "PASS", json.dumps({"state": "OBTAINED"}), json.dumps(["EV-ROBOTS"])),
                ("R2", "AUD", "BR-GEO-018", "PASS", json.dumps({"crawler": "Googlebot", "access": "ALLOW"}), json.dumps(["EV-ROBOTS"])),
                ("R3", "AUD", "BR-GEO-003", "PASS", json.dumps({"state": "OBTAINED"}), json.dumps(["EV-SITEMAP"])),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    workspace = AuditWorkspace(root)
    facts, evidence = _resource_context_facts(workspace, "AUD")
    by_category = {item["category"]: item for item in facts}
    assert set(by_category) == {"ROBOTS", "SITEMAP"}
    assert evidence["ROBOTS"] == frozenset({"EV-ROBOTS"})
    assert evidence["SITEMAP"] == frozenset({"EV-SITEMAP"})


def test_m24_resource_validation_cannot_cross_cite_sitemap_for_robots() -> None:
    base = {
        "summary_pt": "ok",
        "actions": [],
        "resource_assessments": [
            {
                "resource": "ROBOTS",
                "verdict": "POSITIVE",
                "confidence": 0.9,
                "evidence_ids": ["EV-ROBOTS"],
                "rationale_pt": "evidência coerente",
            }
        ],
        "policy_note_pt": "revisão humana",
    }
    value = _validate(
        base,
        allowed_codes=frozenset(),
        allowed_evidence=frozenset({"EV-ROBOTS", "EV-SITEMAP"}),
        resource_evidence={"ROBOTS": frozenset({"EV-ROBOTS"}), "SITEMAP": frozenset({"EV-SITEMAP"})},
    )
    assert value["resource_assessments"][0]["resource"] == "ROBOTS"

    bad = json.loads(json.dumps(base))
    bad["resource_assessments"][0]["evidence_ids"] = ["EV-SITEMAP"]
    try:
        _validate(
            bad,
            allowed_codes=frozenset(),
            allowed_evidence=frozenset({"EV-ROBOTS", "EV-SITEMAP"}),
            resource_evidence={"ROBOTS": frozenset({"EV-ROBOTS"}), "SITEMAP": frozenset({"EV-SITEMAP"})},
        )
    except ValueError as exc:
        assert "resource universe" in str(exc)
    else:
        raise AssertionError("cross-resource evidence must be rejected")
