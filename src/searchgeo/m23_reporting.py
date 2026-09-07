"""Projeção HTML do Synthetic Navigation Apdex no padrão visual canônico do SearchGEO."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from searchgeo import report_navigation
from searchgeo.persistence import AuditWorkspace

APDEX_FILE = "apdex.html"
_START_INDEX = "<!-- searchgeo-m23-index-start -->"
_END_INDEX = "<!-- searchgeo-m23-index-end -->"
_START_REFS = "<!-- searchgeo-m23-references-start -->"
_END_REFS = "<!-- searchgeo-m23-references-end -->"
_START_WEB = "<!-- searchgeo-m23-web-start -->"
_END_WEB = "<!-- searchgeo-m23-web-end -->"

_OFFICIAL_REFERENCES = (
    (
        "Apdex Technical Specification v1.1",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Fórmula, threshold T, limite 4T, erros, tamanho de grupo e formato de apresentação.",
    ),
    (
        "Chrome DevTools Protocol — Emulation.setCPUThrottlingRate",
        "https://chromedevtools.github.io/devtools-protocol/tot/Emulation/#method-setCPUThrottlingRate",
        "Base técnica para o slowdown de CPU aplicado ao perfil sintético.",
    ),
    (
        "Chrome DevTools Protocol — Network",
        "https://chromedevtools.github.io/devtools-protocol/tot/Network/",
        "Base técnica para latência, throughput, cache e emulação de rede.",
    ),
    (
        "Lighthouse — Understanding results",
        "https://github.com/GoogleChrome/lighthouse/blob/main/docs/understanding-results.md",
        "Documenta metadados e configSettings efetivos do Lighthouse Result.",
    ),
    (
        "Lighthouse — Emulation",
        "https://github.com/GoogleChrome/lighthouse/blob/main/docs/emulation.md",
        "Distingue emulação de viewport/User-Agent de throttling de CPU e rede.",
    ),
)


def enrich_m23_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    _register_apdex_navigation()
    data = _load(audit_id, workspace)
    path = report_dir / APDEX_FILE
    path.write_text(_page(data, report_dir), encoding="utf-8", newline="\n")

    index_path = report_dir / "index.html"
    if index_path.is_file():
        html = index_path.read_text(encoding="utf-8")
        html = _replace_or_insert(html, _START_INDEX, _END_INDEX, _index_summary(data), "</main>")
        index_path.write_text(html, encoding="utf-8", newline="\n")

    references_path = report_dir / "references.html"
    if references_path.is_file():
        html = references_path.read_text(encoding="utf-8")
        html = _replace_or_insert(html, _START_REFS, _END_REFS, _references_section(), "</main>")
        references_path.write_text(html, encoding="utf-8", newline="\n")

    web_path = report_dir / "web-performance.html"
    if web_path.is_file():
        html = web_path.read_text(encoding="utf-8")
        html = _replace_or_insert(html, _START_WEB, _END_WEB, _web_link(data), "</main>")
        web_path.write_text(html, encoding="utf-8", newline="\n")

    report_navigation.normalize_report_navigation(report_dir)
    return path


def _register_apdex_navigation() -> None:
    item = ("Apdex", APDEX_FILE)
    if item in report_navigation.NAV_ITEMS:
        return
    items = list(report_navigation.NAV_ITEMS)
    insertion = next(
        (index + 1 for index, value in enumerate(items) if value[1] == "web-performance.html"),
        len(items),
    )
    items.insert(insertion, item)
    report_navigation.NAV_ITEMS = tuple(items)


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,))
        summaries = _many(
            connection,
            "SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id",
            (audit_id,),
        )
        samples = _many(
            connection,
            "SELECT * FROM synthetic_apdex_samples WHERE audit_id=? ORDER BY url,device,run_index,sample_id",
            (audit_id,),
        )
        profiles = _many(
            connection,
            "SELECT * FROM lighthouse_execution_profiles WHERE audit_id=? ORDER BY url,device,observation_id",
            (audit_id,),
        )
        web = _many(
            connection,
            """
            SELECT o.*,p.normalized_url
            FROM web_performance_observations o JOIN pages p ON p.page_id=o.page_id
            WHERE o.audit_id=? ORDER BY p.normalized_url,o.device,o.observation_id
            """,
            (audit_id,),
        )
        return {"run": run, "summaries": summaries, "samples": samples, "profiles": profiles, "web": web}
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _page(data: dict[str, Any], report_dir: Path) -> str:
    run = data["run"]
    summaries = data["summaries"]
    samples = data["samples"]
    profiles = data["profiles"]
    web = data["web"]
    enabled = bool(run["enabled"]) if run is not None else False
    status = str(run["status"]) if run is not None else "UNAVAILABLE"
    threshold = float(run["threshold_seconds"]) if run is not None and run["threshold_seconds"] is not None else None
    configuration = _json_object(run["configuration"]) if run is not None else {}
    host = _json_object(run["host_environment"]) if run is not None else {}
    grouped_samples: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for sample in samples:
        grouped_samples[(str(sample["url"]), str(sample["device"]))].append(sample)
    web_by_context = {(str(row["url"]), str(row["device"])): row for row in web}

    notice = _status_notice(enabled, status)
    metrics = (
        _metric("Estado Synthetic Navigation Apdex", status)
        + _metric("T", f"{_format_t(threshold)} s" if threshold is not None else "NÃO DEFINIDO")
        + _metric("F = 4T", f"{_format_t(4 * threshold)} s" if threshold is not None else "—")
        + _metric("Alvo válido/contexto", int(run["target_valid_samples"]) if run is not None else 0)
        + _metric("Válidas", int(run["valid_samples"]) if run is not None else 0)
        + _metric("Tentativas", int(run["attempted_samples"]) if run is not None else 0)
        + _metric("Delay", f"{float(run['delay_seconds']):g} s" if run is not None else "—")
        + _metric("Concorrência", int(run["concurrency"]) if run is not None else 0)
    )

    comparison_rows = "".join(_comparison_row(row, web_by_context) for row in summaries)
    details = "".join(
        _detail_card(
            row,
            grouped_samples.get((str(row["url"]), str(row["device"])), []),
            configuration,
            web_by_context.get((str(row["url"]), str(row["device"]))),
        )
        for row in summaries
    )
    profile_rows = "".join(_lighthouse_row(row) for row in profiles)

    nav = report_navigation.render_report_navigation(report_dir, APDEX_FILE)
    host_label = " · ".join(
        value
        for value in (
            str(host.get("system") or ""),
            str(host.get("release") or ""),
            f"Chromium {host.get('chromium_version')}" if host.get("chromium_version") else "",
            f"Playwright {host.get('playwright_version')}" if host.get("playwright_version") else "",
        )
        if value
    ) or "não disponível"

    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Apdex — SearchGEO Readiness Auditor</title><link rel='stylesheet' href='css/site.css'><style>{_local_css()}</style></head><body>{nav}<main class='app-main'><header class='hero'><div class='eyebrow'>Synthetic Navigation Apdex · domínio Web Performance</div><h1>Synthetic Navigation Apdex</h1><p class='lead'>Mede repetidamente a Task de navegação sob perfis Mobile/Desktop controlados. O índice é independente de SCORE-GEO-002, Lighthouse, CrUX e IA.</p><div class='metric-grid'>{metrics}</div></header>{notice}<section class='panel'><div class='kicker'>Como o SearchGEO calcula</div><h2>Fórmula e regras aplicadas</h2><p class='intro'><strong>Task:</strong> início imediatamente antes de <code>page.goto</code> → término quando <code>wait_until=load</code> conclui. Cada amostra usa <strong>BrowserContext novo</strong>, sem cookies/storage reutilizados, e cache do browser explicitamente desabilitado.</p><div class='formula-box'><strong>Apdex = (Satisfied + 0,5 × Tolerating) / Total de amostras válidas</strong><span>Satisfied ≤ T · Tolerating &gt; T e ≤ 4T · Frustrated &gt; 4T</span></div><p class='intro'>Erro de aplicação/servidor observável, timeout ou erro de navegação com perfil aplicado é classificado como <strong>Frustrated</strong>. Falha da própria ferramenta ao aplicar browser/CPU/rede é excluída do denominador e permanece auditável como amostra inválida.</p><p class='intro'>O baseline não sorteia CPU, RTT ou throughput. Os perfis são determinísticos e versionados; variações aleatórias sem distribuição empiricamente justificada reduziriam a reprodutibilidade. O delay controla o intervalo mínimo entre inícios das amostras e a concorrência é limitada a 2 workers.</p><div class='notice'><strong>Tamanho do grupo:</strong> o SearchGEO usa 100 amostras válidas por URL/dispositivo como default. Grupos com 1–99 válidas recebem <code>*</code> e são diagnósticos de grupo pequeno; somente grupos com ≥100 válidas podem ser rotulados como grupo final normal.</div></section><section class='panel'><div class='kicker'>Visão executiva</div><h2>Comparação por URL e dispositivo</h2><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Apdex</th><th>Faixa</th><th>Válidas</th><th>S/T/F</th><th>p75</th><th>p95</th><th>p99</th><th>CV</th><th>Tendência</th><th>CWV</th><th>Lighthouse</th></tr></thead><tbody>{comparison_rows or '<tr><td colspan="13">Nenhum grupo Apdex calculável.</td></tr>'}</tbody></table></div></section><section class='panel'><div class='kicker'>Diagnóstico aprofundado</div><h2>Distribuição, estabilidade e evidência amostral</h2>{details or '<p class="intro">Nenhuma amostra persistida.</p>'}</section><section class='panel'><div class='kicker'>Rastreabilidade de laboratório</div><h2>Configuração efetiva do Lighthouse</h2><p class='intro'>Extraída de <code>lighthouseResult.configSettings</code> do artefato PageSpeed já persistido. O SearchGEO não presume que o perfil Lighthouse seja igual ao perfil Apdex e não inventa campos ausentes.</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Form factor</th><th>Throttling</th><th>RTT</th><th>Throughput</th><th>CPU</th><th>Viewport</th><th>Benchmark</th><th>Tempo Lighthouse</th></tr></thead><tbody>{profile_rows or '<tr><td colspan="10">Nenhum configSettings Lighthouse disponível.</td></tr>'}</tbody></table></div><div class='notice'><strong>Não confundir:</strong> o tempo total do Lighthouse é telemetria do auditor Lighthouse. Ele não entra na fórmula Apdex.</div></section><section class='panel'><div class='kicker'>Executor</div><h2>Ambiente e governança de consumo</h2><p class='intro'>{escape(host_label)}</p><p class='intro'>Synthetic Navigation Apdex não chama OpenAI, DeepSeek, MiMo ou qualquer LLM: <strong>0 tokens de IA</strong>. Também não depende de PageSpeed/CrUX. O consumo é local (CPU/RAM/tempo) mais tráfego HTTP real contra o site, incluindo subrecursos carregados pelo browser.</p><div class='notice warn'><strong>Carga no servidor:</strong> 100 amostras de navegação não equivalem a apenas 100 requests HTTP; cada navegação pode carregar HTML, CSS, JavaScript, imagens e terceiros. Use <code>delay</code>, limite de páginas e concorrência conservadora de acordo com a autorização e capacidade do ambiente auditado.</div></section><footer class='footer'>Synthetic Navigation Apdex é evidência sintética controlada. Para Apdex de usuários reais é necessária telemetria RUM/APM da aplicação.</footer></main></body></html>\n"""


