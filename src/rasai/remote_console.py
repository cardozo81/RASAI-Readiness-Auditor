"""Small interactive client for a hosted RASAi control plane.

This is deliberately an opt-in control-plane console, not a second audit engine. It
uses the same HTTP API as the browser. Local ``rasai-console`` behavior remains the
default and unchanged unless ``RASAI_CONSOLE_MODE=remote`` is explicitly selected.
"""
from __future__ import annotations

from typing import Any

from .remote_client import RemoteApiError, RemoteClient, RemoteSettings


def _choose(items: list[dict[str, Any]], id_key: str, label_key: str, title: str) -> dict[str, Any] | None:
    if not items:
        print(f"Nenhum {title.lower()} acessível.")
        return None
    print(f"\n{title}")
    for index, item in enumerate(items, 1):
        print(f"{index}. {item.get(label_key) or item.get(id_key)}")
    print("V. Voltar")
    while True:
        value = input("> ").strip()
        if value.casefold() == "v":
            return None
        if value.isdigit() and 1 <= int(value) <= len(items):
            return items[int(value) - 1]
        print("Opção inválida.")


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
    if not schedules:
        print("Nenhum agendamento.")
        return
    print("\nAGENDAMENTOS")
    for item in schedules:
        print(
            f"{item['schedule_id']} | {item['name']} | {item['status']} | "
            f"próxima={item.get('next_run_at') or '-'} | URLs={len(item.get('urls') or [])}"
        )


def _show_jobs(client: RemoteClient, project_id: str) -> None:
    jobs = list(client.get(f"/api/v1/projects/{project_id}/execution-jobs", query={"limit": 50}))
    if not jobs:
        print("Nenhuma execução.")
        return
    print("\nEXECUÇÕES")
    for item in jobs:
        print(f"{item['job_id']} | {item['job_type']} | {item['status']} | tentativas={item['attempts']}/{item['max_attempts']}")


def _show_consumption(client: RemoteClient, organization_id: str, project_id: str) -> None:
    data = client.get(
        f"/api/v1/organizations/{organization_id}/consumption",
        query={"project_id": project_id, "group_by": "property,user,provider,category"},
    )
    summary = data["summary"]
    print("\nCONSUMO")
    print(f"eventos={summary['event_count']} falhas={summary['failure_count']} retries={summary['retry_count']} tokens={summary['total_tokens']}")
    print(f"quantidade={summary['quantity_by_unit']}")
    print(f"custo conhecido={summary['cost_by_currency']} | eventos sem custo={summary['cost_unknown_events']}")


def main() -> int:
    try:
        client = RemoteClient(RemoteSettings.from_environment())
        me = client.get("/api/v1/me")
    except (ValueError, RemoteApiError) as exc:
        print(f"Falha ao conectar ao RASAi remoto: {exc}")
        return 2
    print("RASAi Console — modo remoto")
    print(f"Usuário: {me.get('user_id')}")
    while True:
        print("\nAÇÕES")
        print("P. Selecionar projeto e consultar")
        print("Q. Sair")
        choice = input("> ").strip().casefold()
        if choice == "q":
            return 0
        if choice != "p":
            print("Opção inválida.")
            continue
        try:
            context = _project_context(client)
            if context is None:
                continue
            org, project = context
            while True:
                print("\nPROJETO REMOTO")
                print("S. Agendamentos")
                print("E. Execuções")
                print("C. Consumo")
                print("V. Voltar")
                action = input("> ").strip().casefold()
                if action == "v":
                    break
                if action == "s":
                    _show_schedules(client, project["project_id"])
                elif action == "e":
                    _show_jobs(client, project["project_id"])
                elif action == "c":
                    _show_consumption(client, org["organization_id"], project["project_id"])
                else:
                    print("Opção inválida.")
        except RemoteApiError as exc:
            print(f"Falha na operação remota: {exc}")
