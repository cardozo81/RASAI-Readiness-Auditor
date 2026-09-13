"""Console workflow presentation for AUD reuse and selective reprocessing.

This module keeps the analytical engines unchanged. It synchronizes restored execution
state with the visible console and gives selective reprocessing the same live operational
feedback expected from a normal audit execution.
"""
from __future__ import annotations

from contextvars import copy_context
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import ModuleType
from typing import Any, Callable, Mapping

_LOAD_WARNINGS: dict[int, tuple[str, ...]] = {}


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "on", "sim", "s"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao", "não", "n"}:
        return False
    return default


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _restore_search_from_persisted_observations(
    state: Any,
    audit_id: str,
) -> tuple[str, ...]:
    """Recover Search inputs from canonical observations when absent from the snapshot."""
    if not hasattr(state, "search_queries"):
        return ()
    database = Path(state.audits_root) / audit_id / "audit.db"
    if not database.is_file():
        return ()
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=0.5,
        )
        connection.row_factory = sqlite3.Row
        try:
            if not _table_exists(connection, "serp_observations"):
                return ()
            rows = connection.execute(
                """
                SELECT query,region,device,requested_depth,provider,data_mode,
                       config_metadata,collected_at,observation_id
                FROM serp_observations
                WHERE audit_id=?
                ORDER BY collected_at,observation_id
                """,
                (audit_id,),
            ).fetchall()
            competitive_present = False
            if _table_exists(connection, "serp_competitive_analyses"):
                try:
                    competitive_present = (
                        connection.execute(
                            "SELECT 1 FROM serp_competitive_analyses "
                            "WHERE audit_id=? LIMIT 1",
                            (audit_id,),
                        ).fetchone()
                        is not None
                    )
                except sqlite3.Error:
                    competitive_present = False
        finally:
            connection.close()
    except sqlite3.Error:
        return ()
    if not rows:
        return ()

    queries: list[str] = []
    seen: set[str] = set()
    depths: list[int] = []
    devices: list[str] = []
    regions: list[str] = []
    providers: list[str] = []
    modes: list[str] = []
    competitive_values: list[bool] = []
    for row in rows:
        query = " ".join(str(row["query"] or "").strip().split())
        key = query.casefold()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
        try:
            depth = int(row["requested_depth"])
            if depth > 0:
                depths.append(depth)
        except (TypeError, ValueError):
            pass
        device = str(row["device"] or "").strip().casefold()
        if device in {"mobile", "desktop"}:
            devices.append(device)
        region = str(row["region"] or "").strip()
        if region:
            regions.append(region)
        provider = str(row["provider"] or "").strip().casefold()
        if provider:
            providers.append(provider)
        mode = str(row["data_mode"] or "").strip().casefold()
        if mode:
            modes.append(mode)
        try:
            metadata = json.loads(str(row["config_metadata"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        if isinstance(metadata, Mapping):
            for key_name in ("competitive", "competitive_enabled", "classify_competitors"):
                if key_name in metadata:
                    competitive_values.append(
                        _as_bool(metadata.get(key_name), default=competitive_present)
                    )
                    break

    if not queries:
        return ()

    warnings: list[str] = []
    state.search_queries = tuple(queries)
    if depths:
        distinct_depths = tuple(dict.fromkeys(depths))
        state.search_depth = max(depths)
        if len(distinct_depths) > 1:
            warnings.append(
                "Search Intelligence: observações persistidas possuem profundidades "
                f"distintas; depth={state.search_depth} foi restaurada para revisão"
            )
    if devices:
        distinct_devices = tuple(dict.fromkeys(devices))
        state.search_device = distinct_devices[0]
        if len(distinct_devices) > 1:
            warnings.append(
                "Search Intelligence: observações persistidas possuem mais de um "
                f"dispositivo; {state.search_device} foi restaurado para revisão"
            )
    state.search_region = regions[0] if regions else ""
    state.search_competitive = (
        competitive_values[-1] if competitive_values else competitive_present
    )

    if providers and not (os.environ.get("RASAI_SERP_PROVIDER") or "").strip():
        os.environ["RASAI_SERP_PROVIDER"] = providers[0]
    normalized_modes = [value for value in modes if value in {"live", "fixture"}]
    if normalized_modes and not (os.environ.get("RASAI_SERP_MODE") or "").strip():
        os.environ["RASAI_SERP_MODE"] = normalized_modes[0]

    state.search_last_status = "PENDING"
    state.search_last_detail = (
        f"{len(state.search_queries)} termo(s) reconstruídos das observações SERP "
        "persistidas"
    )
    state.search_last_report = ""
    state.search_last_duration_seconds = None
    warnings.append(
        "Search Intelligence: termos/contexto foram reconstruídos das observações "
        "persistidas do próprio AUD; revise provider, competitive e limites"
    )
    return tuple(dict.fromkeys(warnings))


def _synchronize_loaded_state(
    state: Any,
    configuration: Mapping[str, Any],
    source_audit_id: str,
) -> tuple[str, ...]:
    """Make the visible session match the configuration already applied by the loader."""
    warnings: list[str] = []
    targets = configuration.get("targets")
    if isinstance(targets, list):
        normalized = tuple(str(value).strip() for value in targets if str(value).strip())
        if normalized and hasattr(state, "current_url"):
            state.current_url = (
                normalized[0]
                if len(normalized) == 1
                else f"{normalized[0]} (+{len(normalized) - 1})"
            )
    if hasattr(state, "current_device"):
        state.current_device = str(getattr(state, "device", "mobile")).upper()

    if "search_intelligence" not in configuration:
        warnings.extend(
            _restore_search_from_persisted_observations(state, source_audit_id)
        )
    return tuple(dict.fromkeys(warnings))


def _dependency_warnings(state: Any, console_module: ModuleType) -> tuple[str, ...]:
    from rasai.audit_configuration_reuse_console import _dependency_warnings

    return _dependency_warnings(state, console_module)


def _serp_runtime_summary() -> tuple[str, str, str]:
    try:
        from rasai.search_intelligence.config import SerpRuntimeConfig, provider_key_env
        from rasai.search_intelligence.provider_catalog import serp_provider_registration

        config = SerpRuntimeConfig.from_environment()
        registration = serp_provider_registration(config.provider)
        key_name = provider_key_env(config.provider)
        key_state = "[SET]" if (os.environ.get(key_name) or "").strip() else "<não definida>"
        engine = registration.engine if registration is not None else "unknown"
        return f"{config.mode} / {config.provider} / {engine}", key_name, key_state
    except (KeyError, TypeError, ValueError):
        return "configuração inválida", "-", "-"


def render_loaded_configuration_summary(
    console_module: ModuleType,
    state: Any,
    source: Any,
) -> tuple[str, ...]:
    """Show exactly what the AUD load placed in the new-execution session."""
    warnings = tuple(
        dict.fromkeys(
            (
                *_LOAD_WARNINGS.get(id(state), ()),
                *_dependency_warnings(state, console_module),
            )
        )
    )
    # Successful reuse is not an error state. Dependency warnings are rendered
    # explicitly below and the normal preflight remains authoritative afterwards.
    state.error = ""
    console_module.render_header(state)
    print("CONFIGURAÇÃO CARREGADA\n")
    print(f"Origem              : {source.audit_id}")
    print(
        f"Entrada              : "
        f"{'URL única' if getattr(state, 'input_mode', 'url') == 'url' else 'lista de URLs'}"
    )
    print(
        f"Alvo                 : "
        f"{getattr(state, 'current_url', '') or getattr(state, 'target', '') or '<não informado>'}"
    )
    print(f"Projeto              : {getattr(state, 'project', '') or '<auto>'}")
    print(f"Dispositivo          : {getattr(state, 'device', '-')}")
    print(
        f"Idioma / mercado     : {getattr(state, 'language', '-')} / "
        f"{getattr(state, 'market', '-')}"
    )

    queries = tuple(getattr(state, "search_queries", ()) or ())
    print("\nSEARCH INTELLIGENCE / SERP")
    print(f"Estado               : {'ATIVO' if queries else 'SEM TERMOS'}")
    print(
        f"Termos               : "
        f"{'; '.join(queries) if queries else '<nenhum termo restaurado>'}"
    )
    print(f"Depth                : {getattr(state, 'search_depth', '-')}")
    print(f"Região               : {getattr(state, 'search_region', '') or '<vazio>'}")
    print(f"Dispositivo SERP     : {getattr(state, 'search_device', '-')}")
    print(
        f"Competitive          : "
        f"{'SIM' if bool(getattr(state, 'search_competitive', False)) else 'NÃO'}"
    )
    runtime, key_name, key_state = _serp_runtime_summary()
    print(f"Modo/provider/engine : {runtime}")
    print(f"Credencial atual     : {key_name}={key_state}")
    print("Credencial do AUD    : não copiada")

    if warnings:
        print("\nATENÇÃO")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("\nDependências atuais  : OK")
    print("\nA próxima execução criará um novo AUD; o AUD de origem não será alterado.")
    print("Revise os valores acima antes de executar.")
    return warnings


def _load_source_with_summary(
    console_module: ModuleType,
    state: Any,
) -> None:
    from rasai.audit_configuration_reuse_console import load_source_configuration

    audit_id = input("Audit ID de origem (AUD-*): ").strip().upper()
    source = load_source_configuration(state, audit_id, console_module=console_module)
    if source is None:
        console_module.render_header(state)
        print("CONFIGURAÇÃO NÃO CARREGADA\n")
        print(state.error or "O AUD não possui snapshot reutilizável válido.")
        input("\nENTER para continuar...")
        return
    render_loaded_configuration_summary(console_module, state, source)
    input("\nENTER para continuar...")


def _load_selected_configuration(
    console_module: ModuleType,
    state: Any,
    audit_id: str,
) -> bool:
    from rasai.audit_configuration_reuse_console import load_source_configuration

    source = load_source_configuration(state, audit_id, console_module=console_module)
    if source is None:
        console_module.render_header(state)
        print("CONFIGURAÇÃO NÃO CARREGADA\n")
        print(state.error or "O AUD não possui snapshot reutilizável válido.")
        input("\nENTER para continuar...")
        return False
    render_loaded_configuration_summary(console_module, state, source)
    print(
        "\nA configuração foi aberta no contexto PREPARAR AUDITORIA "
        "para revisão antes da execução."
    )
    input("\nENTER para continuar...")
    return True


def _audit_primary_url(audit_root: Path) -> str:
    database = audit_root / "audit.db"
    if not database.is_file():
        return ""
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=0.3,
        )
        try:
            row = connection.execute(
                "SELECT normalized_url FROM pages ORDER BY rowid LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return ""
    return str(row[0]) if row and row[0] else ""


def _reprocess_live_snapshot(
    audit_root: Path,
    audit_id: str,
    baseline_attempts: Mapping[tuple[str, str], int],
) -> dict[str, Any]:
    """Read work-item progress without mutating the reprocessing engine."""
    empty = {
        "total": len(baseline_attempts),
        "evaluated": 0,
        "attempted": 0,
        "running": None,
    }
    database = audit_root / "audit.db"
    if not database.is_file() or not baseline_attempts:
        return empty
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=0.2,
        )
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT component,scope_key,status,attempt_count
                FROM audit_fulfillment_work_items
                WHERE audit_id=? AND required=1
                """,
                (audit_id,),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return empty

    attempted = 0
    evaluated = 0
    running: tuple[str, str, str] | None = None
    for row in rows:
        key = (str(row["component"]), str(row["scope_key"]))
        if key not in baseline_attempts:
            continue
        status = str(row["status"])
        current_attempts = int(row["attempt_count"] or 0)
        was_attempted = current_attempts > int(baseline_attempts[key])
        if was_attempted:
            attempted += 1
        if status == "RUNNING":
            running = (key[0], key[1], status)
        elif was_attempted or status in {"SUCCESS", "NOT_APPLICABLE", "DISABLED"}:
            evaluated += 1
    return {
        "total": len(baseline_attempts),
        "evaluated": min(evaluated, len(baseline_attempts)),
        "attempted": min(attempted, len(baseline_attempts)),
        "running": running,
    }


def _reprocess_activity(snapshot: Mapping[str, Any]) -> str:
    running = snapshot.get("running")
    if not running:
        if snapshot.get("attempted", 0):
            return "consolidando o resultado do último requisito avaliado"
        return "preparando requisitos e dependências do reprocessamento"
    component, scope_key, _ = running
    labels = {
        "SEMANTIC_AI": "análise semântica por IA",
        "TECHNICAL_AI": "análise técnica por IA",
        "CONTENT_REMEDIATION_AI": "remediação de conteúdo por IA",
        "WEB_PERFORMANCE": "Web Performance",
        "SYNTHETIC_APDEX": "Synthetic Navigation Apdex",
        "EXPERIENCE_APDEX": "Synthetic User Experience",
        "HTTP_ACQUISITION": "aquisição HTTP",
        "RENDER_CAPTURE": "captura/renderização",
        "CONTENT_EXTRACTION": "extração de conteúdo",
        "CORE_AUDIT": "núcleo da auditoria",
    }
    label = labels.get(component, component.replace("_", " ").title())
    return f"{label} | {scope_key}"


def _usage_costs(usage: Any | None) -> dict[str, float]:
    if usage is None:
        return {}
    return {str(currency): float(amount) for currency, amount in usage.costs}


def _render_reprocess_usage_delta(before: Any | None, after: Any | None) -> None:
    print("\nCONSUMO DESTA TENTATIVA DE REPROCESSAMENTO")
    print("-" * 100)
    if after is None:
        print("Telemetria de consumo indisponível.")
        return

    def previous(name: str) -> int:
        return int(getattr(before, name, 0) or 0) if before is not None else 0

    fields = (
        ("Tentativas IA", "ai_attempts"),
        ("Sucessos IA", "ai_successes"),
        ("Tokens input", "input_tokens"),
        ("Tokens input cache", "cached_input_tokens"),
        ("Tokens output", "output_tokens"),
        ("Tokens reasoning", "reasoning_tokens"),
        ("Tokens total", "total_tokens"),
    )
    for label, name in fields:
        delta = max(int(getattr(after, name, 0) or 0) - previous(name), 0)
        print(f"{label:<20}: {delta:,}")

    before_costs = _usage_costs(before)
    after_costs = _usage_costs(after)
    deltas = [
        (currency, max(amount - before_costs.get(currency, 0.0), 0.0))
        for currency, amount in sorted(after_costs.items())
        if amount - before_costs.get(currency, 0.0) > 1e-12
    ]
    if deltas:
        print(
            "Custo IA estimado   : "
            + " | ".join(f"{currency} {amount:.8f}" for currency, amount in deltas)
        )
    elif int(getattr(after, "ai_attempts", 0) or 0) - previous("ai_attempts") > 0:
        print("Custo IA estimado   : não disponível com pricing/tokens persistidos")
    else:
        print("Custo IA estimado   : 0 (nenhuma nova tentativa de IA)")
    web_delta = max(
        int(getattr(after, "web_external_calls", 0) or 0)
        - previous("web_external_calls"),
        0,
    )
    print(f"Chamadas Web Perf.  : {web_delta}")
    print("Observação           : estimativa técnica persistida; não é invoice do provider.")


def _render_live_reprocess_usage(audit_root: Path) -> None:
    from rasai.console_cost import actual_usage

    usage = actual_usage(audit_root)
    if usage is None:
        return
    if usage.costs:
        costs = " | ".join(
            f"{currency} {amount:.8f}" for currency, amount in usage.costs
        )
    elif usage.ai_attempts:
        costs = "não estimável"
    else:
        costs = "0"
    print(
        f"IA acumulada no AUD : tentativas={usage.ai_attempts} | "
        f"tokens={usage.total_tokens:,} | custo estimado={costs}"
    )


def _reprocess_selected(
    console_module: ModuleType,
    state: Any,
    audit_id: str,
) -> None:
    """Run the canonical reprocessor with live console projection and cost feedback."""
    from rasai import console_navigation, console_runtime
    from rasai.audit_reprocess import reprocess_audit
    from rasai.console_cost import actual_usage

    pending, successes = console_navigation._work_item_preview(state, audit_id)
    console_module.render_header(state)
    print("REPROCESSAMENTO SELETIVO\n")
    print(f"AUD: {audit_id}")
    if pending or successes:
        print(f"Pendentes/bloqueados : {len(pending)}")
        print(f"Sucessos preservados : {len(successes)}")
        if pending:
            print("\nItens que ainda precisam de resolução:")
            for item in pending[:30]:
                print(f"- {item.component}/{item.scope_key}: {item.status}")
    else:
        print(
            "O estado será reavaliado pelo motor de reprocessamento antes de "
            "qualquer nova tentativa."
        )
    print("\nItens já bem-sucedidos não são repetidos por padrão.")
    print(
        "Chamadas externas/IA só ocorrem quando o requisito correspondente "
        "realmente precisar ser recuperado."
    )
    if input("\nPara iniciar, digite REPROCESSAR: ").strip().upper() != "REPROCESSAR":
        state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
        state.error = "reprocessamento cancelado"
        return

    audit_root = Path(state.audits_root) / audit_id
    before_usage = actual_usage(audit_root)
    baseline_attempts = {
        (str(item.component), str(item.scope_key)): int(item.attempt_count)
        for item in pending
        if bool(getattr(item, "required", True))
    }
    state.audit_id = audit_id
    state.status = "REPROCESSING"
    state.operation = "LOCAL:AUD_REPROCESS"
    state.error = ""
    primary_url = _audit_primary_url(audit_root)
    if primary_url and hasattr(state, "current_url"):
        state.current_url = primary_url

    try:
        console_runtime._start_timing(state)
    except (AttributeError, TypeError, ValueError):
        pass
    console_runtime.set_runtime_progress(
        state,
        "Reprocessamento seletivo",
        0.0,
        detail="preparando requisitos pendentes e preservando resultados já válidos",
        exact=False,
    )

    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["result"] = reprocess_audit(
                audit_id,
                audits_root=state.audits_root,
                source="CONSOLE",
            )
        except Exception as exc:  # console boundary: expose engine failures to the operator
            outcome["error"] = exc

    execution_context = copy_context()
    thread = threading.Thread(
        target=lambda: execution_context.run(worker),
        name=f"rasai-reprocess-{audit_id}",
        daemon=True,
    )
    thread.start()

    while thread.is_alive():
        snapshot = _reprocess_live_snapshot(
            audit_root,
            audit_id,
            baseline_attempts,
        )
        total = int(snapshot["total"])
        evaluated = int(snapshot["evaluated"])
        percent = (100.0 * evaluated / total) if total else 0.0
        activity = _reprocess_activity(snapshot)
        console_runtime.set_runtime_progress(
            state,
            "Reprocessamento seletivo",
            percent,
            detail=(
                f"{activity}; requisitos avaliados={evaluated}/{total}; "
                f"sucessos anteriores preservados={len(successes)}"
            ),
            exact=False,
        )
        console_module.render_header(state)
        print("REPROCESSAMENTO EM EXECUÇÃO\n")
        print(f"AUD                  : {audit_id}")
        print(f"Sucessos preservados : {len(successes)}")
        print(f"Itens a avaliar      : {total}")
        print(f"Itens avaliados      : {evaluated}/{total}")
        print(f"Executando           : {activity}")
        _render_live_reprocess_usage(audit_root)
        thread.join(timeout=0.5)

    thread.join()
    try:
        console_runtime._finish_timing(state)
    except (AttributeError, TypeError, ValueError):
        pass

    error = outcome.get("error")
    if error is not None:
        state.status = "REPROCESS_FAILED"
        state.operation = "LOCAL:AUD_REPROCESS"
        state.error = f"{type(error).__name__}: {error}"
        console_module.render_header(state)
        print("REPROCESSAMENTO FALHOU\n")
        print(state.error)
        input("\nENTER para continuar...")
        return

    result = outcome["result"]
    after_usage = actual_usage(audit_root)
    state.audit_id = audit_id
    state.status = result.processing_status
    state.operation = "LOCAL:AUD_REPROCESS"
    state.error = ""
    console_runtime.set_runtime_progress(
        state,
        "Reprocessamento seletivo",
        100.0,
        detail=(
            f"tentativa concluída; resolvidos={result.successful_items}; "
            f"restantes={result.remaining_items}"
        ),
        exact=True,
    )
    console_module.render_header(state)
    print("REPROCESSAMENTO CONCLUÍDO\n")
    print(f"AUD                  : {result.audit_id}")
    print(f"RPR                  : {result.reprocess_id or '<nenhum; sem trabalho pendente>'}")
    print(f"Processamento        : {result.processing_status}")
    print(f"Score                : {result.score_status}")
    print(f"Relatório            : {result.report_status}")
    print(f"Consolidação elegível: {'SIM' if result.consolidation_eligible else 'NÃO'}")
    print(f"Itens tentados       : {result.attempted_items}")
    print(f"Itens resolvidos     : {result.successful_items}")
    print(f"Sucessos preservados : {result.skipped_success_items}")
    print(f"Itens restantes      : {result.remaining_items}")
    if result.temporal_expired_items:
        print(f"Itens expirados      : {result.temporal_expired_items}")

    _render_reprocess_usage_delta(before_usage, after_usage)
    renderer = getattr(console_module, "_render_actual_usage", None)
    if callable(renderer):
        print("\nCONSUMO ACUMULADO DO AUD APÓS O REPROCESSAMENTO")
        renderer(state)
    input("\nENTER para continuar...")


def install(console_module: ModuleType) -> None:
    """Install final console workflow behavior after reuse and navigation adapters."""
    if getattr(console_module, "_rasai_audit_workflow_installed", False):
        return

    from rasai import audit_configuration_reuse_console as reuse
    from rasai import console_navigation

    original_apply: Callable[..., tuple[str, ...]] = reuse._apply_settings

    def apply_settings(
        state: Any,
        configuration: Mapping[str, Any],
        source_audit_id: str,
    ) -> tuple[str, ...]:
        warnings = list(original_apply(state, configuration, source_audit_id))
        warnings.extend(
            _synchronize_loaded_state(state, configuration, source_audit_id)
        )
        unique = tuple(dict.fromkeys(warnings))
        _LOAD_WARNINGS[id(state)] = unique
        return unique

    console_module_ref = console_module

    def load_source(state: Any, console_module: ModuleType | None = None) -> None:
        _load_source_with_summary(console_module or console_module_ref, state)

    reuse._apply_settings = apply_settings
    reuse._load_source = load_source
    console_navigation._load_selected_configuration = _load_selected_configuration
    console_navigation._reprocess_selected = _reprocess_selected
    console_module._rasai_audit_workflow_installed = True