def _comparison_row(row: sqlite3.Row, web_by_context: dict[tuple[str, str], sqlite3.Row]) -> str:
    score = float(row["apdex_score"]) if row["apdex_score"] is not None else None
    web = web_by_context.get((str(row["url"]), str(row["device"])))
    cwv = str(web["cwv_assessment"]) if web is not None else "—"
    lighthouse = _score(web["performance_score"]) if web is not None else "—"
    return (
        "<tr>"
        f"<td class='mono'>{escape(str(row['url']))}</td>"
        f"<td>{escape(str(row['device']).upper())}</td>"
        f"<td><strong>{escape(_uniform_apdex(score, float(row['threshold_seconds']), bool(row['small_group'])))}</strong></td>"
        f"<td>{escape(_rating(score))}</td>"
        f"<td>{int(row['valid_samples'])}</td>"
        f"<td>{int(row['satisfied_count'])}/{int(row['tolerating_count'])}/{int(row['frustrated_count'])}</td>"
        f"<td>{_ms(row['p75_ms'])}</td><td>{_ms(row['p95_ms'])}</td><td>{_ms(row['p99_ms'])}</td>"
        f"<td>{_percent(row['coefficient_of_variation'])}</td>"
        f"<td>{_signed_percent(row['trend_percent'])}</td>"
        f"<td>{escape(cwv)}</td><td>{escape(lighthouse)}</td>"
        "</tr>"
    )


