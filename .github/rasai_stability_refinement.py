from __future__ import annotations

from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# 1) Idempotent/canonical priority presentation.
path = "src/rasai/report_presentation.py"
text = read(path)
text = replace_once(
    text,
    '    "P0": "Crítica (P0)",\n    "P1": "Alta (P1)",\n    "P2": "Média (P2)",\n    "P3": "Baixa (P3)",\n    "P4": "Muito baixa (P4)",',
    '    "P0": "Crítica (P0)",\n    "P1": "Muito alta (P1)",\n    "P2": "Alta (P2)",\n    "P3": "Média (P3)",\n    "P4": "Baixa (P4)",',
    label="priority labels",
)
marker = '\n\ndef humanize_report_html(html: str, *, page_name: str | None = None) -> str:\n'
helper = '''\n\ndef _public_token_replacement(match: re.Match[str]) -> str:\n    value = match.group(1)\n    # Priority labels intentionally retain the canonical Pn token in parentheses.\n    # Keep repeated report-normalization passes idempotent instead of recursively\n    # expanding e.g. P2 -> Alta (P2) -> Alta (Alta (P2)).\n    if value in {"P0", "P1", "P2", "P3", "P4"} and match.start() > 0 and match.string[match.start() - 1] == "(":\n        return value\n    return _PUBLIC_LABELS[value]\n'''
if helper.strip() not in text:
    text = replace_once(text, marker, helper + marker, label="priority idempotency helper")
text = replace_once(
    text,
    '        output.append(_PUBLIC_TOKEN_RE.sub(lambda match: _PUBLIC_LABELS[match.group(1)], part))',
    '        output.append(_PUBLIC_TOKEN_RE.sub(_public_token_replacement, part))',
    label="priority token replacement",
)
write(path, text)


# 2) Console cost/exposure text: deterministic M24 diagnostics are advisory, but
# bounded BR-GEO-055/056 may contribute inside existing groups.
path = "src/rasai/console_cost.py"
text = read(path)
text = replace_once(
    text,
    '            "A remediação técnica de crawling/discovery é audit-level e pode acrescentar tentativas quando houver diagnósticos técnicos elegíveis; permanece advisory/non-scoring."',
    '            "A remediação técnica de crawling/discovery é audit-level e pode acrescentar tentativas quando houver evidência técnica elegível. Os diagnósticos M24 permanecem advisory; uma avaliação evidence-bound válida pode materializar BR-GEO-055/056 dentro dos grupos SITEMAP/ROBOTS, sem peso extra nem bônus duplicado."',
    label="console technical AI wording",
)
write(path, text)

for doc in ("docs/CLI_REFERENCE.md", "docs/CONSOLE_COST_AND_USAGE.md", "docs/AI_GUIDE.md"):
    p = Path(doc)
    if not p.is_file():
        continue
    content = p.read_text(encoding="utf-8")
    content = content.replace(
        "Default OFF; advisory/non-scoring.",
        "Default OFF. Os diagnósticos M24 são advisory; quando habilitada, uma avaliação técnica evidence-bound válida pode materializar BR-GEO-055/056 nos grupos SITEMAP/ROBOTS sem peso adicional.",
    )
    content = content.replace(
        "remediação técnica de crawling/discovery permanece advisory/non-scoring",
        "diagnósticos técnicos de crawling/discovery permanecem advisory; avaliações evidence-bound válidas podem materializar BR-GEO-055/056 nos grupos SITEMAP/ROBOTS sem bônus duplicado",
    )
    p.write_text(content, encoding="utf-8", newline="\n")


