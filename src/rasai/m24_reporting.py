"""Static report projection for Rastreamento, descoberta e acesso de crawlers."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai import report_navigation
from rasai.persistence import AuditWorkspace

M24_FILE = "crawling-discovery.html"
PUBLIC_CONTRACT = "CRAWLING-DISCOVERY-001"
_AI_START = "<!-- crawling-discovery-ai-usage:start -->"
_AI_END = "<!-- crawling-discovery-ai-usage:end -->"
_REF_START = "<!-- crawling-discovery-references:start -->"
_REF_END = "<!-- crawling-discovery-references:end -->"
# Backward cleanup only: old generated reports may still contain these internal
# markers. They are removed before inserting the neutral public markers above.
_LEGACY_AI_START = "<!-- m24-ai-usage:start -->"
_LEGACY_AI_END = "<!-- m24-ai-usage:end -->"
_LEGACY_REF_START = "<!-- m24-references:start -->"
_LEGACY_REF_END = "<!-- m24-references:end -->"


def enrich_m24_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    _register_navigation()
    data = _load(audit_id, workspace)
    path = report_dir / M24_FILE
    path.write_text(
        _page(data, report_dir),
        encoding="utf-8",
        newline="\n",
    )
    _inject_ai_usage(report_dir, data)
    _inject_references(report_dir)
    report_navigation.normalize_report_navigation(report_dir)
    return path


def _register_navigation() -> None:
    items: list[tuple[str, str]] = []
    seen = False
    for label, filename in report_navigation.NAV_ITEMS:
        if filename == M24_FILE:
            if not seen:
                items.append(("Rastreamento e descoberta", M24_FILE))
                seen = True
            continue
        items.append((label, filename))
    if not seen:
        preferred = ("readiness.html", "desktop.html", "mobile.html", "index.html")
        insertion = 1
        for filename in preferred:
            match = next((i for i, item in enumerate(items) if item[1] == filename), None)
            if match is not None:
                insertion = match + 1
                break
        items.insert(insertion, ("Rastreamento e descoberta", M24_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM m24_runs WHERE audit_id=?", (audit_id,))
        diagnostics = _many(
            connection,
            "SELECT * FROM m24_diagnostics WHERE audit_id=? ORDER BY "
            "CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,"
            "category,code,diagnostic_id",
            (audit_id,),
        )
        ai = _one(connection, "SELECT * FROM m24_ai_results WHERE audit_id=?", (audit_id,))
        attempts = _many(
            connection,
            """
            SELECT * FROM ai_provider_attempts
            WHERE audit_id=? AND semantic_contract_version='M24-TECHNICAL-REMEDIATION-v2'
            ORDER BY started_at,attempt_index
            """,
            (audit_id,),
        )
        return {"run": run, "diagnostics": diagnostics, "ai": ai, "attempts": attempts}
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]):
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).casefold():
            return None
        raise


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).casefold():
            return []
        raise


def _page(data: dict[str, Any], report_dir: Path) -> str:
    run = data["run"]
    diagnostics = data["diagnostics"]
    nav = report_navigation.render_report_navigation(report_dir, M24_FILE)
    counts = Counter(str(row["severity"]) for row in diagnostics)
    categories = Counter(str(row["category"]) for row in diagnostics)
    llms_state = str(run["llms_state"]) if run else "UNAVAILABLE"
    ai_state = str(run["ai_state"]) if run else "UNAVAILABLE"
    external_count = 0
    if run:
        try:
            external_count = len(json.loads(str(run["external_sitemaps"])))
        except (TypeError, ValueError, json.JSONDecodeError):
            external_count = 0
    groups = []
    for category in ("ROBOTS", "SITEMAP", "DISCOVERY", "AI_ACCESS"):
        rows = [row for row in diagnostics if str(row["category"]) == category]
        if rows:
            groups.append(_group(category, rows))
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Rastreamento e descoberta - RASAi</title><link rel='stylesheet' href='css/site.css'></head>
<body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Rastreamento, descoberta e acesso de crawlers · diagnóstico técnico complementar</div>
<h1>Rastreamento, descoberta e acesso por IA</h1>
<p class='lead'>Diagnóstico aprofundado de robots.txt, sitemaps/feeds, coerência de descoberta e controles de crawlers. As regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 alimentam o SARI. Quando a IA técnica é explicitamente habilitada, ela pode apenas corroborar ou rebaixar os mesmos grupos de sitemap/robots por classes evidence-bound convertidas em fatores estáticos; nunca escolhe pesos numéricos.</p>
<div class='metric-grid'>
{_metric("Contrato", PUBLIC_CONTRACT)}
{_metric("Diagnósticos", str(len(diagnostics)))}
{_metric("Alta severidade", str(counts.get("HIGH",0)))}
{_metric("Média severidade", str(counts.get("MEDIUM",0)))}
{_metric("llms.txt", llms_state)}
{_metric("IA técnica", ai_state)}
{_metric("Sitemaps externos", str(external_count))}
{_metric("Impacto desta camada", "NENHUM" if run and str(run["scoring_impact"]) == "NONE" else (str(run["scoring_impact"]) if run else "NENHUM"))}
</div></header>
<section class='notice'><strong>Fronteira metodológica:</strong> GPTBot, OAI-SearchBot e Google-Extended possuem finalidades distintas. Bloqueio de GPTBot/Google-Extended não é convertido em penalidade de Search. <code>llms.txt</code> é tratado como proposta comunitária experimental, não como web standard obrigatório.</section>
<section class='panel'><div class='kicker'>Resumo</div><h2>Universo técnico observado</h2>
<div class='metric-grid'>{''.join(_metric(key, str(value)) for key,value in sorted(categories.items()))}</div>
<p class='intro'>A ausência de evidência para IndexNow é reportada como <code>NOT_DETERMINABLE</code>; não é presumida como configuração ausente. Sitemaps declarados em outro origin são preservados, porém não são adquiridos automaticamente para não ampliar o escopo de rede/SSRF da auditoria.</p></section>
{''.join(groups) if groups else "<section class='panel'><p>Nenhum diagnóstico Rastreamento, descoberta e acesso de crawlers persistido.</p></section>"}
{_ai_block(data)}
<section class='panel'><div class='kicker'>Referências</div><h2>Fundamentação externa</h2>
<div class='ref-grid'>
{_reference("IETF RFC 9309","Robots Exclusion Protocol","https://www.rfc-editor.org/rfc/rfc9309.html")}
{_reference("Google Crawling Infrastructure","Interpretação de robots.txt","https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec")}
{_reference("Google Search Central","Criação e formatos de sitemap","https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap")}
{_reference("Google Crawling Infrastructure","Google-Extended e crawlers","https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers")}
{_reference("OpenAI Help Center","Publishers and Developers FAQ","https://help.openai.com/en/articles/12627856-publishers-and-developers-faq")}
{_reference("llms.txt","Proposta comunitária - não web standard","https://llmstxt.org/")}
</div></section>
<footer class='footer'>{PUBLIC_CONTRACT} · os diagnósticos aprofundados desta página são advisory/non-scoring. As regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 permanecem inputs do SARI-001 via SCORE-GEO-004.</footer>
</main></body></html>
"""


