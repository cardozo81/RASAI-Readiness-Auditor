"""CONS-only actionable remediation, BR-GEO references and language normalization."""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from types import ModuleType, SimpleNamespace
from typing import Any, Iterable, Mapping

from rasai.remediation import recipe_for
from rasai.rule_references import references_for

PATCH_VERSION = "CONS-ACTIONABLE-REMEDIATION-001"
_RULE_RE = re.compile(r"\b(BR-GEO-\d{3})\b")
_TAG_RE = re.compile(r"(<[^>]+>)", re.DOTALL)
_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
_EVOLUTION_RANK = {"NEW": 0, "CHANGED": 1, "PERSISTING": 2}
_SEVERITY_PT = {"CRITICAL": "Crítica", "HIGH": "Alta", "MEDIUM": "Média", "LOW": "Baixa", "INFO": "Informativa"}
_EVOLUTION_PT = {"NEW": "Novo achado na auditoria atual", "CHANGED": "Achado alterado na auditoria atual", "PERSISTING": "Achado persistente"}
_EXTRA_TOOLTIPS = {
    "BR-GEO-057": "Content Value · Avalia utilidade e especificidade não trivial do conteúdo observado.",
    "BR-GEO-058": "Content Value · Avalia diferenciação, experiência, análise ou dado próprio explicitamente demonstrado.",
    "BR-GEO-059": "Content Value · Avalia profundidade e contexto proporcionais ao propósito e ao conteúdo observado.",
    "BR-GEO-060": "Discovery & Crawler Access · Evidência externa corroborativa de crawl, sem substituir a avaliação determinística.",
}
_OPERATIONAL = {
    "Verification proves only the persisted rule transition between the two selected audits; it does not prove downstream Search/AI impact.": "A verificação comprova apenas a transição persistida da regra entre as duas auditorias selecionadas; não comprova impacto posterior em Search/IA.",
    "No baseline FAIL/WARNING rule matched the requested verification scope.": "Nenhuma regra em FAIL/WARNING no baseline correspondeu ao escopo solicitado para verificação.",
    "Baseline finding state reached PASS in the current audit.": "O estado do achado no baseline atingiu PASS na auditoria atual.",
    "Rule state improved but has not been demonstrated as fully resolved.": "O estado da regra melhorou, mas ainda não foi demonstrado como totalmente resolvido.",
    "Current evidence is unavailable or not comparable.": "A evidência atual está indisponível ou não é comparável.",
    "The same FAIL/WARNING state remains in the current audit.": "O mesmo estado FAIL/WARNING permanece na auditoria atual.",
    "The rule state degraded relative to the baseline.": "O estado da regra piorou em relação ao baseline.",
}