# 3) SARI reporting: distinguish scoring coverage from crawl/scope coverage and
# remove the unpublished scoring alias link.
path = "src/rasai/rasai_readiness_reporting.py"
text = read(path)
old_target = '''        target = _one(\n            connection,\n            "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY target_id LIMIT 1",\n            (audit_id,),\n        )\n        return {'''
new_target = '''        target = _one(\n            connection,\n            "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY target_id LIMIT 1",\n            (audit_id,),\n        )\n        page_count_row = _one(\n            connection,\n            "SELECT COUNT(*) AS page_count FROM pages WHERE audit_id=?",\n            (audit_id,),\n        )\n        return {'''
text = replace_once(text, old_target, new_target, label="readiness page count query")
text = replace_once(
    text,
    '            "m24_run": m24_run,\n        }',
    '            "m24_run": m24_run,\n            "page_count": int(page_count_row["page_count"]) if page_count_row is not None else 0,\n        }',
    label="readiness page count projection",
)
text = replace_once(
    text,
    '{_audit_limitations_block(audit)}\n{_sari_governance_block(data)}',
    '{_audit_limitations_block(audit)}\n{_scope_coverage_block(data)}\n{_sari_governance_block(data)}',
    label="scope coverage block insertion",
)
text = text.replace("<h3>Coverage</h3><p>Mede completude da análise aplicável. O Overall usa a média da Coverage das dimensões aplicáveis.</p>", "<h3>Scoring Coverage</h3><p>Mede a completude das regras aplicáveis dentro do universo efetivamente auditado. O Overall usa a média dessa Coverage entre dimensões aplicáveis; ela não representa percentual de URLs do domínio rastreadas ou auditadas.</p>")
text = text.replace("href='score-geo-004.html'", "href='scoring.html'")

scope_helper = r'''

def _scope_coverage_block(data: dict[str, Any]) -> str:
    """Explain rule coverage separately from crawl/scope coverage.

    Discovered URL counts are an observed crawl frontier, not a guaranteed exhaustive
    denominator for the domain. Therefore the report exposes counts and matrix limits
    without manufacturing a percentage of "domain coverage".
    """
    audit = data.get("audit")
    target = data.get("target")
    scores = data.get("scores") or []
    audited_pages = int(data.get("page_count") or 0)
    target_type = str(target["target_type"]) if target is not None and "target_type" in target.keys() else "-"
    max_pages = int(audit["max_pages"] or 0) if audit is not None and "max_pages" in audit.keys() else 0

    limitations: list[str] = []
    if audit is not None and "limitations" in audit.keys() and audit["limitations"]:
        raw = audit["limitations"]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = [raw]
        else:
            parsed = raw
        if isinstance(parsed, list):
            limitations = [str(item) for item in parsed]
        elif parsed:
            limitations = [str(parsed)]

    discovered: int | None = None
    reported_audited: int | None = None
    for item in limitations:
        match = re.search(r"MAX_PAGES_REACHED:discovered=(\d+);audited=(\d+)", item)
        if match:
            discovered = int(match.group(1))
            reported_audited = int(match.group(2))
            break

    overall_rows = [row for row in scores if str(row["dimension"]) == "OVERALL_READINESS"]
    scoring = " · ".join(
        f"{str(row['device']).title()} {float(row['coverage']) * 100:.1f}%"
        for row in overall_rows
    ) or "Indisponível"
    audited_display = reported_audited if reported_audited is not None else audited_pages
    discovered_display = str(discovered) if discovered is not None else "não consolidado como universo exaustivo"

    warning = ""
    if target_type.upper() == "DOMAIN" and discovered is not None and audited_display < discovered:
        warning = (
            "<div class='notice warn'><strong>Matriz de domínio limitada pela parametrização:</strong> "
            f"o crawler observou {discovered} URL(s), mas {audited_display} página(s) entraram no universo auditado "
            f"com <code>max_pages={max_pages}</code>. Isso não é erro do RASAi e não reduz automaticamente o score; "
            "é uma opção de escopo. Para avaliar o domínio com maior representatividade, aumente max_pages de forma "
            "conservadora. Se a intenção era avaliar somente a URL informada, use escopo de URL/página.</div>"
        )

    return (
        "<section class='panel'><div class='kicker'>Cobertura e escopo</div>"
        "<h2>Scoring Coverage não é cobertura do domínio</h2>"
        "<p class='intro'>Scoring Coverage mede quanta evidência/regra aplicável foi concluída no universo auditado. "
        "A cobertura de escopo descreve quantas páginas efetivamente entraram na matriz. URLs descobertas são uma "
        "fronteira observada do crawl e não um denominador exaustivo garantido do domínio.</p>"
        "<div class='metric-grid'>"
        f"{_metric('Scoring Coverage', scoring)}"
        f"{_metric('Páginas auditadas', str(audited_display))}"
        f"{_metric('URLs descobertas no crawl', discovered_display)}"
        f"{_metric('Target / max_pages', f'{target_type} / {max_pages if max_pages else "-"}')}"
        "</div>" + warning + "</section>"
    )
'''
if "def _scope_coverage_block(" not in text:
    insertion = "\n\ndef _overall_card(scores: list[sqlite3.Row], device: str) -> str:\n"
    text = replace_once(text, insertion, scope_helper + insertion, label="scope coverage helper")
