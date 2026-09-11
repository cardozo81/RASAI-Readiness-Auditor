"""Read-only report for URL, device and synthetic-profile capture scopes."""
from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.context_scope import (
    CONTEXT_SCOPE_CONTRACT_VERSION,
    ContextScope,
    SCOPE_DEFINITIONS,
    evidence_scope,
    scope_label,
)
from rasai.persistence import AuditWorkspace
from rasai import report_navigation


REPORT_FILE = "context.html"
DOMAIN_REPORT_FILE = "crawling-discovery.html"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        origins: list[str] = []
        if _table_exists(connection, "audit_targets"):
            cols = _columns(connection, "audit_targets")
            origin_col = "normalized_origin" if "normalized_origin" in cols else "input_url" if "input_url" in cols else None
            if origin_col:
                origins = [
                    str(row[0]) for row in connection.execute(
                        f"SELECT DISTINCT {origin_col} FROM audit_targets WHERE audit_id=? ORDER BY {origin_col}",
                        (audit_id,),
                    ).fetchall() if row[0]
                ]

        scope_counts: Counter[str] = Counter()
        if _table_exists(connection, "evidence"):
            cols = _columns(connection, "evidence")
            selected = [name for name in ("page_id", "snapshot_id", "device") if name in cols]
            if selected and "audit_id" in cols:
                rows = connection.execute(
                    f"SELECT {','.join(selected)} FROM evidence WHERE audit_id=? ORDER BY rowid",
                    (audit_id,),
                ).fetchall()
                for row in rows:
                    values = dict(row)
                    scope = evidence_scope(
                        page_id=values.get("page_id"),
                        snapshot_id=values.get("snapshot_id"),
                        device=values.get("device"),
                    )
                    scope_counts[scope.value] += 1

        snapshots: list[dict[str, Any]] = []
        if _table_exists(connection, "page_snapshots") and _table_exists(connection, "pages"):
            s_cols = _columns(connection, "page_snapshots")
            p_cols = _columns(connection, "pages")
            if {"snapshot_id", "page_id", "device", "browser_metadata"}.issubset(s_cols) and {"page_id", "audit_id"}.issubset(p_cols):
                url_expr = "p.normalized_url" if "normalized_url" in p_cols else "ps.requested_url"
                rows = connection.execute(
                    f"""SELECT ps.snapshot_id,ps.page_id,ps.device,{url_expr} AS url,ps.browser_metadata
                        FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                        WHERE p.audit_id=? ORDER BY p.rowid,ps.device""",
                    (audit_id,),
                ).fetchall()
                for row in rows:
                    metadata = _json(row["browser_metadata"], {})
                    document_source = metadata.get("document_source") if isinstance(metadata, dict) else None
                    runtime = metadata.get("runtime_diagnostics") if isinstance(metadata, dict) else None
                    source_hash = document_source.get("sha256") if isinstance(document_source, dict) else None
                    source_bytes = document_source.get("bytes") if isinstance(document_source, dict) else None
                    diagnostic_count = runtime.get("count", 0) if isinstance(runtime, dict) else 0
                    items = runtime.get("items", []) if isinstance(runtime, dict) else []
                    snapshots.append(
                        {
                            "snapshot_id": str(row["snapshot_id"]),
                            "page_id": str(row["page_id"]),
                            "device": str(row["device"]),
                            "url": str(row["url"] or "-"),
                            "source_hash": str(source_hash) if source_hash else None,
                            "source_bytes": int(source_bytes) if isinstance(source_bytes, int) else source_bytes,
                            "runtime_diagnostics": int(diagnostic_count or 0),
                            "diagnostic_items": items if isinstance(items, list) else [],
                            "capture_contract": metadata.get("context_scope_contract") if isinstance(metadata, dict) else None,
                        }
                    )

        variance: list[dict[str, Any]] = []
        by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in snapshots:
            by_page[item["page_id"]].append(item)
        for page_id, items in by_page.items():
            hashes = {item["source_hash"] for item in items if item["source_hash"]}
            devices = tuple(sorted({item["device"] for item in items}))
            if len(devices) < 2:
                state = "SINGLE_DEVICE"
            elif len(hashes) == 0:
                state = "NOT_DETERMINED"
            elif len(hashes) == 1 and all(item["source_hash"] for item in items):
                state = "SAME_DOCUMENT_SOURCE"
            elif len(hashes) > 1:
                state = "DEVICE_VARIANT_DOCUMENT_SOURCE"
            else:
                state = "PARTIAL_SOURCE_CAPTURE"
            variance.append(
                {
                    "page_id": page_id,
                    "url": items[0]["url"],
                    "devices": devices,
                    "state": state,
                    "hashes": tuple(sorted(hashes)),
                }
            )

        page_count = 0
        if _table_exists(connection, "pages") and "audit_id" in _columns(connection, "pages"):
            page_count = int(connection.execute("SELECT COUNT(*) FROM pages WHERE audit_id=?", (audit_id,)).fetchone()[0])

        return {
            "origins": origins,
            "scope_counts": scope_counts,
            "snapshots": snapshots,
            "variance": variance,
            "page_count": page_count,
        }
    finally:
        connection.close()


