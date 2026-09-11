"""Relatório dedicado do Synthetic User Experience Apdex."""
from __future__ import annotations

from html import escape
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from rasai import report_navigation
from rasai.m25_cli import (
    DEFAULT_UX_CONCURRENCY,
    DEFAULT_UX_DELAY_SECONDS,
    DEFAULT_UX_DEVICE_MIX,
    DEFAULT_UX_ERROR_SCOPE,
    DEFAULT_UX_FRUSTRATED_SECONDS,
    DEFAULT_UX_KPM,
    DEFAULT_UX_MAX_PAGES,
    DEFAULT_UX_SAMPLES,
    DEFAULT_UX_SATISFIED_SECONDS,
    DEFAULT_UX_SESSION_MODE,
    DEFAULT_UX_SETTLE_SECONDS,
)
from rasai.m25_dynatrace_defaults import DYNATRACE_LOAD_PRIMARY_KPM
from rasai.persistence import AuditWorkspace

M25_REPORT_FILE = "apdex-experience.html"

_OFFICIAL_REFERENCES = (
    (
        "Apdex Technical Specification v1.1",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Fórmula Apdex; o Synthetic User Experience Apdex mantém a fórmula, mas permite thresholds calibrados independentes.",
    ),
    (
        "Dynatrace - Apdex configuration for load actions",
        "https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions",
        "KPM, thresholds e fallback para User Action Duration quando a KPM selecionada não é detectada.",
    ),
    (
        "Dynatrace - Work with key performance metrics",
        "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/analyze-and-use/work-with-key-performance-metrics",
        "Visually Complete como KPM padrão documentada para Load/XHR e User Action Duration para Custom actions.",
    ),
    (
        "Dynatrace - Apdex ratings",
        "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/scores-and-ratings/apdex-ratings",
        "Classificação de experiência e impacto de JavaScript/request errors.",
    ),
    (
        "Dynatrace Configuration API - Web applications",
        "https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application",
        "Modelo clássico de configuração usado como referência de thresholds e importação.",
    ),
)


def enrich_m25_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    _register_navigation()
    data = _load(audit_id, workspace)
    path = report_dir / M25_REPORT_FILE
    path.write_text(_page(data, report_dir), encoding="utf-8", newline="\n")
    report_navigation.normalize_report_navigation(report_dir)
    return path


def _register_navigation() -> None:
    item = ("Apdex calibrado", M25_REPORT_FILE)
    if item in report_navigation.NAV_ITEMS:
        return
    items = list(report_navigation.NAV_ITEMS)
    insertion = next(
        (index + 1 for index, value in enumerate(items) if value[1] == "apdex.html"),
        len(items),
    )
    items.insert(insertion, item)
    report_navigation.NAV_ITEMS = tuple(items)


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,))
        summaries = _many(
            connection,
            "SELECT * FROM synthetic_ux_apdex_summaries WHERE audit_id=? ORDER BY url,CASE device WHEN 'POPULATION' THEN 0 WHEN 'MOBILE' THEN 1 WHEN 'DESKTOP' THEN 2 ELSE 3 END",
            (audit_id,),
        )
        samples = _many(
            connection,
            "SELECT * FROM synthetic_ux_apdex_samples WHERE audit_id=? ORDER BY url,device,run_index",
            (audit_id,),
        )
        standard = _many(
            connection,
            "SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device",
            (audit_id,),
        )
        return {"run": run, "summaries": summaries, "samples": samples, "standard": standard}
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError:
        return []