write(path, text)


# 4) M24 technical AI: expose deterministic ROBOTS/SITEMAP baseline evidence even
# when there is no problem diagnostic. Resource assessments remain evidence-bound.
path = "src/rasai/m24_ai.py"
text = read(path)
helper = r'''

_RESOURCE_RULES: dict[str, tuple[str, ...]] = {
    "SITEMAP": ("BR-GEO-003",),
    "ROBOTS": ("BR-GEO-017", "BR-GEO-018"),
}


def _decode_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _resource_context_facts(
    workspace: AuditWorkspace,
    audit_id: str,
) -> tuple[list[dict[str, Any]], dict[str, frozenset[str]]]:
    """Build non-diagnostic resource facts from persisted scoring inputs.

    A clean/present robots.txt may produce no M24 problem diagnostic; that must not
    prevent an explicitly enabled technical-AI assessment from reviewing the same
    deterministic evidence. These facts are provider context only and are not new
    findings or score contributions by themselves.
    """
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = list(
            connection.execute(
                """SELECT rule_id,result,observed_value,evidence_ids
                   FROM rule_executions
                   WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018')
                   ORDER BY rule_id,rule_execution_id""",
                (audit_id,),
            ).fetchall()
        )
    except sqlite3.OperationalError:
        rows = []
    finally:
        connection.close()

    facts: list[dict[str, Any]] = []
    resource_evidence: dict[str, frozenset[str]] = {}
    for resource, rule_ids in _RESOURCE_RULES.items():
        selected = [row for row in rows if str(row["rule_id"]) in rule_ids]
        evidence_ids: list[str] = []
        rule_states: list[dict[str, Any]] = []
        for row in selected:
            raw_ids = _decode_json_value(row["evidence_ids"], [])
            if isinstance(raw_ids, (list, tuple)):
                for evidence_id in raw_ids:
                    value = str(evidence_id).strip()
                    if value and value not in evidence_ids:
                        evidence_ids.append(value)
            rule_states.append(
                {
                    "rule_id": str(row["rule_id"]),
                    "result": str(row["result"]),
                    "observed": _decode_json_value(row["observed_value"], row["observed_value"]),
                }
            )
        if not rule_states or not evidence_ids:
            continue
        resource_evidence[resource] = frozenset(evidence_ids)
        facts.append(
            {
                "code": f"M24-RESOURCE-{resource}-BASELINE",
                "category": resource,
                "severity": "INFO",
                "title": f"Evidência determinística de {resource.lower()} para avaliação técnica bounded",
                "scope_url": None,
                "observed": {"rule_states": rule_states},
                "evidence_ids": evidence_ids,
                "deterministic_remediation": "Nenhuma conclusão adicional: avaliar somente a evidência fornecida.",
                "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            }
        )
    return facts, resource_evidence
'''
if "_RESOURCE_RULES:" not in text:
    text = replace_once(text, '\n\ndef maybe_remediate_m24(\n', helper + '\n\ndef maybe_remediate_m24(\n', label="m24 resource context helper")

