from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.consolidation.consolidated_report_enrichment import (
    _enhance_rule_links,
    _render_technical_remediation,
    _technical_context,
    _translate_operational_wording,
)


def _database(root: Path, *, finding_id: str, observed: object, rule_id: str = "BR-GEO-013", severity: str = "HIGH") -> None:
    root.mkdir(parents=True)
    connection = sqlite3.connect(root / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE pages(page_id TEXT PRIMARY KEY, normalized_url TEXT);
            CREATE TABLE findings(
                finding_id TEXT PRIMARY KEY, audit_id TEXT, rule_id TEXT, page_id TEXT,
                severity TEXT, device TEXT, title TEXT, status TEXT
            );
            CREATE TABLE root_cause_analyses(
                finding_id TEXT PRIMARY KEY, rule_id TEXT, cause_type TEXT, affected_scope TEXT,
                cause_summary TEXT, evidence_basis TEXT, affected_elements TEXT,
                selector_status TEXT, observed_value TEXT, expected_condition TEXT,
                exact_change TEXT, example_after TEXT, acceptance_criteria TEXT,
                revalidation_steps TEXT, human_decision_required TEXT, diagnostic_confidence TEXT
            );
            """
        )
        connection.execute("INSERT INTO pages VALUES (?,?)", ("PAGE-1", "https://example.test/pagina"))
        connection.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?)",
            (finding_id, root.name, rule_id, "PAGE-1", severity, "MOBILE", "Canonical inconsistente", "OPEN"),
        )
        connection.execute(
            "INSERT INTO root_cause_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                finding_id, rule_id, "CANONICAL_DECLARATION", "<head>",
                "A canonical observada não satisfaz a condição esperada.",
                json.dumps(["EV-1"]),
                json.dumps([{"selector": "link[rel=canonical]", "tag_name": "link", "outer_html": '<link rel="canonical" href="/antiga">', "device": "MOBILE"}]),
                "EXACT", json.dumps(observed), "Uma canonical absoluta e coerente",
                "Corrigir o href da canonical após confirmar a URL preferencial.",
                '<link rel="canonical" href="https://example.test/pagina">',
                json.dumps(["Canonical única e absoluta."]),
                json.dumps(["Reexecutar BR-GEO-013."]),
                None, "HIGH",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_technical_context_reads_persisted_root_cause_and_marks_change(tmp_path: Path) -> None:
    baseline = tmp_path / "AUD-BASE"
    current = tmp_path / "AUD-CURR"
    _database(baseline, finding_id="F-1", observed={"href": "/old"})
    _database(current, finding_id="F-2", observed={"href": "/new"})
    bundle = SimpleNamespace(
        baseline_workspace=baseline,
        current_workspace=current,
        comparison=SimpleNamespace(
            baseline=SimpleNamespace(audit_id="AUD-BASE"),
            current=SimpleNamespace(audit_id="AUD-CURR"),
        ),
        events=({"rule_id": "BR-GEO-013", "url": "https://example.test/pagina"},),
        fixes=(),
    )

    context = _technical_context(bundle)

    assert len(context) == 1
    item = context[0]
    assert item["evolution_status"] == "CHANGED"
    assert item["url"] == "https://example.test/pagina"
    assert item["affected_elements"][0]["outer_html"].startswith("<link")
    assert item["remediation_recipe"]["title"] == "Corrigir declaração canonical"


def test_rule_ids_become_descriptive_links() -> None:
    artifact = {
        "rule_reference": [
            {
                "rule_id": "BR-GEO-013",
                "tooltip": "Verifica se declarações canonical são interpretáveis.",
                "remediation": {},
                "references": [],
            }
        ]
    }
    html = "<html><body><section id='specialist-evolution' class='panel'><p>BR-GEO-013</p><code>BR-GEO-013</code></section></body></html>"

    rendered = _enhance_rule_links(html, artifact)

    assert rendered.count("href='rules-reference.html#BR-GEO-013'") == 2
    assert "title='Verifica se declarações canonical são interpretáveis.'" in rendered
    assert "Consultar definições e remediações" in rendered


def test_technical_remediation_distinguishes_observed_from_example() -> None:
    artifact = {
        "current_technical_findings": [
            {
                "rule_id": "BR-GEO-013",
                "severity": "HIGH",
                "evolution_status": "NEW",
                "url": "https://example.test/pagina",
                "device": "MOBILE",
                "finding_title": "Canonical inconsistente",
                "cause_summary": "A canonical observada é inconsistente.",
                "observed_value": {"href": "/old"},
                "affected_elements": [{"outer_html": '<link rel="canonical" href="/old">'}],
                "exact_change": "Corrigir o href.",
                "example_after": '<link rel="canonical" href="https://example.test/pagina">',
                "acceptance_criteria": ["Canonical única."],
                "revalidation_steps": ["Reexecutar BR-GEO-013."],
            }
        ]
    }

    rendered = _render_technical_remediation(artifact)

    assert "HTML observado na URL" in rendered
    assert "Exemplo de implementação" in rendered
    assert "Proveniência" in rendered
    assert "não devem ser confundidos com conteúdo observado" in rendered


def test_operational_english_is_normalized_but_metric_names_are_preserved() -> None:
    html = (
        "<p>Verification proves only the persisted rule transition between the two selected audits; "
        "it does not prove downstream Search/AI impact.</p>"
        "<p>Média findings</p><p>Δ 2 count</p><p>Δ -26.667 points</p>"
        "<p>Evidence & Trust</p><p>Core Web Vitals: Fail</p>"
    )

    rendered = _translate_operational_wording(html)

    assert "A verificação comprova apenas" in rendered
    assert "Achados de severidade Média" in rendered
    assert "Δ 2 ocorrências" in rendered
    assert "Δ -26.667 pontos" in rendered
    assert "Evidence & Trust" in rendered
    assert "Core Web Vitals: Não aprovado" in rendered