def _page(data: dict[str, Any], report_dir: Path) -> str:
    run = data["run"]
    summaries = data["summaries"]
    samples = data["samples"]
    standard = data["standard"]
    nav = report_navigation.render_report_navigation(report_dir, M25_REPORT_FILE)
    if run is None:
        return _shell(nav, "<section class='panel'><h1>Synthetic User Experience Apdex</h1><p>Nenhum estado Synthetic User Experience Apdex persistido.</p></section>")

    mix = _json(run["device_mix"])
    metadata = _json(run["calibration_metadata"])
    configuration = _json(run["configuration"])
    standard_map = {(str(row["url"]), str(row["device"]).upper()): row for row in standard}
    rows = "".join(_summary_row(row, standard_map) for row in summaries)
    population = [row for row in summaries if str(row["device"]) == "POPULATION"]
    sample_rollup = _sample_rollup(samples)
    mix_text = " · ".join(f"{name} {float(value):g}%" for name, value in mix.items()) or "não informado"
    errors = "SIM" if bool(run["errors_affect_apdex"]) else "NÃO"
    calibration_note = _calibration_note(str(run["calibration_source"]), metadata)
    status = escape(str(run["status"]))
    settings_table = _settings_table(run, configuration, metadata)
    dynatrace_contract = _dynatrace_contract_table(metadata)
    metrics = "".join((
        _metric("Estado", status),
        _metric("KPM efetiva", str(run["kpm"])),
        _metric("Satisfied <", f"{float(run['satisfied_threshold_seconds']):g} s"),
        _metric("Frustrated >", f"{float(run['frustrated_threshold_seconds']):g} s"),
        _metric("Erros afetam", errors),
        _metric("Escopo de erro", str(run["error_scope"])),
        _metric("Sessão", str(run["session_mode"]).upper()),
        _metric("Amostras válidas", int(run["valid_samples"])),
    ))

    refs = "".join(
        f"<li><a href='{escape(url)}' target='_blank' rel='noreferrer'>{escape(title)}</a> - {escape(note)}</li>"
        for title, url, note in _OFFICIAL_REFERENCES
    )
    pop_cards = "".join(_population_card(row) for row in population)
    fallback_notice = ""
    if metadata.get("rasai_capability_fallback_applied"):
        fallback_notice = (
            "<p><strong>Fallback de capacidade aplicado:</strong> a configuração Dynatrace selecionou "
            f"<code>{escape(str(metadata.get('requested_kpm') or DYNATRACE_LOAD_PRIMARY_KPM))}</code>, "
            "que o RASAi não mede com equivalência de fornecedor. O cálculo usou explicitamente "
            "<code>USER_ACTION_DURATION</code> com os fallback thresholds importados. A substituição está registrada; não é silenciosa.</p>"
        )

    body = f"""
    <header class='hero'>
      <div class='eyebrow'>Synthetic User Experience Apdex · Web Performance sintética calibrável</div>
      <h1>Synthetic User Experience Apdex</h1>
      <p class='lead'>Medição sintética enriquecida para aproximar a estrutura de uma <em>user action</em>: navegação, XHR/fetch, recursos tardios, erros JavaScript/request e KPM configurável. <strong>Não é RUM e não representa usuários humanos observados.</strong></p>
      <div class='metric-grid'>{metrics}</div>
    </header>
    <section class='panel notice-critical'>
      <h2>Fronteira metodológica</h2>
      <p>O Synthetic User Experience Apdex não substitui <a href='apdex.html'>Synthetic Navigation Apdex Standard</a>. O Synthetic Navigation Apdex continua usando <strong>T/4T</strong> conforme a especificação Apdex. O Synthetic User Experience Apdex usa thresholds independentes e política de erros calibrável para permitir comparação metodologicamente mais próxima de ferramentas RUM/APM.</p>
      <p><strong>Zonas temporais efetivas:</strong> valor &lt; Satisfied = SATISFIED; Satisfied ≤ valor ≤ Frustrated = TOLERATING; valor &gt; Frustrated = FRUSTRATED. Um erro qualificável pode forçar FRUSTRATED conforme a política configurada.</p>
      <p>O Dynatrace documenta <strong>{escape(DYNATRACE_LOAD_PRIMARY_KPM)}</strong> como KPM padrão de Load Action. O RASAi não implementa uma imitação visual com alegação de equivalência; seu baseline executável usa <strong>USER_ACTION_DURATION</strong>, que também é o fallback documentado pelo Dynatrace quando a KPM selecionada não é detectada.</p>
      <p>Proximidade numérica com Dynatrace <strong>não é objetivo do algoritmo</strong>. Se os valores convergirem, isso deve decorrer de KPM, thresholds, política de erros e população sintética alinhados - nunca de ajuste forçado do score.</p>
    </section>
    <section class='panel'>
      <div class='kicker'>Configuração</div><h2>Padrão, customização e origem de cada parâmetro</h2>
      <p>O relatório identifica separadamente valores de baseline, customizações do usuário e valores importados do Dynatrace. Parâmetros sem equivalente RUM são marcados como defaults operacionais do RASAi.</p>
      {settings_table}
    </section>
    <section class='panel'>
      <div class='kicker'>Calibração</div><h2>Critérios efetivos desta execução</h2>
      <p><strong>Origem:</strong> {escape(str(run['calibration_source']))}. {escape(calibration_note)}</p>
      {fallback_notice}
      <p><strong>Mix de dispositivos:</strong> {escape(mix_text)}. <strong>Alvo:</strong> {int(run['target_samples_per_page'])} amostras válidas por página no total, não por device.</p>
      <p><strong>Janela pós-load:</strong> até {float(run['settle_seconds']):g}s para observar atividade tardia. <strong>Session mode:</strong> {escape(str(run['session_mode']))}; <code>cold</code> cria contexto isolado/cache frio por sample, <code>warm</code> preserva contexto/cookies/cache entre samples do mesmo worker/perfil.</p>
      <p><strong>Política de erros:</strong> errors_affect_apdex={errors}, scope={escape(str(run['error_scope']))}. <code>console.error</code> é apenas observado; não força Frustrated por si só.</p>
    </section>
    <section class='panel'>
      <div class='kicker'>Resultado</div><h2>Apdex calibrado por população e dispositivo</h2>
      {pop_cards}
      <div class='table-wrap'><table><thead><tr><th>URL</th><th>Grupo</th><th>Apdex calibrado</th><th>Válidas</th><th>S/T/F</th><th>Frustrated por erro</th><th>p75</th><th>p95</th><th>JS error samples</th><th>Request error samples</th><th>Standard Synthetic Navigation Apdex</th></tr></thead><tbody>{rows or '<tr><td colspan="11">Sem resumo calculável.</td></tr>'}</tbody></table></div>
    </section>
    <section class='panel'>
      <div class='kicker'>Coleta</div><h2>Sinais observados nas user actions sintéticas</h2>
      <div class='metric-grid'>
        {_metric('XHR/fetch', sample_rollup['xhr_fetch'])}
        {_metric('Recursos tardios', sample_rollup['dynamic'])}
        {_metric('Erros JavaScript', sample_rollup['js'])}
        {_metric('console.error', sample_rollup['console'])}
        {_metric('Requests falhos', sample_rollup['failed'])}
        {_metric('HTTP ≥400', sample_rollup['http'])}
        {_metric('Network não estabilizou', sample_rollup['unsettled'])}
        {_metric('Amostras', len(samples))}
      </div>
      <p>Além de User Action Duration, o Synthetic User Experience Apdex persiste Navigation Timing (Response Start/End, DOM Interactive, Load Event Start/End), LCP, CLS e contadores de erros/requests quando observáveis. A KPM efetivamente usada no Apdex aparece no cabeçalho.</p>
    </section>
    <section class='panel'>
      <div class='kicker'>Dynatrace</div><h2>Cobertura do contrato Dynatrace</h2>
      <p>O RASAi executa uma <strong>Load Action sintética</strong>. Configurações Dynatrace de XHR e Custom Action são lidas e mantidas como metadados sanitizados quando presentes, mas não são executadas como ações independentes: isso exigiria clickpath/script de interação e correlação de uma ação específica. XHR/fetch observados durante o load permanecem telemetria da Load Action.</p>
      {dynatrace_contract}
      <p>Na importação live, o token vem de <code>DYNATRACE_API_TOKEN</code> e não é persistido. O payload integral de configuração também não é copiado para o audit workspace.</p>
    </section>
    <section class='panel'><div class='kicker'>Referências</div><h2>Fundamentação pública</h2><ul>{refs}</ul></section>
    <footer class='footer'>Synthetic User Experience Apdex é evidence-backed, reproduzível e informativo; não altera o índice. Não altera SCORE-GEO-004, SARI-001, RuleExecution, findings ou recomendações GEO.</footer>
    """
    return _shell(nav, body)


