"""Interactive-console surface for safe AUD evidence deletion."""
from __future__ import annotations

import builtins
from datetime import date
import math
from types import ModuleType
from typing import Any

from rasai.audit_management import (
    AuditInventoryFilter,
    AuditInventoryItem,
    DeletionImpact,
    cleanup_pending,
    execute_deletion,
    filter_inventory,
    inventory,
    plan_deletion,
)

_PAGE_SIZE = 40


def _size_label(value: int) -> str:
    size = float(max(0, value))
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for candidate in units:
        unit = candidate
        if size < 1024.0 or candidate == units[-1]:
            break
        size /= 1024.0
    return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"


def _date_label(item: AuditInventoryItem) -> str:
    value = item.event_time or item.created_at or ""
    return value[:10] if value else "-"


def _domains_label(item: AuditInventoryItem) -> str:
    if not item.domains:
        return "-"
    value = ", ".join(item.domains[:2])
    return value + (" …" if len(item.domains) > 2 else "")


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    return date.fromisoformat(raw)


def _configure_filters(current: AuditInventoryFilter) -> AuditInventoryFilter:
    print("\nFILTROS — ENTER remove/ignora o filtro")
    try:
        date_from = _parse_date(input("Data inicial [AAAA-MM-DD]: "))
        date_to = _parse_date(input("Data final   [AAAA-MM-DD]: "))
    except ValueError:
        print("Data inválida. Os filtros anteriores foram mantidos.")
        return current
    if date_from and date_to and date_from > date_to:
        print("Intervalo inválido. Os filtros anteriores foram mantidos.")
        return current
    domain = input("Domínio contém: ").strip() or None
    project = input("Projeto contém: ").strip() or None
    status = input("Status exato: ").strip() or None
    return AuditInventoryFilter(
        date_from=date_from,
        date_to=date_to,
        domain=domain,
        project=project,
        status=status,
    )


def _impact_summary(impact: DeletionImpact) -> None:
    print("\nIMPACTO DA EXCLUSÃO")
    print(f"AUDs                         : {len(impact.audits)}")
    print(f"CONS derivados afetados      : {len(impact.consolidated)}")
    print(f"Espaço estimado              : {_size_label(impact.total_bytes)}")
    print(f"Séries de execução afetadas  : {len(impact.series_ids)}")
    print(f"Configurações reutilizáveis  : {impact.reusable_configurations}")
    print("\nAUDs:")
    for item in impact.audits[:30]:
        print(f"- {item.audit_id} | {_date_label(item)} | {_domains_label(item)}")
    if len(impact.audits) > 30:
        print(f"- ... mais {len(impact.audits) - 30}")
    if impact.consolidated:
        print("\nCONS que serão removidos por dependência:")
        for item in impact.consolidated[:30]:
            print(f"- {item.cons_id}")
        if len(impact.consolidated) > 30:
            print(f"- ... mais {len(impact.consolidated) - 30}")
    print("\nA exclusão remove evidência física e impede reprocessamento/reuso futuro desses AUDs.")
    print("Registros históricos já existentes no control plane não são apagados por esta operação local.")


def _delete(
    console_module: ModuleType,
    state: Any,
    audit_ids: tuple[str, ...],
    *,
    all_audits: bool = False,
) -> bool:
    try:
        impact = plan_deletion(state.audits_root, audit_ids)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        state.status = "AUDIT_DELETION_REJECTED"
        state.operation = "LOCAL:AUDIT_DELETE"
        state.error = str(exc)
        return False

    console_module.render_header(state)
    _impact_summary(impact)
    required = "EXCLUIR TODOS OS AUDS" if all_audits else "EXCLUIR"
    if input(f"\nDigite {required} para confirmar: ").strip().upper() != required:
        state.status = "AUDIT_DELETION_CANCELLED"
        state.operation = "LOCAL:AUDIT_DELETE"
        state.error = "exclusão cancelada"
        return False

    result = execute_deletion(state.audits_root, impact)
    state.operation = "LOCAL:AUDIT_DELETE"
    state.status = result.status
    state.error = "" if result.status in {"COMPLETED", "PHYSICAL_CLEANUP_PENDING"} else result.message
    if getattr(state, "audit_id", "").upper() in {value.upper() for value in result.audit_ids}:
        state.audit_id = ""

    console_module.render_header(state)
    print("RESULTADO DA EXCLUSÃO\n")
    print(f"Status        : {result.status}")
    print(f"Lote          : {result.batch_id or '-'}")
    print(f"AUDs          : {len(result.audit_ids)}")
    print(f"CONS          : {len(result.consolidated_ids)}")
    print(f"Detalhe       : {result.message}")
    if result.cleanup_pending_bytes:
        print(f"Limpeza física pendente: {_size_label(result.cleanup_pending_bytes)}")
    if result.rollback_failures:
        print("\nATENÇÃO: o rollback não conseguiu restaurar todos os itens:")
        for item in result.rollback_failures:
            print(f"- {item}")
    input("\nENTER para continuar...")
    return result.status in {"COMPLETED", "PHYSICAL_CLEANUP_PENDING", "LOGICALLY_DELETED"}


def _render_filters(filters: AuditInventoryFilter) -> str:
    pieces: list[str] = []
    if filters.date_from:
        pieces.append(f"de={filters.date_from.isoformat()}")
    if filters.date_to:
        pieces.append(f"até={filters.date_to.isoformat()}")
    if filters.domain:
        pieces.append(f"domínio={filters.domain}")
    if filters.project:
        pieces.append(f"projeto={filters.project}")
    if filters.status:
        pieces.append(f"status={filters.status}")
    return ", ".join(pieces) if pieces else "nenhum"


