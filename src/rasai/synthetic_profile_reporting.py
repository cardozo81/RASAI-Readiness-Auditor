"""Report disclosure for controlled synthetic profiles and provider-owned Lighthouse.

This module is read-only over persisted configuration. It does not recalculate Apdex,
Lighthouse or scoring and performs no network calls.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace

_START = "<!-- rasai-synthetic-profile-disclosure-start -->"
_END = "<!-- rasai-synthetic-profile-disclosure-end -->"


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_configuration(workspace: AuditWorkspace, table: str, audit_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                f"SELECT configuration FROM {table} WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return {}
        return _json(row["configuration"]) if row is not None else {}
    finally:
        connection.close()


def _profile_row(device: str, profile: dict[str, Any]) -> str:
    viewport = profile.get("viewport") if isinstance(profile.get("viewport"), dict) else {}
    limits = profile.get("emulation_limitations") if isinstance(profile.get("emulation_limitations"), dict) else {}
    return (
        "<tr>"
        f"<td><strong>{escape(device)}</strong></td>"
        f"<td class='mono'>{escape(str(profile.get('client_profile_id') or '-'))}</td>"
        f"<td class='mono'>{escape(str(profile.get('hardware_profile_id') or '-'))}</td>"
        f"<td class='mono'>{escape(str(profile.get('network_profile_id') or '-'))}</td>"
        f"<td>{escape(str(viewport.get('width') or '-'))}×{escape(str(viewport.get('height') or '-'))} · DPR {escape(str(profile.get('device_scale_factor') or '-'))}</td>"
        f"<td>{escape(str(profile.get('cpu_slowdown') or '-'))}×</td>"
        f"<td>RTT {escape(str(profile.get('rtt_ms') or '-'))} ms · ↓ {escape(str(profile.get('download_kbps') or '-'))} Kbps · ↑ {escape(str(profile.get('upload_kbps') or '-'))} Kbps</td>"
        f"<td>{escape(str(profile.get('browser_family') or 'chromium'))} / {escape(str(profile.get('os_family') or '-'))}</td>"
        f"<td>{escape(str(limits.get('physical_ram') or 'NOT_EMULATED'))}; GPU {escape(str(limits.get('physical_gpu') or 'NOT_EMULATED'))}</td>"
        "</tr>"
    )


def _navigation_section(configuration: dict[str, Any]) -> str:
    profiles = []
    for device, key in (("MOBILE", "mobile_profile"), ("DESKTOP", "desktop_profile")):
        value = configuration.get(key)
        if isinstance(value, dict):
            profiles.append(_profile_row(device, value))
    if not profiles:
        return ""
    return (
        "<section class='panel'><div class='kicker'>Condição de laboratório</div>"
        "<h2>Perfis efetivos da medição sintética</h2>"
        "<p class='intro'>Cada contexto usa perfil explícito de cliente, CPU e rede. CPU é slowdown relativo via Chrome DevTools Protocol; rede é envelope controlado de RTT/throughput. Isso aproxima condições de uso, mas não transforma Chromium em hardware físico.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Contexto</th><th>Cliente</th><th>Hardware</th><th>Rede</th><th>Viewport</th><th>CPU</th><th>Rede efetiva</th><th>Browser / SO lógico</th><th>Limites físicos</th></tr></thead><tbody>"
        + "".join(profiles)
        + "</tbody></table></div>"
        "<div class='notice'><strong>Limite de emulação:</strong> RAM física, GPU física, estado térmico e scheduler do sistema operacional não são emulados pelo runtime atual. O relatório não apresenta esses fatores como se fossem controlados.</div></section>"
    )


def _experience_section(configuration: dict[str, Any]) -> str:
    profiles = configuration.get("runtime_profiles")
    if not isinstance(profiles, dict) or not profiles:
        return ""
    rows = []
    for device in ("MOBILE", "DESKTOP", "TABLET"):
        value = profiles.get(device)
        if not isinstance(value, dict):
            continue
        rows.append(
            "<tr>"
            f"<td><strong>{device}</strong></td>"
            f"<td class='mono'>{escape(str(value.get('client') or '-'))}</td>"
            f"<td class='mono'>{escape(str(value.get('hardware') or '-'))}</td>"
            f"<td class='mono'>{escape(str(value.get('network') or '-'))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        "<section class='panel'><div class='kicker'>Perfis da população sintética</div>"
        "<h2>Cliente, hardware e rede por dispositivo</h2>"
        "<p class='intro'>O device mix define quantas user actions pertencem a cada contexto; os presets abaixo definem como cada contexto é executado. O perfil é persistido junto da medição e não altera a fórmula Apdex.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Dispositivo</th><th>Cliente</th><th>Hardware/CPU</th><th>Rede</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        "<div class='notice'><strong>Browser/OS:</strong> a execução controlada usa Chromium. User-Agent, viewport, DPR, mobile/touch e descritores são coerentes com o contexto selecionado, mas não equivalem a executar Safari/WebKit, Firefox ou um sistema operacional físico diferente.</div></section>"
    )


def _replace_or_insert(html: str, section: str) -> str:
    if not section:
        return html
    block = _START + section + _END
    start = html.find(_START)
    end = html.find(_END)
    if start >= 0 and end >= start:
        return html[:start] + block + html[end + len(_END):]
    marker = "</main>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def _write(path: Path, section: str) -> None:
    if not path.is_file() or not section:
        return
    html = path.read_text(encoding="utf-8")
    updated = _replace_or_insert(html, section)
    if updated != html:
        path.write_text(updated, encoding="utf-8", newline="\n")


def _lighthouse_disclosure() -> str:
    return (
        "<section class='panel'><div class='kicker'>Contexto Lighthouse</div>"
        "<h2>Perfil efetivo controlado pelo provider</h2>"
        "<p class='intro'>Na integração PageSpeed Insights, o RASAi escolhe a estratégia Mobile ou Desktop. CPU, throttling de rede, viewport e demais configSettings da execução remota são definidos pelo serviço/Lighthouse e são tratados como provenance observada, não como parâmetros arbitrariamente emulados pelo RASAi.</p>"
        "<div class='notice'>Quando o artefato Lighthouse fornece <code>configSettings</code>, o RASAi persiste os valores efetivos — incluindo form factor, throttling, RTT/throughput, CPU slowdown, screen emulation, user agents e benchmark — para permitir leitura e comparação sem inventar campos ausentes.</div></section>"
    )


def enrich_synthetic_profile_reports(*, audit_id: str, workspace: AuditWorkspace) -> None:
    report_dir = workspace.root / "report"
    navigation = _read_configuration(workspace, "synthetic_apdex_runs", audit_id)
    experience = _read_configuration(workspace, "synthetic_ux_apdex_runs", audit_id)
    _write(report_dir / "apdex.html", _navigation_section(navigation))
    _write(report_dir / "apdex-experience.html", _experience_section(experience))
    _write(report_dir / "web-performance.html", _lighthouse_disclosure())
