"""Final operator-facing refinements for selective AUD reprocessing.

This module is intentionally presentation/orchestration-only. It keeps the canonical
``audit_reprocess.reprocess_audit`` engine, fixes the final work-item preview semantics,
adds a selective pre-execution AI cost preview based on the same historical forecaster
used by normal processing, and keeps the operator on a complete post-run action surface.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

_AI_COMPONENTS = frozenset(
    {
        "SEMANTIC_AI",
        "TECHNICAL_AI",
        "CONTENT_REMEDIATION_AI",
        "IMPROVEMENT_INTELLIGENCE",
    }
)
_EXCLUDED_STATUSES = frozenset({"SUCCESS", "DISABLED", "NOT_APPLICABLE"})
_REPEAT_ATTR = "_rasai_repeat_reprocess"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def _work_item_preview(state: Any, audit_id: str) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Return only actionable pending items plus already successful required items."""
    try:
        from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, SUCCESS, list_work_items
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
        items = tuple(list_work_items(workspace, audit_id))
        successes = tuple(item for item in items if item.required and item.status == SUCCESS)
        pending = tuple(
            item
            for item in items
            if item.required and item.status not in {SUCCESS, DISABLED, NOT_APPLICABLE}
        )
        return pending, successes
    except (OSError, ValueError, RuntimeError):
        return (), ()


def _all_applicable_ai_items(state: Any, audit_id: str) -> tuple[Any, ...]:
    try:
        from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, list_work_items
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
        return tuple(
            item
            for item in list_work_items(workspace, audit_id)
            if item.required
            and str(item.component).upper() in _AI_COMPONENTS
            and item.status not in {DISABLED, NOT_APPLICABLE}
        )
    except (OSError, ValueError, RuntimeError):
        return ()


def _source_forecast_state(state: Any, audit_id: str) -> Any | None:
    """Build the minimal forecast state from the AUD's canonical secret-free snapshot."""
    try:
        from rasai.audit_configuration_reuse import KIND_CONSOLE, load_reusable_audit_configuration

        source = load_reusable_audit_configuration(
            state.audits_root,
            audit_id,
            expected_kind=KIND_CONSOLE,
        )
    except (FileNotFoundError, OSError, ValueError):
        return None

    configuration = source.configuration
    settings = configuration.get("settings")
    targets = configuration.get("targets")
    if not isinstance(settings, dict) or not isinstance(targets, list) or not targets:
        return None
    ai = settings.get("ai") if isinstance(settings.get("ai"), dict) else {}
    console = settings.get("console") if isinstance(settings.get("console"), dict) else {}
    environment = settings.get("environment") if isinstance(settings.get("environment"), dict) else {}
    clean_targets = tuple(str(item).strip() for item in targets if str(item).strip())
    if not clean_targets:
        return None
    try:
        max_pages = max(int(console.get("max_pages") or 1), len(clean_targets), 1)
    except (TypeError, ValueError):
        max_pages = max(len(clean_targets), 1)
    provider = str(ai.get("provider") or "none").strip().casefold()
    model = str(ai.get("model") or "").strip() or None
    return SimpleNamespace(
        ai_provider=provider,
        ai_model=model,
        content_remediation=_as_bool(ai.get("content_remediation")),
        technical_remediation=_as_bool(ai.get("technical_remediation")),
        improvement_enabled=_as_bool(environment.get("RASAI_IMPROVEMENT_INTELLIGENCE")),
        device=str(console.get("device") or "mobile").strip().casefold(),
        input_mode="url",
        target=clean_targets[0],
        max_pages=max_pages,
        audits_root=str(state.audits_root),
    )


def _scale_forecast(forecast: Any, *, pending_ai: int, total_ai: int) -> Any:
    """Scale the normal historical forecast to the unresolved AI share of this AUD."""
    if pending_ai <= 0 or total_ai <= 0:
        return forecast
    ratio = min(max(float(pending_ai) / float(total_ai), 0.0), 1.0)

    def scaled(value: float | None) -> float | None:
        return None if value is None else round(float(value) * ratio, 8)

    notes = tuple(
        dict.fromkeys(
            (
                *tuple(getattr(forecast, "notes", ()) or ()),
                (
                    "reprocessamento seletivo: valores monetários foram proporcionados ao escopo "
                    f"de IA ainda pendente ({pending_ai}/{total_ai} requisito(s) aplicável(is))"
                ),
            )
        )
    )
    return replace(
        forecast,
        success_baseline=scaled(forecast.success_baseline),
        expected=scaled(forecast.expected),
        likely_low=scaled(forecast.likely_low),
        likely_high=scaled(forecast.likely_high),
        potential=scaled(forecast.potential),
        source=f"{forecast.source}:selective-reprocess" if forecast.source else "selective-reprocess",
        notes=notes,
    )


