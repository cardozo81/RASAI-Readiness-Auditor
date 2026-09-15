"""Final operator-facing refinements for selective AUD reprocessing.

This module owns the final console UX for selective reprocessing. It keeps the canonical
``audit_reprocess.reprocess_audit`` engine, excludes terminal/non-applicable work from the
retry queue, presents an explicit pre-run AI cost forecast, and guarantees immediate
operator feedback after confirmation even when the RPR completes quickly.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
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
_REPEAT_REQUESTED: ContextVar[bool] = ContextVar("rasai_repeat_reprocess_requested", default=False)
_CURRENT_AUDIT_ID: ContextVar[str] = ContextVar("rasai_current_reprocess_audit_id", default="")
_WIDTH = 100
_LABEL_WIDTH = 22
_VALUE_WIDTH = _WIDTH - _LABEL_WIDTH - 3


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * _WIDTH)


def _field(label: str, value: Any) -> None:
    print(f"{label:<{_LABEL_WIDTH}} : {value}")


def _wrapped_field(label: str, value: Any) -> None:
    text = str(value or "-").strip() or "-"
    lines = wrap(text, width=_VALUE_WIDTH, break_long_words=False, break_on_hyphens=False) or ["-"]
    print(f"{label:<{_LABEL_WIDTH}} : {lines[0]}")
    continuation = " " * (_LABEL_WIDTH + 3)
    for line in lines[1:]:
        print(f"{continuation}{line}")


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
    reasoning = str(ai.get("reasoning") or ai.get("reasoning_effort") or "").strip() or None
    return SimpleNamespace(
        ai_provider=provider,
        ai_model=model,
        ai_reasoning=reasoning,
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


def _catalog_fallback_estimate(
    forecast_state: Any,
    pending_ai_items: tuple[Any, ...],
) -> tuple[float, str, int, int, str] | None:
    """Estimate explicit-provider RPR cost from canonical pricing when history is absent."""
    selection = str(getattr(forecast_state, "ai_provider", "none") or "none").strip().casefold()
    if selection in {"none", "auto"}:
        return None

    from rasai.ai_cost_policy import estimate_candidate_cost
    from rasai.provider_registry import get_provider_registration

    registration = get_provider_registration(selection)
    provider_name = registration.provider_name if registration is not None else selection.upper()
    model = str(getattr(forecast_state, "ai_model", "") or "").strip()
    if not model and registration is not None:
        model = str(registration.default_model or "").strip()
    if not provider_name or not model:
        return None

    provider = SimpleNamespace(
        name=provider_name,
        model=model,
        reasoning_profile=str(getattr(forecast_state, "ai_reasoning", "") or "PROVIDER_DEFAULT"),
    )
    scope_by_component = {
        "SEMANTIC_AI": "SEMANTIC",
        "TECHNICAL_AI": "M24_TECHNICAL_REMEDIATION",
        "CONTENT_REMEDIATION_AI": "CONTENT_REMEDIATION",
        "IMPROVEMENT_INTELLIGENCE": "CONSOLIDATED_SPECIALIST",
    }
    total = 0.0
    currency: str | None = None
    input_tokens = 0
    output_tokens = 0
    contexts: list[str] = []
    now = datetime.now(timezone.utc)
    for item in pending_ai_items:
        scope = scope_by_component.get(str(getattr(item, "component", "")).upper(), "SEMANTIC")
        estimate = estimate_candidate_cost(provider, None, scope=scope, at=now)
        if estimate.estimated_cost is None or not estimate.currency:
            return None
        if currency is None:
            currency = estimate.currency
        elif currency != estimate.currency:
            return None
        total += float(estimate.estimated_cost)
        input_tokens += int(estimate.estimated_input_tokens)
        output_tokens += int(estimate.estimated_output_tokens)
        if estimate.pricing_context:
            contexts.append(str(estimate.pricing_context))
    if currency is None:
        return None
    context = ", ".join(dict.fromkeys(contexts)) or "STANDARD"
    return round(total, 10), currency, input_tokens, output_tokens, context


def _render_reprocess_cost_preview(state: Any, audit_id: str, pending: tuple[Any, ...]) -> None:
    """Render a truthful pre-RPR AI cost preview, with catalog fallback when needed."""
    pending_ai_items = tuple(
        item
        for item in pending
        if str(getattr(item, "component", "")).upper() in _AI_COMPONENTS
        and str(getattr(item, "status", "")).upper() not in _EXCLUDED_STATUSES
    )
    _section("PREVISÃO DE CUSTO DE IA")
    if not pending_ai_items:
        _field("Requisitos IA", "0")
        _field("Previsão", "NÃO APLICÁVEL")
        _field("Custo incremental", "0 (nenhuma chamada de IA prevista nesta tentativa)")
        return

    all_ai_items = _all_applicable_ai_items(state, audit_id)
    total_ai = max(len(all_ai_items), len(pending_ai_items))
    _field("Requisitos IA", f"{len(pending_ai_items)}/{total_ai} pendente(s)")

    forecast_state = _source_forecast_state(state, audit_id)
    if forecast_state is None:
        _field("Previsão", "INDISPONÍVEL")
        _wrapped_field("Motivo", "snapshot canônico da configuração original indisponível ou incompatível")
        _wrapped_field("Segurança", "nenhum custo ou volume de tokens desconhecido será inventado")
        return

    _field(
        "Configuração do AUD",
        f"{forecast_state.ai_provider} / {forecast_state.ai_model or '<modelo efetivo/default>'}",
    )
    from rasai.cost_forecast import forecast_local_cost

    forecast = _scale_forecast(
        forecast_local_cost(forecast_state),
        pending_ai=len(pending_ai_items),
        total_ai=total_ai,
    )
    if forecast.show_confirmation and forecast.expected is not None and forecast.currency:
        _field("Previsão", "HISTÓRICA")
        _field("Base histórica", f"{forecast.sample_runs} execução(ões) / {forecast.sample_calls} chamada(s)")
        _field("Custo só sucessos", _money(forecast.success_baseline, forecast.currency))
        _field("Custo esperado", _money(forecast.expected, forecast.currency))
        _field(
            "Faixa provável",
            f"{_money(forecast.likely_low, forecast.currency)} - {_money(forecast.likely_high, forecast.currency)}",
        )
        _field("Cenário potencial", _money(forecast.potential, forecast.currency))
        _field("Confiança", forecast.confidence)
        _wrapped_field(
            "Critério",
            "histórico financeiro comparável e pricing vigente, proporcional somente aos requisitos de IA pendentes",
        )
        return

    catalog = _catalog_fallback_estimate(forecast_state, pending_ai_items)
    if catalog is not None:
        amount, currency, input_tokens, output_tokens, context = catalog
        _field("Previsão", "CATÁLOGO / BAIXA CONFIANÇA")
        _field("Custo estimado", _money(amount, currency))
        _field("Tokens estimados", f"entrada={input_tokens} | saída={output_tokens}")
        _field("Contexto de preço", context)
        _wrapped_field(
            "Base",
            "pricing canônico vigente e orçamento estático de tokens por escopo; usado somente porque não há histórico financeiro comparável",
        )
        _wrapped_field("Limite", "estimativa técnica de pré-execução; não representa invoice/fatura do provider")
        return

    _field("Previsão", "SEM VALOR MONETÁRIO CONFIÁVEL")
    notes = tuple(forecast.notes or ())
    _wrapped_field("Motivo", notes[0] if notes else "não há base financeira comparável para estimar esta tentativa")
    if str(forecast_state.ai_provider).casefold() == "auto":
        _wrapped_field("Contexto", "AI=auto pode escolher provider/modelo diferente; sem histórico comparável não há valor único seguro antes do roteamento")
    _wrapped_field("Após executar", "tokens e custo técnico persistido serão exibidos quando disponíveis")


def render_reprocess_preparation(
    console_module: ModuleType,
    state: Any,
    audit_id: str,
    pending: tuple[Any, ...],
    successes: tuple[Any, ...],
) -> None:
    """Render a compact, hierarchical preparation screen with explicit cost semantics."""
    from rasai import console_navigation
    from rasai import console_reprocess_parity as parity
    from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, list_work_items
    from rasai.persistence import AuditWorkspace

    _CURRENT_AUDIT_ID.set(audit_id)
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
    print("INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA")
    print("\nPREPARAR REPROCESSAMENTO")
    print("=" * _WIDTH)
    _field("AUD", audit_id)
    _field("Situação", parity._friendly_status(summary.get("processing_status")))
    if summary:
        _field(
            "Requisitos",
            f"{summary.get('successful_items', 0)}/{summary.get('required_items', 0)} atendidos",
        )
    _field("Pendências a tentar", len(pending))
    _field("Sucessos preservados", len(successes))
    _field("Fora da fila", f"{excluded} não aplicável(is)/desabilitado(s)")

    _section("PENDÊNCIAS DESTA TENTATIVA")
    if pending:
        for index, item in enumerate(pending[:30], start=1):
            component = f"{item.component} / {item.scope_key}"
            print(f"{index:>2}. {component}")
            _wrapped_field("    Status", parity._friendly_status(getattr(item, "status", "")))
            reason = parity._reason_text(item)
            if reason != "motivo específico não persistido":
                _wrapped_field("    Motivo", reason)
            if index != min(len(pending), 30):
                print()
        if len(pending) > 30:
            print(f"... e mais {len(pending) - 30} requisito(s) pendente(s)")
    else:
        print("Nenhum requisito aplicável está pendente para nova tentativa.")

    _section("REGRAS DESTA TENTATIVA")
    print("- sucessos anteriores são preservados e não são executados novamente por padrão")
    print("- itens DISABLED/NOT_APPLICABLE ficam fora da fila")
    print("- chamadas externas/IA só ocorrem para requisitos que realmente precisarem de recuperação")
    print("- consumo adicional e consumo acumulado do AUD aparecem ao final")

    _render_reprocess_cost_preview(state, audit_id, pending)

    _section("AÇÕES")
    print(" C. Confirmar e iniciar reprocessamento")
    print(" V. Voltar sem reprocessar")


def _confirm_reprocess_with_feedback(console_module: ModuleType, state: Any) -> bool:
    """Require an explicit choice and render the execution surface immediately on C."""
    from rasai import console_runtime

    while True:
        choice = input("Escolha [C/V]: ").strip().upper()
        if choice == "C":
            audit_id = _CURRENT_AUDIT_ID.get()
            if audit_id and hasattr(state, "audit_id"):
                state.audit_id = audit_id
            state.status = "REPROCESSING"
            state.operation = "LOCAL:AUD_REPROCESS"
            state.error = ""
            console_runtime.set_runtime_progress(
                state,
                "Preparando reprocessamento",
                0.0,
                detail="confirmação recebida; iniciando os requisitos pendentes",
                exact=False,
            )
            console_module.render_header(state)
            print("REPROCESSAMENTO EM EXECUÇÃO")
            print("-" * _WIDTH)
            if audit_id:
                _field("AUD", audit_id)
                _field("Log técnico", Path(state.audits_root) / audit_id / "logs" / "audit.log")
            print("A execução foi iniciada. Esta tela será atualizada automaticamente.")
            return True
        if choice in {"V", "Q"}:
            state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
            state.error = ""
            _CURRENT_AUDIT_ID.set("")
            return False
        print("Opção inválida. Use C para confirmar ou V para voltar.")


def _render_live_frame(console_module: ModuleType, state: Any, audit_root: Path) -> None:
    """Render the same progress header as processing plus explicit RPR context."""
    console_module.render_header(state)
    if str(getattr(state, "status", "")).upper() == "REPROCESSING":
        print("REPROCESSAMENTO EM EXECUÇÃO")
        print("-" * _WIDTH)
    if getattr(state, "audit_id", ""):
        _field("Audit ID", state.audit_id)
    _field("Log técnico", audit_root / "logs" / "audit.log")


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
                _REPEAT_REQUESTED.set(True)
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
        token = _REPEAT_REQUESTED.set(False)
        try:
            parity.reprocess_selected(console_module, state, audit_id)
            repeat_requested = _REPEAT_REQUESTED.get()
        finally:
            _REPEAT_REQUESTED.reset(token)
        if not repeat_requested:
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
    parity._confirm_reprocess = lambda state: _confirm_reprocess_with_feedback(console_module, state)
    parity._render_live_frame = _render_live_frame
    parity._run_post_actions = _run_post_actions
    navigation._reprocess_selected = _reprocess_selected
    usability._reprocess_selected = _reprocess_selected
    console_module._rasai_reprocess_final_refinements = True
