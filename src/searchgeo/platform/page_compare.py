"""Page-level before/after and URL-to-URL comparison for RASAI."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from searchgeo.monitoring.models import Signal
from searchgeo.monitoring.reader import read_audit_snapshot


@dataclass(frozen=True, slots=True)
class PageChange:
    identity: str
    domain: str
    label: str
    device: str | None
    before: Any
    after: Any
    status: str
    material: bool


@dataclass(frozen=True, slots=True)
class PageComparison:
    baseline_audit_id: str
    current_audit_id: str
    baseline_url: str
    current_url: str
    comparable: bool
    changes: tuple[PageChange, ...]
    notes: tuple[str, ...]


def _signal_identity(signal: Signal) -> str:
    field = str(signal.metadata.get("field") or "")
    return "|".join(
        (
            signal.domain,
            signal.device or "GLOBAL",
            signal.rule_id or signal.label,
            field,
        )
    )


def _page_signals(snapshot: Any, url: str) -> dict[str, Signal]:
    return {
        _signal_identity(signal): signal
        for signal in snapshot.signals.values()
        if signal.url == url
    }


def compare_pages(
    baseline_workspace: str | Path,
    current_workspace: str | Path,
    *,
    baseline_url: str,
    current_url: str | None = None,
) -> PageComparison:
    current_url = current_url or baseline_url
    baseline = read_audit_snapshot(baseline_workspace)
    current = read_audit_snapshot(current_workspace)
    notes: list[str] = []
    comparable = True
    if baseline.domains != current.domains and baseline_url == current_url:
        comparable = False
        notes.append("audit domain sets differ for same-URL comparison")
    if baseline.ruleset_version != current.ruleset_version:
        notes.append(f"ruleset differs: {baseline.ruleset_version} → {current.ruleset_version}")
    before = _page_signals(baseline, baseline_url)
    after = _page_signals(current, current_url)
    if not before:
        notes.append(f"baseline URL has no persisted page-level signals: {baseline_url}")
    if not after:
        notes.append(f"current URL has no persisted page-level signals: {current_url}")
    changes: list[PageChange] = []
    for identity in sorted(set(before) | set(after)):
        old = before.get(identity)
        new = after.get(identity)
        signal = new or old
        assert signal is not None
        if old is None:
            status = "ADDED"
            material = True
            old_value = None
            new_value = new.value if new else None
        elif new is None:
            status = "REMOVED"
            material = True
            old_value = old.value
            new_value = None
        elif old.value == new.value:
            status = "UNCHANGED"
            material = False
            old_value = old.value
            new_value = new.value
        else:
            status = "CHANGED"
            material = True
            old_value = old.value
            new_value = new.value
        changes.append(
            PageChange(
                identity,
                signal.domain,
                signal.label,
                signal.device,
                old_value,
                new_value,
                status,
                material,
            )
        )
    return PageComparison(
        baseline.audit_id,
        current.audit_id,
        baseline_url,
        current_url,
        comparable,
        tuple(changes),
        tuple(notes),
    )


def write_page_compare_report(comparison: PageComparison, output: str | Path) -> Path:
    path = Path(output)
    if path.suffix.lower() != ".html":
        path.mkdir(parents=True, exist_ok=True)
        path = path / "page-compare.html"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"<tr><td>{escape(item.status)}</td><td>{escape(item.domain)}</td><td>{escape(item.device or '—')}</td><td>{escape(item.label)}</td><td><pre>{escape(str(item.before))}</pre></td><td><pre>{escape(str(item.after))}</pre></td></tr>"
        for item in comparison.changes
        if item.material
    ) or "<tr><td colspan='6'>Nenhuma diferença material.</td></tr>"
    notes = "".join(f"<li>{escape(item)}</li>" for item in comparison.notes) or "<li>Sem limitações adicionais.</li>"
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>RASAI Page Compare</title><style>body{{font:14px/1.5 system-ui;background:#f6f7fb;color:#273449;margin:0;padding:28px}}header,section{{max-width:1400px;margin:0 auto 16px;background:#fffefd;border:1px solid rgba(111,123,141,.16);border-radius:6px;padding:22px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid rgba(111,123,141,.16);text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:12px/1.45 ui-monospace,Consolas,monospace}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.card{{background:#f7f8fb;border-radius:5px;padding:12px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><header><div>RASAI Page Compare · non-scoring</div><h1>Comparação longitudinal de página</h1><div class='grid'><div class='card'><strong>Antes</strong><br>{escape(comparison.baseline_audit_id)}<br><code>{escape(comparison.baseline_url)}</code></div><div class='card'><strong>Depois</strong><br>{escape(comparison.current_audit_id)}<br><code>{escape(comparison.current_url)}</code></div></div></header><section><h2>Diferenças</h2><table><thead><tr><th>Status</th><th>Domínio</th><th>Device</th><th>Sinal</th><th>Antes</th><th>Depois</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>Limitações</h2><ul>{notes}</ul></section></body></html>"""
    path.write_text(html, encoding="utf-8", newline="\n")
    return path
