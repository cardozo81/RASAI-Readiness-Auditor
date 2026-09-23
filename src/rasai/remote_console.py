"""Small interactive client for a hosted RASAi control plane.

This is deliberately an opt-in control-plane console, not a second audit engine. It
uses the same HTTP API as the browser. Local ``rasai-console`` behavior remains the
default and unchanged unless ``RASAI_CONSOLE_MODE=remote`` is explicitly selected.
"""
from __future__ import annotations

from typing import Any

from rasai.console_ui import CYAN, GREEN, RED, YELLOW, paint

from .remote_client import RemoteApiError, RemoteClient, RemoteSettings


def _message(kind: str, text: str) -> None:
    normalized = kind.strip().upper()
    color = {"OK": GREEN, "INFO": CYAN, "ALERTA": YELLOW, "ERRO": RED}.get(normalized, CYAN)
    print(f"{paint(f'{normalized:<10}', color, bold=True)} : {text}")


def _heading(title: str) -> None:
    print("\n" + paint(title, CYAN, bold=True))
    print("-" * 80)


def _choose(items: list[dict[str, Any]], id_key: str, label_key: str, title: str) -> dict[str, Any] | None:
    if not items:
        _message("INFO", f"Nenhum item disponível em {title} para o usuário atual.")
        return None
    _heading(title.upper())
    for index, item in enumerate(items, 1):
        print(f"{index}. {item.get(label_key) or item.get(id_key)}")
    print("V. Voltar sem selecionar")
    while True:
        value = input("Escolha: ").strip()
        if value.casefold() == "v":
            return None
        if value.isdigit() and 1 <= int(value) <= len(items):
            return items[int(value) - 1]
        _message("ERRO", "Opção não reconhecida. Escolha um número exibido ou V para voltar.")


def _project_context(client: RemoteClient) -> tuple[dict[str, Any], dict[str, Any]] | None:
    org = _choose(list(client.get("/api/v1/organizations")), "organization_id", "name", "Organizações")
    if org is None:
        return None
    workspaces = list(client.get(f"/api/v1/organizations/{org['organization_id']}/workspaces"))
    workspace = _choose(workspaces, "workspace_id", "name", "Workspaces")
    if workspace is None:
        return None
    projects = list(client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/projects"))
    project = _choose(projects, "project_id", "name", "Projetos")
    if project is None:
        return None
    return org, project


def _show_schedules(client: RemoteClient, project_id: str) -> None:
    schedules = list(client.get(f"/api/v1/projects/{project_id}/schedules"))
    _heading("REMOTO > AGENDAMENTOS")
    if not schedules:
        _message("INFO", "Nenhum agendamento foi encontrado para este projeto.")
        return
    for item in schedules:
        print(
            f"{item['schedule_id']} | {item['name']} | {item['status']} | "
            f"próxima={item.get('next_run_at') or '-'} | URLs={len(item.get('urls') or [])}"
        )


def _show_jobs(client: RemoteClient, project_id: str) -> None:
    jobs = list(client.get(f"/api/v1/projects/{project_id}/execution-jobs", query={"limit": 50}))
    _heading("REMOTO > EXECUÇÕES")
    if not jobs:
        _message("INFO", "Nenhuma execução foi encontrada para este projeto.")
        return
    for item in jobs:
        print(
            f"{item['job_id']} | {item['job_type']} | {item['status']} | "
            f"tentativas={item['attempts']}/{item['max_attempts']}"
        )


def _show_consumption(client: RemoteClient, organization_id: str, project_id: str) -> None:
    data = client.get(
        f"/api/v1/organizations/{organization_id}/consumption",
        query={"project_id": project_id, "group_by": "property,user,provider,category"},
    )
    summary = data["summary"]
    _heading("REMOTO > CONSUMO")
    print(
        f"Eventos       : {summary['event_count']} | Falhas: {summary['failure_count']} | "
        f"Retentativas: {summary['retry_count']} | Tokens: {summary['total_tokens']}"
    )
    print(f"Quantidade    : {summary['quantity_by_unit']}")
    print(
        f"Custo conhecido: {summary['cost_by_currency']} | "
        f"Eventos sem custo conhecido: {summary['cost_unknown_events']}"
    )


def main() -> int:
    try:
        client = RemoteClient(RemoteSettings.from_environment())
        me = client.get("/api/v1/me")
    except (ValueError, RemoteApiError) as exc:
        _message("ERRO", f"Não foi possível conectar ao RASAi remoto. Detalhe: {exc}")
        return 2

    print(paint("RASAi Console — modo remoto", CYAN, bold=True))
    print(f"Usuário: {me.get('user_id')}")
    while True:
        _heading("AÇÕES")
        print("P. Selecionar projeto remoto e abrir consultas")
        print("Q. Sair do console remoto")
        choice = input("Escolha: ").strip().casefold()
        if choice == "q":
            return 0
        if choice != "p":
            _message("ERRO", "Opção não reconhecida. Use P para selecionar um projeto ou Q para sair.")
            continue
        try:
            context = _project_context(client)
            if context is None:
                continue
            org, project = context
            while True:
                _heading("PROJETO REMOTO > AÇÕES")
                print("S. Consultar agendamentos deste projeto")
                print("E. Consultar execuções deste projeto")
                print("C. Consultar consumo deste projeto")
                print("V. Voltar ao menu remoto")
                action = input("Escolha: ").strip().casefold()
                if action == "v":
                    break
                if action == "s":
                    _show_schedules(client, project["project_id"])
                elif action == "e":
                    _show_jobs(client, project["project_id"])
                elif action == "c":
                    _show_consumption(client, org["organization_id"], project["project_id"])
                else:
                    _message("ERRO", "Opção não reconhecida. Use S, E, C ou V conforme as ações exibidas.")
        except RemoteApiError as exc:
            _message("ERRO", f"A operação remota não pôde ser concluída. Detalhe: {exc}")
