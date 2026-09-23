"""CONS-only actionable remediation, BR-GEO references and language normalization."""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from types import ModuleType
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
    "No baseline FAIL/WARNING rule matched the requested verification scope.": "Nenhuma regra em estado não aprovado/atenção no marco inicial correspondeu ao escopo solicitado para verificação.",
    "Baseline finding state reached PASS in the current audit.": "O estado da ocorrência no marco inicial atingiu o estado aprovado na auditoria atual.",
    "Rule state improved but has not been demonstrated as fully resolved.": "O estado da regra melhorou, mas ainda não foi demonstrado como totalmente resolvido.",
    "Current evidence is unavailable or not comparable.": "A evidência atual está indisponível ou não é comparável.",
    "The same FAIL/WARNING state remains in the current audit.": "O mesmo estado não aprovado/atenção permanece na auditoria atual.",
    "The rule state degraded relative to the baseline.": "O estado da regra piorou em relação ao marco inicial.",
}

_ACTION_LABELS = {
    "RESTORE_ACCESS": "Restabelecer acesso técnico",
    "RESOLVE_CONFLICT": "Resolver conflito",
    "REVIEW_DIRECTIVE": "Revisar diretiva",
    "ADD_OR_CORRECT": "Adicionar ou corrigir",
    "CORRECT_TARGET": "Corrigir destino",
    "CORRECT_RESOURCE": "Corrigir recurso",
    "REVIEW_CRAWLER_POLICY": "Revisar política de rastreamento",
    "EDIT_CONTENT": "Editar conteúdo",
    "RESTRUCTURE_CONTENT": "Reestruturar conteúdo",
    "CLARIFY_ENTITY": "Clarificar entidade",
    "CLARIFY_ENTITY_RELATIONSHIPS": "Clarificar relações entre entidades",
    "DISAMBIGUATE_ENTITY": "Eliminar ambiguidade de entidade",
    "CORRECT_STRUCTURED_DATA": "Corrigir dados estruturados",
    "ALIGN_STRUCTURED_DATA": "Alinhar dados estruturados",
    "ALIGN_ENTITY_MARKUP": "Alinhar marcação de entidades",
    "CLARIFY_INTENT": "Clarificar intenção",
    "ADD_OR_RESTRUCTURE_ANSWER": "Adicionar ou reestruturar resposta",
    "ADD_CONTEXT": "Adicionar contexto",
    "CLARIFY_CLAIMS": "Clarificar afirmações factuais",
    "ADD_FACTUAL_CONTEXT": "Adicionar contexto factual",
    "ADD_QUALIFIERS": "Adicionar qualificadores",
    "MAKE_EXPLICIT": "Tornar explícito",
    "ADD_ATTRIBUTION": "Adicionar atribuição",
    "ADD_RESPONSIBILITY_SIGNAL": "Adicionar sinal de responsabilidade",
    "ALIGN_FRESHNESS_SIGNALS": "Alinhar sinais de publicação e atualização",
    "CLOSE_INTENT_GAPS": "Tratar lacunas de intenção",
    "REVIEW_AND_CORRECT": "Revisar e corrigir",
    "UPDATE": "Atualizar",
    "ADD": "Adicionar",
    "REMOVE": "Remover",
    "REPLACE": "Substituir",
    "CONFIGURE": "Configurar",
}

_REFERENCE_BASIS_LABELS = {
    "STANDARD": "Padrão técnico",
    "HEURISTIC": "Heurística",
    "INTERNAL_BASELINE": "Referência interna do RASAi",
    "OFFICIAL_DOCUMENTATION": "Documentação oficial",
}

_RULE_TITLE_PT = {
    "BR-GEO-003": "Recursos de sitemap devem ser adquiridos e interpretados quando disponíveis",
    "BR-GEO-013": "Declarações canonical devem ser interpretáveis e não conflitantes",
    "BR-GEO-017": "robots.txt deve ser interpretável quando presente",
}

