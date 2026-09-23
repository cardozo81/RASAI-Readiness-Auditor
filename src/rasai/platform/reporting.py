"""HTML/JSON reporting for the RASAi product platform layer."""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path
from typing import Any

from rasai.monitoring.models import ComparisonResult, GateResult
from rasai.time_contract import localize_html_timestamps, normalize_timestamp_values

from .models import DeploymentPair
from .store import PlatformStore

_PLATFORM_CSS = """
:root{--bg:#f6f7fb;--surface:#fffefd;--ink:#273449;--muted:#6f7b8d;--line:rgba(111,123,141,.16);--blue:#657fc6;--green:#5f9674;--amber:#b68a50;--red:#bf6f70;--soft-blue:#eef2fb;--soft-green:#edf6f0;--soft-amber:#fbf4e8;--soft-red:#fbefef;--radius:6px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.55 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);min-height:100vh}.nav{background:#2f3a4d;color:#e8edf4;padding:20px 14px}.brand{padding:4px 8px 18px;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:14px}.brand strong{display:block;font-size:18px}.brand small{color:#bac4d2}.nav a{display:block;color:#d8e0ea;text-decoration:none;padding:9px 10px;border-radius:5px;margin:3px 0}.nav a.active,.nav a:hover{background:#46536a;color:#fff}.nav-context{display:block;color:#fff;padding:9px 10px;border-radius:5px;margin:3px 0;background:#46536a}.main{padding:30px clamp(18px,3vw,42px) 60px;max-width:1560px}.hero,.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 4px 16px rgba(47,58,78,.04);padding:22px;margin:0 0 16px}.eyebrow,.kicker{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:var(--muted);font-weight:700}.lead{max-width:78ch;color:#526074}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin-top:16px}.metric{padding:12px 13px;border-radius:5px;background:#f7f8fb}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{font-size:18px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--muted);font-weight:650}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.good{color:#35664a}.bad{color:#8f4245}.warn{color:#82632e}.chip{display:inline-block;padding:3px 7px;border-radius:999px;background:#f1f3f6;font-size:11px;font-weight:650}.chip.good{background:var(--soft-green)}.chip.bad{background:var(--soft-red)}.chip.warn{background:var(--soft-amber)}.timeline{display:flex;flex-direction:column;gap:10px}.timeline-item{display:grid;grid-template-columns:180px 12px minmax(0,1fr);gap:10px;align-items:start}.dot{width:10px;height:10px;border-radius:50%;background:var(--blue);margin-top:7px}.card{padding:12px;border:1px solid var(--line);border-radius:5px;background:#fff}.footer{color:var(--muted);font-size:12px;margin-top:18px}@media(max-width:850px){.layout{grid-template-columns:1fr}.nav{position:static}.main{padding:18px}.timeline-item{grid-template-columns:1fr}.dot{display:none}}
"""

_NAV = (
    ("Portfolio", "index.html"),
    ("Timeline", "timeline.html"),
    ("Deployments", "deployments.html"),
    ("Pages", "pages.html"),
    ("Usage", "usage.html"),
)


def _nav(current: str, *, platform_links: bool = True) -> str:
    if platform_links:
        content = "".join(
            f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>"
            for label, filename in _NAV
        )
    else:
        content = "<span class='nav-context'>Deployment Impact</span>"
    return f"<aside class='nav'><div class='brand'><strong>RASAi</strong><small>Product Platform</small></div>{content}</aside>"