def _group(category: str, rows: list[sqlite3.Row]) -> str:
    labels = {
        "ROBOTS": "robots.txt e crawlers",
        "SITEMAP": "Sitemaps e feeds",
        "DISCOVERY": "Descoberta e coerência",
        "AI_ACCESS": "Acesso por sistemas de IA",
    }
    cards = "".join(_diagnostic(row) for row in rows)
    return f"<section class='panel'><div class='kicker'>{escape(category)}</div><h2>{escape(labels.get(category,category))}</h2>{cards}</section>"


def _diagnostic(row: sqlite3.Row) -> str:
    severity = str(row["severity"])
    badge = "bad" if severity == "HIGH" else "warn" if severity == "MEDIUM" else "info"
    observed = _pretty_json(row["observed_value"])
    evidence = _json_list(row["evidence_ids"])
    scope = str(row["scope_url"] or "Escopo da auditoria")
    remediation = str(row["remediation"] or "Nenhuma ação determinística adicional.")
    return f"""<article class='page-card'>
<div class='panel-head'><div><div class='kicker'>{escape(str(row["code"]))}</div><h3>{escape(str(row["title"]))}</h3></div><span class='badge {badge}'>{escape(severity)}</span></div>
<p class='page-url'>{escape(scope)}</p>
<div class='notice'><strong>Impacto em scoring:</strong> o diagnóstico determinístico isolado é advisory; BR-GEO-003/017/018 são os inputs técnicos de base. Se IA técnica estiver habilitada e produzir classificação válida, somente a avaliação bounded do mesmo recurso pode compartilhar o grupo de scoring correspondente, sem bônus duplicado.</div>
<details><summary>Evidência observada</summary><div class='detail-body'><pre>{escape(observed)}</pre><p><strong>Evidence IDs:</strong> {escape(", ".join(evidence) or "-")}</p></div></details>
<p><strong>Orientação determinística:</strong> {escape(remediation)}</p>
</article>"""