_VISIBLE_TERM_PT = {
    "MOBILE": "Dispositivo móvel",
    "DESKTOP": "Desktop",
    "BOTH": "Mobile e Desktop",
    "GLOBAL": "Escopo global",
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "WARNING": "Atenção",
    "SUCCESS": "Sucesso",
    "COMPLETE": "Concluído",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "PARTIAL": "Parcial",
    "NOT_FIXED": "Não corrigido",
    "FIXED": "Corrigido",
    "NEW": "Novo",
    "CHANGED": "Alterado",
    "REGRESSED": "Piorou",
    "IMPROVED": "Melhorou",
    "RESOLVED": "Resolvido",
    "DATA_UNAVAILABLE": "Dado indisponível",
    "NOT_CONFIGURED": "Não configurado",
    "NOT_REQUESTED": "Não solicitado",
    "ABSENT": "Ausente",
    "COHERENT": "Coerente",
    "PERSISTING": "Persistente",
    "NAVIGATION_LOAD": "Carregamento de navegação",
    "USER_ACTION_DURATION": "Duração da ação do usuário",
    "MANUAL_CALIBRATION": "Calibração manual",
    "REVIEW_AND_CORRECT": "Revisar e corrigir",
    "ADD_FACTUAL_CONTEXT": "Adicionar contexto factual",
    "ADD_QUALIFIERS": "Adicionar qualificadores",
    "ADD_ATTRIBUTION": "Adicionar atribuição",
    "CLOSE_INTENT_GAPS": "Tratar lacunas de intenção",
}