def _shell(title: str, current: str, body: str, *, platform_links: bool = True) -> str:
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)} · RASAi</title><style>{_PLATFORM_CSS}</style></head><body><div class='layout'>{_nav(current, platform_links=platform_links)}<main class='main'>{body}<footer class='footer'>RASAi Product Platform · dados gerenciais derivados; AUD workspaces permanecem imutáveis.</footer></main></div></body></html>"""
    return localize_html_timestamps(html)


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def write_platform_site(store: PlatformStore, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    counts = store.counts()
    properties = store.list_properties()
    audits = store.list_audits()
    milestones = store.list_milestones()
    recent_audits = sorted(audits, key=lambda item: item.event_time, reverse=True)[:25]
    property_rows = []
    for prop in properties:
        scoped = store.list_audits(property_id=prop.property_id)
        last = max(scoped, key=lambda item: item.event_time) if scoped else None
        hierarchy = store.hierarchy_for_property(prop.property_id)
        property_rows.append(
            f"<tr><td>{escape(str(hierarchy['workspace_name']))}</td><td>{escape(str(hierarchy['project_name']))}</td><td>{escape(prop.name)}</td><td class='mono'>{escape(prop.canonical_origin)}</td><td>{len(scoped)}</td><td>{escape(last.event_time if last else '-')}</td><td>{escape(last.status if last else '-')}</td></tr>"
        )
    body = f"""<header class='hero'><div class='eyebrow'>RASAi Portfolio</div><h1>Portfólio Search & AI Readiness</h1><p class='lead'>Visão centralizada de workspaces, projetos, propriedades, ambientes, auditorias e marcos operacionais. Esta camada organiza o produto sem alterar evidências AUD históricas.</p><div class='metric-grid'>{_metric('Workspaces', counts['workspaces'])}{_metric('Projetos', counts['projects'])}{_metric('Propriedades', counts['properties'])}{_metric('Ambientes', counts['environments'])}{_metric('AUDs indexados', counts['audit_index'])}{_metric('Milestones', counts['milestones'])}</div></header><section class='panel'><div class='kicker'>Portfolio</div><h2>Propriedades monitoradas</h2><div class='table-wrap'><table><thead><tr><th>Workspace</th><th>Projeto</th><th>Property</th><th>Origin</th><th>AUDs</th><th>Último AUD</th><th>Status</th></tr></thead><tbody>{''.join(property_rows) or '<tr><td colspan=7>Nenhuma propriedade.</td></tr>'}</tbody></table></div></section><section class='panel'><h2>AUDs recentes</h2><div class='table-wrap'><table><thead><tr><th>Data</th><th>AUD</th><th>Projeto legado</th><th>Status</th><th>URLs</th><th>Devices</th><th>SHA audit.db</th></tr></thead><tbody>{''.join(f"<tr><td>{escape(a.event_time)}</td><td class='mono'>{escape(a.audit_id)}</td><td>{escape(a.project_name)}</td><td>{escape(a.status)}</td><td>{a.url_count}</td><td>{escape(', '.join(a.devices) or '-')}</td><td class='mono'>{escape(a.audit_db_sha256[:16])}…</td></tr>" for a in recent_audits) or '<tr><td colspan=7>Nenhum AUD indexado.</td></tr>'}</tbody></table></div></section>"""
    (root / "index.html").write_text(_shell("Portfolio", "index.html", body), encoding="utf-8", newline="\n")

    timeline_items = sorted(
        [(a.event_time, "AUD", a.audit_id, a.status, a.property_id) for a in audits]
        + [(m.occurred_at, m.kind, m.title, m.release or m.description or "", m.property_id) for m in milestones],
        key=lambda item: item[0],
        reverse=True,
    )
    timeline_body = "".join(
        f"<div class='timeline-item'><div class='mono'>{escape(ts)}</div><div class='dot'></div><div class='card'><span class='chip'>{escape(kind)}</span> <strong>{escape(title)}</strong><div>{escape(detail)}</div><small class='mono'>{escape(property_id)}</small></div></div>"
        for ts, kind, title, detail, property_id in timeline_items[:200]
    ) or "<p>Sem eventos.</p>"
    (root / "timeline.html").write_text(
        _shell("Timeline", "timeline.html", f"<header class='hero'><div class='eyebrow'>Project Timeline</div><h1>AUDs e marcos</h1><p class='lead'>Linha do tempo factual. Eventos posteriores a deploy são associação temporal, não prova automática de causalidade.</p></header><section class='panel'><div class='timeline'>{timeline_body}</div></section>"),
        encoding="utf-8", newline="\n"
    )

    deployment_rows = "".join(
        f"<tr><td>{escape(m.occurred_at)}</td><td class='mono'>{escape(m.milestone_id)}</td><td>{escape(m.title)}</td><td>{escape(m.release or '-')}</td><td class='mono'>{escape(m.commit_sha or '-')}</td><td>{escape(m.source)}</td></tr>"
        for m in milestones if m.kind in {"DEPLOYMENT", "RELEASE"}
    ) or "<tr><td colspan=6>Nenhum deploy/release registrado.</td></tr>"
    (root / "deployments.html").write_text(
        _shell("Deployments", "deployments.html", f"<header class='hero'><div class='eyebrow'>Change Management</div><h1>Deployments e releases</h1></header><section class='panel'><div class='table-wrap'><table><thead><tr><th>Data</th><th>Milestone</th><th>Título</th><th>Release</th><th>Commit</th><th>Origem</th></tr></thead><tbody>{deployment_rows}</tbody></table></div></section>"),
        encoding="utf-8", newline="\n"
    )

    identities = store.list_page_identities()
    page_rows = "".join(
        f"<tr><td class='mono'>{escape(p.page_identity_id)}</td><td>{escape(p.canonical_name)}</td><td class='mono'>{escape(p.property_id)}</td><td>{len(store.page_identity_urls(p.page_identity_id))}</td><td>{escape(p.status)}</td></tr>"
        for p in identities
    ) or "<tr><td colspan=5>Nenhuma PageIdentity.</td></tr>"
    (root / "pages.html").write_text(
        _shell("Pages", "pages.html", f"<header class='hero'><div class='eyebrow'>Page Lineage</div><h1>Identidade longitudinal de páginas</h1><p class='lead'>Permite acompanhar uma entidade de página através de mudança de URL, redirects e migrations sem confundir URL com identidade de negócio.</p></header><section class='panel'><div class='table-wrap'><table><thead><tr><th>ID</th><th>Nome</th><th>Property</th><th>URLs vinculadas</th><th>Status</th></tr></thead><tbody>{page_rows}</tbody></table></div></section>"),
        encoding="utf-8", newline="\n"
    )

    usage = store.usage_summary()
    usage_rows = "".join(
        f"<tr><td>{escape(str(x.get('category') or '-'))}</td><td>{escape(str(x.get('provider') or '-'))}</td><td>{escape(str(x.get('quantity') or 0))}</td><td>{escape(str(x.get('unit') or '-'))}</td><td>{escape(str(x.get('cost') if x.get('cost') is not None else '-'))}</td><td>{escape(str(x.get('currency') or '-'))}</td></tr>"
        for x in usage
    ) or "<tr><td colspan=6>Sem eventos de uso.</td></tr>"
    (root / "usage.html").write_text(
        _shell("Usage", "usage.html", f"<header class='hero'><div class='eyebrow'>Usage Ledger</div><h1>Consumo e custos estimados</h1></header><section class='panel'><div class='table-wrap'><table><thead><tr><th>Categoria</th><th>Provider</th><th>Quantidade</th><th>Unidade</th><th>Custo</th><th>Moeda</th></tr></thead><tbody>{usage_rows}</tbody></table></div></section>"),
        encoding="utf-8", newline="\n"
    )
    return root / "index.html"


def write_deployment_report(
    store: PlatformStore,
    pair: DeploymentPair,
    result: ComparisonResult,
    gate: GateResult,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "report.html"
    manifest_path = root / "manifest.json"
    changes = [event for event in result.events if event.material and event.status != "UNCHANGED"]
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    changes.sort(key=lambda event: (severity_order.get(event.severity.upper(), 9), event.status, event.key))
    rows = "".join(
        f"<tr><td><span class='chip {'bad' if e.status == 'REGRESSED' else 'good' if e.status in {'IMPROVED','RESOLVED'} else 'warn'}'>{escape(e.status)}</span></td><td>{escape(e.severity)}</td><td>{escape(e.domain)}</td><td class='mono'>{escape(e.rule_id or e.label)}</td><td>{escape(e.device or '-')}</td><td class='mono'>{escape(e.url or '-')}</td><td>{escape(str(e.before))}</td><td>{escape(str(e.after))}</td><td>{escape(e.reason or '-')}</td></tr>"
        for e in changes
    ) or "<tr><td colspan=9>Sem mudanças materiais.</td></tr>"
    limitation_html = "".join(f"<li>{escape(x)}</li>" for x in result.compatibility_notes) or "<li>Nenhuma limitação adicional registrada.</li>"
    body = f"""<header class='hero'><div class='eyebrow'>Deployment Impact</div><h1>{escape(pair.milestone.title)}</h1><p class='lead'>Marco em {escape(pair.milestone.occurred_at)} · release {escape(pair.milestone.release or '-')} · commit {escape(pair.milestone.commit_sha or '-')}. Comparação técnica before/after; outcomes posteriores devem ser tratados como associação temporal até existir evidência causal independente.</p><div class='metric-grid'>{_metric('Baseline', pair.baseline_audit_id or '-')}{_metric('Current', pair.current_audit_id or '-')}{_metric('Comparável', 'SIM' if result.comparable else 'NÃO')}{_metric('Regressões', len(result.regressions))}{_metric('Melhorias', len(result.improvements))}{_metric('Release gate', 'PASS' if gate.passed else 'FAIL')}</div></header><section class='panel'><div class='kicker'>Baseline resolution</div><h2>Par selecionado</h2><p><strong>Antes:</strong> {escape(pair.baseline_reason)}<br><strong>Depois:</strong> {escape(pair.current_reason)}</p></section><section class='panel'><div class='kicker'>Material changes</div><h2>Mudanças detectadas</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Sev.</th><th>Domínio</th><th>Sinal/regra</th><th>Device</th><th>URL</th><th>Antes</th><th>Depois</th><th>Interpretação</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class='panel'><h2>Limitações de comparabilidade</h2><ul>{limitation_html}</ul></section>"""
    # This report is stored under audits/deployments/<milestone>/, not inside
    # the portfolio directory. Avoid emitting dead relative navigation links.
    path.write_text(_shell("Deployment Impact", "deployments.html", body, platform_links=False), encoding="utf-8", newline="\n")
    manifest = normalize_timestamp_values({
        "schema": "RASAI-DEPLOYMENT-IMPACT-001",
        "milestone": asdict(pair.milestone),
        "pair": {
            "baseline_audit_id": pair.baseline_audit_id,
            "current_audit_id": pair.current_audit_id,
            "baseline_reason": pair.baseline_reason,
            "current_reason": pair.current_reason,
        },
        "comparable": result.comparable,
        "compatibility_notes": list(result.compatibility_notes),
        "counts": result.counts,
        "material_counts": result.material_counts,
        "gate": {
            "passed": gate.passed,
            "reason": gate.reason,
            "blocking": [asdict(event) for event in gate.blocking_events],
        },
        "changes": [asdict(event) for event in changes],
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8", newline="\n")
    return path, manifest_path