old = '''    allowed_codes = frozenset(item.code for item in diagnostics)\n    allowed_evidence = frozenset(\n        evidence_id\n        for item in diagnostics\n        for evidence_id in item.evidence_ids\n        if evidence_id\n    )\n    facts = [\n        {\n            "code": item.code,\n            "category": item.category,\n            "severity": item.severity,\n            "title": item.title,\n            "scope_url": item.scope_url,\n            "observed": item.observed,\n            "evidence_ids": list(item.evidence_ids),\n            "deterministic_remediation": item.remediation,\n            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",\n        }\n        for item in diagnostics[:40]\n    ]\n'''
new = '''    resource_facts, resource_evidence = _resource_context_facts(workspace, audit_id)\n    allowed_codes = frozenset(\n        [item.code for item in diagnostics]\n        + [str(item["code"]) for item in resource_facts]\n    )\n    allowed_evidence_set = {\n        evidence_id\n        for item in diagnostics\n        for evidence_id in item.evidence_ids\n        if evidence_id\n    }\n    for values in resource_evidence.values():\n        allowed_evidence_set.update(values)\n    allowed_evidence = frozenset(allowed_evidence_set)\n    facts = [\n        {\n            "code": item.code,\n            "category": item.category,\n            "severity": item.severity,\n            "title": item.title,\n            "scope_url": item.scope_url,\n            "observed": item.observed,\n            "evidence_ids": list(item.evidence_ids),\n            "deterministic_remediation": item.remediation,\n            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",\n        }\n        for item in diagnostics[:40]\n    ]\n    facts.extend(resource_facts)\n'''
text = replace_once(text, old, new, label="m24 fact universe")
text = replace_once(
    text,
    '            allowed_evidence=allowed_evidence,\n            page_row=page_row,',
    '            allowed_evidence=allowed_evidence,\n            resource_evidence=resource_evidence,\n            page_row=page_row,',
    label="m24 call resource evidence",
)
text = replace_once(
    text,
    '    allowed_evidence: frozenset[str],\n    page_row: Mapping[str, Any],',
    '    allowed_evidence: frozenset[str],\n    resource_evidence: Mapping[str, frozenset[str]],\n    page_row: Mapping[str, Any],',
    label="m24 call signature",
)
text = replace_once(
    text,
    '                allowed_codes=allowed_codes,\n                allowed_evidence=allowed_evidence,\n            )',
    '                allowed_codes=allowed_codes,\n                allowed_evidence=allowed_evidence,\n                resource_evidence=resource_evidence,\n            )',
    label="m24 validate call",
)
text = replace_once(
    text,
    '    allowed_codes: frozenset[str],\n    allowed_evidence: frozenset[str],\n) -> dict[str, Any]:',
    '    allowed_codes: frozenset[str],\n    allowed_evidence: frozenset[str],\n    resource_evidence: Mapping[str, frozenset[str]],\n) -> dict[str, Any]:',
    label="m24 validate signature",
)
# Restrict resource-assessment evidence to the evidence universe of that resource,
# while actions remain allowed to cite the general supplied diagnostic universe.
needle = '        if not set(evidence_ids).issubset(allowed_evidence):\n            raise ValueError("M24 AI resource assessment references evidence outside supplied universe")'
replacement = '        allowed_for_resource = resource_evidence.get(resource, frozenset())\n        if not evidence_ids or not set(evidence_ids).issubset(allowed_for_resource):\n            raise ValueError("M24 AI resource assessment references evidence outside its resource universe")'
if needle not in text:
    # Be tolerant to an existing non-empty check in the same statement.
    needle2 = '        if not evidence_ids or not set(evidence_ids).issubset(allowed_evidence):\n            raise ValueError("M24 AI resource assessment references evidence outside supplied universe")'
    text = replace_once(text, needle2, replacement, label="m24 resource evidence validation")
else:
    text = replace_once(text, needle, replacement, label="m24 resource evidence validation")
write(path, text)


# 5) Regression tests for the refinements.
test = r'''from __future__ import annotations

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
    assert "URLs descobertas são uma fronteira observada" in readiness
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
    workspace = AuditWorkspace(root=root, database=db)
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
'''
write("tests/test_stability_refinement_20260908.py", test)

print("stability refinement applied")
