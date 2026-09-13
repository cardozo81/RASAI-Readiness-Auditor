"""Task-oriented navigation shell for the local interactive console.

The shell is deliberately additive: the existing configuration dashboard remains the
single detailed configuration surface, while the first level is organized around user
tasks. AUD recovery and configuration reuse are contextual actions of a selected AUD.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any


def _audit_directories(audits_root: str | Path) -> tuple[Path, ...]:
    root = Path(audits_root)
    if not root.is_dir():
        return ()
    candidates = [
        item
        for item in root.iterdir()
        if item.is_dir() and item.name.upper().startswith("AUD-") and (item / "audit.db").is_file()
    ]
    return tuple(sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True))


def _safe_summary(audit_root: Path, audit_id: str) -> dict[str, Any]:
    try:
        from rasai.audit_fulfillment import read_summary
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(audit_root)
        summary = read_summary(workspace, audit_id)
        if summary is None:
            return {}
        return {
            "processing_status": summary.processing_status,
            "score_status": summary.score_status,
            "report_status": summary.report_status,
            "consolidation_eligible": summary.consolidation_eligible,
            "required_items": summary.required_items,
            "successful_items": summary.successful_items,
            "pending_items": summary.pending_items,
            "blocked_items": summary.blocked_items,
            "expired_items": summary.expired_items,
            "reprocess_count": summary.reprocess_count,
            "last_reprocess_id": summary.last_reprocess_id,
        }
    except (OSError, ValueError, RuntimeError):
        return {}


def _render_audit_row(index: int, audit_root: Path) -> None:
    audit_id = audit_root.name
    summary = _safe_summary(audit_root, audit_id)
    status = str(summary.get("processing_status") or "STATUS NÃO PROJETADO")
    report = str(summary.get("report_status") or "-")
    print(f"{index:2d}. {audit_id:<30} {status:<24} relatório={report}")


def _choose_audit(state: Any) -> str | None:
    audits = _audit_directories(state.audits_root)
    while True:
        print("\nAUDITORIAS / HISTÓRICO")
        print(f"Raiz: {state.audits_root}")
        if audits:
            print("\nRecentes:")
            for index, audit_root in enumerate(audits[:20], 1):
                _render_audit_row(index, audit_root)
        else:
            print("\nNenhum AUD com audit.db encontrado nesta raiz.")
        print("\nI. Informar Audit ID")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw == "I":
            audit_id = input("Audit ID (AUD-*): ").strip().upper()
            candidate = Path(state.audits_root) / audit_id
            if audit_id.startswith("AUD-") and (candidate / "audit.db").is_file():
                return audit_id
            state.error = f"AUD não encontrado em {state.audits_root}: {audit_id or '<vazio>'}"
            continue
        try:
            selected = int(raw) - 1
        except ValueError:
            state.error = "opção de auditoria inválida"
            continue
        if 0 <= selected < min(len(audits), 20):
            return audits[selected].name
        state.error = "opção de auditoria inválida"


def _work_item_preview(state: Any, audit_id: str) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    try:
        from rasai.audit_fulfillment import SUCCESS, list_work_items
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
        items = tuple(list_work_items(workspace, audit_id))
        successes = tuple(item for item in items if item.required and item.status == SUCCESS)
        pending = tuple(item for item in items if item.required and item.status != SUCCESS)
        return pending, successes
    except (OSError, ValueError, RuntimeError):
        return (), ()


def _reprocess_selected(console_module: ModuleType, state: Any, audit_id: str) -> None:
    from rasai.audit_reprocess import reprocess_audit

    pending, successes = _work_item_preview(state, audit_id)
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
        print("O estado será reavaliado pelo motor de reprocessamento antes de qualquer nova tentativa.")
    print("\nItens já bem-sucedidos não são repetidos por padrão.")
    print("Chamadas externas/IA só ocorrem quando o requisito correspondente realmente precisar ser recuperado.")
    if input("\nPara iniciar, digite REPROCESSAR: ").strip().upper() != "REPROCESSAR":
        state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
        state.error = "reprocessamento cancelado"
        return

    try:
        result = reprocess_audit(audit_id, audits_root=state.audits_root, source="CONSOLE")
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        state.status = "REPROCESS_FAILED"
        state.operation = "LOCAL:AUD_REPROCESS"
        state.error = f"{type(exc).__name__}: {exc}"
        return

    state.audit_id = audit_id
    state.status = result.processing_status
    state.operation = "LOCAL:AUD_REPROCESS"
    state.error = ""
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
    input("\nENTER para continuar...")


def _load_selected_configuration(console_module: ModuleType, state: Any, audit_id: str) -> None:
    from rasai.audit_configuration_reuse_console import load_source_configuration

    source = load_source_configuration(state, audit_id, console_module=console_module)
    console_module.render_header(state)
    if source is None:
        print("CONFIGURAÇÃO NÃO CARREGADA\n")
        print(state.error or "O AUD não possui snapshot reutilizável válido.")
    else:
        print("CONFIGURAÇÃO CARREGADA\n")
        print(f"Origem: {source.audit_id}")
        print("A próxima execução criará um novo AUD; o AUD de origem não será alterado.")
        print("Credenciais nunca são copiadas do AUD e continuam sendo resolvidas na sessão/Windows/SaaS atual.")
        if state.error:
            print(f"\n{state.error}")
    input("\nENTER para continuar...")


def _selected_audit_menu(console_module: ModuleType, state: Any, audit_id: str) -> None:
    while True:
        audit_root = Path(state.audits_root) / audit_id
        summary = _safe_summary(audit_root, audit_id)
        console_module.render_header(state)
        print("AUDITORIA SELECIONADA\n")
        print(f"AUD            : {audit_id}")
        print(f"Processamento  : {summary.get('processing_status', 'STATUS NÃO PROJETADO')}")
        print(f"Score          : {summary.get('score_status', '-')}")
        print(f"Relatório      : {summary.get('report_status', '-')}")
        eligible = summary.get("consolidation_eligible")
        print(f"Consolidação   : {'ELEGÍVEL' if eligible is True else ('NÃO ELEGÍVEL' if eligible is False else '-')}")
        if summary:
            print(
                "Requisitos     : "
                f"{summary.get('successful_items', 0)}/{summary.get('required_items', 0)} atendidos | "
                f"pendentes={summary.get('pending_items', 0)} | bloqueados={summary.get('blocked_items', 0)}"
            )
            print(
                f"Reprocessamentos: {summary.get('reprocess_count', 0)} | "
                f"último={summary.get('last_reprocess_id') or '-'}"
            )
        print("\nAÇÕES")
        print("1. Reprocessar pendências desta auditoria")
        print("2. Carregar esta configuração para uma nova auditoria")
        print("3. Mostrar caminhos de artefatos")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice == "1":
            _reprocess_selected(console_module, state, audit_id)
        elif choice == "2":
            _load_selected_configuration(console_module, state, audit_id)
        elif choice == "3":
            report = audit_root / "report" / "index.html"
            console_module.render_header(state)
            print("ARTEFATOS\n")
            print(f"Workspace : {audit_root}")
            print(f"audit.db  : {audit_root / 'audit.db'}")
            print(f"Relatório : {report if report.is_file() else '<não materializado>'}")
            input("\nENTER para continuar...")


def _audit_history(console_module: ModuleType, state: Any) -> None:
    while True:
        console_module.render_header(state)
        audit_id = _choose_audit(state)
        if audit_id is None:
            return
        _selected_audit_menu(console_module, state, audit_id)


def install(console_module: ModuleType) -> None:
    """Install the task-oriented first level while retaining the complete old dashboard."""
    if getattr(console_module, "_rasai_task_navigation_installed", False):
        return

    original_menu = console_module._menu

    def menu(state: Any) -> str:
        while True:
            console_module.render_header(state)
            print("INÍCIO\n")
            print(f"Projeto atual : {getattr(state, 'project', '') or '<auto>'}")
            print(f"Alvo          : {getattr(state, 'target', '') or '<não informado>'}")
            if getattr(state, "audit_id", ""):
                print(f"Último AUD    : {state.audit_id}")
            print("\n1. Nova auditoria / configurar e executar")
            print("2. Auditorias / histórico")
            print("3. Relatórios consolidados")
            print("4. Integrações / credenciais")
            print("5. Sistema / restaurar padrões")
            print("?. Ajuda")
            print("Q. Sair")
            choice = input("Escolha: ").strip().upper()
            if choice == "1":
                return original_menu(state)
            if choice == "2":
                _audit_history(console_module, state)
                continue
            if choice == "3":
                return "C"
            if choice == "4":
                return "E"
            if choice == "5":
                return "D"
            if choice == "?":
                return "H"
            if choice == "Q":
                return "Q"
            state.error = "opção inválida no menu inicial"

    console_module._menu = menu
    console_module._rasai_task_navigation_installed = True