def _toggle_indexes(raw: str, filtered: tuple[AuditInventoryItem, ...], selected: set[str]) -> None:
    indexes: set[int] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            begin, end = int(left), int(right)
            if begin > end:
                begin, end = end, begin
            indexes.update(range(begin, end + 1))
        else:
            indexes.add(int(token))
    for index in indexes:
        if 1 <= index <= len(filtered):
            audit_id = filtered[index - 1].audit_id
            if audit_id in selected:
                selected.remove(audit_id)
            else:
                selected.add(audit_id)


def _management_menu(console_module: ModuleType, state: Any) -> None:
    filters = AuditInventoryFilter()
    selected: set[str] = set()
    page = 0
    while True:
        all_items = inventory(state.audits_root)
        filtered = filter_inventory(all_items, filters)
        valid_ids = {item.audit_id for item in all_items}
        selected.intersection_update(valid_ids)
        pages = max(1, math.ceil(len(filtered) / _PAGE_SIZE))
        page = min(page, pages - 1)
        start = page * _PAGE_SIZE
        visible = filtered[start : start + _PAGE_SIZE]

        console_module.render_header(state)
        print("GERENCIAR AUDITORIAS / EXCLUSÃO SEGURA\n")
        print(f"Raiz       : {state.audits_root}")
        print(f"AUDs       : {len(all_items)} total | {len(filtered)} no filtro | {len(selected)} selecionados")
        print(f"Espaço AUD : {_size_label(sum(item.size_bytes for item in all_items))}")
        print(f"Filtros    : {_render_filters(filters)}")
        print(f"Página     : {page + 1}/{pages}\n")
        if visible:
            print("    SEL AUD-ID                         DATA       STATUS              TAMANHO     DOMÍNIO")
            for absolute_index, item in enumerate(visible, start + 1):
                marker = "[x]" if item.audit_id in selected else "[ ]"
                status = item.completion_status or item.status or "-"
                print(
                    f"{absolute_index:3d} {marker} {item.audit_id:<30} {_date_label(item):<10} "
                    f"{status[:18]:<18} {_size_label(item.size_bytes):>10}  {_domains_label(item)}"
                )
        else:
            print("Nenhum AUD atende aos filtros atuais.")

        print("\nAÇÕES")
        print("< / >. Página anterior / próxima")
        print("N. Alternar seleção informando números (ex.: 1,3,7-10)")
        print("A. Selecionar TODOS os AUDs do filtro atual")
        print("L. Limpar seleção")
        print("F. Definir filtros")
        print("X. Excluir AUDs selecionados")
        print("T. Excluir TODOS os AUDs existentes")
        print("R. Repetir limpeza física pendente")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice == ">":
            page = min(page + 1, pages - 1)
            continue
        if choice == "<":
            page = max(0, page - 1)
            continue
        if choice == "F":
            filters = _configure_filters(filters)
            page = 0
            continue
        if choice == "A":
            selected.update(item.audit_id for item in filtered)
            continue
        if choice == "L":
            selected.clear()
            continue
        if choice == "N":
            raw = input("Números/intervalos: ").strip()
            try:
                _toggle_indexes(raw, filtered, selected)
            except ValueError:
                state.error = "seleção inválida"
            continue
        if choice == "X":
            if not selected:
                state.error = "nenhum AUD selecionado"
                continue
            _delete(console_module, state, tuple(sorted(selected)))
            selected.clear()
            continue
        if choice == "T":
            if not all_items:
                state.error = "nenhum AUD disponível para exclusão"
                continue
            _delete(
                console_module,
                state,
                tuple(item.audit_id for item in all_items),
                all_audits=True,
            )
            selected.clear()
            continue
        if choice == "R":
            result = cleanup_pending(state.audits_root)
            state.operation = "LOCAL:AUDIT_DELETE_CLEANUP"
            state.status = "COMPLETED" if result.pending_batches == 0 else "PHYSICAL_CLEANUP_PENDING"
            state.error = "; ".join(result.errors)
            console_module.render_header(state)
            print("LIMPEZA FÍSICA PENDENTE\n")
            print(f"Lotes removidos : {result.removed_batches}")
            print(f"Lotes pendentes : {result.pending_batches}")
            print(f"Espaço pendente : {_size_label(result.pending_bytes)}")
            for error in result.errors[:20]:
                print(f"- {error}")
            input("\nENTER para continuar...")
            continue
        state.error = "opção inválida"


def install(console_module: ModuleType) -> None:
    """Add audit management to the existing history picker without changing normal flows."""
    if getattr(console_module, "_rasai_audit_management_installed", False):
        return
    import rasai.console_navigation as navigation

    original_choose = navigation._choose_audit

    def choose_with_management(state: Any) -> str | None:
        while True:
            original_input = builtins.input
            management_requested = False

            def managed_input(prompt: str = "") -> str:
                nonlocal management_requested
                if prompt.strip().casefold().startswith("escolha"):
                    print("G. Gerenciar / excluir auditorias")
                raw = original_input(prompt)
                if raw.strip().upper() == "G":
                    management_requested = True
                    return "V"
                return raw

            builtins.input = managed_input
            try:
                result = original_choose(state)
            finally:
                builtins.input = original_input
            if not management_requested:
                return result
            _management_menu(console_module, state)

    navigation._choose_audit = choose_with_management
    console_module._rasai_audit_management_installed = True