def _detail_card(row: sqlite3.Row, samples: list[sqlite3.Row], configuration: dict[str, Any], web: sqlite3.Row | None) -> str:
    score = float(row["apdex_score"]) if row["apdex_score"] is not None else None
    device = str(row["device"])
    profile = configuration.get("mobile_profile" if device == "mobile" else "desktop_profile")
    profile = profile if isinstance(profile, dict) else {}
    viewport = profile.get("viewport") if isinstance(profile.get("viewport"), dict) else {}
    profile_text = (
        f"{profile.get('profile_id', row['profile_id'])} · CPU {profile.get('cpu_slowdown', '—')}× · "
        f"RTT {profile.get('rtt_ms', '—')} ms · down {profile.get('download_kbps', '—')} Kbps · "
        f"up {profile.get('upload_kbps', '—')} Kbps · viewport {viewport.get('width', '—')}×{viewport.get('height', '—')} · "
        "BrowserContext novo · cache OFF · randomização NONE"
    )
    valid_samples = [item for item in samples if item["classification"] is not None]
    diagnostics = _diagnostic_notes(row, web)
    table_rows = "".join(_sample_row(item) for item in samples)
    distribution = _distribution_bar(row)
    trend = _sparkline(valid_samples, float(row["threshold_seconds"]))
    final_badge = "GRUPO FINAL" if bool(row["final_group"]) else "GRUPO PEQUENO *"
    return f"""<article class='page-card apdex-card'><div class='finding-head'><div><span class='badge'>{escape(device.upper())}</span> <span class='badge info'>{escape(final_badge)}</span></div><span class='badge'>{escape(_rating(score))}</span></div><h3 class='page-url'>{escape(str(row['url']))}</h3><div class='metric-grid'>{_metric('Apdex', _uniform_apdex(score, float(row['threshold_seconds']), bool(row['small_group'])))}{_metric('Satisfied', int(row['satisfied_count']))}{_metric('Tolerating', int(row['tolerating_count']))}{_metric('Frustrated', int(row['frustrated_count']))}{_metric('Média', _ms(row['mean_ms']))}{_metric('Mediana/p50', _ms(row['median_ms']))}{_metric('p75', _ms(row['p75_ms']))}{_metric('p90', _ms(row['p90_ms']))}{_metric('p95', _ms(row['p95_ms']))}{_metric('p99', _ms(row['p99_ms']))}{_metric('Mínimo', _ms(row['min_ms']))}{_metric('Máximo', _ms(row['max_ms']))}{_metric('Desvio-padrão', _ms(row['stddev_ms']))}{_metric('Coef. variação', _percent(row['coefficient_of_variation']))}{_metric('Tendência 2ª/1ª metade', _signed_percent(row['trend_percent']))}{_metric('Amostras excluídas', int(row['invalid_samples']))}</div><h4>Distribuição Apdex</h4>{distribution}<h4>Série temporal das amostras válidas</h4>{trend}<p class='intro'><strong>Perfil sintético:</strong> {escape(profile_text)}</p><div class='analysis-grid'>{''.join(f'<div class="notice"><strong>{escape(title)}</strong><span>{escape(text)}</span></div>' for title, text in diagnostics)}</div><details><summary>Ver todas as {len(samples)} tentativas/amostras persistidas</summary><div class='table-wrap'><table><thead><tr><th>#</th><th>Duração</th><th>Classe</th><th>Status</th><th>HTTP</th><th>Erro</th><th>CPU</th><th>Rede</th></tr></thead><tbody>{table_rows or '<tr><td colspan="8">Sem amostras.</td></tr>'}</tbody></table></div></details></article>"""