def _action_label(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return _ACTION_LABELS.get(raw, "Executar correção técnica indicada") if raw else "-"


def _reference_basis_label(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return _REFERENCE_BASIS_LABELS.get(raw, "Referência técnica") if raw else "Referência técnica"


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


def _humanize_domain_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "Severidade CRITICAL": "Severidade crítica",
        "Severidade HIGH": "Severidade alta",
        "Severidade MEDIUM": "Severidade média",
        "Severidade LOW": "Severidade baixa",
        "Severidade INFO": "Severidade informativa",
        "Content Value": "Valor de conteúdo",
        "Discovery & Crawler Access": "Acesso e descoberta",
        "Structured Data": "Dados estruturados",
        "Answerability": "Capacidade de resposta",
        "Citation Readiness": "Preparação para citação",
        "Intent Coverage": "Cobertura de intenção",
        "Evidence & Trust": "Evidência e confiança",
        "Entity Clarity": "Clareza de entidades",
        "Semantic Structure": "Estrutura semântica",
        "Canonical declarations must be interpretable and non-conflicting": "Declarações canonical devem ser interpretáveis e não conflitantes",
        "robots.txt must be interpretable when present": "robots.txt deve ser interpretável quando presente",
        "Sitemap resources must be acquired and interpreted when available": "Recursos de sitemap devem ser adquiridos e interpretados quando disponíveis",
        "evidence-bound": "baseada em evidências",
        "root cause": "causa raiz",
        "claims": "afirmações",
        "Claims": "Afirmações",
        "freshness": "atualização",
        "fallback": "alternativa genérica",
        "no ocorrência": "na ocorrência",
        "do ocorrência": "da ocorrência",
        "IDs de evidência": "identificadores de evidência",
        "RAW": "HTML bruto",
        "RENDERED": "HTML renderizado",
        "Desktop e Mobile": "desktop e dispositivo móvel",
        "Mobile": "dispositivo móvel",
        "claim": "afirmação",
        "novos afirmações": "novas afirmações",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    for raw, label in _ACTION_LABELS.items():
        text = text.replace(raw, label)
    for raw, label in _VISIBLE_TERM_PT.items():
        text = re.sub(rf"\b{re.escape(raw)}\b", label, text)
    text = text.replace("evidence_ids", "IDs de evidência")
    text = text.replace("findings", "ocorrências").replace("finding", "ocorrência")
    text = text.replace("recipe específica", "receita de remediação específica")
    text = text.replace("confirmar PASS", "confirmar estado aprovado")
    # These forms can be introduced by the generic substitutions above, so they
    # intentionally run last.
    text = (
        text.replace("no ocorrência", "na ocorrência")
        .replace("do ocorrência", "da ocorrência")
        .replace("um alternativa", "uma alternativa")
        .replace("IDs de evidência", "identificadores de evidência")
    )
    return text


def _tooltip(rule_id: str, title: str, description: str) -> str:
    if rule_id in _EXTRA_TOOLTIPS:
        return _humanize_domain_text(_EXTRA_TOOLTIPS[rule_id])
    try:
        from rasai import report_navigation
        detail = getattr(report_navigation, "_RULE_TOOLTIPS", {}).get(rule_id)
        if detail:
            return _humanize_domain_text(detail)
    except Exception:
        pass
    value = f"{title}. {description}".strip() if title and not title.startswith("Remediar BR-GEO-") else (description or f"Regra de Avaliação de Prontidão {rule_id} do RASAi.")
    return _humanize_domain_text(value)


def _rule_reference(bundle: Any, technical: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    ids = {str(i.get("rule_id")) for i in (*bundle.events, *bundle.fixes, *tuple(technical)) if isinstance(i, Mapping) and i.get("rule_id")}
    out = []
    for rule_id in sorted(ids):
        recipe = recipe_for(rule_id)
        out.append({"rule_id": rule_id, "tooltip": _tooltip(rule_id, recipe.title, recipe.description),
                    "remediation": asdict(recipe), "references": [asdict(r) for r in references_for(rule_id)]})
    return tuple(out)


def _augment_longitudinal_packet(original: Any, bundle: Any) -> tuple[dict[str, Any], tuple[str, ...]]:
    packet, allowed = original(bundle)
    references: dict[str, dict[str, Any]] = {}

    additional_allowed = list(allowed)
    intervals = packet.get("intervals") if isinstance(packet.get("intervals"), list) else []
    for index, pair in enumerate(getattr(bundle, "intervals", ())):
        technical = []
        for finding_index, item in enumerate(_technical_context(pair)[:16], 1):
            copied = dict(item)
            copied["evidence_id"] = f"I{index + 1:03d}-FINDING-{finding_index:04d}"
            additional_allowed.append(copied["evidence_id"])
            technical.append(copied)
        refs = _rule_reference(pair, technical)
        for item in refs:
            references[str(item.get("rule_id") or "")] = item
        if index < len(intervals) and isinstance(intervals[index], dict):
            intervals[index]["current_technical_findings"] = technical
            intervals[index]["rule_reference"] = list(refs)

    global_pair = getattr(bundle, "global_evolution", None)
    if global_pair is not None:
        technical = []
        for finding_index, item in enumerate(_technical_context(global_pair)[:24], 1):
            copied = dict(item)
            copied["evidence_id"] = f"GLOBAL-FINDING-{finding_index:04d}"
            additional_allowed.append(copied["evidence_id"])
            technical.append(copied)
        refs = _rule_reference(global_pair, technical)
        for item in refs:
            references[str(item.get("rule_id") or "")] = item
        initial_final = packet.get("initial_to_final")
        if isinstance(initial_final, dict):
            initial_final["current_technical_findings"] = technical
            initial_final["rule_reference"] = list(refs)

    packet["rule_reference"] = [references[key] for key in sorted(references) if key]
    packet.setdefault("governance", {}).update({
        "technical_remediation_origin": "PERSISTED_ROOT_CAUSE_AND_DETERMINISTIC_RECIPE",
        "observed_snippet_policy": "USE_ONLY_WHEN_PRESENT_IN_PERSISTED_AFFECTED_ELEMENTS",
    })
    return packet, tuple(dict.fromkeys(str(item) for item in additional_allowed if str(item)))


def _enhanced_instructions(original: Any) -> str:
    return original() + (
        " Use current_technical_findings and rule_reference whenever they support a recommendation. For every material problem, "
        "identify the BR-GEO rule and URL/device when supplied, state the concrete technical change, and reuse exact_change, "
        "example_after, acceptance_criteria and revalidation_steps when applicable. Prefer observed outer_html/text_excerpt as the "
        "example of what is wrong; if absent, explicitly say the observed snippet was not persisted and never fabricate one. "
        "For aggregate FINDINGS changes, prioritize current findings marked NEW or CHANGED instead of saying only 'investigate'. "
        "Keep deterministic remediation distinct from interpretive prioritization. All user-facing prose/actions must be pt-BR. "
        "Never expose internal enum names or field names such as source_state, INCOMPLETE, COMPLETE, PARTIAL, PASS, WARNING or FAIL as the primary human label; "
        "use their pt-BR meaning and keep a canonical technical token only when it materially helps auditability. "
        "Established metric names may remain in English only as secondary text after a humanized pt-BR label."
    )


def _augment_artifact(result: Any, bundle: Any) -> None:
    path = Path(result.report_dir) / "specialist-analysis.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    references: dict[str, dict[str, Any]] = {}
    interval_payload: list[dict[str, Any]] = []
    for index, pair in enumerate(getattr(bundle, "intervals", ()), 1):
        technical = _technical_context(pair)
        refs = _rule_reference(pair, technical)
        for item in refs:
            references[str(item.get("rule_id") or "")] = item
        interval_payload.append({
            "interval_id": f"INTERVALO-{index:03d}",
            "baseline_audit_id": pair.comparison.baseline.audit_id,
            "current_audit_id": pair.comparison.current.audit_id,
            "findings": list(technical),
        })

    global_pair = getattr(bundle, "global_evolution", bundle)
    current_technical = _technical_context(global_pair)
    for item in _rule_reference(global_pair, current_technical):
        references[str(item.get("rule_id") or "")] = item

    payload.update({
        "current_technical_findings": list(current_technical),
        "technical_findings_by_interval": interval_payload,
        "rule_reference": [references[key] for key in sorted(references) if key],
        "actionable_remediation_contract": PATCH_VERSION,
    })
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
        detail = _humanize_domain_text(item.get("tooltip") or f"Regra de Avaliação de Prontidão {rule_id} do RASAi.")
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
        link = "<p class='cons-rule-reference-link'><a href='rules-reference.html'>Consultar definições e remediações das Regras de Avaliação de Prontidão citadas neste relatório</a></p>"
        m = re.search(r"(<section\s+id=['\"](?:longitudinal-evolution|specialist-evolution)['\"][^>]*>)", rendered)
        if m: rendered = rendered[:m.end()] + link + rendered[m.end():]
    return rendered


def _li(values: Any) -> str:
    if not isinstance(values, (list, tuple)): return "<li>Não informado.</li>"
    rendered = "".join(f"<li>{escape(_humanize_domain_text(v))}</li>" for v in values if str(v).strip())
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
        raw_title = i.get("finding_title") or i.get("cause_summary") or "Achado técnico"
        title = _RULE_TITLE_PT.get(rule) or _humanize_domain_text(raw_title)
        snippet, label = _snippet(i)
        snippet_html = f"<h5>{escape(label or 'Trecho observado')}</h5><pre><code>{escape(snippet)}</code></pre>" if snippet else "<p class='subtle'><strong>Trecho observado:</strong> não persistido para este achado; o relatório não fabrica código da página.</p>"
        example = i.get("example_after"); example_html = f"<h5>Exemplo de implementação</h5><pre><code>{escape(str(example))}</code></pre>" if example else ""
        cards.append(
            "<details class='technical-finding'><summary>" +
            f"<span><strong>{escape(rule)}</strong> · {escape(title)}</span><span class='technical-meta'>{escape(_SEVERITY_PT.get(sev, sev))} · {escape(_EVOLUTION_PT.get(evo, evo))}</span></summary>" +
            "<div class='technical-finding-body'>" +
            f"<p><strong>URL:</strong> {escape(str(i.get('url') or 'Escopo global'))}<br><strong>Dispositivo:</strong> {escape(_humanize_domain_text(i.get('device') or '-'))}</p>" +
            f"<p><strong>Problema encontrado:</strong> {escape(_humanize_domain_text(i.get('cause_summary') or title))}</p><h5>Valor observado</h5><pre><code>{escape(_pretty(i.get('observed_value')))}</code></pre>" +
            snippet_html + f"<h5>Correção técnica recomendada</h5><p>{escape(_humanize_domain_text(i.get('exact_change') or i.get('cause_summary') or 'Revisar a condição registrada.'))}</p>" +
            example_html + f"<h5>Critérios de aceite</h5><ul>{_li(i.get('acceptance_criteria'))}</ul><h5>Como revalidar</h5><ul>{_li(i.get('revalidation_steps'))}</ul>" +
            (f"<p class='notice warning'><strong>Decisão humana necessária:</strong> {escape(_humanize_domain_text(i.get('human_decision_required')))}</p>" if i.get("human_decision_required") else "") +
            "</div></details>"
        )
    return (
        "<section id='technical-remediation' class='panel' data-cons-technical-remediation='true'><div class='kicker'>Remediação técnica baseada em evidência persistida</div>"
        "<h2>O que corrigir, onde alterar e como validar</h2><p>Este bloco é determinístico e reutiliza root cause, elementos afetados e receitas do próprio RASAi. "
        "A análise longitudinal por IA recebe esta mesma base técnica quando pertinente, evitando recomendações genéricas.</p>"
        "<p class='notice info'><strong>Proveniência:</strong> trechos marcados como observados vêm do AUD atual. Exemplos de implementação são receitas de remediação e não devem ser confundidos com conteúdo observado.</p>" + "".join(cards) + "</section>"
    )


def _presentation(original: Any, html: str, artifact: Mapping[str, Any] | None = None) -> str:
    rendered = _translate_operational_wording(original(html, artifact))
    if "data-cons-technical-remediation" not in rendered:
        block = _render_technical_remediation(artifact)
        if block:
            m = re.search(r"<section\s+id=['\"](?:longitudinal-ai|specialist-ai)['\"]", rendered); pos = m.start() if m else rendered.find("<footer")
            rendered = rendered[:pos] + block + rendered[pos:] if pos >= 0 else rendered.replace("</body>", block + "</body>", 1)
    rendered = _enhance_rule_links(rendered, artifact)
    if (
        "id='technical-remediation'" in rendered or 'id="technical-remediation"' in rendered
    ) and "href='#technical-remediation'" not in rendered:
        technical_link = "<a href='#technical-remediation'>Correções técnicas</a>"
        if "href='#longitudinal-ai'" in rendered:
            rendered = rendered.replace(
                "<a href='#longitudinal-ai'>Análise por IA</a>",
                technical_link + "<a href='#longitudinal-ai'>Análise por IA</a>",
                1,
            )
        elif "href='#cons-governance'" in rendered:
            rendered = rendered.replace(
                "<a href='#cons-governance'>Governança</a>",
                technical_link + "<a href='#cons-governance'>Governança</a>",
                1,
            )
    if "rasai-cons-actionable-remediation" not in rendered:
        css = """<style id='rasai-cons-actionable-remediation'>.cons-rule-ref{font-weight:700;text-decoration:underline dotted;text-underline-offset:2px}.cons-rule-reference-link{margin:10px 0 14px}.technical-finding{border:1px solid var(--line);border-radius:7px;background:#fbfcfe;margin:10px 0;overflow:hidden}.technical-finding>summary{display:flex;justify-content:flex-start;gap:12px;padding:12px 14px;cursor:pointer;font-weight:600;text-align:left}.technical-finding>summary>span:first-of-type{margin-right:auto;text-align:left}.technical-meta{font-size:.8rem;color:var(--muted);white-space:nowrap;margin-left:auto;text-align:right}.technical-finding-body{padding:0 14px 14px}.technical-finding-body h5{margin:14px 0 5px}.technical-finding-body pre{max-height:320px;overflow:auto;white-space:pre-wrap;word-break:break-word}@media(max-width:760px){.technical-finding>summary{display:block}.technical-meta{display:block;margin-top:5px;white-space:normal}}</style>"""
        rendered = rendered.replace("</head>", css + "</head>", 1)
    return rendered


def _rules_page(artifact: Mapping[str, Any]) -> str:
    sections = []
    rules = [item for item in artifact.get("rule_reference", ()) if isinstance(item, Mapping)]
    for item in rules:
        rule = str(item.get("rule_id") or "")
        rem = item.get("remediation") if isinstance(item.get("remediation"), Mapping) else {}
        example = rem.get("example")
        refs = "".join(
            (
                f"<li><a href='{escape(str(ref.get('url')), quote=True)}' target='_blank' rel='noopener noreferrer'>"
                f"{escape(str(ref.get('authority') or 'Fonte primária'))} - "
                f"{escape(str(ref.get('title') or ref.get('reference_scope') or 'Referência'))}</a> "
                f"<small>({escape(_reference_basis_label(ref.get('basis')))})</small></li>"
                if ref.get("url")
                else f"<li>{escape(str(ref.get('reference_scope') or 'Referência interna RASAi'))} "
                f"<small>({escape(_reference_basis_label(ref.get('basis')))})</small></li>"
            )
            for ref in item.get("references", ())
            if isinstance(ref, Mapping)
        ) or "<li>Referência interna RASAi.</li>"
        sections.append(
            f"<section id='{escape(rule, quote=True)}' class='rule-card' data-rule-card>"
            f"<div class='rule-head'><span class='rule-id'>{escape(rule)}</span>"
            f"<a class='back-top' href='#topo'>Topo</a></div>"
            f"<h2>{escape(_RULE_TITLE_PT.get(rule) or _humanize_domain_text(rem.get('title') or rule))}</h2>"
            f"<p class='rule-summary'>{escape(_humanize_domain_text(item.get('tooltip') or rem.get('description') or ''))}</p>"
            f"<div class='rule-meta'><div><small>Alvo</small><strong>{escape(_humanize_domain_text(rem.get('target') or '-'))}</strong></div>"
            f"<div><small>Elemento</small><strong>{escape(str(rem.get('element') or '-'))}</strong></div>"
            f"<div><small>Local</small><strong>{escape(str(rem.get('location') or '-'))}</strong></div>"
            f"<div><small>Ação</small><strong>{escape(_action_label(rem.get('action')))}</strong></div></div>"
            f"<h3>Correção recomendada</h3><p>{escape(_humanize_domain_text(rem.get('description') or '-'))}</p>"
            + (f"<h3>Exemplo de implementação</h3><pre><code>{escape(str(example))}</code></pre>" if example else "")
            + f"<div class='rule-grid'><div><h3>Critérios de aceite</h3><ul>{_li(rem.get('acceptance'))}</ul></div>"
            f"<div><h3>Como revalidar</h3><ul>{_li(rem.get('validation'))}</ul></div></div>"
            + (f"<p class='notice warning'><strong>Decisão humana necessária:</strong> {escape(_humanize_domain_text(rem.get('human_decision')))}</p>" if rem.get("human_decision") else "")
            + f"<details><summary>Referências técnicas</summary><ul>{refs}</ul></details></section>"
        )
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Definições BR-GEO - RASAi</title>
<style>
:root{{--bg:#f6f8fb;--surface:#fff;--ink:#172033;--secondary-ink:#475467;--muted:#667085;--light-muted:#6c7789;--line:#e2e7ef;--blue:#3157c8;--green:#187a45;--green-soft:#edf8f0;--amber:#9a6200;--amber-soft:#fff8e9;--orange:#9a5b13;--red:#b42318;--cyan:#087a8c;--red-soft:#fff1f0;--soft:#f2f6ff;--nav:#111827;--radius:14px;--shadow:0 1px 3px rgba(16,24,40,.06)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}a{{color:var(--blue)}}header{{background:var(--nav);color:white;padding:22px 0}}.rules-header-shell{{margin:auto;padding:0 24px}}header h1{{margin:4px 0;font-size:1.55rem;line-height:1.2}}header p{{color:#cbd5e1;max-width:900px}}.kicker{{font-size:.66rem;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:#93a4ba}}.toolbar{{position:sticky;top:0;z-index:20;background:rgba(246,248,251,.96);backdrop-filter:blur(7px);border-bottom:1px solid var(--line);padding:8px 24px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.toolbar a{{text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 9px;font-size:.74rem;color:#46536a}}.toolbar a:hover,.toolbar a:focus{{background:#f2f6ff;border-color:#bdc8da;color:#274690}}.toolbar input{{flex:1;min-width:240px;max-width:560px;border:1px solid #bdc8da;border-radius:8px;padding:7px 10px;font:inherit;background:#fff;color:var(--ink)}}main{{margin:auto;padding:24px}}.rule-card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px;margin:0 0 14px;box-shadow:var(--shadow)}}.rule-card[hidden]{{display:none}}.rule-head{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.rule-id{{display:inline-flex;background:#eef3fb;color:#345184;border-radius:999px;padding:3px 7px;font-size:.7rem;font-weight:700}}.back-top{{font-size:.82rem}}.rule-card h2{{margin:8px 0 5px}}.rule-summary{{color:var(--secondary-ink)}}.rule-meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:9px;margin:12px 0}}.rule-meta>div{{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:10px}}small{{display:block;color:var(--muted);margin-bottom:4px}}.rule-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.rule-grid>div{{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.rule-grid>div h3{{margin:0 0 6px;font-size:.95rem}}.rule-grid>div ul{{margin-bottom:0}}pre{{background:#0f172a;color:#e2e8f0;border-radius:9px;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-word}}code{{background:#f3f5f8;padding:1px 4px;border-radius:4px;word-break:break-word}}pre code{{background:transparent;color:inherit;padding:0}}details{{border:1px solid var(--line);border-radius:9px;background:#fbfcfd;margin:14px 0;overflow:hidden;padding:0}}details>summary{{cursor:pointer;font-weight:650;padding:9px 11px;background:#fbfcfd;list-style:none;display:flex;align-items:center;justify-content:flex-start;gap:8px;text-align:left}}details>summary::-webkit-details-marker{{display:none}}details>summary::before{{content:'›';display:inline-block;font-size:1.25rem;line-height:1;transition:transform .15s ease}}details[open]>summary::before{{transform:rotate(90deg)}}details[open]>summary{{border-bottom:1px solid var(--line)}}details>summary~*{{margin-left:12px;margin-right:12px}}.notice{{padding:11px 13px;border-radius:10px;border:1px solid #cbd8f5;background:#f2f6ff}}.warning{{background:var(--amber-soft);border-color:#ecd09d}}.warning>strong{{color:var(--amber)}}.result-count{{color:var(--muted);font-size:.86rem}}@media(max-width:760px){{header{{padding:18px 0}}.rules-header-shell{{padding:0 16px}}main{{padding:16px}}.toolbar{{padding-left:16px;padding-right:16px}}.rule-grid{{grid-template-columns:1fr}}}}
</style></head><body id='topo'>
<header><div class='rules-header-shell'><div class='kicker'>Referência técnica do relatório consolidado</div><h1>Definições e remediações das Regras de Avaliação de Prontidão citadas</h1>
<p>Esta página pertence ao mesmo pacote CONS. Ela detalha apenas regras efetivamente citadas no estudo longitudinal, mantendo IDs canônicos e explicações em pt-BR.</p></div></header>
<div class='toolbar'><a href='report.html'>Voltar ao relatório consolidado</a><input id='rule-search' type='search' placeholder='Pesquisar regra, problema, alvo ou ação...'><span id='rule-count' class='result-count'>{len(sections)} regra(s)</span></div>
<main>{''.join(sections) if sections else "<section class='rule-card'><p>Nenhuma Regra de Avaliação de Prontidão foi citada neste consolidado.</p></section>"}</main>
<script>(function(){{var input=document.getElementById('rule-search'),cards=Array.from(document.querySelectorAll('[data-rule-card]')),count=document.getElementById('rule-count');if(!input)return;function norm(v){{return (v||'').toLocaleLowerCase('pt-BR')}}function run(){{var q=norm(input.value),visible=0;cards.forEach(function(card){{var show=!q||norm(card.textContent).includes(q);card.hidden=!show;if(show)visible++;}});count.textContent=visible+' regra(s)';}}input.addEventListener('input',run);run();}})();</script>
</body></html>"""


def _write_rules(result: Any, artifact: Mapping[str, Any] | None = None) -> None:
    if not isinstance(artifact, Mapping):
        path = Path(result.report_dir) / "specialist-analysis.json"
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        artifact = loaded if isinstance(loaded, Mapping) else None
    if isinstance(artifact, Mapping) and artifact.get("rule_reference"):
        try:
            (Path(result.report_dir) / "rules-reference.html").write_text(
                _rules_page(artifact),
                encoding="utf-8",
                newline="\n",
            )
        except OSError:
            pass


def install(specialist: ModuleType, presentation: ModuleType) -> None:
    """Instala a extensão de remediação sobre o contrato longitudinal vigente."""
    if getattr(specialist, "_rasai_actionable_cons_patch", False):
        return

    packet0 = specialist._longitudinal_packet
    instructions0 = specialist._instructions
    apply0 = specialist.apply_longitudinal_analysis
    refine_html0 = presentation.refine_html
    refine_result0 = presentation.refine_result

    specialist._longitudinal_packet = lambda bundle: _augment_longitudinal_packet(packet0, bundle)
    specialist._instructions = lambda: _enhanced_instructions(instructions0)

    def apply(result: Any, filters: Any, bundle: Any, run: Any, *, prepared: Any = None) -> Any:
        enriched = apply0(result, filters, bundle, run, prepared=prepared)
        try:
            _augment_artifact(enriched, bundle)
        except Exception:
            pass
        return enriched

    specialist.apply_longitudinal_analysis = apply
    specialist._rasai_actionable_cons_patch = True

    presentation.refine_html = lambda html, artifact=None: _presentation(refine_html0, html, artifact)

    def refine(result: Any) -> Any:
        refined = refine_result0(result)
        artifact = presentation._load_artifact(Path(refined.report_dir))
        _write_rules(refined, artifact)
        return refined

    presentation.refine_result = refine
    presentation._rasai_actionable_cons_patch = True