def _settings_table(run: sqlite3.Row, configuration: dict[str, Any], metadata: dict[str, Any]) -> str:
    imported = str(run["calibration_source"]).startswith("DYNATRACE")
    samples = int(configuration.get("target_samples_per_page", run["target_samples_per_page"]))
    derived_attempts = max(samples, int(math.ceil(samples * 1.25)))
    config_mix = configuration.get("device_mix") or _json(run["device_mix"])
    mix_value = ", ".join(f"{k}={float(v):g}%" for k, v in config_mix.items()) if isinstance(config_mix, dict) else str(config_mix)
    default_mix = DEFAULT_UX_DEVICE_MIX

    rows = [
        _setting_row("KPM efetiva", run["kpm"], DEFAULT_UX_KPM, "DYNATRACE IMPORT" if imported else _origin(run["kpm"], DEFAULT_UX_KPM), f"Dynatrace Load primária: {DYNATRACE_LOAD_PRIMARY_KPM}; baseline RASAi usa fallback mensurável."),
        _setting_row("Satisfied", f"{float(run['satisfied_threshold_seconds']):g} s", f"{DEFAULT_UX_SATISFIED_SECONDS:g} s", "DYNATRACE IMPORT" if imported else _origin(float(run["satisfied_threshold_seconds"]), DEFAULT_UX_SATISFIED_SECONDS), "Valor estritamente abaixo deste limiar é Satisfied; igualdade inicia Tolerating."),
        _setting_row("Frustrated", f"{float(run['frustrated_threshold_seconds']):g} s", f"{DEFAULT_UX_FRUSTRATED_SECONDS:g} s", "DYNATRACE IMPORT" if imported else _origin(float(run["frustrated_threshold_seconds"]), DEFAULT_UX_FRUSTRATED_SECONDS), "Valor estritamente acima deste limiar é Frustrated; igualdade permanece Tolerating."),
        _setting_row("Erros afetam Apdex", bool(run["errors_affect_apdex"]), True, "DYNATRACE IMPORT/POLICY" if imported and metadata.get("errors_affect_apdex_observed") else _origin(bool(run["errors_affect_apdex"]), True), "Dynatrace também pode frustrar ações por JavaScript/request errors; regras específicas podem variar."),
        _setting_row("Escopo de erro", run["error_scope"], DEFAULT_UX_ERROR_SCOPE, _origin(str(run["error_scope"]), DEFAULT_UX_ERROR_SCOPE), "Default conservador RASAi; não existe um único scope equivalente no Dynatrace."),
        _setting_row("Amostras por página", samples, DEFAULT_UX_SAMPLES, _origin(samples, DEFAULT_UX_SAMPLES), "Parâmetro sintético RASAi; RUM não possui N sintético."),
        _setting_row("Máximo de tentativas", configuration.get("max_attempts_per_page", derived_attempts), derived_attempts, _origin(int(configuration.get("max_attempts_per_page", derived_attempts)), derived_attempts), "Default derivado: ceil(1.25 × samples)."),
        _setting_row("Máximo de páginas", configuration.get("max_pages", DEFAULT_UX_MAX_PAGES), DEFAULT_UX_MAX_PAGES, _origin(int(configuration.get("max_pages", DEFAULT_UX_MAX_PAGES)), DEFAULT_UX_MAX_PAGES), "Parâmetro operacional RASAi."),
        _setting_row("Device mix", mix_value, default_mix, _origin(_mix_normalized(config_mix), _mix_normalized(_mix_from_text(default_mix))), "Sem default Dynatrace RUM; população real é observada."),
        _setting_row("Session mode", configuration.get("session_mode", run["session_mode"]), DEFAULT_UX_SESSION_MODE, _origin(str(configuration.get("session_mode", run["session_mode"])), DEFAULT_UX_SESSION_MODE), "Parâmetro sintético RASAi; sem equivalente direto RUM."),
        _setting_row("Janela pós-load", f"{float(configuration.get('settle_seconds', run['settle_seconds'])):g} s", f"{DEFAULT_UX_SETTLE_SECONDS:g} s", _origin(float(configuration.get("settle_seconds", run["settle_seconds"])), DEFAULT_UX_SETTLE_SECONDS), "Envelope sintético RASAi."),
        _setting_row("Delay", f"{float(configuration.get('delay_seconds', DEFAULT_UX_DELAY_SECONDS)):g} s", f"{DEFAULT_UX_DELAY_SECONDS:g} s", _origin(float(configuration.get("delay_seconds", DEFAULT_UX_DELAY_SECONDS)), DEFAULT_UX_DELAY_SECONDS), "Controle de carga RASAi."),
        _setting_row("Concorrência", int(configuration.get("concurrency", DEFAULT_UX_CONCURRENCY)), DEFAULT_UX_CONCURRENCY, _origin(int(configuration.get("concurrency", DEFAULT_UX_CONCURRENCY)), DEFAULT_UX_CONCURRENCY), "Controle de carga RASAi."),
    ]
    return "<div class='table-wrap'><table><thead><tr><th>Parâmetro</th><th>Efetivo</th><th>Padrão/referência</th><th>Origem</th><th>Observação</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"