def _ai_block(data: dict[str, Any]) -> str:
    ai = data["ai"]
    attempts = data["attempts"]
    state = str(ai["state"]) if ai else "DISABLED"
    provider = str(ai["provider"] or "-") if ai else "-"
    model = str(ai["model"] or "-") if ai else "-"
    artifact = str(ai["artifact_reference"] or "-") if ai else "-"
    total_tokens = sum(int(row["total_tokens"] or 0) for row in attempts)
    costs = [float(row["estimated_cost"]) for row in attempts if row["estimated_cost"] is not None]
    cost = f"{sum(costs):.6f} USD" if costs else "não calculável/zero chamadas"
    return f"""<section class='panel'><div class='kicker'>IA técnica de crawling/discovery (opcional)</div><h2>Telemetria e limites da remediação técnica</h2>
<div class='metric-grid'>{_metric("Estado",state)}{_metric("Provider",provider)}{_metric("Modelo",model)}{_metric("Tentativas",str(len(attempts)))}{_metric("Tokens",str(total_tokens))}{_metric("Custo estimado",cost)}</div>
<p class='intro'>A IA técnica desta página é controlada por <code>RASAI_AI_TECHNICAL_REMEDIATION</code>, independente de <code>RASAI_AI_CONTENT_REMEDIATION</code>. Ela recebe apenas diagnósticos/evidence IDs persistidos e não pode criar fatos, pesos ou elevar Confidence por opinião. Para sitemap/robots, uma classificação válida pode gerar somente PASS/WARNING/FAIL em regras auxiliares bounded que compartilham o mesmo grupo das regras determinísticas; resultado positivo não soma bônus e resultado neutro/negativo pode rebaixar o grupo.</p>
<p><strong>Artifact:</strong> <code>{escape(artifact)}</code></p><p><a href='content-suggestions.html'>Ver separadamente a remediação de conteúdo por IA →</a></p></section>"""


def _inject_ai_usage(report_dir: Path, data: dict[str, Any]) -> None:
    path = report_dir / "ai-usage.html"
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    html = _replace_marker(html, _LEGACY_AI_START, _LEGACY_AI_END, "")
    html = _replace_marker(html, _AI_START, _AI_END, "")
    block = _AI_START + _ai_block(data) + _AI_END
    html = _before_footer(html, block)
    path.write_text(html, encoding="utf-8", newline="\n")


def _inject_references(report_dir: Path) -> None:
    path = report_dir / "references.html"
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    html = _replace_marker(html, _LEGACY_REF_START, _LEGACY_REF_END, "")
    html = _replace_marker(html, _REF_START, _REF_END, "")
    block = f"""{_REF_START}<section class='panel' id='crawling-discovery-references'>
<div class='kicker'>{PUBLIC_CONTRACT}</div><h2>Rastreamento, descoberta e acesso por IA</h2>
<p class='intro'>Os diagnósticos aprofundados de crawling/discovery permanecem advisory/non-scoring. Separadamente, as regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 já alimentam SCORE-GEO-004/SARI-001. llms.txt é explicitamente identificado como proposta comunitária.</p>
<ul><li><a href='https://www.rfc-editor.org/rfc/rfc9309.html'>RFC 9309 - Robots Exclusion Protocol</a></li>
<li><a href='https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec'>Google - robots.txt</a></li>
<li><a href='https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap'>Google - sitemaps</a></li>
<li><a href='https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers'>Google - Google-Extended</a></li>
<li><a href='https://help.openai.com/en/articles/12627856-publishers-and-developers-faq'>OpenAI - publishers/developers</a></li>
<li><a href='https://llmstxt.org/'>llms.txt - proposta comunitária</a></li></ul></section>{_REF_END}"""
    html = _before_footer(html, block)
    path.write_text(html, encoding="utf-8", newline="\n")


def _replace_marker(html: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.DOTALL)
    return pattern.sub(replacement, html)


def _before_footer(html: str, block: str) -> str:
    index = html.lower().rfind("<footer")
    if index >= 0:
        return html[:index] + block + html[index:]
    index = html.lower().rfind("</main>")
    if index >= 0:
        return html[:index] + block + html[index:]
    return html + block


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"


def _reference(owner: str, title: str, url: str) -> str:
    return f"<article class='ref-card'><h3>{escape(owner)}</h3><p>{escape(title)}</p><p><a href='{escape(url)}'>{escape(url)}</a></p></article>"


def _pretty_json(raw: Any) -> str:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw)
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _json_list(raw: Any) -> list[str]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []