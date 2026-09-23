"""Fluxo interativo do relatório consolidado longitudinal."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable

from rasai.console_ui import (
    CYAN,
    GRAY,
    GREEN,
    RED,
    YELLOW,
    paint,
    semantic_text,
    title_text,
)
from rasai.execution_progress_presentation import render_canonical_progress
from .index import ConsolidationIndex
from .presentation import specialist_usage_summary
from .selection import (
    AuditCandidate,
    candidate_audits,
    compatible_candidates,
    list_consolidated_history,
    resolve_selection,
)
from .service import find_reusable, generate, normalize_filter
from .specialist import SpecialistPreview, prepare_longitudinal_specialist, preview_longitudinal_specialist


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _pause() -> None:
    input("\nENTER para continuar...")


def _open(path: Path) -> tuple[bool, str]:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.name == "posix":
            command = ["open", str(path)] if os.uname().sysname == "Darwin" else ["xdg-open", str(path)]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return False, str(path)
        return True, str(path)
    except OSError as exc:
        return False, f"{path}: {exc}"


def _print_preview(preview: SpecialistPreview, selection: str) -> None:
    print("\nPRÉVIA DE CUSTO - ANÁLISE LONGITUDINAL POR IA\n")
    print(f"Marco inicial: {preview.baseline_audit_id or '-'}")
    print(f"Marco final  : {preview.current_audit_id or '-'}")
    print(f"Eventos      : {preview.event_count} evento(s) direcionais")
    print(f"Seleção IA   : {selection.upper()}")
    print(f"Elegíveis    : {len(preview.candidates)} provedor(es)")
    print(f"Fallback     : {'disponível' if len(preview.candidates) > 1 else 'não disponível'}")
    if preview.excluded_candidates:
        print(f"Excluídos    : {len(preview.excluded_candidates)} configuração(ões)")
    if not preview.available or preview.selected is None:
        print(f"Estado       : indisponível ({preview.reason or 'sem candidato'})")
        return
    selected = preview.selected
    cost = (
        f"{selected.estimated_cost:.8f} {selected.currency}"
        if selected.estimated_cost is not None and selected.currency
        else "não determinável pelo catálogo de preços atual"
    )
    print(f"Provedor     : {selected.provider}")
    print(f"Modelo       : {selected.model}")
    print(f"Raciocínio   : {selected.reasoning_profile}")
    print(
        "Tokens       : "
        f"entrada aproximada {selected.estimated_input_tokens} | "
        f"saída aproximada {selected.estimated_output_tokens}"
    )
    projection = preview.context_projection or {}
    if projection:
        print(
            "Contexto IA  : "
            f"{projection.get('level') or '-'} | "
            f"{projection.get('estimated_input_tokens') or '-'} tokens estimados "
            f"(limite {projection.get('max_input_hint_tokens') or '-'})"
        )
        print("Evidência    : integral local; somente a projeção compacta é enviada ao provider")
    print(f"Tarifa       : {selected.pricing_context or '-'} | {selected.pricing_version}")
    print(f"Estimativa   : {cost}")
    forecast = preview.forecast or {}
    if forecast.get("likely_high") is not None and forecast.get("currency"):
        print(f"1ª rodada máx.: {forecast['currency']} {float(forecast['likely_high']):.8f}")
    if forecast.get("potential") is not None and forecast.get("currency"):
        print(
            f"Cenário retry: {forecast['currency']} {float(forecast['potential']):.8f} "
            f"(até {forecast.get('max_rounds', 2)} rodadas)"
        )
    print(
        "Observação   : estimativa anterior à chamada; pode variar conforme uso real, "
        "cache, fallback, retry e política do provedor."
    )


def _print_ai_usage(report_dir: Path) -> None:
    print("\nUSO E CUSTO DA IA NESTE CONSOLIDADO")
    print("-" * 88)
    usage = specialist_usage_summary(report_dir)
    if usage is None:
        print("IA não utilizada ou telemetria não materializada para este consolidado.")
        return
    status_label = {
        "COMPLETE": "Concluída",
        "UNAVAILABLE": "Indisponível",
        "NO_DATA": "Sem dados elegíveis",
        "NOT_REQUESTED": "Não solicitada",
    }.get(usage.status.upper(), usage.status)
    print("Estado               : " + semantic_text(status_label, bold=True))
    print(f"Tentativas de IA     : {usage.attempts} (sucesso: {usage.successes})")
    print(f"Tokens de entrada    : {usage.input_tokens:,}")
    print(f"Tokens de cache      : {usage.cached_input_tokens:,}")
    print(f"Tokens de saída      : {usage.output_tokens:,}")
    print(f"Tokens de raciocínio : {usage.reasoning_tokens:,}")
    print(f"Tokens total         : {usage.total_tokens:,}")
    if usage.costs:
        print("Custo IA estimado    : " + " | ".join(
            f"{currency} {amount:.8f}" for currency, amount in usage.costs
        ))
    elif usage.attempts:
        print("Custo IA estimado    : não disponível com preços/tokens retornados")
    else:
        print("Custo IA estimado    : zero - nenhuma chamada executada")


def _short_url(value: str, limit: int = 62) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _local_timestamp(value: str | None) -> str:
    from rasai.console_usability_refinements import _local_timestamp as local_timestamp

    return local_timestamp(value)


def _friendly_status(value: str | None) -> str:
    from rasai.console_usability_refinements import _friendly_status as friendly_status

    return friendly_status(value)


def _candidate_summary(root: Path, item: AuditCandidate) -> dict[str, Any]:
    from rasai.console_usability_refinements import _safe_summary

    return _safe_summary(root / item.audit_id, item.audit_id)


def _candidate_eligible(root: Path, item: AuditCandidate) -> bool:
    return bool(_candidate_summary(root, item).get("consolidation_eligible"))


def _candidate_status(root: Path, item: AuditCandidate) -> tuple[str, str]:
    summary = _candidate_summary(root, item)
    raw = str(
        summary.get("processing_status")
        or item.completion_status
        or item.status
        or "UNKNOWN"
    ).upper()
    return raw, _friendly_status(raw)


def _state_color(raw: str) -> str:
    normalized = str(raw or "").upper()
    if normalized in {"COMPLETE", "COMPLETED", "SUCCESS", "FINAL", "READY"}:
        return GREEN
    if any(token in normalized for token in ("FAIL", "ERROR", "BLOCK", "EXPIRED")):
        return RED
    if any(token in normalized for token in ("PARTIAL", "WAIT", "PENDING", "RETRY", "LIMIT")):
        return YELLOW
    if any(token in normalized for token in ("PROCESS", "RUNNING", "START", "ANALYZ")):
        return CYAN
    return GRAY


def _eligibility_label(eligible: bool) -> str:
    return "SIM" if eligible else "NÃO"


def _selected_audit_label(root: Path, item: AuditCandidate) -> str:
    eligible = _candidate_eligible(root, item)
    return paint(
        f"{item.audit_id} | {_local_timestamp(item.event_time)}",
        GREEN if eligible else YELLOW,
        bold=True,
    )


def _candidate_by_id(values: Iterable[AuditCandidate], audit_id: str) -> AuditCandidate | None:
    return next((item for item in values if item.audit_id == audit_id), None)


def _candidate_table(
    values: Iterable[AuditCandidate],
    audits_root: Path,
    *,
    selected_ids: Iterable[str] = (),
) -> None:
    material = tuple(values)
    selected = {str(value) for value in selected_ids}
    audit_width = max(36, min(44, max((len(item.audit_id) for item in material), default=36)))
    print(
        f"{'Nº':>3} {'AUDITORIA':<{audit_width}}  {'DATA/HORA LOCAL':<16}  "
        f"{'SITUAÇÃO':<27}  {'DISPOSITIVO':<17}  {'ELEGÍVEL':<9}  DOMÍNIO"
    )
    print(
        f"{'---':>3} {'-' * audit_width}  {'-' * 16}  "
        f"{'-' * 27}  {'-' * 17}  {'-' * 9}  {'-' * 24}"
    )
    for pos, item in enumerate(material, 1):
        raw_status, friendly = _candidate_status(audits_root, item)
        eligible = _candidate_eligible(audits_root, item)
        eligibility_color = GREEN if eligible else YELLOW
        number = paint(f"{pos:>2}.", eligibility_color, bold=True)
        audit_cell = f"{item.audit_id:<{audit_width}}"
        if item.audit_id in selected:
            audit_cell = paint(audit_cell, eligibility_color, bold=True)
        status_cell = paint(f"{friendly[:27]:<27}", _state_color(raw_status))
        eligible_cell = paint(f"{_eligibility_label(eligible):<9}", eligibility_color, bold=True)
        print(
            f"{number} {audit_cell}  {_local_timestamp(item.event_time):<16}  "
            f"{status_cell}  {item.device:<17}  {eligible_cell}  {item.domain or '-'}"
        )
    print(
        "\nElegibilidade: "
        + paint("SIM = fonte conclusiva", GREEN, bold=True)
        + " | "
        + paint("NÃO = fonte não conclusiva quando o contrato permitir", YELLOW, bold=True)
    )


def _choose_candidate(
    title: str,
    values: tuple[AuditCandidate, ...],
    *,
    audits_root: Path,
    context: tuple[str, ...] = (),
    selected_ids: Iterable[str] = (),
) -> AuditCandidate | None:
    query = ""
    while True:
        filtered = values
        if query:
            needle = query.casefold()
            filtered = tuple(
                item for item in values
                if needle in " ".join(
                    (item.audit_id, item.url, item.domain, item.device, item.event_time)
                ).casefold()
            )
        _clear()
        print(title_text(title) + "\n")
        for line in context:
            print(line)
        if context:
            print()
        if not filtered:
            print("Nenhuma auditoria encontrada para a pesquisa atual.")
        else:
            _candidate_table(filtered, audits_root, selected_ids=selected_ids)
        print("\nP. Pesquisar por ID, domínio/URL ou dispositivo")
        if query:
            print("L. Limpar pesquisa")
        print("V. Voltar")
        raw = input("Escolha: ").strip()
        upper = raw.upper()
        if upper == "V":
            return None
        if upper == "P":
            new_query = input("Pesquisa por ID, domínio/URL ou dispositivo [V=voltar]: ").strip()
            if new_query.upper() == "V":
                continue
            query = new_query
            continue
        if upper == "L" and query:
            query = ""
            continue
        try:
            return filtered[int(raw) - 1]
        except (ValueError, IndexError):
            continue


def _manual_intermediates(
    candidates: tuple[AuditCandidate, ...],
    baseline_id: str,
    current_id: str,
    *,
    audits_root: Path,
) -> tuple[str, ...] | None:
    intermediates = tuple(
        item for item in sorted(candidates, key=lambda value: (value.event_time, value.audit_id))
        if item.audit_id not in {baseline_id, current_id}
    )
    if not intermediates:
        return ()
    while True:
        _clear()
        print(title_text("CONSOLIDADOS > GERAR > SELEÇÃO MANUAL") + "\n")
        baseline = _candidate_by_id(candidates, baseline_id)
        current = _candidate_by_id(candidates, current_id)
        print(
            "BASE : "
            + (_selected_audit_label(audits_root, baseline) if baseline is not None else baseline_id)
        )
        print(
            "ATUAL: "
            + (_selected_audit_label(audits_root, current) if current is not None else current_id)
            + "\n"
        )
        _candidate_table(intermediates, audits_root)
        print("\nInforme os números separados por vírgula.")
        print("Vazio = nenhum intermediário. V = voltar.")
        raw = input("Intermediárias: ").strip()
        if raw.upper() == "V":
            return None
        if not raw:
            return ()
        try:
            positions = {
                int(value.strip())
                for value in raw.split(",")
                if value.strip()
            }
        except ValueError:
            continue
        if any(value < 1 or value > len(intermediates) for value in positions):
            continue
        return tuple(intermediates[value - 1].audit_id for value in sorted(positions))


def _selection_policy(
    index: ConsolidationIndex,
    first: AuditCandidate,
    second: AuditCandidate,
) -> tuple[str, tuple[str, ...]] | None:
    initial = resolve_selection(index, first.audit_id, second.audit_id, selection_mode="ALL")
    if initial.intermediate_count == 0:
        return "ALL", ()
    interval_ids = set(initial.audit_ids)
    compatible = tuple(
        item for item in candidate_audits(index)
        if item.audit_id in interval_ids
    )
    while True:
        _clear()
        print(title_text("CONSOLIDADOS > GERAR > AUDITORIAS DO INTERVALO") + "\n")
        print(f"URL          : {initial.url}")
        print(f"Dispositivo  : {initial.device}")
        baseline_candidate = first if first.audit_id == initial.baseline_audit_id else second
        current_candidate = first if first.audit_id == initial.current_audit_id else second
        print("BASE         : " + _selected_audit_label(index.audits_root, baseline_candidate))
        print("ATUAL        : " + _selected_audit_label(index.audits_root, current_candidate))
        print(f"Intermediárias: {initial.intermediate_count}")
        print("Regra temporal : BASE = menor data/hora; ATUAL = maior data/hora")
        print("                 a ordem escolhida nas telas anteriores não altera esses papéis.\n")
        print("1. Incluir todas as auditorias elegíveis do intervalo")
        print("2. Incluir somente auditorias concluídas com sucesso")
        print("3. Selecionar manualmente auditorias intermediárias")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw == "1":
            return "ALL", ()
        if raw == "2":
            return "SUCCESS_ONLY", ()
        if raw == "3":
            manual = _manual_intermediates(
                compatible,
                initial.baseline_audit_id,
                initial.current_audit_id,
                audits_root=index.audits_root,
            )
            if manual is not None:
                return "MANUAL", manual


def _choose_ai_mode(
    *,
    audits_root: Path | None = None,
    ai_provider: str,
    ai_available: bool,
    ai_unavailable_reason: str | None,
    preview: SpecialistPreview | None,
    selected: Any,
    recognition: dict[str, int],
    ai_reusable: bool = False,
    preview_error: str | None = None,
) -> bool | None:
    """Final generation choice: selecting a mode starts the non-destructive operation."""
    while True:
        _clear()
        print(title_text("CONSOLIDADOS > GERAR > MODO DE GERAÇÃO") + "\n")
        print(title_text("RESUMO DAS ESCOLHAS"))
        print("-" * 100)
        print(f"URL                  : {selected.url}")
        print(f"Dispositivo          : {selected.device}")
        selected_by_id: dict[str, AuditCandidate] = {}
        if audits_root is not None:
            try:
                index = ConsolidationIndex(audits_root)
                selected_by_id = {
                    item.audit_id: item
                    for item in candidate_audits(index, allowed_audit_ids=selected.audit_ids)
                }
            except (OSError, ValueError, RuntimeError):
                selected_by_id = {}

        baseline = selected_by_id.get(selected.baseline_audit_id)
        current = selected_by_id.get(selected.current_audit_id)
        print(
            "BASE                 : "
            + (
                _selected_audit_label(audits_root, baseline)
                if audits_root is not None and baseline is not None
                else selected.baseline_audit_id
            )
        )
        print(
            "ATUAL                : "
            + (
                _selected_audit_label(audits_root, current)
                if audits_root is not None and current is not None
                else selected.current_audit_id
            )
        )
        selected_eligible = (
            sum(_candidate_eligible(audits_root, item) for item in selected_by_id.values())
            if audits_root is not None
            else 0
        )
        selected_non_eligible = (
            max(len(selected.audit_ids) - selected_eligible, 0)
            if audits_root is not None
            else 0
        )
        print(f"Auditorias selecionadas: {len(selected.audit_ids)}")
        if audits_root is not None:
            print(
                "Elegibilidade selecionada: "
                + paint(f"{selected_eligible} elegível(is)", GREEN, bold=True)
                + " | "
                + paint(f"{selected_non_eligible} não elegível(is)", YELLOW, bold=True)
            )
        print(f"Política de seleção  : {selected.selection_mode}")
        print(f"Reconhecidas         : {recognition.get('discovered', 0)}")
        print(f"Fontes disponíveis   : {recognition.get('available', recognition.get('eligible', 0))}")
        print(f"Elegíveis conclusivas: {recognition.get('eligible', 0)}")
        print(f"Não elegíveis        : {recognition.get('non_eligible', 0)}")
        print(f"Fora do conjunto     : {recognition.get('excluded', 0)}")

        if ai_reusable:
            print("\nPRÉVIA DE CUSTO - ANÁLISE LONGITUDINAL POR IA")
            print("-" * 100)
            print("Estado       : consolidado íntegro reutilizável")
            print("Nova chamada : NÃO")
            print("Custo novo IA: USD 0.000000")
        elif preview is not None:
            _print_preview(preview, ai_provider)
        else:
            print("\nPRÉVIA DE CUSTO - ANÁLISE LONGITUDINAL POR IA")
            print("-" * 100)
            reason = preview_error or ai_unavailable_reason or "provider não configurado"
            print(f"Estado       : indisponível ({reason})")

        availability = (
            "reuso disponível; sem nova chamada"
            if ai_reusable
            else "disponível"
            if preview is not None and preview.available and ai_provider.casefold() != "none"
            else "indisponível"
        )
        print("\n" + title_text("COMO GERAR O RELATÓRIO"))
        print("-" * 100)
        availability_color = GREEN if availability.startswith(("disponível", "reuso")) else YELLOW
        print(
            "1. Gerar relatório consolidado "
            + paint("com IA", YELLOW, bold=True)
            + " ["
            + paint(availability, availability_color, bold=True)
            + "]"
        )
        print("   Se a IA não estiver apta, o determinístico é preservado e a limitação fica materializada.")
        print("2. Gerar relatório consolidado " + paint("sem IA", GREEN, bold=True))
        print("   Modo determinístico; nenhuma chamada de IA será solicitada.")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw in {"1", "C"}:
            return True
        if raw in {"2", "N"}:
            return False
        print("\nOpção inválida. Use 1, 2 ou V.")

_CONSOLIDATED_PROGRESS_CONTEXT: dict[str, Any] = {}

_CONSOLIDATED_STAGE_FLOW = (
    "Reconhecendo auditorias",
    "Validando fontes e artefatos",
    "Preparando conjunto de análise",
    "Análise complementar / IA",
    "Gerando relatório",
    "Validação e conclusão",
)


def _render_progress(stage: str, status: str, message: str) -> None:
    """Render CONS progress with the same canonical grammar used by AUD/RPR."""
    logical_index = {
        "INDEX": 1,
        "PREPARING": 2,
        "PREPARED": 3,
        "AI": 4,
        "AI_FORECAST": 4,
        "AI_RUNNING": 4,
        "MATERIALIZING": 5,
        "COMPLETE": 6,
        "FAILED": 6,
    }.get(str(stage).upper(), 1)
    stage_key = str(stage).upper()
    status_key = str(status).upper()
    current_label = _CONSOLIDATED_STAGE_FLOW[logical_index - 1]
    previous = _CONSOLIDATED_STAGE_FLOW[logical_index - 2] if logical_index > 1 else None
    following = _CONSOLIDATED_STAGE_FLOW[logical_index] if logical_index < len(_CONSOLIDATED_STAGE_FLOW) else None
    current_status = {
        "COMPLETE": "CONCLUÍDA",
        "REUSED": "REUTILIZADA",
        "READY": "PRONTA",
        "NOT_REQUESTED": "NÃO SOLICITADA",
        "NOT_CONFIGURED": "NÃO CONFIGURADA",
        "UNAVAILABLE": "INDISPONÍVEL",
        "FAILED": "FALHA",
    }.get(status_key, "EM EXECUÇÃO")

    overall_projection = {
        1: 8.0,
        2: 22.0,
        3: 40.0,
        4: 65.0 if stage_key == "AI_RUNNING" else 52.0,
        5: 88.0,
        6: 100.0,
    }[logical_index]
    overall_exact = logical_index == 6 and status_key in {"COMPLETE", "REUSED"}
    stage_percent = 100.0 if status_key in {
        "COMPLETE", "REUSED", "READY", "NOT_REQUESTED", "NOT_CONFIGURED", "UNAVAILABLE"
    } else None
    stage_exact = stage_percent is not None

    details: list[tuple[str, Any]] = []
    context = _CONSOLIDATED_PROGRESS_CONTEXT
    if context.get("selected_count") is not None:
        details.append(("Auditorias do conjunto", str(context["selected_count"])))
    if context.get("excluded_count") is not None:
        details.append(("Auditorias fora do conjunto", str(context["excluded_count"])))
    if context.get("source_databases") is not None:
        details.append(("Fontes audit.db", str(context["source_databases"])))
    details.append(("Estado", current_status))

    if stage_key in {"AI", "AI_FORECAST", "AI_RUNNING"}:
        details.append(("Modo", "Com IA" if context.get("use_ai") else "Sem IA"))
        if context.get("ai_provider"):
            details.append(("Provider", str(context["ai_provider"]).upper()))
        if context.get("ai_model"):
            details.append(("Modelo", str(context["ai_model"])))
        preview = context.get("preview")
        selected = getattr(preview, "selected", None) if preview is not None else None
        if selected is not None:
            estimated = (
                f"{selected.currency} {selected.estimated_cost:.8f}"
                if selected.estimated_cost is not None and selected.currency
                else "não determinável"
            )
            details.append(("Custo previsto IA", estimated))

    if stage_key == "MATERIALIZING":
        details.extend((
            ("Fonte", "somente dados/evidências já persistidos"),
            ("Subprocesso", "consolidar dados / renderizar HTML / gravar artefatos"),
            ("Nova coleta da URL", "NÃO"),
        ))

    _clear()
    print(title_text("RELATÓRIO CONSOLIDADO EM EXECUÇÃO") + "\n")
    render_canonical_progress(
        current_label=current_label,
        current_status=current_status,
        stage_index=logical_index,
        stage_count=len(_CONSOLIDATED_STAGE_FLOW),
        stage_count_planned=False,
        previous_label=previous,
        next_label=following,
        next_status="AGUARDANDO" if following else "",
        stage_percent=stage_percent,
        stage_exact=stage_exact,
        overall_percent=overall_projection,
        overall_exact=overall_exact,
        message=message,
        detail_rows=details,
    )


def _history(root: Path) -> None:
    query = ""
    while True:
        items = list_consolidated_history(root, query=query)
        _clear()
        print(title_text("CONSOLIDADOS > HISTÓRICO") + "\n")
        if query:
            print(f"Pesquisa: {query}\n")
        if not items:
            print("Nenhum consolidado encontrado.")
        else:
            cons_width = max(30, min(40, max(len(item.cons_id) for item in items)))
            print(
                f"{'Nº':>3} {'CONSOLIDADO':<{cons_width}}  {'GERADO EM':<16}  "
                f"{'DISPOSITIVO':<12}  {'AUDITORIAS':>10}  {'MODO':<28}  "
                f"{'CONFIANÇA':<18}  DOMÍNIO"
            )
            print(
                f"{'---':>3} {'-' * cons_width}  {'-' * 16}  "
                f"{'-' * 12}  {'-' * 10}  {'-' * 28}  {'-' * 18}  {'-' * 24}"
            )
            for pos, item in enumerate(items, 1):
                mode = {
                    "DETERMINISTIC": "Determinístico",
                    "DETERMINISTIC_AI": "Determinístico + IA",
                    "DETERMINISTIC_AI_UNAVAILABLE": "Determinístico; IA indisponível",
                }.get(item.generation_mode, item.generation_mode)
                confidence = str(item.confidence or "Não determinada")
                confidence_key = confidence.casefold()
                confidence_color = (
                    GREEN
                    if confidence_key in {"alta", "muito alta"}
                    else YELLOW
                    if "limit" in confidence_key or "baixa" in confidence_key
                    else GRAY
                )
                mode_color = YELLOW if "UNAVAILABLE" in item.generation_mode else CYAN
                number = paint(f"{pos:>2}.", CYAN, bold=True)
                mode_cell = paint(f"{mode[:28]:<28}", mode_color)
                confidence_cell = paint(f"{confidence[:18]:<18}", confidence_color, bold=True)
                print(
                    f"{number} {item.cons_id:<{cons_width}}  {_local_timestamp(item.generated_at):<16}  "
                    f"{item.device:<12}  {item.audit_count:>10}  {mode_cell}  "
                    f"{confidence_cell}  {item.domain or '-'}"
                )
        print("\nP. Pesquisar por ID, domínio/URL ou dispositivo")
        if query:
            print("L. Limpar pesquisa")
        print("V. Voltar")
        raw = input("Escolha: ").strip()
        upper = raw.upper()
        if upper == "V":
            return
        if upper == "P":
            new_query = input("Pesquisa por ID, domínio/URL ou dispositivo [V=voltar]: ").strip()
            if new_query.upper() == "V":
                continue
            query = new_query
            continue
        if upper == "L" and query:
            query = ""
            continue
        try:
            item = items[int(raw) - 1]
        except (ValueError, IndexError):
            continue
        while True:
            _clear()
            print(title_text("CONSOLIDADOS > HISTÓRICO > DETALHE") + "\n")
            print(f"Consolidado    : {item.cons_id}")
            print(f"Gerado em      : {_local_timestamp(item.generated_at)}")
            print(f"URL            : {item.url}")
            print(f"Dispositivo    : {item.device}")
            print(
                f"Período        : {_local_timestamp(item.period_start)} -> "
                f"{_local_timestamp(item.period_end)}"
            )
            print(f"Auditorias     : {item.audit_count}")
            print(f"BASE           : {item.audit_ids[0] if item.audit_ids else '-'}")
            print(f"ATUAL          : {item.audit_ids[-1] if item.audit_ids else '-'}")
            print(f"Seleção        : {item.selection_mode}")
            print(f"Modo           : {item.generation_mode}")
            print("IA             : " + semantic_text(item.ai_status))
            print("Confiabilidade : " + semantic_text(item.confidence, bold=True) + "\n")
            print("M. Ver linha de comando")
            print("I. Abrir relatório")
            print("P. Abrir pasta")
            print("V. Voltar")
            action = input("Escolha: ").strip().upper()
            if action == "V":
                break
            if action == "M":
                from rasai.execution_commands import show_logged

                if not show_logged(root, item.cons_id, artifact_root=item.report_dir):
                    print("\nLog de linha de comando não disponível para este consolidado.")
                    _pause()
                continue
            if action == "I":
                _open(item.report_path)
            elif action == "P":
                _open(item.report_dir)


def _generate(
    root: Path,
    *,
    ai_provider: str,
    ai_model: str | None,
    ai_reasoning: str | None,
    ai_timeout: float,
    ai_available: bool,
    ai_unavailable_reason: str | None,
) -> None:
    index = ConsolidationIndex(root)

    # Recognition is an explicit read-only phase. No AUD is analyzed or crossed here.
    _clear()
    print(title_text("CONSOLIDADOS > GERAR") + "\n")
    render_canonical_progress(
        current_label="Reconhecendo auditorias",
        current_status="EM EXECUÇÃO",
        stage_index=1,
        stage_count=len(_CONSOLIDATED_STAGE_FLOW),
        stage_count_planned=True,
        next_label="Validando fontes e artefatos",
        stage_percent=None,
        overall_percent=0.0,
        overall_exact=False,
        message="localizando AUDs persistidas e atualizando o índice analítico reconstruível",
        detail_rows=(("Nova coleta da URL", "NÃO"),),
    )
    try:
        refresh = index.refresh()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nNão foi possível preparar o índice: {type(exc).__name__}: {exc}")
        _pause()
        return

    candidates = candidate_audits(index)
    eligible_candidates = sum(_candidate_eligible(root, item) for item in candidates)
    recognition = {
        "discovered": int(refresh.discovered),
        "indexed": int(refresh.indexed),
        "reused": int(refresh.reused),
        "available": len(candidates),
        "eligible": eligible_candidates,
        "non_eligible": max(len(candidates) - eligible_candidates, 0),
        "issues": len(refresh.issues),
        "excluded": max(int(refresh.discovered) - len(candidates), 0),
    }
    _clear()
    print(title_text("CONSOLIDADOS > GERAR") + "\n")
    render_canonical_progress(
        current_label="Reconhecendo auditorias",
        current_status="CONCLUÍDA",
        stage_index=1,
        stage_count=len(_CONSOLIDATED_STAGE_FLOW),
        stage_count_planned=True,
        next_label="Validando fontes e artefatos",
        stage_percent=100.0,
        stage_exact=True,
        overall_percent=8.0,
        overall_exact=False,
        message=(
            "reconhecimento concluído; fontes utilizáveis serão oferecidas para seleção "
            "e a elegibilidade conclusiva será indicada explicitamente"
        ),
        detail_rows=(
            ("Auditorias encontradas", str(recognition["discovered"])),
            ("Indexadas nesta leitura", str(recognition["indexed"])),
            ("Índice reutilizado", str(recognition["reused"])),
            ("Fontes disponíveis", str(recognition["available"])),
            ("Elegíveis conclusivas", str(recognition["eligible"])),
            ("Não elegíveis", str(recognition["non_eligible"])),
            ("Fora da lista", str(recognition["excluded"])),
            ("Problemas de leitura", str(recognition["issues"])),
        ),
    )

    if len(candidates) < 2:
        print("\nNão existem pelo menos duas fontes utilizáveis para consolidação.")
        _pause()
        return

    recognition_context = (
        f"Reconhecidas       : {recognition['discovered']} AUD(s)",
        f"Fontes disponíveis : {recognition['available']} AUD(s)",
        f"Elegíveis          : {recognition['eligible']} AUD(s)",
        f"Não elegíveis      : {recognition['non_eligible']} AUD(s)",
        f"Fora da lista      : {recognition['excluded']} AUD(s)",
        "A seleção abaixo ainda não cruza dados; apenas define o conjunto da execução.",
    )
    first = _choose_candidate(
        "CONSOLIDADOS > GERAR > PRIMEIRO MARCO",
        candidates,
        audits_root=root,
        context=(
            *recognition_context,
            "",
            "Selecione o primeiro marco. Ele ainda não é BASE nem ATUAL.",
            "BASE/ATUAL serão definidos automaticamente pela menor/maior data e hora.",
        ),
    )
    if first is None:
        return
    compatible = compatible_candidates(index, first.audit_id)
    if not compatible:
        print("\nNão existe outra auditoria da mesma URL e dispositivo.")
        _pause()
        return
    second = _choose_candidate(
        "CONSOLIDADOS > GERAR > SEGUNDO MARCO",
        compatible,
        audits_root=root,
        selected_ids=(first.audit_id,),
        context=(
            *recognition_context,
            "",
            f"URL        : {first.url}",
            f"Dispositivo: {first.device}",
            "1º selecionado: " + _selected_audit_label(root, first),
            "Regra temporal : BASE/ATUAL independem da ordem de seleção.",
        ),
    )
    if second is None:
        return

    policy = _selection_policy(index, first, second)
    if policy is None:
        return
    selection_mode, manual_ids = policy
    try:
        selected = resolve_selection(
            index,
            first.audit_id,
            second.audit_id,
            selection_mode=selection_mode,
            manual_audit_ids=manual_ids,
        )
    except ValueError as exc:
        _clear()
        print("CONSOLIDADOS > GERAR > SELEÇÃO INVÁLIDA\n")
        print(str(exc))
        _pause()
        return

    # From this point forward the effective AUD set is frozen in audit_ids. All filters,
    # previews and generation use exactly this set; unrelated AUDs found on disk cannot
    # enter calculations or AI context.
    recognition["excluded"] = max(recognition["discovered"] - len(selected.audit_ids), 0)
    selected_ai = str(ai_provider or "none").strip().casefold()
    common_filter = dict(
        devices=(selected.device,),
        urls=(selected.url,),
        audit_ids=selected.audit_ids,
        selection_mode=selected.selection_mode,
        comparison_mode="FIRST_LAST",
    )
    deterministic_filters = normalize_filter(
        **common_filter,
        specialist_ai=False,
    )
    ai_filters = normalize_filter(
        **common_filter,
        specialist_ai=True,
        ai_provider=selected_ai,
        ai_model=ai_model,
        ai_reasoning=ai_reasoning,
        ai_timeout_seconds=ai_timeout,
    )

    try:
        deterministic_reuse = find_reusable(root, deterministic_filters, index=index, refresh=refresh)
        ai_reuse = find_reusable(root, ai_filters, index=index, refresh=refresh)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nNão foi possível verificar reuso do consolidado: {type(exc).__name__}: {exc}")
        _pause()
        return

    ai_prepared = None
    preview = None
    preview_error: str | None = None
    if ai_reuse is None and selected_ai not in {"", "none"}:
        try:
            _clear()
            print("CONSOLIDADOS > GERAR > PREPARAÇÃO\n")
            render_canonical_progress(
                current_label="Validando fontes e artefatos",
                current_status="EM EXECUÇÃO",
                stage_index=2,
                stage_count=len(_CONSOLIDATED_STAGE_FLOW),
                stage_count_planned=True,
                previous_label="Reconhecendo auditorias",
                next_label="Preparando conjunto de análise",
                stage_percent=None,
                overall_percent=16.0,
                overall_exact=False,
                message="validando somente as fontes do conjunto selecionado; nenhuma URL será recoletada",
                detail_rows=(
                    ("Conjunto efetivo", f"{len(selected.audit_ids)} AUD(s)"),
                    ("Fora do conjunto", f"{recognition['excluded']} AUD(s)"),
                    ("Fontes audit.db", f"{len(selected.audit_ids)} selecionadas"),
                    ("Nova coleta da URL", "NÃO"),
                ),
            )
            ai_prepared = prepare_longitudinal_specialist(root, ai_filters)
            _clear()
            print("CONSOLIDADOS > GERAR > PREPARAÇÃO\n")
            render_canonical_progress(
                current_label="Preparando conjunto de análise",
                current_status="CONCLUÍDA",
                stage_index=3,
                stage_count=len(_CONSOLIDATED_STAGE_FLOW),
                stage_count_planned=True,
                previous_label="Validando fontes e artefatos",
                next_label="Análise complementar / IA",
                stage_percent=100.0,
                stage_exact=True,
                overall_percent=40.0,
                overall_exact=False,
                message="conjunto longitudinal congelado; calculando prévia de IA sem chamar o provider",
                detail_rows=(
                    ("Auditorias utilizadas", str(len(selected.audit_ids))),
                    ("Intervalos", str(max(len(selected.audit_ids) - 1, 0))),
                    ("Fonte", "dados e evidências persistidos"),
                ),
            )
            preview = preview_longitudinal_specialist(root, ai_filters, prepared=ai_prepared)
        except (OSError, ValueError, RuntimeError) as exc:
            preview_error = f"{type(exc).__name__}: {exc}"
            ai_prepared = None
            preview = None

    use_ai = _choose_ai_mode(
        audits_root=root,
        ai_provider=selected_ai,
        ai_available=ai_available,
        ai_unavailable_reason=ai_unavailable_reason,
        preview=preview,
        selected=selected,
        recognition=recognition,
        ai_reusable=ai_reuse is not None,
        preview_error=preview_error,
    )
    if use_ai is None:
        return

    filters = ai_filters if use_ai else deterministic_filters
    result = ai_reuse if use_ai else deterministic_reuse

    from rasai.execution_commands import consolidation_plan

    command_plan = consolidation_plan(root, selected, filters)
    generation_seconds = 0.0

    _CONSOLIDATED_PROGRESS_CONTEXT.clear()
    _CONSOLIDATED_PROGRESS_CONTEXT.update({
        "selected_count": len(selected.audit_ids),
        "excluded_count": recognition["excluded"],
        "source_databases": len(selected.audit_ids),
        "use_ai": bool(use_ai),
        "ai_provider": selected_ai if use_ai else "",
        "ai_model": ai_model if use_ai else "",
        "preview": preview if use_ai else None,
    })

    if result is None:
        prepared = ai_prepared if use_ai else None
        effective_preview = preview if use_ai else None

        # If IA was explicitly requested without a preview-ready provider, generation
        # still materializes the deterministic report with the canonical NOT_CONFIGURED/
        # UNAVAILABLE state. Local preparation remains scoped to the frozen AUD set.
        if use_ai and prepared is None:
            try:
                prepared = prepare_longitudinal_specialist(root, filters)
                if selected_ai not in {"", "none"} and effective_preview is None:
                    effective_preview = preview_longitudinal_specialist(
                        root,
                        filters,
                        prepared=prepared,
                    )
                    _CONSOLIDATED_PROGRESS_CONTEXT["preview"] = effective_preview
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"\nFalha ao preparar a consolidação: {type(exc).__name__}: {exc}")
                _pause()
                return

        started = time.monotonic()
        try:
            result = generate(
                root,
                filters,
                refresh_index=False,
                prepared=prepared,
                preview=effective_preview,
                progress=_render_progress,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"\nFalha na consolidação: {type(exc).__name__}: {exc}")
            execution_dir = getattr(exc, "execution_dir", None)
            if execution_dir:
                print(f"Execução preservada: {execution_dir}")
            _pause()
            return
        finally:
            generation_seconds = max(time.monotonic() - started, 0.0)
    else:
        _CONSOLIDATED_PROGRESS_CONTEXT["preview"] = None
        _render_progress(
            "COMPLETE",
            "REUSED",
            "consolidado íntegro reutilizado; nenhuma nova chamada externa ou geração foi necessária",
        )

    from rasai.execution_commands import executed, record, show

    effective_command_plan = executed(command_plan)
    try:
        record(
            effective_command_plan,
            root,
            result.report_dir.name,
            append=True,
        )
    except Exception:
        # Command logging is observability only and cannot alter the CONS result.
        pass

    while True:
        _clear()
        print("RELATÓRIO CONSOLIDADO CONCLUÍDO\n")
        print("RESUMO DA EXECUÇÃO")
        print("-" * 100)
        print(f"CONS                 : {result.report_dir.name}")
        print(f"URL                  : {selected.url}")
        print(f"Dispositivo          : {selected.device}")
        print(f"Período              : {selected.period_start} -> {selected.period_end}")
        print(f"Auditorias reconhecidas: {recognition['discovered']}")
        print(f"Auditorias utilizadas: {len(selected.audit_ids)}")
        print(f"Auditorias fora do conjunto: {recognition['excluded']}")
        print(f"Fontes audit.db usadas: {len(selected.audit_ids)}")
        print(f"Modo                 : {'Com IA' if use_ai else 'Sem IA - determinístico'}")
        print(f"Resultado            : {'Reutilizado' if result.reused else 'Novo consolidado'}")
        if not result.reused:
            print(f"Tempo de geração     : {generation_seconds:.2f} s")
        print("\nMATERIALIZAÇÃO")
        print("-" * 100)
        print("Dados persistidos    : processados")
        print("Relatório HTML       : concluído")
        print("Artefatos CONS       : concluídos")
        print("Nova coleta da URL   : NÃO")
        print(f"Relatório            : {result.report_path}")
        print(f"Manifesto            : {result.manifest_path}")
        _print_ai_usage(result.report_dir)
        print("\nAÇÕES")
        print("M. Ver linha de comando")
        print("I. Abrir relatório")
        print("P. Abrir pasta")
        print("V. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "M":
            show(
                effective_command_plan,
                root,
                artifact_root=result.report_dir,
                execution_id=result.report_dir.name,
            )
        elif action == "I":
            _open(result.report_path)
        elif action == "P":
            _open(result.report_dir)


def run(
    audits_root: str | Path,
    *,
    ai_provider: str = "none",
    ai_model: str | None = None,
    ai_reasoning: str | None = None,
    ai_timeout: float = 180.0,
    ai_available: bool = False,
    ai_unavailable_reason: str | None = None,
) -> None:
    root = Path(audits_root)
    while True:
        _clear()
        print("RELATÓRIOS CONSOLIDADOS\n")
        print("1. Gerar novo consolidado")
        print("2. Histórico de consolidados")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "1":
            _generate(
                root,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_reasoning=ai_reasoning,
                ai_timeout=ai_timeout,
                ai_available=ai_available,
                ai_unavailable_reason=ai_unavailable_reason,
            )
        elif raw == "2":
            _history(root)
