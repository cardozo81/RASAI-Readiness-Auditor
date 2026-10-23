"""#358: read-only CAT-07 architecture explanation from this AUD, not the host INI.

No provider calls, synthetic load computation, schema migration or AUD writes.
An old complete AUD has no architecture/profile override unless frozen evidence
is actually available; current console settings are never backfilled into it.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.experience_architecture_guidance import (
    RECORDED_CONTEXT_FIELDS,
    resolve_experience_architecture_guidance,
)

ARCH_LABELS = {
    "CSR_SPA": "SPA com renderização principal no cliente",
    "HYDRATED": "Página com hidratação de componentes",
    "MIXED": "Arquitetura mista",
    "STATIC_OR_SSR": "Página estática ou renderizada no servidor",
    "UNKNOWN": "Não determinada com evidências suficientes",
}
# Presentation-only vocabulary. Executable KPM/source enums remain unchanged
# in SQLite and in the architecture-advisory contract.
_KPM_LABELS = {
    "USER_ACTION_DURATION": "Duração da ação de carregamento inicial",
    "DOM_INTERACTIVE": "Tempo até o documento ficar interativo (DOM)",
    "LOAD_EVENT_START": "Início do evento de carregamento",
    "LOAD_EVENT_END": "Conclusão do evento de carregamento",
    "RESPONSE_START": "Início da resposta HTTP",
    "RESPONSE_END": "Conclusão da resposta HTTP",
    "LARGEST_CONTENTFUL_PAINT": "Maior pintura de conteúdo (LCP)",
}
_ARCHITECTURE_SOURCE_LABELS = {
    "M6_OBSERVED": "Identificada pela captura desta auditoria",
    "OPERATOR_DECLARED": "Informada pelo operador; sem observação conclusiva",
    "UNKNOWN": "Não determinada com evidências suficientes",
}

ADVICE_LABELS = {
    "ADEQUADA_AO_ESCOPO": "Compatível apenas com o carregamento inicial",
    "COBERTURA_PARCIAL": "Cobertura parcial para experiência além da entrada inicial",
    "REVISAO_RECOMENDADA": "Revisão da configuração recomendada",
    "INDETERMINADA": "Não determinável com as evidências disponíveis",
}


# Structured resolver codes are kept for diagnostics; the report explains them in PT-BR.
_REASON_LABELS = {
    "KPM_NOT_EXECUTABLE_IN_M25": "a métrica registrada não é executável pelo Apdex de experiência",
    "SATISFIED_INVALID": "o limite Satisfied registrado é inválido",
    "FRUSTRATED_INVALID": "o limite Frustrated registrado é inválido",
    "FRUSTRATED_NOT_GREATER_THAN_SATISFIED": "o limite Frustrated não supera o Satisfied",
    "EFFECTIVE_CONFIG_NOT_AVAILABLE": "configuração efetiva do Apdex de experiência indisponível",
    "DECLARED_VS_OBSERVED_ARCHITECTURE_MISMATCH": "arquitetura declarada diferente da observada",
    "PROFILE_MODE_NOT_RECOGNIZED": "modo de calibração não comprovado nesta auditoria",
    "IMPORTED_CONFIG_PROVENANCE_UNAVAILABLE": "origem da calibração importada indisponível",
    "ARCHITECTURE_NOT_PROVEN": "arquitetura sem evidência conclusiva",
    "MEASUREMENT_OBJECTIVE_NOT_PROVEN": "objetivo de medição não comprovado",
    "INITIAL_LOAD_DOES_NOT_COVER_WIDER_EXPERIENCE": "o carregamento inicial não cobre a experiência ampla",
    "GUIDED_PRESET_CONFLICTS_WITH_EFFECTIVE_FIELDS": "a proposta Guided diverge de valores efetivos já registrados",
}


def _columns(con: sqlite3.Connection, name: str) -> set[str]:
    return {str(row[1]) for row in con.execute(
        "PRAGMA table_info(" + name + ")"
    )}


def _observed_architecture(con: sqlite3.Connection, audit_id: str):
    cols = _columns(con, "page_snapshots")
    if not {"snapshot_id", "page_id", "device", "architecture_classification"}.issubset(cols):
        return "UNKNOWN", None, "Nenhuma classificação arquitetural por página foi persistida."
    if not {"page_id", "audit_id"}.issubset(_columns(con, "pages")):
        return "UNKNOWN", None, "Vínculo da classificação arquitetural com a auditoria não comprovável."
    rows = con.execute(
        "SELECT ps.snapshot_id, ps.page_id, ps.device, ps.architecture_classification "
        "FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id "
        "WHERE p.audit_id=? ORDER BY ps.snapshot_id LIMIT 257",
        (audit_id,),
    ).fetchall()
    if not rows:
        return "UNKNOWN", None, "Nenhuma arquitetura observada nesta auditoria."
    if len(rows) != 1:
        return "UNKNOWN", None, (
            "Há múltiplas capturas nesta AUD; arquitetura de uma única página/ação "
            "não deve ser atribuída ao índice agregado."
        )
    snapshot, page, device, classification = rows[0]
    # A snapshot ID reused by another page/AUD cannot identify the evidence
    # shown to the analyst, even if the scoped JOIN yielded one row.
    if con.execute(
        "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?", (snapshot,),
    ).fetchone()[0] != 1:
        return "UNKNOWN", None, (
            "Identificador de snapshot repetido; a origem desta "
            "classificação arquitetural não é inequívoca."
        )
    architecture = str(classification or "").strip().upper()
    if architecture not in ARCH_LABELS or architecture == "UNKNOWN" or any(
        not isinstance(x, str) or not x.strip()
        for x in (snapshot, page, device)
    ):
        return "UNKNOWN", None, "Classificação de arquitetura insuficiente ou incompleta."
    return architecture, {
        "snapshot_id": snapshot, "page_id": page, "device": device,
    }, "Arquitetura observada e registrada nesta auditoria, não inferida pelo relatório."


def _run_config(con: sqlite3.Connection, audit_id: str) -> Mapping[str, Any]:
    cols = _columns(con, "synthetic_ux_apdex_runs")
    if not {"audit_id", "configuration"}.issubset(cols):
        return {}
    rows = con.execute(
        "SELECT configuration FROM synthetic_ux_apdex_runs WHERE audit_id=? "
        "LIMIT 2", (audit_id,),
    ).fetchall()
    if len(rows) != 1:
        return {}
    try:
        value = json.loads(str(rows[0][0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dynatrace_rum_kpm_reference_html(architecture: str) -> str:
    """Static vendor action-type options, not evidence of tenant configuration.

    #355: translate an observed M6 architecture into a checklist for a future
    RUM review. Never promote M25 Synthetic KPM to a Dynatrace RUM setting,
    invent a numeric threshold or infer that XHR/Fetch is instrumented.
    """
    from rasai.dynatrace_apdex_arch_advisory import KPM_BY_ACTION

    title = "<h4>Referência de KPMs Dynatrace RUM por tipo de ação (não aplicada)</h4>"
    if architecture not in ("CSR_SPA", "HYDRATED", "MIXED", "STATIC_OR_SSR"):
        return (
            title + "<p>Seleção por arquitetura: N/D (arquitetura da página "
            "não comprovada). Nenhuma configuração de Load, XHR ou Custom "
            "do tenant foi consultada nesta auditoria.</p>"
        )
    soft_route_context = architecture in ("CSR_SPA", "HYDRATED", "MIXED")
    contexts = (
        ("load_actions", "Load", "Verificar ações de carregamento inicial do documento."),
        (
            "xhr_actions", "XHR",
            "Investigar soft navigation e ações XHR/Fetch antes de selecionar a KPM."
            if soft_route_context else
            "Somente considerar se ações XHR/Fetch forem efetivamente observadas.",
        ),
        (
            "custom_actions", "Custom",
            "Somente considerar com instrumentação Custom explicitamente comprovada.",
        ),
    )
    rows = "".join(
        "<tr><td><code>" + escape(label) + "</code></td><td>" + escape(context)
        + "</td><td>" + ", ".join(
            "<code>" + escape(kpm) + "</code>"
            for kpm in sorted(KPM_BY_ACTION[key])
        )
        + "</td><td>N/D (tenant não consultado)</td></tr>"
        for key, label, context in contexts
    )
    return (
        title
        + "<p>Lista de métricas <strong>admitidas pelo esquema do fornecedor</strong>, "
        "não métrica recomendada ou configurada. A arquitetura observada na "
        "captura do RASAi não comprova navegação por rota, população de ações "
        "Dynatrace, captura XHR/Fetch, dispositivo ou janela equivalentes. "
        "Uma SPA pode possuir ações Load e XHR legítimas; a existência "
        "da arquitetura não obriga trocar a KPM Load por XHR. "
        "<strong>KPM configurada no tenant: N/D; thresholds e fallback: N/D.</strong> "
        "As medições sintéticas de Apdex de navegação e experiência permanecem independentes.</p>"
        + "<details><summary>Consultar KPMs possíveis por Load, XHR e Custom</summary>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Tipo de ação RUM</th><th>Critério para revisão</th>"
        "<th>KPMs previstas no esquema Dynatrace</th><th>Configuração comprovada</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table></div></details>"
    )


def _unsealed_cat07_advisory() -> str:
    """Abstain without touching a live/symlinked SQLite source."""
    return (
        "<div class='subsection' data-contract='CAT07-ARCHITECTURE-358'>"
        "<h3>Arquitetura observada e adequação do Apdex</h3>"
        "<p><strong>Arquitetura:</strong> N/D. "
        "Fonte SQLite não estável ou caminho não confiável; "
        "a interpretação CAT-07 foi suspensa sem reprocessar a AUD.</p>"
        "<p><strong>Configuração efetiva:</strong> N/D. "
        "Nenhuma comparação Load/XHR/Custom ou equivalência com "
        "Dynatrace RUM foi comprovada.</p></div>"
    )


def _unsealed_sqlite_source(db: Path) -> bool:
    return (
        db.is_symlink() or db.parent.is_symlink()
        or any(Path(str(db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal"))
    )


def _source_stamp(db: Path) -> tuple[int, int, int, int] | None:
    """Inexpensive physical metadata gate, not a SHA-256 source seal."""
    try:
        stat = db.stat()
        if not db.is_file() or db.is_symlink() or db.parent.is_symlink():
            return None
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    except OSError:
        return None


def cat07_architecture_advice_html(
    database: Path, audit_id: str, *,
    frozen_meta: Mapping[str, Any] | None = None,
) -> str:
    """Render an advisory from one AUD. Empty/ambiguous old data => explicit N/D."""
    db = Path(database)
    if _unsealed_sqlite_source(db):
        return _unsealed_cat07_advisory()
    before_stamp = _source_stamp(db)
    if before_stamp is None:
        return _unsealed_cat07_advisory()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        architecture, provenance, note = _observed_architecture(con, audit_id)
        run = _run_config(con, audit_id)
    # Do not publish a positive architectural conclusion if an AUD writer
    # added a journal during the read; the bare source is not attested.
    if _unsealed_sqlite_source(db) or _source_stamp(db) != before_stamp:
        return _unsealed_cat07_advisory()
    config = {
        "kpm": run.get("kpm"),
        "satisfied_threshold_seconds": run.get("satisfied_threshold_seconds"),
        "frustrated_threshold_seconds": run.get("frustrated_threshold_seconds"),
    }
    config.update({key: run.get(key) for key in RECORDED_CONTEXT_FIELDS})
    meta = frozen_meta if isinstance(frozen_meta, Mapping) else {}
    # The canonical console handoff serializes INI sections under "settings".
    # Only a hash-verified frozen audit_execution_configurations snapshot can
    # supply these values. An old AUD with no such fields remains N/D.
    stored_sections = meta.get("settings", {})
    stored = (
        stored_sections.get("synthetic_apdex_experience", {})
        if isinstance(stored_sections, Mapping) else {}
    )
    if not isinstance(stored, Mapping):
        stored = {}
    selected = str(stored.get("architecture", "AUTO"))
    raw_mode = str(stored.get("profile_mode", "UNKNOWN"))
    mode = raw_mode if raw_mode in {"CUSTOM", "DYNATRACE_GUIDED", "DYNATRACE_IMPORTED"} else "UNKNOWN"
    if not run:
        mode = "UNKNOWN"
    objective = "INITIAL_LOAD"  # The M25 runtime only executes Load, never a soft route.
    guidance = resolve_experience_architecture_guidance(
        config,
        selected_architecture=selected,
        observed_architecture=architecture,
        provenance=provenance,
        profile_mode=mode,
        objective=objective,
    )
    label = ARCH_LABELS.get(architecture, ARCH_LABELS["UNKNOWN"])
    kpm = config.get("kpm") if isinstance(config.get("kpm"), str) else None
    kpm_label = _KPM_LABELS.get(kpm, kpm) if kpm else "N/D"
    origin_label = _ARCHITECTURE_SOURCE_LABELS.get(
        guidance["architecture_source"], "Não determinada com evidências suficientes"
    )
    parts = [
        "<div class='subsection' data-contract='CAT07-ARCHITECTURE-358'>",
        "<h3>Arquitetura observada e adequação do Apdex</h3>",
        "<p><strong>Arquitetura observada na captura:</strong> " + escape(label) + ". "
        + escape(note) + "</p>",
        "<p><strong>Configuração efetiva do Apdex de experiência:</strong> Métrica "
        + escape(kpm_label) + "; Satisfied "
        + escape(str(config.get("satisfied_threshold_seconds")
                    if config.get("satisfied_threshold_seconds") is not None else "N/D"))
        + " s; Frustrated "
        + escape(str(config.get("frustrated_threshold_seconds")
                    if config.get("frustrated_threshold_seconds") is not None else "N/D"))
        + " s.</p>",
        "<p><strong>Adequação ao objetivo medido:</strong> "
        + escape(ADVICE_LABELS[guidance["adequacy"]]) + ".</p>",
        "<p><strong>Modo de calibração da AUD:</strong> "
        + escape(mode if mode != "UNKNOWN" else "N/D (não congelado nesta AUD)")
        + ". Não inferir modo Guided pela simples coincidência numérica.</p>",
        "<p><strong>Limite de medição:</strong> Este Apdex mede apenas o carregamento inicial; "
        "não produz ações XHR/Custom autônomas, prontidão de conteúdo ou "
        "equivalência com Dynatrace RUM. Um Apdex alto pode não representar "
        "uma transição SPA ou hidratação completa.</p>",
    ]
    parts.append(_dynatrace_rum_kpm_reference_html(architecture))
    # Context is whitelisted from the persisted M25 run, never from the
    # console process, old INI, vendor JSON, credentials or inferred defaults.
    recorded = guidance["effective_recorded_run_context"]
    policy_labels = {
        "errors_affect_apdex": "Erros impactam a classificação",
        "javascript_errors_affect_apdex": "Erros JavaScript impactam a classificação",
        "request_errors_affect_apdex": "Erros de requisição impactam a classificação",
        "console_errors_affect_apdex": "Erros de console impactam a classificação",
        "javascript_error_capture": "Captura de erros JavaScript",
        "xhr_capture": "Captura de observações XHR",
        "fetch_capture": "Captura de observações Fetch",
        "console_error_capture": "Captura de erros de console",
    }
    scope_labels = {
        "error_scope": "Escopo dos erros",
        "session_mode": "Modo de sessão",
        "target_samples_per_page": "Amostras previstas por página",
        "max_attempts_per_page": "Tentativas máximas por página",
        "concurrency": "Concorrência efetiva",
        "settle_seconds": "Observação pós-load (s; não somada ao Apdex)",
        "delay_seconds": "Intervalo entre tentativas (s)",
    }
    details = []
    for key, label_text in (*policy_labels.items(), *scope_labels.items()):
        value = recorded.get(key)
        shown = (
            "Sim" if value is True else "Não" if value is False
            else "N/D" if value is None else str(value)
        )
        details.append(
            "<li><strong>" + escape(label_text) + ":</strong> "
            + escape(shown) + "</li>"
        )
    parts.append(
        "<h4>Políticas de erro e contexto efetivamente persistidos</h4>"
        "<p>Valores obtidos somente da configuração de execução gravada nesta AUD; "
        "campos ausentes ou inválidos permanecem N/D, sem preenchimento pelo INI atual. "
        "Capturar XHR/Fetch não equivale a executar uma XHR Action autônoma.</p>"
        "<ul>" + "".join(details) + "</ul>"
    )
    if provenance:
        parts.append(
            "<p><strong>Rastreabilidade da arquitetura identificada (contexto observado):</strong> "
            "snapshot <code>" + escape(provenance["snapshot_id"]) + "</code>; "
            "página <code>" + escape(provenance["page_id"]) + "</code>; "
            "dispositivo <code>" + escape(provenance["device"]) + "</code>. "
            "Essa evidência não é extrapolada a outras páginas ou dispositivos.</p>"
        )
    else:
        parts.append(
            "<p><strong>Rastreabilidade da arquitetura identificada:</strong> N/D "
            "(captura ausente, insuficiente ou múltiplos contextos não individualizados).</p>"
        )
    parts.append(
        "<p><strong>Contrato de interpretação:</strong> "
        + escape(str(guidance["contract_version"]))
        + "; tarefa efetivamente medida: "
        + escape(str(guidance["measured_task"]))
        + ". É uma orientação RASAi, não um Apdex RUM/Synthetic Browser Dynatrace.</p>"
    )
    if guidance["reasons"]:
        parts.append("<p><strong>Motivos do diagnóstico:</strong> "
                     + escape("; ".join(_REASON_LABELS.get(code, "condição não catalogada")
                                        for code in guidance["reasons"])) + ".</p>")
    # Render only advice computed from the effective M25 run and a verified
    # frozen console handoff. Display proposed future variables as proposals,
    # never as settings silently used by this historical AUD.
    declared = guidance["selected_architecture"]
    declared_label = (
        "AUTO - não declarada previamente"
        if declared == "AUTO" else ARCH_LABELS.get(declared, "N/D")
    )
    parts.append(
        "<p><strong>Arquitetura informada antes da AUD:</strong> "
        + escape(declared_label if meta else "N/D (sem handoff congelado)")
        + ". <strong>Origem da identificação:</strong> "
        + escape(origin_label) + ".</p>"
    )
    source_labels = {
        "RASAI_EXECUTABLE_NOW": "No RASAi (executável após confirmação)",
        "DYNATRACE_EXTERNAL": "Somente Dynatrace externo (não executado pelo RASAi)",
        "FUTURE_CAPABILITY": "Capacidade futura (não disponível nesta AUD)",
    }
    action_rows = guidance.get("next_actions", ())
    if action_rows:
        parts.append("<h4>Ações recomendadas e limites de execução</h4><ul>")
        for action in action_rows:
            parts.append(
                "<li><strong>"
                + escape(source_labels.get(action.get("scope"), "Escopo não comprovado"))
                + ":</strong> " + escape(str(action.get("text", "N/D"))) + "</li>"
            )
        parts.append("</ul>")
    preview = guidance.get("new_audit_configuration_preview") or []
    if preview:
        parts.append(
            "<h4>Prévia para uma NOVA auditoria (não aplicada)</h4>"
            "<p>Somente o modo Guided apresenta valores propostos; "
            "não há alteração de configuração nesta página nem garantia "
            "de precedência sobre CLI, INI ou ambiente. Confirmar novamente "
            "no console antes da execução.</p>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Variável</th><th>Valor proposto</th><th>Origem</th>"
            "<th>Substituiria valor atual?</th></tr></thead><tbody>"
        )
        for item in preview:
            parts.append(
                "<tr><td><code>" + escape(str(item.get("variable") or "N/D"))
                + "</code></td><td>" + escape(str(item.get("value") or "N/D"))
                + "</td><td>" + escape(str(item.get("source") or "N/D"))
                + "</td><td>"
                + ("Sim - requer aceite" if item.get("would_override_current")
                   else "Não identificado")
                + "</td></tr>"
            )
        parts.append("</tbody></table></div>")
    elif mode in {"CUSTOM", "DYNATRACE_IMPORTED"}:
        parts.append(
            "<p><strong>Valores de nova auditoria:</strong> não gerar um "
            "preset substituto em modo Custom/Imported. Valores efetivos "
            "persistidos acima são apenas o registro da AUD corrente.</p>"
        )
    if guidance["architecture_mismatch"]:
        parts.append("<p><strong>Atenção:</strong> arquitetura declarada diverge da observada. "
                     "Revisar a configuração antes de uma nova auditoria.</p>")
    if architecture in {"CSR_SPA", "HYDRATED", "MIXED"}:
        parts.append("<p><strong>Próxima validação:</strong> avaliar separadamente "
                     "XHR/Fetch, soft navigation e interatividade real; "
                     "não recalcular o Apdex homologado com dados inexistentes.</p>")
    if not run:
        parts.append("<p>Sem configuração do Apdex de experiência persistida suficiente para comparação numérica.</p>")
    parts.append("<p class='muted'>Orientação derivada exclusivamente de dados persistidos "
                 "desta AUD. A configuração de uma nova auditoria não altera a AUD original.</p></div>")
    return "".join(parts)