def _setting_row(name: Any, effective: Any, default: Any, origin: str, note: str) -> str:
    return (
        "<tr>"
        f"<td><strong>{escape(str(name))}</strong></td>"
        f"<td>{escape(str(effective))}</td>"
        f"<td>{escape(str(default))}</td>"
        f"<td><strong>{escape(origin)}</strong></td>"
        f"<td>{escape(note)}</td>"
        "</tr>"
    )


def _origin(value: Any, default: Any) -> str:
    return "PADRÃO" if value == default else "CUSTOMIZADO"


def _mix_from_text(raw: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        try:
            result[key.strip().upper()] = float(value)
        except ValueError:
            continue
    return result


def _mix_normalized(value: Any) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, dict):
        return ()
    return tuple(sorted((str(k).upper(), float(v)) for k, v in value.items()))


def _dynatrace_contract_table(metadata: dict[str, Any]) -> str:
    contract = metadata.get("dynatrace_apdex_contract")
    if not isinstance(contract, dict) or not contract:
        return (
            "<div class='table-wrap'><table><thead><tr><th>Ação</th><th>Suporte RASAi</th><th>Observação</th></tr></thead><tbody>"
            "<tr><td>Load</td><td>EXECUTÁVEL</td><td>Baseline 3s/12s com USER_ACTION_DURATION como fallback mensurável.</td></tr>"
            "<tr><td>XHR</td><td>TELEMETRIA NO LOAD</td><td>Não é uma XHR Action independente sem clickpath/script.</td></tr>"
            "<tr><td>Custom</td><td>NÃO EXECUTÁVEL</td><td>Exige ação de usuário/script explicitamente definido.</td></tr>"
            "</tbody></table></div>"
        )
    support = metadata.get("standalone_action_support") if isinstance(metadata.get("standalone_action_support"), dict) else {}
    rows: list[str] = []
    for key, label in (("load", "Load"), ("xhr", "XHR"), ("custom", "Custom")):
        item = contract.get(key)
        if not isinstance(item, dict):
            continue
        thresholds = _pair(item.get("satisfied_threshold_seconds"), item.get("frustrated_threshold_seconds"))
        fallback = _pair(item.get("fallback_satisfied_threshold_seconds"), item.get("fallback_frustrated_threshold_seconds"))
        rows.append(
            "<tr>"
            f"<td><strong>{label}</strong></td>"
            f"<td>{escape(str(item.get('normalized_kpm') or item.get('raw_kpm') or '-'))}</td>"
            f"<td>{escape(thresholds)}</td>"
            f"<td>{escape(fallback)}</td>"
            f"<td>{escape(str(support.get(key, '-')))}</td>"
            "</tr>"
        )
    return "<div class='table-wrap'><table><thead><tr><th>Ação Dynatrace</th><th>KPM</th><th>Thresholds S/F</th><th>Fallback UAD S/F</th><th>Suporte RASAi</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"