def _safe_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _value(value: Any, limit: int = 2400) -> Any:
    parsed = _safe_json(value, value)
    try:
        raw = json.dumps(parsed, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = str(parsed)
    return parsed if len(raw) <= limit else raw[: limit - 1].rstrip() + "…"


def _elements(raw: Any) -> list[dict[str, Any]]:
    material = _safe_json(raw, [])
    if not isinstance(material, list):
        return []
    result = []
    for item in material[:3]:
        if not isinstance(item, Mapping):
            continue
        result.append({
            "selector": _text(item.get("selector"), 500), "tag_name": _text(item.get("tag_name"), 120),
            "element_id": _text(item.get("element_id"), 200), "classes": list(item.get("classes") or ())[:12],
            "outer_html": _text(item.get("outer_html"), 1800), "text_excerpt": _text(item.get("text_excerpt"), 800),
            "snapshot_id": _text(item.get("snapshot_id"), 200), "device": _text(item.get("device"), 40),
        })
    return result


def _read_findings(workspace: Path, audit_id: str) -> tuple[dict[str, Any], ...]:
    db = workspace / "audit.db"
    if not db.is_file():
        return ()
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='root_cause_analyses'").fetchone() is None:
            con.close(); return ()
        rows = con.execute("""
            SELECT r.*, f.severity, f.device, f.title AS finding_title, f.status AS finding_status, p.normalized_url
            FROM root_cause_analyses r JOIN findings f ON f.finding_id=r.finding_id
            LEFT JOIN pages p ON p.page_id=f.page_id WHERE f.audit_id=?
            ORDER BY CASE UPPER(f.severity) WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,
                     r.rule_id, f.finding_id LIMIT 220
        """, (audit_id,)).fetchall()
        con.close()
    except sqlite3.Error:
        return ()
    result = []
    for row in rows:
        result.append({
            "finding_id": str(row["finding_id"]), "rule_id": str(row["rule_id"]),
            "url": str(row["normalized_url"] or "") or None, "device": str(row["device"] or "") or None,
            "severity": str(row["severity"] or "INFO").upper(), "finding_title": str(row["finding_title"] or ""),
            "finding_status": str(row["finding_status"] or ""), "cause_type": str(row["cause_type"] or ""),
            "affected_scope": str(row["affected_scope"] or ""), "cause_summary": str(row["cause_summary"] or ""),
            "evidence_basis": _safe_json(row["evidence_basis"], []), "affected_elements": _elements(row["affected_elements"]),
            "selector_status": str(row["selector_status"] or ""), "observed_value": _value(row["observed_value"]),
            "expected_condition": _text(row["expected_condition"], 1800), "exact_change": _text(row["exact_change"], 2600),
            "example_after": _text(row["example_after"], 2600), "acceptance_criteria": _safe_json(row["acceptance_criteria"], []),
            "revalidation_steps": _safe_json(row["revalidation_steps"], []),
            "human_decision_required": _text(row["human_decision_required"], 1800),
            "diagnostic_confidence": str(row["diagnostic_confidence"] or ""),
        })
    return tuple(result)


def _key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(item.get("rule_id") or ""), str(item.get("url") or ""), str(item.get("device") or "").upper()


def _fingerprint(item: Mapping[str, Any]) -> str:
    return json.dumps(item.get("observed_value"), ensure_ascii=False, sort_keys=True, default=str)


def _technical_context(bundle: Any) -> tuple[dict[str, Any], ...]:
    current = list(_read_findings(Path(bundle.current_workspace), str(bundle.comparison.current.audit_id)))
    if not current:
        return ()
    baseline = _read_findings(Path(bundle.baseline_workspace), str(bundle.comparison.baseline.audit_id))
    old: dict[tuple[str, str, str], set[str]] = {}
    for item in baseline:
        old.setdefault(_key(item), set()).add(_fingerprint(item))
    relevant_rules = {str(i.get("rule_id")) for i in (*bundle.events, *bundle.fixes) if isinstance(i, Mapping) and i.get("rule_id")}
    relevant_urls = {str(i.get("url")) for i in (*bundle.events, *bundle.fixes) if isinstance(i, Mapping) and i.get("url")}
    out = []
    for item in current:
        prior = old.get(_key(item))
        evolution = "NEW" if prior is None else ("CHANGED" if _fingerprint(item) not in prior else "PERSISTING")
        row = dict(item)
        row["evolution_status"] = evolution
        row["remediation_recipe"] = asdict(recipe_for(str(item.get("rule_id") or "")))
        row["relevant_to_material_change"] = bool(
            (not relevant_rules and not relevant_urls) or row["rule_id"] in relevant_rules or str(row.get("url") or "") in relevant_urls
        )
        out.append(row)
    out.sort(key=lambda i: (0 if i["relevant_to_material_change"] else 1, _EVOLUTION_RANK.get(i["evolution_status"], 9), _SEVERITY_RANK.get(i["severity"], 9), i["rule_id"], str(i.get("url") or "")))
    return tuple(out[:48])


def _tooltip(rule_id: str, title: str, description: str) -> str:
    if rule_id in _EXTRA_TOOLTIPS:
        return _EXTRA_TOOLTIPS[rule_id]
    try:
        from rasai import report_navigation
        detail = getattr(report_navigation, "_RULE_TOOLTIPS", {}).get(rule_id)
        if detail:
            return str(detail)
    except Exception:
        pass
    return f"{title}. {description}".strip() if title and not title.startswith("Remediar BR-GEO-") else (description or f"Business Rule {rule_id} do RASAi.")


def _rule_reference(bundle: Any, technical: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    ids = {str(i.get("rule_id")) for i in (*bundle.events, *bundle.fixes, *tuple(technical)) if isinstance(i, Mapping) and i.get("rule_id")}
    out = []
    for rule_id in sorted(ids):
        recipe = recipe_for(rule_id)
        out.append({"rule_id": rule_id, "tooltip": _tooltip(rule_id, recipe.title, recipe.description),
                    "remediation": asdict(recipe), "references": [asdict(r) for r in references_for(rule_id)]})
    return tuple(out)


def _augment_packet(original: Any, bundle: Any) -> dict[str, Any]:
    packet = original(bundle)
    technical = _technical_context(bundle)
    packet["current_technical_findings"] = list(technical)
    packet["rule_reference"] = list(_rule_reference(bundle, technical))
    packet.setdefault("governance", {}).update({
        "technical_remediation_origin": "PERSISTED_ROOT_CAUSE_AND_DETERMINISTIC_RECIPE",
        "observed_snippet_policy": "USE_ONLY_WHEN_PRESENT_IN_PERSISTED_AFFECTED_ELEMENTS",
    })
    return packet


def _enhanced_instructions(original: Any) -> str:
    return original() + (
        " Use current_technical_findings and rule_reference whenever they support a recommendation. For every material problem, "
        "identify the BR-GEO rule and URL/device when supplied, state the concrete technical change, and reuse exact_change, "
        "example_after, acceptance_criteria and revalidation_steps when applicable. Prefer observed outer_html/text_excerpt as the "
        "example of what is wrong; if absent, explicitly say the observed snippet was not persisted and never fabricate one. "
        "For aggregate FINDINGS changes, prioritize current findings marked NEW or CHANGED instead of saying only 'investigate'. "
        "Keep deterministic remediation distinct from interpretive prioritization. All user-facing prose/actions must be pt-BR; "
        "established metric names may remain in English."
    )


def _augment_artifact(result: Any, bundle: Any) -> None:
    path = Path(result.report_dir) / "specialist-analysis.json"
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return
    technical = _technical_context(bundle)
    payload.update({"current_technical_findings": list(technical), "rule_reference": list(_rule_reference(bundle, technical)),
                    "actionable_remediation_contract": PATCH_VERSION})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def _translate_operational_wording(html: str) -> str:
    for old, new in _OPERATIONAL.items(): html = html.replace(old, new)
    html = re.sub(r"\b(Crítica|Alta|Média|Baixa|Informativa) findings\b", lambda m: f"Achados de severidade {m.group(1)}", html)
    html = re.sub(r"(Δ\s*[-+]?\d+(?:[.,]\d+)?)\s+count\b", r"\1 ocorrências", html, flags=re.I)
    html = re.sub(r"(Δ\s*[-+]?\d+(?:[.,]\d+)?)\s+points\b", r"\1 pontos", html, flags=re.I)
    return html.replace("Core Web Vitals: Fail", "Core Web Vitals: Não aprovado").replace(">Fail<", ">Não aprovado<")


def _refs(artifact: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(artifact, Mapping): return {}
    return {str(i.get("rule_id")): i for i in artifact.get("rule_reference", ()) if isinstance(i, Mapping) and i.get("rule_id")}


def _enhance_rule_links(html: str, artifact: Mapping[str, Any] | None) -> str:
    refs = _refs(artifact)
    if not refs: return html
    blocked = {"a": 0, "pre": 0, "script": 0, "style": 0}; out = []
    def repl(match: re.Match[str]) -> str:
        rule_id = match.group(1); item = refs.get(rule_id)
        if not item: return rule_id
        detail = str(item.get("tooltip") or f"Business Rule {rule_id} do RASAi.")
        return f"<a class='cons-rule-ref' href='rules-reference.html#{escape(rule_id, quote=True)}' title='{escape(detail, quote=True)}' aria-label='{escape(rule_id + ': ' + detail, quote=True)}'>{escape(rule_id)}</a>"
    for part in _TAG_RE.split(html):
        if part.startswith("<"):
            m = re.match(r"<\s*(/?)\s*([A-Za-z0-9]+)", part)
            if m and m.group(2).lower() in blocked:
                tag = m.group(2).lower(); blocked[tag] = max(0, blocked[tag] - 1) if m.group(1) else blocked[tag] + (0 if part.rstrip().endswith("/>") else 1)
            out.append(part)
        else: out.append(part if any(blocked.values()) else _RULE_RE.sub(repl, part))
    rendered = "".join(out)
    if "rules-reference.html" in rendered and "cons-rule-reference-link" not in rendered:
        link = "<p class='cons-rule-reference-link'><a href='rules-reference.html'>Consultar definições e remediações das regras BR-GEO citadas neste relatório</a></p>"
        m = re.search(r"(<section\s+id=['\"]specialist-evolution['\"][^>]*>)", rendered)
        if m: rendered = rendered[:m.end()] + link + rendered[m.end():]
    return rendered


def _li(values: Any) -> str:
    if not isinstance(values, (list, tuple)): return "<li>Não informado.</li>"
    rendered = "".join(f"<li>{escape(str(v))}</li>" for v in values if str(v).strip())
    return rendered or "<li>Não informado.</li>"


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else ("-" if value is None else str(value))


def _snippet(item: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for element in item.get("affected_elements", ()):
        if not isinstance(element, Mapping): continue
        if element.get("outer_html"): return str(element["outer_html"]), "HTML observado na URL"
        if element.get("text_excerpt"): return str(element["text_excerpt"]), "Trecho textual observado na URL"
    return None, None


def _render_technical_remediation(artifact: Mapping[str, Any] | None) -> str:
    if not isinstance(artifact, Mapping): return ""
    findings = [i for i in artifact.get("current_technical_findings", ()) if isinstance(i, Mapping)]
    if not findings: return ""
    cards = []
    for i in findings[:20]:
        rule = str(i.get("rule_id") or "-"); sev = str(i.get("severity") or "INFO").upper(); evo = str(i.get("evolution_status") or "PERSISTING").upper()
        title = str(i.get("finding_title") or i.get("cause_summary") or "Achado técnico"); snippet, label = _snippet(i)
        snippet_html = f"<h5>{escape(label or 'Trecho observado')}</h5><pre><code>{escape(snippet)}</code></pre>" if snippet else "<p class='subtle'><strong>Trecho observado:</strong> não persistido para este achado; o relatório não fabrica código da página.</p>"
        example = i.get("example_after"); example_html = f"<h5>Exemplo de implementação</h5><pre><code>{escape(str(example))}</code></pre>" if example else ""
        cards.append(
            "<details class='technical-finding'><summary>" +
            f"<span><strong>{escape(rule)}</strong> · {escape(title)}</span><span class='technical-meta'>{escape(_SEVERITY_PT.get(sev, sev))} · {escape(_EVOLUTION_PT.get(evo, evo))}</span></summary>" +
            "<div class='technical-finding-body'>" +
            f"<p><strong>URL:</strong> {escape(str(i.get('url') or 'Escopo global'))}<br><strong>Dispositivo:</strong> {escape(str(i.get('device') or '-'))}</p>" +
            f"<p><strong>Problema encontrado:</strong> {escape(str(i.get('cause_summary') or title))}</p><h5>Valor observado</h5><pre><code>{escape(_pretty(i.get('observed_value')))}</code></pre>" +
            snippet_html + f"<h5>Correção técnica recomendada</h5><p>{escape(str(i.get('exact_change') or i.get('cause_summary') or 'Revisar a condição registrada.'))}</p>" +
            example_html + f"<h5>Critérios de aceite</h5><ul>{_li(i.get('acceptance_criteria'))}</ul><h5>Como revalidar</h5><ul>{_li(i.get('revalidation_steps'))}</ul>" +
            (f"<p class='notice warning'><strong>Decisão humana necessária:</strong> {escape(str(i.get('human_decision_required')))}</p>" if i.get("human_decision_required") else "") +
            "</div></details>"
        )
    return (
        "<section id='technical-remediation' class='panel' data-cons-technical-remediation='true'><div class='kicker'>Remediação técnica baseada em evidência persistida</div>"
        "<h2>O que corrigir, onde alterar e como validar</h2><p>Este bloco é determinístico e reutiliza root cause, elementos afetados e receitas do próprio RASAi. "
        "Quando a análise especialista por IA está habilitada, esta mesma base técnica é enviada ao modelo para evitar recomendações genéricas.</p>"
        "<p class='notice info'><strong>Proveniência:</strong> trechos marcados como observados vêm do AUD atual. Exemplos de implementação são receitas de remediação e não devem ser confundidos com conteúdo observado.</p>" + "".join(cards) + "</section>"
    )


def _presentation(original: Any, html: str, artifact: Mapping[str, Any] | None = None) -> str:
    rendered = _translate_operational_wording(original(html, artifact))
    if "data-cons-technical-remediation" not in rendered:
        block = _render_technical_remediation(artifact)
        if block:
            m = re.search(r"<section\s+id=['\"]specialist-ai['\"]", rendered); pos = m.start() if m else rendered.find("<footer")
            rendered = rendered[:pos] + block + rendered[pos:] if pos >= 0 else rendered.replace("</body>", block + "</body>", 1)
    rendered = _enhance_rule_links(rendered, artifact)
    if "rasai-cons-actionable-remediation" not in rendered:
        css = """<style id='rasai-cons-actionable-remediation'>.cons-rule-ref{font-weight:700;text-decoration:underline dotted;text-underline-offset:2px}.cons-rule-reference-link{margin:10px 0 14px}.technical-finding{border:1px solid var(--line);border-radius:7px;background:#fbfcfe;margin:10px 0;overflow:hidden}.technical-finding>summary{display:flex;justify-content:space-between;gap:12px;padding:12px 14px;cursor:pointer;font-weight:600}.technical-meta{font-size:.8rem;color:var(--muted);white-space:nowrap}.technical-finding-body{padding:0 14px 14px}.technical-finding-body h5{margin:14px 0 5px}.technical-finding-body pre{max-height:320px;overflow:auto;white-space:pre-wrap;word-break:break-word}@media(max-width:760px){.technical-finding>summary{display:block}.technical-meta{display:block;margin-top:5px;white-space:normal}}</style>"""
        rendered = rendered.replace("</head>", css + "</head>", 1)
    return rendered


def _rules_page(artifact: Mapping[str, Any]) -> str:
    sections = []
    for item in [i for i in artifact.get("rule_reference", ()) if isinstance(i, Mapping)]:
        rule = str(item.get("rule_id") or ""); rem = item.get("remediation") if isinstance(item.get("remediation"), Mapping) else {}; example = rem.get("example")
        refs = "".join((f"<li><a href='{escape(str(r.get('url')), quote=True)}' target='_blank' rel='noopener noreferrer'>{escape(str(r.get('authority') or 'Fonte primária'))} — {escape(str(r.get('title') or r.get('reference_scope') or 'Referência'))}</a> <small>({escape(str(r.get('basis') or ''))})</small></li>" if r.get("url") else f"<li>{escape(str(r.get('reference_scope') or 'Referência interna RASAi'))} <small>({escape(str(r.get('basis') or ''))})</small></li>") for r in item.get("references", ()) if isinstance(r, Mapping)) or "<li>Referência interna RASAi.</li>"
        sections.append(f"<section id='{escape(rule, quote=True)}' class='rule-card'><div class='kicker'>{escape(rule)}</div><h2>{escape(str(rem.get('title') or rule))}</h2><p>{escape(str(item.get('tooltip') or rem.get('description') or ''))}</p><dl><dt>Alvo</dt><dd>{escape(str(rem.get('target') or '-'))}</dd><dt>Elemento</dt><dd>{escape(str(rem.get('element') or '-'))}</dd><dt>Local</dt><dd>{escape(str(rem.get('location') or '-'))}</dd><dt>Ação</dt><dd><code>{escape(str(rem.get('action') or '-'))}</code></dd></dl><h3>Correção recomendada</h3><p>{escape(str(rem.get('description') or '-'))}</p>" + (f"<h3>Exemplo</h3><pre><code>{escape(str(example))}</code></pre>" if example else "") + f"<h3>Critérios de aceite</h3><ul>{_li(rem.get('acceptance'))}</ul><h3>Como revalidar</h3><ul>{_li(rem.get('validation'))}</ul>" + (f"<p class='warning'><strong>Decisão humana:</strong> {escape(str(rem.get('human_decision')))}</p>" if rem.get("human_decision") else "") + f"<h3>Referências</h3><ul>{refs}</ul></section>")
    return """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Definições BR-GEO — RASAi</title><style>:root{font-family:Inter,system-ui,sans-serif;color:#273449;background:#f6f7fb}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:28px 20px 60px}a{color:#315d9a}header,.rule-card{background:#fff;border:1px solid #dde3ec;border-radius:8px;padding:20px;margin-bottom:14px}.kicker{font-size:.78rem;font-weight:750;color:#5b6f91;text-transform:uppercase}dl{display:grid;grid-template-columns:120px 1fr;gap:7px 12px}dt{font-weight:700}dd{margin:0}pre{background:#f3f5f8;border-radius:6px;padding:12px;overflow:auto;white-space:pre-wrap}.warning{background:#fff6df;border-left:4px solid #b68a50;padding:10px 12px}</style></head><body><main class='wrap'><a href='report.html'>← Voltar ao relatório consolidado</a><header><div class='kicker'>Referência técnica do relatório consolidado</div><h1>Definições e remediações das regras BR-GEO citadas</h1><p>Somente regras efetivamente referenciadas pelo CONS são listadas. IDs permanecem canônicos; descrições e ações são apresentadas em pt-BR.</p></header>""" + "".join(sections) + "</main></body></html>"


def _backfill(result: Any) -> None:
    path = Path(result.report_dir) / "specialist-analysis.json"
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return
    if payload.get("actionable_remediation_contract") == PATCH_VERSION: return
    comp = payload.get("comparison") if isinstance(payload.get("comparison"), Mapping) else {}; base = str(comp.get("baseline_audit_id") or ""); curr = str(comp.get("current_audit_id") or "")
    root = Path(result.report_dir).parent.parent
    if not base or not curr or not (root/base/"audit.db").is_file() or not (root/curr/"audit.db").is_file(): return
    bundle = SimpleNamespace(baseline_workspace=root/base, current_workspace=root/curr, comparison=SimpleNamespace(baseline=SimpleNamespace(audit_id=base), current=SimpleNamespace(audit_id=curr)), events=tuple(i for i in payload.get("changes", ()) if isinstance(i, Mapping)), fixes=tuple(i for i in payload.get("fix_verification", ()) if isinstance(i, Mapping)))
    technical = _technical_context(bundle); payload.update({"current_technical_findings": list(technical), "rule_reference": list(_rule_reference(bundle, technical)), "actionable_remediation_contract": PATCH_VERSION})
    try: path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    except OSError: pass


def _write_rules(result: Any) -> None:
    path = Path(result.report_dir) / "specialist-analysis.json"
    try: artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return
    if artifact.get("rule_reference"):
        try: (Path(result.report_dir) / "rules-reference.html").write_text(_rules_page(artifact), encoding="utf-8", newline="\n")
        except OSError: pass


def install(specialist: ModuleType, presentation: ModuleType) -> None:
    """Install the isolated CONS extension before service imports bind functions."""
    if getattr(specialist, "_rasai_actionable_cons_patch", False): return
    packet0, instructions0, enrich0 = specialist._packet, specialist._instructions, specialist.enrich_result
    refine_html0, refine_result0 = presentation.refine_html, presentation.refine_result
    specialist._packet = lambda bundle: _augment_packet(packet0, bundle)
    specialist._instructions = lambda: _enhanced_instructions(instructions0)
    def enrich(audits_root: str | Path, filters: Any, result: Any, *, env: Mapping[str, str] | None = None) -> Any:
        enriched = enrich0(audits_root, filters, result, env=env)
        try: _augment_artifact(enriched, specialist.build_evolution(audits_root, filters))
        except Exception: pass
        return enriched
    specialist.enrich_result = enrich; specialist._rasai_actionable_cons_patch = True
    presentation.refine_html = lambda html, artifact=None: _presentation(refine_html0, html, artifact)
    def refine(result: Any) -> Any:
        _backfill(result); refined = refine_result0(result); _write_rules(refined); return refined
    presentation.refine_result = refine; presentation._rasai_actionable_cons_patch = True
