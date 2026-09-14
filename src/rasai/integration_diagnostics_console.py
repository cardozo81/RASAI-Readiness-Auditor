"""Interactive-console surface for read-only external integration diagnostics."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import os
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rasai import console_provider_environment as environment_console
from rasai import integration_diagnostics as diagnostics
from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint
from rasai.time_contract import configured_presentation_timezone


# ``transient`` and ``deterministic`` are derived from ``status``. Keep diagnostic
# serialization minimal so callers can reconstruct them instead of duplicating fields.
# This also keeps compatibility with diagnostics created before this console installer.
def _diagnostic_to_dict(value: diagnostics.IntegrationDiagnostic) -> dict[str, Any]:
    return asdict(value)


diagnostics.IntegrationDiagnostic.to_dict = _diagnostic_to_dict  # type: ignore[method-assign]


def _status_color(status: str) -> str:
    if status == diagnostics.STATUS_OPERATIONAL:
        return GREEN
    if status in {diagnostics.STATUS_OPERATIONAL_LIMITED, diagnostics.STATUS_TRANSIENT_FAILURE}:
        return YELLOW
    if status in {
        diagnostics.STATUS_CONFIGURATION_ERROR,
        diagnostics.STATUS_AUTHENTICATION_ERROR,
        diagnostics.STATUS_AUTHORIZATION_ERROR,
        diagnostics.STATUS_RESOURCE_ERROR,
        diagnostics.STATUS_QUOTA_OR_BILLING,
        diagnostics.STATUS_RASAI_ERROR,
    }:
        return RED
    return DIM


def _friendly_status(status: str) -> str:
    return {
        diagnostics.STATUS_NOT_CONFIGURED: "NÃO CONFIGURADO",
        diagnostics.STATUS_OPERATIONAL: "OPERACIONAL",
        diagnostics.STATUS_OPERATIONAL_LIMITED: "OPERACIONAL COM VALIDAÇÃO LIMITADA",
        diagnostics.STATUS_CONFIGURATION_ERROR: "ERRO DE CONFIGURAÇÃO",
        diagnostics.STATUS_AUTHENTICATION_ERROR: "CREDENCIAL RECUSADA",
        diagnostics.STATUS_AUTHORIZATION_ERROR: "SEM AUTORIZAÇÃO",
        diagnostics.STATUS_RESOURCE_ERROR: "RECURSO/ENDPOINT NÃO DISPONÍVEL",
        diagnostics.STATUS_QUOTA_OR_BILLING: "QUOTA / BILLING",
        diagnostics.STATUS_TRANSIENT_FAILURE: "FALHA TEMPORÁRIA",
        diagnostics.STATUS_RASAI_ERROR: "ERRO DO DIAGNÓSTICO RASAI",
    }.get(status, status.replace("_", " "))


def _formatted_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        timezone_name = configured_presentation_timezone()
        return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m/%Y %H:%M:%S %Z")
    except (ValueError, ZoneInfoNotFoundError):
        return value or "-"


def _configured(spec: diagnostics.IntegrationSpec) -> bool:
    return not diagnostics.missing_dependencies(spec)


def _summary_status(
    spec: diagnostics.IntegrationSpec,
    result: diagnostics.IntegrationDiagnostic | None,
) -> tuple[str, str]:
    if not _configured(spec):
        return "CONFIGURAR", RED
    currency = diagnostics.result_currency(spec, result)
    if result is None or currency == "MISSING":
        return "CONFIGURADO — NÃO VALIDADO", YELLOW
    if currency == "CONFIG_CHANGED":
        return "DIAGNÓSTICO DESATUALIZADO — CONFIGURAÇÃO ALTERADA", YELLOW
    if currency == "STALE":
        return _friendly_status(result.status) + " — VALIDAÇÃO ANTIGA", YELLOW
    return _friendly_status(result.status), _status_color(result.status)


def _render_header(console_module: ModuleType, state: Any, *parts: str) -> None:
    console_module.render_header(state)
    suffix = "  >  ".join(parts)
    print(paint("INÍCIO  >  INTEGRAÇÕES / CREDENCIAIS" + ("  >  " + suffix if suffix else ""), CYAN, bold=True))
    print()


def _dependency_value(item: diagnostics.IntegrationDependency) -> str:
    raw = str(os.environ.get(item.name) or "").strip()
    if raw:
        return "[SET]" if item.secret else raw
    if item.default is not None:
        return f"<default: {item.default}>"
    return "<ausente>" if item.required else "<não definido>"


def _render_dependencies(spec: diagnostics.IntegrationSpec) -> None:
    print("DEPENDÊNCIAS E PARÂMETROS")
    for index, item in enumerate(spec.dependencies, 1):
        value = _dependency_value(item)
        state = "OBRIGATÓRIA" if item.required else "OPCIONAL"
        secret = " | SECRET" if item.secret else ""
        value_color = GREEN if str(os.environ.get(item.name) or "").strip() or item.default is not None else RED if item.required else DIM
        print(f" {index:2d}. {item.name:<44} {paint(value, value_color)}  [{state}{secret}]")
        print(paint(f"     {item.purpose}", DIM))
    if spec.related_envs:
        print("\nPARÂMETROS RELACIONADOS À EXECUÇÃO")
        for name in spec.related_envs:
            value = str(os.environ.get(name) or "").strip() or "<default/não definido>"
            print(f" - {name:<44} {value}")
    print(f"\nTipo de probe: {spec.probe_cost}")
    if spec.probe_cost == diagnostics.PROBE_NO_GENERATION:
        print(paint("O teste não envia prompt nem gera tokens de IA.", DIM))
    elif spec.probe_cost == diagnostics.PROBE_SCARCE_QUOTA_AVOIDED:
        print(paint("O teste evita a operação de Data Export para não consumir a quota escassa do fornecedor.", YELLOW))
    elif spec.probe_cost == diagnostics.PROBE_LIGHT_QUOTA:
        print(paint("O teste usa uma requisição técnica mínima e deliberadamente incompleta quando isso evita executar a coleta real.", DIM))


def _render_result(spec: diagnostics.IntegrationSpec, result: diagnostics.IntegrationDiagnostic | None) -> None:
    print("\nÚLTIMO DIAGNÓSTICO")
    if result is None:
        print(paint("Ainda não validado.", YELLOW))
        return
    currency = diagnostics.result_currency(spec, result)
    status = _friendly_status(result.status)
    if currency == "CONFIG_CHANGED":
        status += " / DESATUALIZADO APÓS ALTERAÇÃO"
    elif currency == "STALE":
        status += " / VALIDAÇÃO ANTIGA"
    print("Status      : " + paint(status, _status_color(result.status), bold=True))
    print(f"Data        : {_formatted_time(result.checked_at)}")
    print(f"Categoria   : {result.category}")
    if result.http_status is not None:
        print(f"HTTP        : {result.http_status}")
    if result.latency_ms is not None:
        print(f"Latência    : {result.latency_ms} ms")
    print(f"Diagnóstico : {result.detail}")
    print(f"Orientação  : {result.action}")
    if result.transient:
        print(paint("Classificação: falha temporária; não é tratada como prova de configuração inválida.", YELLOW))
    elif result.deterministic:
        print(paint("Classificação: condição determinística até que configuração/permissão/quota seja alterada.", RED))


def _run_and_store(state: Any, spec: diagnostics.IntegrationSpec) -> diagnostics.IntegrationDiagnostic:
    result = diagnostics.run_diagnostic(spec)
    diagnostics.save_diagnostic(state.audits_root, result)
    state.operation = "LOCAL:INTEGRATION_DIAGNOSTIC"
    state.error = ""
    return result


def _editable_specs(spec: diagnostics.IntegrationSpec) -> tuple[tuple[str, Any], ...]:
    environment_console.refresh_specs()
    names = spec.environment_names
    rows: list[tuple[str, Any]] = []
    for name in names:
        environment_spec = environment_console.SPEC_BY_NAME.get(name)
        if environment_spec is not None:
            rows.append((name, environment_spec))
    return tuple(rows)


def _edit_dependency(console_module: ModuleType, state: Any, spec: diagnostics.IntegrationSpec) -> bool:
    rows = _editable_specs(spec)
    if not rows:
        state.error = "esta integração não possui variável editável registrada no catálogo atual do console"
        return False
    _render_header(console_module, state, spec.label, "AJUSTAR CONFIGURAÇÃO")
    print("Selecione a variável. Ao sair do editor você retorna para esta integração.\n")
    for index, (name, environment_spec) in enumerate(rows, 1):
        required = next((item.required for item in spec.dependencies if item.name == name), False)
        marker = "obrigatória" if required else "relacionada/opcional"
        print(f" {index:2d}. {name:<44} [{marker}] {environment_console.decision_badge(environment_spec)}")
    print("\n V. Voltar")
    raw = input("Escolha: ").strip().upper()
    if raw == "V":
        return False
    try:
        _, selected = rows[int(raw) - 1]
    except (ValueError, IndexError):
        state.error = "variável inválida"
        return False

    environment_console._variable_menu(state, selected)
    environment_console.refresh_specs()
    while True:
        _render_header(console_module, state, spec.label, "CONFIGURAÇÃO ATUALIZADA")
        print("A alteração já está ativa nesta sessão.")
        print("Secrets nunca são gravados no INI; persistência Windows/User continua explícita no editor de credenciais.")
        print("\nS. Salvar configuração não secreta no INI e retestar")
        print("T. Retestar agora sem salvar o INI")
        print("V. Voltar sem retestar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return False
        if choice == "S":
            console_module._save_configuration(state)
            _run_and_store(state, spec)
            return True
        if choice == "T":
            _run_and_store(state, spec)
            return True


def _detail_menu(console_module: ModuleType, state: Any, spec: diagnostics.IntegrationSpec) -> None:
    while True:
        results = diagnostics.load_diagnostics(state.audits_root)
        result = results.get(spec.id)
        _render_header(console_module, state, spec.label)
        print(f"Categoria    : {spec.category}")
        print(f"Integração   : {spec.id}")
        _render_dependencies(spec)
        _render_result(spec, result)
        print("\nAÇÕES")
        print("T. Validar / retestar integração")
        print("A. Ajustar dependência/parâmetro")
        print("C. Abrir catálogo completo de configuração")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice == "T":
            _run_and_store(state, spec)
            continue
        if choice == "A":
            _edit_dependency(console_module, state, spec)
            continue
        if choice == "C":
            environment_console.environment_menu(state)
            continue


def _bulk_validate(console_module: ModuleType, state: Any, specs: tuple[diagnostics.IntegrationSpec, ...]) -> None:
    _render_header(console_module, state, "VALIDAR CONFIGURADAS")
    configured = tuple(spec for spec in specs if _configured(spec))
    if not configured:
        print("Nenhuma integração com todas as dependências obrigatórias configuradas.")
        input("\nENTER para voltar...")
        return
    print("Somente probes seguros para execução em lote serão chamados.")
    print("Integrações de quota escassa podem ser omitidas e permanecem disponíveis para diagnóstico individual.\n")
    for spec in configured:
        if not spec.safe_for_bulk:
            print(f"- {spec.label}: omitida no lote ({spec.probe_cost})")
            continue
        print(f"- {spec.label}: validando...")
        result = _run_and_store(state, spec)
        print("  " + paint(_friendly_status(result.status), _status_color(result.status), bold=True) + f" — {result.detail}")
    input("\nENTER para voltar...")


def integration_menu(console_module: ModuleType, state: Any, original_environment_menu) -> None:
    while True:
        specs = diagnostics.integration_specs()
        results = diagnostics.load_diagnostics(state.audits_root)
        _render_header(console_module, state)
        print("Diagnóstico operacional independente da auditoria.")
        print("Não altera AUTO, quarentena, scoring, execução ou reprocessamento.")
        print("Uma chamada isolada comprova somente o estado no momento do teste; falha 5xx/timeout/rate-limit é classificada como temporária.\n")

        choices: dict[str, diagnostics.IntegrationSpec] = {}
        index = 1
        for category in ("IA", "SERP / Search Intelligence", "Serviços externos"):
            rows = tuple(item for item in specs if item.category == category)
            if not rows:
                continue
            print(paint(f"[{category}]", CYAN, bold=True))
            for spec in rows:
                result = results.get(spec.id)
                label, color = _summary_status(spec, result)
                print(f" {index:2d}. {spec.label:<38} {paint(label, color, bold=True)}")
                choices[str(index)] = spec
                index += 1
            print()

        print("AÇÕES")
        print("T. Validar todas as integrações configuradas com probe seguro")
        print("C. Configuração avançada / todas as variáveis")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "T":
            _bulk_validate(console_module, state, specs)
            continue
        if raw == "C":
            original_environment_menu(state)
            continue
        selected = choices.get(raw)
        if selected is not None:
            _detail_menu(console_module, state, selected)
        else:
            state.error = "opção inválida em Integrações / credenciais"


def install(console_module: ModuleType) -> None:
    """Replace only the integration/environment surface; audit behavior stays untouched."""
    if getattr(console_module, "_rasai_integration_diagnostics_installed", False):
        return
    original_environment_menu = console_module._environment_menu

    def wrapped_environment_menu(state: Any) -> None:
        integration_menu(console_module, state, original_environment_menu)

    console_module._environment_menu = wrapped_environment_menu
    console_module._rasai_integration_diagnostics_installed = True
