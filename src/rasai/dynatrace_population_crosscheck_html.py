"""#355: human-readable offline Dynatrace Settings / USQL RUM advisory.

Presentation only. Never executes Dynatrace, changes configuration,
creates synthetic KPM thresholds or equates RUM and RASAi M25.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


_VERSION = "RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002"
_ACTIONS = (("load", "Load"), ("xhr", "XHR"), ("custom", "Custom"), ("other", "Outras"))
_KPM = (("load_actions", "Load"), ("xhr_actions", "XHR"), ("custom_actions", "Custom"))
_ARCH = {
    "CSR_SPA": "SPA client-side (CSR)",
    "HYDRATED": "Hydrated / hidratação",
    "MIXED": "Mista (navegação de documento e ações cliente)",
    "STATIC_OR_SSR": "HTML estático ou SSR",
    "UNKNOWN": "Indeterminada",
}
_RECOMMENDATIONS = {
    "SETTINGS_SCOPE_IS_OPERATOR_DECLARED_NOT_AUTHENTICATED":
        "Confirmar o escopo da aplicação na API Settings autenticada; a exportação não atesta tenant.",
    "RUM_EXTRAPOLATION_LEVEL_UNKNOWN":
        "Conferir a amostragem da consulta USQL; extrapolação ausente não demonstra censo bruto.",
    "RUM_COUNTS_EXTRAPOLATED_NOT_RAW_CENSUS":
        "Interpretar as contagens USQL como valores extrapolados, não sessões físicas individuais.",
    "NO_REPORTED_XHR_ACTIONS_DOES_NOT_PROVE_CAPTURE_DISABLED":
        "Verificar escopo, filtros e instrumentação XHR/Fetch; zero XHR não prova captura desativada.",
    "XHR_ACTIONS_REPORTED_WITHOUT_MATCHING_KPM_SNAPSHOT":
        "Revisar o KPM configurado para XHR no export recebido, sem concluir falha de Apdex.",
    "INITIAL_LOAD_COUNTS_DO_NOT_PROVE_SOFT_ROUTE_READINESS":
        "Load observado não mede, por si, a prontidão de rotas SPA e navegações soft.",
    "LOAD_ACTION_COUNTS_DO_NOT_PROVE_SAME_PAGE_SAMPLE":
        "Confirmar que ações Load se referem à mesma URL e população observada.",
    "ARCHITECTURE_NOT_COMPARABLE_WITH_RUM_ACTION_POPULATION":
        "Investigar a arquitetura e o padrão de navegação antes de avaliar cobertura RUM.",
}


def _s(value: object) -> str:
    if value is None:
        return "N/D"
    if not isinstance(value, (str, int, float, bool)):
        return "N/D"
    txt = str(value)
    return escape(txt[:2048] if txt else "N/D", quote=True)


def _count(value: object) -> str:
    return _s(value) if type(value) is int and value >= 0 else "N/D"


def render_dynatrace_population_crosscheck_html(
    result: Mapping[str, Any],
) -> str:
    """Render an advisory from a valid versioned projection; no side effects."""
    if not isinstance(result, Mapping) or result.get("contract_version") != _VERSION:
        raise ValueError("Dynatrace crosscheck v2 projection required")
    status = result.get("status")
    if status not in {
        "NOT_COMPARABLE", "CLAIMED_LIVE_APPLICATION_ID_MATCH",
        "DECLARED_APPLICATION_ID_MATCH",
    }:
        raise ValueError("invalid Dynatrace crosscheck status")
    eligible = status != "NOT_COMPARABLE"
    description = {
        "NOT_COMPARABLE":
            "N/D - fontes não comparáveis. Nenhuma cobertura por ação foi comprovada.",
        "CLAIMED_LIVE_APPLICATION_ID_MATCH":
            "ID de aplicação declarado coincide. O export afirma origem live; tenant não autenticado nesta leitura.",
        "DECLARED_APPLICATION_ID_MATCH":
            "ID de aplicação declarado coincide. Origem Settings depende da declaração do operador.",
    }[status]
    counts = result.get("action_counts_reported")
    kpm = result.get("action_apdex_kpm")
    findings = result.get("review_findings")
    if eligible and (not isinstance(counts, Mapping)
                     or not isinstance(kpm, Mapping)
                     or not isinstance(findings, list)
                     or len(findings) > 40
                     or any(not isinstance(item, str) or len(item) > 200
                            for item in findings)):
        raise ValueError("Dynatrace eligible projection missing evidence sets")
    if not eligible:
        counts, kpm, findings = {}, {}, []
    assert isinstance(counts, Mapping) and isinstance(kpm, Mapping)
    assert isinstance(findings, list)
    reported = "".join(
        f"<tr><th scope='row'>{escape(label)}</th><td>{_count(counts.get(key))}</td></tr>"
        for key, label in _ACTIONS
    )
    kpm_rows = "".join(
        f"<tr><th scope='row'>{escape(label)}</th><td>{_s(kpm.get(key))}</td></tr>"
        for key, label in _KPM
    )
    architecture = result.get("architecture") if eligible else None
    architecture_label = (
        _ARCH.get(architecture, "N/D")
        if isinstance(architecture, str) else "N/D"
    )
    extrap = result.get("usql_extrapolation_level") if eligible else None
    if type(extrap) is int and extrap > 1:
        extrap_label = f"Nível {extrap} informado; contagens extrapoladas"
    elif extrap == 1 and type(extrap) is int:
        extrap_label = "Nível 1 informado; censo bruto ainda não comprovado"
    else:
        extrap_label = "N/D - amostragem não comprovada"
    if eligible:
        explanations = [
            _RECOMMENDATIONS.get(item, "Código de revisão não reconhecido: " + str(item)[:200])
            for item in findings
        ]
    else:
        explanations = [
            "Não concluir configuração ou cobertura por ação com fontes incompletas. "
            "Verifique: " + str(result.get("reason") or "evidência ausente")[:200]
        ]
    recommendations = "".join(
        f"<li>{_s(item)}</li>" for item in explanations
    ) or "<li>Sem orientação adicional derivável desta amostra.</li>"
    app_label = _s(result.get("application_id")) if eligible else "N/D"
    target = _s(result.get("target_url")) if eligible else "N/D"
    device = _s(result.get("declared_dynatrace_device_filter")) if eligible else "N/D"
    started = _s(result.get("period_start_utc")) if eligible else "N/D"
    ended = _s(result.get("period_end_utc")) if eligible else "N/D"
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dynatrace: conferência de ações RUM e KPM - RASAi</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#183044}
body{max-width:1100px;margin:auto;padding:clamp(14px,3vw,34px);background:#f7f9fb}
h1{font-size:1.75rem}h2{font-size:1.2rem}p{line-height:1.55}
.summary{padding:15px 19px;border-left:4px solid #45617c;background:#e8eef4}
.section{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:20px;margin-top:17px}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}
table{width:100%;border-collapse:collapse}
th,td{padding:9px 8px;border-bottom:1px solid #e2e8f0;text-align:left;overflow-wrap:anywhere}
th{font-weight:600}ul{line-height:1.55}li{margin-bottom:10px}
.muted{font-size:.92rem;color:#41556d}
@media(max-width:680px){.columns{grid-template-columns:1fr}.section{padding:14px}}
@media print{body{background:#fff}.section{break-inside:avoid}}
</style></head><body><header><h1>Dynatrace: cobertura RUM por ação</h1>
<p class="muted">Diagnóstico consultivo derivado de JSONs já obtidos.
RUM Classic e Synthetic Apdex RASAi são universos diferentes.</p></header>
<div class="summary"><strong>""" + escape(description) + """</strong></div>
<section class="section"><h2>Escopo declarado</h2>
<p>Arquitetura: <strong>""" + escape(architecture_label) + """</strong></p>
<p>Aplicação: """ + app_label + """</p>
<p>URL: """ + target + """</p>
<p>Dispositivo declarado: """ + device + """</p>
<p>Janela UTC: """ + started + """ até """ + ended + """</p>
<p>Extrapolação USQL: """ + escape(extrap_label) + """</p>
<p class="muted">Mesmo tenant, navegador, sessão, dispositivo físico,
intenção e amostragem NÃO foram autenticados entre as fontes.</p></section>
<section class="section"><div class="columns">
<div><h2>Ações RUM reportadas</h2><table>""" + reported + """</table></div>
<div><h2>KPM informada nos Settings</h2><table>""" + kpm_rows + """</table></div>
</div><p class="muted">Zero XHR não significa captura desativada; Load
não comprova renderização de navegações SPA. Contagens extrapoladas
não são censo de sessões individuais.</p></section>
<section class="section"><h2>Revisões recomendadas</h2>
<ul>""" + recommendations + """</ul></section>
<footer class="muted"><p>Nenhum threshold foi inferido da arquitetura.
Sem novas consultas ao Dynatrace, mudanças no ambiente monitorado, nas medições
sintéticas de navegação e experiência, na pontuação Apdex ou nos índices de
prontidão e GEO. Nenhuma auditoria ou relatório canônico foi alterado e não
houve cobrança adicional.</p></footer>
</body></html>
"""


__all__ = ["render_dynatrace_population_crosscheck_html"]