def _pair(satisfied: Any, frustrated: Any) -> str:
    if satisfied is None and frustrated is None:
        return "-"
    left = "-" if satisfied is None else f"{float(satisfied):g}s"
    right = "-" if frustrated is None else f"{float(frustrated):g}s"
    return f"{left} / {right}"


def _summary_row(row: sqlite3.Row, standard_map: dict[tuple[str, str], sqlite3.Row]) -> str:
    device = str(row["device"]).upper()
    std = standard_map.get((str(row["url"]), device)) if device != "POPULATION" else None
    std_score = _score(std["apdex_score"]) if std is not None else "-"
    small = "*" if bool(row["small_group"]) else ""
    return (
        "<tr>"
        f"<td class='mono'>{escape(str(row['url']))}</td>"
        f"<td><strong>{escape(device)}</strong></td>"
        f"<td><strong>{_score(row['apdex_score'])}{small}</strong></td>"
        f"<td>{int(row['valid_samples'])}/{int(row['target_samples'])}</td>"
        f"<td>{int(row['satisfied_count'])}/{int(row['tolerating_count'])}/{int(row['frustrated_count'])}</td>"
        f"<td>{int(row['error_forced_frustrated_count'])}</td>"
        f"<td>{_ms(row['p75_ms'])}</td><td>{_ms(row['p95_ms'])}</td>"
        f"<td>{int(row['javascript_error_samples'])}</td>"
        f"<td>{int(row['request_error_samples'])}</td>"
        f"<td>{std_score}</td>"
        "</tr>"
    )