def _scope_cards(data: dict[str, Any]) -> str:
    counts: Counter[str] = data["scope_counts"]
    cards = []
    for definition in SCOPE_DEFINITIONS:
        observed = counts.get(definition.scope.value, 0)
        if definition.scope is ContextScope.PROFILE_MEASUREMENT:
            observed_text = "medição configurada separadamente"
        else:
            observed_text = f"{observed} evidência(s) persistida(s)"
        destination = ""
        if definition.scope is ContextScope.ORIGIN:
            destination = (
                f"<p><a href='{DOMAIN_REPORT_FILE}'>Abrir dados detalhados de domínio/origem</a></p>"
            )
        cards.append(
            "<div class='page-card'>"
            f"<h3>{escape(scope_label(definition.scope))}</h3>"
            f"<p><code>{escape(definition.scope.value)}</code> · {escape(observed_text)}</p>"
            f"<p>{escape(definition.meaning)}</p>"
            f"<p><strong>Exemplos:</strong> {escape(', '.join(definition.examples))}</p>"
            f"<p><strong>Política:</strong> {escape(definition.reacquisition_policy)}</p>"
            f"{destination}"
            "</div>"
        )
    return "".join(cards)


def _snapshot_table(data: dict[str, Any]) -> str:
    rows = []
    for item in data["snapshots"]:
        digest = item["source_hash"][:12] + "..." if item["source_hash"] else "não capturado"
        rows.append(
            "<tr>"
            f"<td>{escape(item['device'])}</td><td><code>{escape(item['url'])}</code></td>"
            f"<td><code>{escape(digest)}</code></td><td>{escape(str(item['source_bytes'] or '-'))}</td>"
            f"<td>{item['runtime_diagnostics']}</td><td>{escape(scope_label(ContextScope.DEVICE_SNAPSHOT))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>Nenhum snapshot por dispositivo disponível.</p>"
    return (
        "<div class='table-wrap'><table><thead><tr><th>Dispositivo</th><th>URL</th><th>Hash do documento recebido</th>"
        "<th>Bytes</th><th>Erros runtime</th><th>Escopo</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _variance_table(data: dict[str, Any]) -> str:
    labels = {
        "SINGLE_DEVICE": "Somente um dispositivo executado",
        "NOT_DETERMINED": "Fonte do documento não capturada",
        "SAME_DOCUMENT_SOURCE": "Mesmo documento recebido nos dispositivos",
        "DEVICE_VARIANT_DOCUMENT_SOURCE": "Documento recebido varia por dispositivo",
        "PARTIAL_SOURCE_CAPTURE": "Captura parcial; comparação inconclusiva",
    }
    rows = []
    for item in data["variance"]:
        rows.append(
            f"<tr><td><code>{escape(item['url'])}</code></td><td>{escape(', '.join(item['devices']))}</td>"
            f"<td><strong>{escape(labels.get(item['state'], item['state']))}</strong></td>"
            f"<td>{len(item['hashes'])}</td></tr>"
        )
    if not rows:
        return "<p>Nenhuma URL disponível para comparação entre dispositivos.</p>"
    return (
        "<div class='table-wrap'><table><thead><tr><th>URL</th><th>Dispositivos</th><th>Estado</th><th>Documentos distintos</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _runtime_details(data: dict[str, Any]) -> str:
    blocks = []
    for item in data["snapshots"]:
        diagnostics = item["diagnostic_items"]
        if not diagnostics:
            continue
        rows = []
        for diagnostic in diagnostics[:20]:
            if not isinstance(diagnostic, dict):
                continue
            rows.append(
                f"<tr><td>{escape(str(diagnostic.get('type') or '-'))}</td>"
                f"<td>{escape(str(diagnostic.get('message') or '-'))}</td>"
                f"<td><code>{escape(str(diagnostic.get('url') or '-'))}</code></td></tr>"
            )
        blocks.append(
            f"<details><summary>{escape(item['device'])} · {escape(item['url'])} · {len(diagnostics)} diagnóstico(s)</summary>"
            "<div class='table-wrap'><table><thead><tr><th>Tipo</th><th>Mensagem</th><th>Recurso</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div></details>"
        )
    return "".join(blocks) or "<p>Nenhum erro de console, page error ou request failure foi capturado nos snapshots disponíveis.</p>"


def write_context_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Render capture topology without recalculating any score."""
    data = _load(audit_id, workspace)
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / REPORT_FILE
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    origins = ", ".join(data["origins"]) or "não disponível"
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi · Contexto de captura</title><link rel='stylesheet' href='css/site.css'></head><body>
<div class='app-shell'>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Contrato de captura · {escape(CONTEXT_SCOPE_CONTRACT_VERSION)}</div>
<h1>Contexto de captura: URL e dispositivo</h1>
<p>Esta superfície explica onde cada evidência é capturada e mostra diferenças observadas entre snapshots. Dados detalhados da origem ficam concentrados em <a href='{DOMAIN_REPORT_FILE}'>Domínio e descoberta</a>. Esta apresentação não altera fórmulas, pesos ou scores.</p></header>
<section class='panel'><h2>Topologia desta auditoria</h2><div class='metric-grid'>
<div class='metric'><small>Origem</small><strong>{escape(origins)}</strong></div>
<div class='metric'><small>URLs auditadas</small><strong>{data['page_count']}</strong></div>
<div class='metric'><small>Snapshots de browser</small><strong>{len(data['snapshots'])}</strong></div>
<div class='metric'><small>Contrato</small><strong>{escape(CONTEXT_SCOPE_CONTRACT_VERSION)}</strong></div>
</div><div class='grid'>{_scope_cards(data)}</div></section>
<section class='panel'><h2>Dados de domínio/origem</h2>
<div class='notice'><strong>Sem repetição nesta página.</strong> <code>robots.txt</code>, sitemaps, <code>llms.txt</code> e demais fatos <code>ORIGIN</code> são exibidos em uma única superfície: <a href='{DOMAIN_REPORT_FILE}'>Domínio e descoberta</a>. Eles não são replicados por URL ou por dispositivo.</div>
</section>
<section class='panel'><h2>Snapshots por dispositivo</h2>
<p>DOM, execução JavaScript, identidade de browser e o documento efetivamente recebido pelo browser pertencem ao snapshot do dispositivo.</p>
{_snapshot_table(data)}</section>
<section class='panel'><h2>Variação do documento por dispositivo</h2>
<p>A comparação usa o corpo da resposta de navegação já realizada pelo browser. Não existe requisição adicional para produzir esta verificação.</p>
{_variance_table(data)}</section>
<section class='panel'><h2>Erros JavaScript e de recursos</h2>
<p>Erros de console, exceções de página e falhas de requests observadas durante o browser são associados ao dispositivo/snapshot onde ocorreram. Um defeito no HTML bruto comum da URL permanece no escopo URL.</p>
{_runtime_details(data)}</section>
<section class='panel'><h2>Política de IA e economia de tokens</h2>
<div class='notice'><strong>Sem IA adicional para este relatório.</strong> A análise semântica usa uma resposta estruturada para o conjunto contratado de regras de cada snapshot, em vez de uma chamada por regra. Recursos globais não provocam chamadas repetidas por dispositivo. Saídas devem ser concisas e evidence-bound.</div>
</section>
<footer class='footer'>RASAi · contexto de captura read-only · não altera fórmulas de scoring</footer>
</main></div></body></html>"""
    path.write_text(html, encoding="utf-8", newline="\n")
    return path