def _diagnostic_notes(row: sqlite3.Row, web: sqlite3.Row | None) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    valid = max(int(row["valid_samples"]), 1)
    frustrated_share = int(row["frustrated_count"]) / valid
    tolerating_share = int(row["tolerating_count"]) / valid
    cv = float(row["coefficient_of_variation"]) if row["coefficient_of_variation"] is not None else None
    median = float(row["median_ms"]) if row["median_ms"] is not None else None
    p95 = float(row["p95_ms"]) if row["p95_ms"] is not None else None
    trend = float(row["trend_percent"]) if row["trend_percent"] is not None else None
    if int(row["application_error_count"]):
        notes.append(("Erros da aplicação", f"{int(row['application_error_count'])} amostra(s) retornaram erro HTTP da aplicação e foram classificadas como Frustrated. Investigue disponibilidade, redirects e respostas 4xx/5xx."))
    if int(row["timeout_count"]):
        notes.append(("Timeouts", f"{int(row['timeout_count'])} amostra(s) ultrapassaram o timeout configurado. Investigue cauda longa, recursos bloqueantes, backend e dependências externas."))
    if frustrated_share >= 0.10:
        notes.append(("Fração Frustrated", f"{frustrated_share:.1%} das amostras válidas ficaram em Frustrated. Priorize reduzir a cauda e eliminar falhas antes de otimizações marginais."))
    elif tolerating_share >= 0.20:
        notes.append(("Fração Tolerating", f"{tolerating_share:.1%} das amostras ficaram entre T e 4T. Há oportunidade de deslocar a distribuição para Satisfied."))
    if cv is not None and cv >= 0.25:
        notes.append(("Variabilidade", f"Coeficiente de variação {cv:.1%}. O comportamento é instável; investigue backend, terceiros, CDN/cache de origem e contenção de recursos. O indicador não identifica sozinho a causa."))
    if median and p95 and p95 >= median * 2:
        notes.append(("Cauda longa", f"p95 ({p95:.0f} ms) é pelo menos 2× a mediana ({median:.0f} ms). A média pode ocultar uma parcela relevante de experiências lentas."))
    if trend is not None and trend >= 15:
        notes.append(("Degradação ao longo da sequência", f"A média da segunda metade ficou {trend:.1f}% acima da primeira. Investigue throttling, saturação ou variabilidade temporal; não atribua causa sem evidência adicional."))
    if web is not None and str(web["cwv_assessment"]) == "FAIL":
        notes.append(("Correlação com campo", "CrUX/Core Web Vitals também não aprovou neste contexto. Use o diagnóstico Lighthouse/CrUX para separar laboratório sintético de experiência real agregada."))
    if not notes:
        notes.append(("Leitura", "Não há um sinal diagnóstico dominante pelas regras conservadoras do Synthetic Navigation Apdex. Use percentis, distribuição e amostras individuais para análise técnica."))
    return notes


