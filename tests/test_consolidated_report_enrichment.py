from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.consolidation.consolidated_report_enrichment import (
    _ACTION_LABELS,
    _augment_longitudinal_packet,
    _enhance_rule_links,
    _humanize_domain_text,
    _presentation,
    _render_technical_remediation,
    _rules_page,
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


def test_longitudinal_packet_receives_bounded_technical_context_per_interval(tmp_path: Path) -> None:
    baseline = tmp_path / "AUD-BASE"
    current = tmp_path / "AUD-CURR"
    _database(baseline, finding_id="F-1", observed={"href": "/old"})
    _database(current, finding_id="F-2", observed={"href": "/new"})

    pair = SimpleNamespace(
        baseline_workspace=baseline,
        current_workspace=current,
        comparison=SimpleNamespace(
            baseline=SimpleNamespace(audit_id="AUD-BASE"),
            current=SimpleNamespace(audit_id="AUD-CURR"),
        ),
        events=({"rule_id": "BR-GEO-013", "url": "https://example.test/pagina"},),
        fixes=(),
    )
    bundle = SimpleNamespace(intervals=(pair,), global_evolution=pair)

    def original(_bundle):
        return (
            {
                "intervals": [{"interval_id": "INTERVALO-001"}],
                "initial_to_final": {},
                "governance": {},
            },
            ("I001-CHANGE-0001",),
        )

    packet, allowed = _augment_longitudinal_packet(original, bundle)

    assert "I001-CHANGE-0001" in allowed
    assert "I001-FINDING-0001" in allowed
    assert "GLOBAL-FINDING-0001" in allowed
    assert packet["intervals"][0]["current_technical_findings"][0]["evidence_id"] == "I001-FINDING-0001"
    assert packet["intervals"][0]["current_technical_findings"][0]["rule_id"] == "BR-GEO-013"
    assert packet["initial_to_final"]["current_technical_findings"][0]["evidence_id"] == "GLOBAL-FINDING-0001"
    assert packet["initial_to_final"]["current_technical_findings"][0]["evolution_status"] == "CHANGED"
    assert packet["rule_reference"][0]["rule_id"] == "BR-GEO-013"
    assert packet["governance"]["technical_remediation_origin"] == "PERSISTED_ROOT_CAUSE_AND_DETERMINISTIC_RECIPE"


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
                "device": "BOTH",
                "finding_title": "Canonical declarations must be interpretable and non-conflicting",
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
    assert "Declarações canonical devem ser interpretáveis e não conflitantes" in rendered
    assert "Mobile e Desktop" in rendered
    assert "Canonical declarations must be interpretable and non-conflicting" not in rendered


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


def test_rules_reference_uses_same_cons_identity_and_search() -> None:
    artifact = {
        "rule_reference": [
            {
                "rule_id": "BR-GEO-013",
                "tooltip": "Verifica se declarações canonical são interpretáveis.",
                "remediation": {
                    "title": "Corrigir declaração canonical",
                    "target": "SEO técnico",
                    "element": "link rel=canonical",
                    "location": "head",
                    "action": "UPDATE",
                    "description": "Ajustar a canonical para a URL preferencial.",
                    "acceptance": ["Canonical única e absoluta."],
                    "validation": ["Reexecutar a regra."],
                },
                "references": [],
            }
        ]
    }

    html = _rules_page(artifact)

    assert "Definições BR-GEO - RASAi" in html
    assert "Voltar ao relatório consolidado" in html
    assert "Pesquisar regra, problema, alvo ou ação" in html
    assert "rules-header-shell" in html
    assert ".rules-header-shell{margin:auto;padding:0 24px}" in html
    assert "main{margin:auto;padding:24px}" in html
    assert "max-width:1280px" not in html
    assert "Atualizar" in html
    assert ">UPDATE<" not in html
    assert "details>summary::before" in html
    assert "text-align:left" in html
    assert "data-rule-card" in html
    assert ".rule-grid>div{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:12px 14px}" in html
    assert "BR-GEO-013" in html
    assert "—" not in html
    assert "--green-soft:#edf8f0" in html


def test_rules_reference_humanizes_all_remediation_action_domains() -> None:
    expected_actions = {
        "RESTORE_ACCESS", "RESOLVE_CONFLICT", "REVIEW_DIRECTIVE", "ADD_OR_CORRECT",
        "CORRECT_TARGET", "CORRECT_RESOURCE", "REVIEW_CRAWLER_POLICY", "EDIT_CONTENT",
        "RESTRUCTURE_CONTENT", "CLARIFY_ENTITY", "CLARIFY_ENTITY_RELATIONSHIPS",
        "DISAMBIGUATE_ENTITY", "CORRECT_STRUCTURED_DATA", "ALIGN_STRUCTURED_DATA",
        "ALIGN_ENTITY_MARKUP", "CLARIFY_INTENT", "ADD_OR_RESTRUCTURE_ANSWER",
        "ADD_CONTEXT", "CLARIFY_CLAIMS", "ADD_FACTUAL_CONTEXT", "ADD_QUALIFIERS",
        "MAKE_EXPLICIT", "ADD_ATTRIBUTION", "ADD_RESPONSIBILITY_SIGNAL",
        "ALIGN_FRESHNESS_SIGNALS", "CLOSE_INTENT_GAPS", "REVIEW_AND_CORRECT",
    }
    assert expected_actions <= set(_ACTION_LABELS)
    assert all("_" not in _ACTION_LABELS[action] for action in expected_actions)

    artifact = {
        "rule_reference": [
            {
                "rule_id": "BR-GEO-060",
                "tooltip": "Regra sem receita específica.",
                "remediation": {
                    "title": "Revisar condição",
                    "target": "Condição observada",
                    "element": None,
                    "location": None,
                    "action": "REVIEW_AND_CORRECT",
                    "description": "Revisar e corrigir a condição registrada.",
                    "acceptance": ["Atender à condição esperada."],
                    "validation": ["Reexecutar BR-GEO-060 e revisar evidence_ids associadas."],
                },
                "references": [
                    {"reference_scope": "Baseline interno", "basis": "INTERNAL_BASELINE"},
                    {"reference_scope": "Heurística", "basis": "HEURISTIC"},
                    {"reference_scope": "Padrão", "basis": "STANDARD"},
                ],
            }
        ]
    }
    html = _rules_page(artifact)
    assert "Revisar e corrigir" in html
    assert "REVIEW_AND_CORRECT" not in html
    assert "Referência interna do RASAi" in html
    assert "Heurística" in html
    assert "Padrão técnico" in html
    assert "identificadores de evidência" in html
    assert "IDs de evidência" not in html
    assert "evidence_ids" not in html


def test_domain_text_is_humanized_in_pt_br() -> None:
    text = _humanize_domain_text("Severidade MEDIUM · Content Value · Structured Data · REVIEW_AND_CORRECT · MOBILE · PASS")
    assert "Severidade média" in text
    assert "Valor de conteúdo" in text
    assert "Dados estruturados" in text
    assert "Revisar e corrigir" in text
    assert "(Content Value)" not in text
    assert "(Structured Data)" not in text
    assert "REVIEW_AND_CORRECT" not in text
    assert "Dispositivo móvel" in text
    assert "Aprovado" in text

def test_rule_reference_humanizes_remaining_control_language_and_grammar() -> None:
    from rasai.consolidation.consolidated_report_enrichment import _humanize_domain_text

    rendered = _humanize_domain_text(
        "Claims materiais com freshness insuficiente usam fallback; "
        "condição registrada no finding e condição esperada do finding; "
        "este é um fallback; evidence_ids."
    )

    assert "Afirmações materiais" in rendered
    assert "atualização" in rendered
    assert "alternativa genérica" in rendered
    assert "na ocorrência" in rendered
    assert "da ocorrência" in rendered
    assert "uma alternativa genérica" in rendered
    assert "identificadores de evidência" in rendered
    assert "Claims" not in rendered
    assert "freshness" not in rendered
    assert "fallback" not in rendered

def test_presentation_adds_technical_navigation_after_remediation_section_is_inserted() -> None:
    html = (
        "<html><head></head><body>"
        "<nav aria-label='Navegação do relatório'><a href='#cons-governance'>Governança</a></nav>"
        "<main></main><footer></footer></body></html>"
    )
    artifact = {
        "current_technical_findings": [
            {
                "rule_id": "BR-GEO-013",
                "severity": "HIGH",
                "evolution_status": "NEW",
                "finding_title": "Canonical inconsistente",
                "cause_summary": "A canonical observada é inconsistente.",
                "acceptance_criteria": ["Canonical única."],
                "revalidation_steps": ["Reexecutar BR-GEO-013."],
            }
        ]
    }

    rendered = _presentation(lambda value, _artifact=None: value, html, artifact)

    assert "id='technical-remediation'" in rendered
    assert rendered.count("href='#technical-remediation'") == 1
    assert rendered.index("href='#technical-remediation'") < rendered.index("href='#cons-governance'")