def _population_card(row: sqlite3.Row) -> str:
    return (
        "<article class='population-card'>"
        f"<div><strong>{escape(str(row['url']))}</strong></div>"
        f"<div class='population-score'>{_score(row['apdex_score'])}</div>"
        f"<div>População sintética · {int(row['valid_samples'])}/{int(row['target_samples'])} válidas · "
        f"S/T/F {int(row['satisfied_count'])}/{int(row['tolerating_count'])}/{int(row['frustrated_count'])}</div>"
        "</article>"
    )


def _sample_rollup(samples: list[sqlite3.Row]) -> dict[str, int]:
    return {
        "xhr_fetch": sum(int(row["xhr_fetch_count"] or 0) for row in samples),
        "dynamic": sum(int(row["dynamic_resource_count"] or 0) for row in samples),
        "js": sum(int(row["javascript_error_count"] or 0) for row in samples),
        "console": sum(int(row["console_error_count"] or 0) for row in samples),
        "failed": sum(int(row["request_failed_count"] or 0) for row in samples),
        "http": sum(int(row["http_error_count"] or 0) for row in samples),
        "unsettled": sum(not bool(row["network_settled"]) for row in samples),
    }


def _calibration_note(source: str, metadata: dict[str, Any]) -> str:
    if source.startswith("DYNATRACE"):
        if metadata.get("rasai_capability_fallback_applied"):
            return "Configuração Dynatrace importada; KPM primária indisponível no RASAi e fallback explícito para User Action Duration aplicado com thresholds importados."
        if metadata.get("errors_affect_apdex_observed"):
            return "KPM, thresholds e política de erro foram observados na configuração importada quando disponíveis."
        return "KPM/thresholds vieram do Dynatrace; a política de erro não estava exposta no payload e foi fornecida pela configuração do Synthetic User Experience Apdex."
    return "Baseline RASAi/Dynatrace-compatible ou customização explícita; a tabela acima identifica cada parâmetro."


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def _score(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.3f}"


def _ms(value: Any) -> str:
    return "-" if value is None else f"{float(value):.0f} ms"


def _shell(nav: str, body: str) -> str:
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Apdex calibrado - RASAi</title><link rel='stylesheet' href='css/site.css'><style>.population-card{{padding:1rem;border:1px solid rgba(127,127,127,.25);border-radius:12px;margin:.7rem 0}}.population-score{{font-size:2rem;font-weight:750;margin:.25rem 0}}.mono{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.84em}}</style></head><body>{nav}<main class='app-main'>{body}</main></body></html>\n"""