def _money(value: float | None, currency: str | None) -> str:
    if value is None or not currency:
        return "-"
    return f"{currency} {value:.6f}"


def _render_reprocess_cost_preview(state: Any, audit_id: str, pending: tuple[Any, ...]) -> None:
    """Render an explicit pre-RPR AI cost preview without inventing unknown token usage."""
    pending_ai_items = tuple(
        item
        for item in pending
        if str(getattr(item, "component", "")).upper() in _AI_COMPONENTS
        and str(getattr(item, "status", "")).upper() not in _EXCLUDED_STATUSES
    )
    print("\nPRÉVIA DE CUSTO - REPROCESSAMENTO SELETIVO")
    print("-" * 100)
    if not pending_ai_items:
        print("Requisitos IA pendentes: 0")
        print("Custo IA incremental : 0 (nenhum requisito de IA será reexecutado nesta tentativa)")
        return

    all_ai_items = _all_applicable_ai_items(state, audit_id)
    total_ai = max(len(all_ai_items), len(pending_ai_items))
    print(f"Requisitos IA pendentes: {len(pending_ai_items)}/{total_ai} aplicável(is)")

    forecast_state = _source_forecast_state(state, audit_id)
    if forecast_state is None:
        print("Custo monetário       : não estimável antes da tentativa")
        print("Motivo                 : snapshot canônico da configuração original indisponível/incompatível")
        print("Observação             : nenhuma quantidade de tokens ou preço desconhecido foi inventado")
        return

    print(
        "Configuração IA      : "
        f"{forecast_state.ai_provider} / {forecast_state.ai_model or '<modelo efetivo/default>'}"
    )
    from rasai.cost_forecast import forecast_local_cost

    forecast = _scale_forecast(
        forecast_local_cost(forecast_state),
        pending_ai=len(pending_ai_items),
        total_ai=total_ai,
    )
    if not forecast.show_confirmation or forecast.expected is None or not forecast.currency:
        print("Custo monetário       : não estimável com segurança antes da tentativa")
        for note in tuple(forecast.notes or ())[:5]:
            print(f"Observação             : {note}")
        print("Após a tentativa, tokens e custo técnico persistido serão exibidos quando disponíveis.")
        return

    print(
        "Base histórica       : "
        f"{forecast.sample_runs} execução(ões), {forecast.sample_calls} chamada(s) com custo conhecido"
    )
    print(f"Custo só sucessos     : {_money(forecast.success_baseline, forecast.currency)}")
    print(f"Custo esperado        : {_money(forecast.expected, forecast.currency)}")
    print(
        "Faixa provável       : "
        f"{_money(forecast.likely_low, forecast.currency)} - "
        f"{_money(forecast.likely_high, forecast.currency)}"
    )
    print(f"Cenário potencial     : {_money(forecast.potential, forecast.currency)}")
    print(f"Confiança             : {forecast.confidence}")
    print(
        "Critério             : mesmo histórico/preço canônico da execução normal, proporcional "
        "somente aos requisitos de IA ainda pendentes"
    )
    print("Observação             : estimativa técnica; não representa invoice/fatura do provider")


def render_reprocess_preparation(
    console_module: ModuleType,
    state: Any,
    audit_id: str,
    pending: tuple[Any, ...],
    successes: tuple[Any, ...],
) -> None:
    """Render preparation, selective cost preview and explicit confirm/cancel actions."""
    from rasai import console_navigation
    from rasai import console_reprocess_parity as parity
    from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, list_work_items
    from rasai.persistence import AuditWorkspace

    audit_root = Path(state.audits_root) / audit_id
    summary = console_navigation._safe_summary(audit_root, audit_id)
    excluded = 0
    try:
        workspace = AuditWorkspace.open(audit_root)
        excluded = sum(
            1
            for item in list_work_items(workspace, audit_id)
            if item.required and item.status in {DISABLED, NOT_APPLICABLE}
        )
    except (OSError, ValueError, RuntimeError):
        excluded = 0

    console_module.render_header(state)
    print("INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA\n")
    print("PREPARAR REPROCESSAMENTO")
    print("-" * 100)
    print(f"AUD                  : {audit_id}")
    print(f"Situação atual       : {parity._friendly_status(summary.get('processing_status'))}")
    if summary:
        print(
            "Requisitos           : "
            f"{summary.get('successful_items', 0)}/{summary.get('required_items', 0)} atendidos"
        )
    print(f"Pendentes/bloqueados : {len(pending)}")
    print(f"Sucessos preservados : {len(successes)}")
    if excluded:
        print(f"Não aplicáveis       : {excluded} (fora da fila de reprocessamento)")

    print("\nESCOPO DESTA TENTATIVA")
    print("-" * 100)
    if pending:
        for item in pending[:30]:
            print(
                f"- {item.component}/{item.scope_key}: "
                f"{parity._friendly_status(getattr(item, 'status', ''))}"
            )
            reason = parity._reason_text(item)
            if reason != "motivo específico não persistido":
                print(f"  Motivo              : {reason}")
        if len(pending) > 30:
            print(f"- ... e mais {len(pending) - 30} requisito(s) pendente(s)")
    else:
        print("Nenhum requisito aplicável está pendente para nova tentativa.")

    print("\nCOMPORTAMENTO")
    print("-" * 100)
    print("- resultados já bem-sucedidos permanecem preservados e não são repetidos por padrão")
    print("- itens DISABLED/NOT_APPLICABLE ficam fora da fila e não contam como pendência")
    print("- chamadas externas/IA ocorrem apenas quando o requisito realmente precisar ser recuperado")
    print("- consumo adicional desta tentativa e consumo acumulado do AUD aparecem ao final")

    _render_reprocess_cost_preview(state, audit_id, pending)

    print("\nAÇÕES")
    print("C. Confirmar e iniciar reprocessamento")
    print("V. Voltar sem reprocessar")