def _distribution_bar(row: sqlite3.Row) -> str:
    total = max(int(row["valid_samples"]), 1)
    s = int(row["satisfied_count"]) / total * 100
    t = int(row["tolerating_count"]) / total * 100
    f = int(row["frustrated_count"]) / total * 100
    return f"""<div class='apdex-distribution' role='img' aria-label='Satisfied {s:.1f}%, Tolerating {t:.1f}%, Frustrated {f:.1f}%'><span class='apdex-s' style='width:{s:.4f}%'></span><span class='apdex-t' style='width:{t:.4f}%'></span><span class='apdex-f' style='width:{f:.4f}%'></span></div><div class='apdex-legend'><span>Satisfied {s:.1f}%</span><span>Tolerating {t:.1f}%</span><span>Frustrated {f:.1f}%</span></div>"""


def _sparkline(samples: list[sqlite3.Row], threshold: float) -> str:
    values = [float(row["duration_ms"]) for row in samples if row["duration_ms"] is not None]
    if not values:
        return "<p class='intro'>Sem série temporal válida.</p>"
    width, height, pad = 760.0, 180.0, 28.0
    ceiling = max(max(values), threshold * 4000.0, 1.0)
    def x(index: int) -> float:
        return pad + (width - 2 * pad) * (index / max(len(values) - 1, 1))
    def y(value: float) -> float:
        return height - pad - (height - 2 * pad) * min(value / ceiling, 1.0)
    points = " ".join(f"{x(i):.1f},{y(value):.1f}" for i, value in enumerate(values))
    t_y = y(threshold * 1000.0)
    f_y = y(threshold * 4000.0)
    return f"""<svg class='apdex-chart' viewBox='0 0 {width:.0f} {height:.0f}' role='img' aria-label='Série temporal das durações das amostras'><line x1='{pad}' y1='{t_y:.1f}' x2='{width-pad}' y2='{t_y:.1f}' class='threshold-t'/><line x1='{pad}' y1='{f_y:.1f}' x2='{width-pad}' y2='{f_y:.1f}' class='threshold-f'/><polyline points='{points}' fill='none' class='sample-line'/><text x='{pad+4}' y='{max(t_y-4,12):.1f}'>T</text><text x='{pad+4}' y='{max(f_y-4,12):.1f}'>4T</text></svg>"""


