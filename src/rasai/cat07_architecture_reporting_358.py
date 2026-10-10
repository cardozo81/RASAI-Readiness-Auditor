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

from rasai.experience_architecture_guidance_358 import resolve_experience_architecture_guidance

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


def cat07_architecture_advice_html(
    database: Path, audit_id: str, *,
    frozen_meta: Mapping[str, Any] | None = None,
) -> str:
    """Render an advisory from one AUD. Empty/ambiguous old data => explicit N/D."""
    with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        architecture, provenance, note = _observed_architecture(con, audit_id)
        run = _run_config(con, audit_id)
    config = {
        "kpm": run.get("kpm"),
        "satisfied_threshold_seconds": run.get("satisfied_threshold_seconds"),
        "frustrated_threshold_seconds": run.get("frustrated_threshold_seconds"),
    }
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
        parts.append("<p>Sem configuração M25 persistida suficiente para comparação numérica.</p>")
    parts.append("<p class='muted'>Orientação derivada exclusivamente de dados persistidos "
                 "desta AUD. A configuração de uma nova auditoria não altera a AUD original.</p></div>")
    return "".join(parts)