def _can_repeat(unresolved: tuple[Any, ...]) -> bool:
    return any(
        bool(getattr(item, "required", True))
        and bool(getattr(item, "retryable", False))
        and str(getattr(item, "status", "")).upper() not in _EXCLUDED_STATUSES
        for item in unresolved
    )


def _run_post_actions(
    console_module: ModuleType,
    state: Any,
    *,
    result: Any,
    unresolved: tuple[Any, ...],
    before_usage: Any | None,
    after_usage: Any | None,
) -> None:
    """Keep result, cost, remaining errors and all contextual actions on one screen."""
    from rasai import console_reprocess_parity as parity
    from rasai.console_artifacts import artifact_status
    from rasai.console_ui import availability_badge

    normal_usage = getattr(console_module, "_render_actual_usage", None)
    artifact_action = getattr(console_module, "_artifact_action", None)
    confirm_exit = getattr(console_module, "_confirm_exit", None)

    while True:
        console_module.render_header(state)
        workspace, report = artifact_status(state)
        if getattr(state, "audit_id", ""):
            print(f"Audit ID    : {state.audit_id}")
        parity.render_reprocess_result(result, unresolved)
        parity._render_reprocess_usage_delta(before_usage, after_usage)
        if callable(normal_usage):
            print("\nCONSUMO ACUMULADO DO AUD APÓS O REPROCESSAMENTO")
            normal_usage(state)

        repeatable = _can_repeat(unresolved)
        print("\nAÇÕES DO REPROCESSAMENTO")
        if repeatable:
            print(" R. Reprocessar novamente somente as pendências ainda recuperáveis")
        elif unresolved:
            print(" R. Reprocessar novamente [INDISPONÍVEL — não há pendência com retry automático]")
        print(f" P. Abrir pasta da auditoria [{availability_badge(bool(workspace))}]")
        print(f" I. Abrir relatório HTML   [{availability_badge(bool(report))}]")
        print(" V. Voltar para a auditoria selecionada")
        print(" Q. Sair")
        choice = input("Escolha: ").strip().upper()

        if choice == "R":
            if repeatable:
                setattr(state, _REPEAT_ATTR, True)
                return
            state.error = "não há pendência recuperável para novo reprocessamento"
            continue
        if choice == "V":
            return
        if choice == "Q":
            if callable(confirm_exit) and confirm_exit(state):
                raise SystemExit(0)
            continue
        if choice == "P":
            if workspace and callable(artifact_action):
                artifact_action(state, "P")
            else:
                state.error = "pasta da auditoria ainda não disponível"
            continue
        if choice == "I":
            if report and callable(artifact_action):
                artifact_action(state, "I")
            else:
                state.error = "relatório HTML ainda não disponível"
            continue
        state.error = "opção inválida; use R, P, I, V ou Q"


def _reprocess_selected(console_module: ModuleType, state: Any, audit_id: str) -> None:
    """Allow another RPR directly from the result screen without losing context."""
    from rasai import console_reprocess_parity as parity

    while True:
        setattr(state, _REPEAT_ATTR, False)
        parity.reprocess_selected(console_module, state, audit_id)
        if not bool(getattr(state, _REPEAT_ATTR, False)):
            return


def install(console_module: ModuleType) -> None:
    """Install last, after history/usability overlays, as the final RPR UX owner."""
    if getattr(console_module, "_rasai_reprocess_final_refinements", False):
        return
    from rasai import console_navigation as navigation
    from rasai import console_reprocess_parity as parity
    from rasai import console_usability_refinements as usability

    navigation._work_item_preview = _work_item_preview
    parity.render_reprocess_preparation = render_reprocess_preparation
    parity._run_post_actions = _run_post_actions
    navigation._reprocess_selected = _reprocess_selected
    usability._reprocess_selected = _reprocess_selected
    console_module._rasai_reprocess_final_refinements = True