def _sample_row(row: sqlite3.Row) -> str:
    return (
        "<tr>"
        f"<td>{int(row['run_index'])}</td><td>{_ms(row['duration_ms'])}</td>"
        f"<td>{escape(str(row['classification'] or 'EXCLUÍDA'))}</td>"
        f"<td>{escape(str(row['status']))}</td>"
        f"<td>{escape(str(row['http_status'] if row['http_status'] is not None else '—'))}</td>"
        f"<td>{escape(str(row['error_code'] or '—'))}</td>"
        f"<td>{escape(str(row['cpu_method'] or '—'))}</td>"
        f"<td>{escape(str(row['network_method'] or '—'))}</td>"
        "</tr>"
    )


def _lighthouse_row(row: sqlite3.Row) -> str:
    viewport = (
        f"{row['screen_width']}×{row['screen_height']} @ {row['device_scale_factor']}"
        if row["screen_width"] is not None and row["screen_height"] is not None
        else "—"
    )
    return (
        "<tr>"
        f"<td class='mono'>{escape(str(row['url']))}</td><td>{escape(str(row['device']).upper())}</td>"
        f"<td>{escape(str(row['form_factor'] or '—'))}</td><td>{escape(str(row['throttling_method'] or '—'))}</td>"
        f"<td>{_number(row['rtt_ms'], ' ms')}</td><td>{_number(row['throughput_kbps'], ' Kbps')}</td>"
        f"<td>{_number(row['cpu_slowdown_multiplier'], '×')}</td><td>{escape(viewport)}</td>"
        f"<td>{_number(row['benchmark_index'])}</td><td>{_number(row['lighthouse_total_ms'], ' ms')}</td>"
        "</tr>"
    )


def _index_summary(data: dict[str, Any]) -> str:
    run = data["run"]
    summaries = data["summaries"]
    if run is None:
        state, detail = "NÃO MATERIALIZADO", "Synthetic Navigation Apdex ainda não possui estado persistido."
    elif not bool(run["enabled"]):
        state, detail = "DESABILITADO", "Nenhuma navegação sintética adicional foi executada."
    else:
        state = str(run["status"])
        detail = f"{int(run['valid_samples'])} amostra(s) válida(s); alvo {int(run['target_valid_samples'])} por contexto."
    final_groups = sum(bool(row["final_group"]) for row in summaries)
    return f"""{_START_INDEX}<section id='m23-apdex-summary' class='panel'><div class='kicker'>Web Performance · Synthetic Navigation Apdex</div><h2>Apdex</h2><p class='intro'>Synthetic Navigation Apdex separado de SCORE-GEO-002, Lighthouse e CrUX.</p><div class='metric-grid'>{_metric('Estado', state)}{_metric('Grupos finais', final_groups)}{_metric('Contextos', len(summaries))}</div><p class='intro'>{escape(detail)}</p><p><a href='{APDEX_FILE}'>Abrir análise Apdex completa →</a></p></section>{_END_INDEX}"""


def _web_link(data: dict[str, Any]) -> str:
    run = data["run"]
    state = str(run["status"]) if run is not None else "NÃO MATERIALIZADO"
    return f"""{_START_WEB}<section id='m23-apdex-link' class='panel'><div class='kicker'>Synthetic Navigation Apdex · performance sintética transacional</div><h2>Apdex</h2><p class='intro'>Estado: <strong>{escape(state)}</strong>. O Apdex mede uma Task de navegação repetida sob perfil CPU/rede controlado; não é derivado dos scores Lighthouse/CWV desta página.</p><p><a href='{APDEX_FILE}'>Abrir Apdex →</a></p></section>{_END_WEB}"""


def _references_section() -> str:
    rows = "".join(
        f"<tr><td>{escape(name)}</td><td>OFICIAL</td><td>{escape(use)}</td><td><a href='{escape(url)}' target='_blank' rel='noopener'>abrir fonte</a></td></tr>"
        for name, url, use in _OFFICIAL_REFERENCES
    )
    return f"""{_START_REFS}<section id='m23-apdex-methodology' class='panel'><div class='kicker'>Synthetic Navigation Apdex · metodologia</div><h2>Apdex sintético e rastreabilidade Lighthouse</h2><p class='intro'>As fontes abaixo sustentam somente o domínio Web Performance. Não homologam SCORE-GEO-002.</p><div class='table-wrap'><table><thead><tr><th>Fonte</th><th>Base</th><th>Uso</th><th>Referência</th></tr></thead><tbody>{rows}</tbody></table></div></section>{_END_REFS}"""


def _status_notice(enabled: bool, status: str) -> str:
    if not enabled:
        return "<div class='notice'><strong>Apdex desabilitado.</strong> Nenhuma navegação adicional foi executada e nenhum T foi inventado.</div>"
    if status == "SUCCESS":
        return "<div class='notice good'><strong>Coleta Apdex concluída.</strong> Todos os contextos atingiram o alvo de amostras válidas sem exclusões.</div>"
    if status == "PARTIAL":
        return "<div class='notice warn'><strong>Coleta Apdex parcial.</strong> Há grupos incompletos ou amostras excluídas por integridade da ferramenta/perfil. Consulte os detalhes.</div>"
    return "<div class='notice warn'><strong>Apdex indisponível.</strong> Não houve população válida suficiente. Falha da ferramenta não é transformada em falha do site.</div>"


def _uniform_apdex(score: float | None, threshold: float, small: bool) -> str:
    t = _format_t(threshold)
    if score is None:
        return f"NS [{t}]"
    rounded = Decimal(str(score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f} [{t}]{'*' if small else ''}"


def _rating(score: float | None) -> str:
    if score is None:
        return "NoSample"
    if score >= 0.94:
        return "Excellent"
    if score >= 0.85:
        return "Good"
    if score >= 0.70:
        return "Fair"
    if score >= 0.50:
        return "Poor"
    return "Unacceptable"


def _format_t(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 10:
        return f"{value:.1f}"
    if value < 1000:
        return f"{value:.0f}"
    return f"{value:.15g}"


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _ms(value: Any) -> str:
    return "—" if value is None else f"{float(value):.0f} ms"


def _number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    rendered = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return rendered + suffix


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def _signed_percent(value: Any) -> str:
    return "—" if value is None else f"{float(value):+.1f}%"


def _score(value: Any) -> str:
    return "—" if value is None else f"{float(value):.0f}/100"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _replace_or_insert(html: str, start: str, end: str, content: str, before: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.DOTALL)
    if pattern.search(html):
        return pattern.sub(content, html, count=1)
    return html.replace(before, content + before, 1) if before in html else html + content


def _local_css() -> str:
    return """
.formula-box{display:flex;flex-direction:column;gap:5px;padding:16px 18px;margin:14px 0;border:1px solid var(--line);border-radius:12px;background:var(--soft-blue)}
.apdex-distribution{display:flex;height:16px;overflow:hidden;border-radius:999px;background:var(--soft-slate);margin:8px 0}.apdex-s{background:var(--green)}.apdex-t{background:var(--amber)}.apdex-f{background:var(--red)}
.apdex-legend{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:.82rem;margin-bottom:14px}.apdex-chart{width:100%;height:auto;max-height:220px;border:1px solid var(--line);border-radius:12px;background:#fbfbfc}.apdex-chart .sample-line{stroke:var(--blue);stroke-width:2}.apdex-chart .threshold-t{stroke:var(--amber);stroke-width:1;stroke-dasharray:5 4}.apdex-chart .threshold-f{stroke:var(--red);stroke-width:1;stroke-dasharray:5 4}.apdex-chart text{font-size:10px;fill:var(--muted)}
.analysis-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin:14px 0}.analysis-grid .notice{margin:0}.analysis-grid .notice strong,.analysis-grid .notice span{display:block}.analysis-grid .notice span{margin-top:5px;color:var(--muted)}
.apdex-card{margin-bottom:18px}.apdex-card details{margin-top:14px}
"""
