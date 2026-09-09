"""Tenant-aware authorization helpers independent from the HTTP framework."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_EXECUTION_CREATE_ROLES = {"OWNER", "ADMIN", "ANALYST", "OPERATOR"}
_EXECUTION_MANAGE_ROLES = {"OWNER", "ADMIN", "OPERATOR"}


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str


class AuthorizationError(PermissionError):
    pass


def _active_user(store: Any, user_id: str) -> bool:
    return any(
        str(row.get("user_id")) == user_id and str(row.get("status", "ACTIVE")).upper() == "ACTIVE"
        for row in store.list_users()
    )


def _memberships(store: Any, principal: Principal) -> list[dict[str, Any]]:
    if not _active_user(store, principal.user_id):
        return []
    return list(store.list_memberships(user_id=principal.user_id))


def accessible_organization_ids(store: Any, principal: Principal) -> set[str]:
    return {str(row["organization_id"]) for row in _memberships(store, principal)}


def accessible_workspace_ids(store: Any, principal: Principal) -> set[str]:
    memberships = _memberships(store, principal)
    workspaces = list(store.list_workspaces())
    projects = list(store.list_projects())
    project_by_id = {item.project_id: item for item in projects}
    workspace_ids: set[str] = set()
    for membership in memberships:
        if membership.get("project_id"):
            project = project_by_id.get(str(membership["project_id"]))
            if project is not None:
                workspace_ids.add(project.workspace_id)
        elif membership.get("workspace_id"):
            workspace_ids.add(str(membership["workspace_id"]))
        else:
            organization_id = str(membership["organization_id"])
            workspace_ids.update(
                workspace.workspace_id
                for workspace in workspaces
                if workspace.organization_id == organization_id and workspace.status == "ACTIVE"
            )
    return workspace_ids


def accessible_project_ids(store: Any, principal: Principal) -> set[str]:
    memberships = _memberships(store, principal)
    workspaces = list(store.list_workspaces())
    projects = list(store.list_projects())
    workspace_by_id = {item.workspace_id: item for item in workspaces}
    project_ids: set[str] = set()
    for membership in memberships:
        if membership.get("project_id"):
            project_ids.add(str(membership["project_id"]))
            continue
        if membership.get("workspace_id"):
            workspace_id = str(membership["workspace_id"])
            project_ids.update(
                project.project_id
                for project in projects
                if project.workspace_id == workspace_id and project.status == "ACTIVE"
            )
            continue
        organization_id = str(membership["organization_id"])
        allowed_workspaces = {
            workspace.workspace_id
            for workspace in workspaces
            if workspace.organization_id == organization_id and workspace.status == "ACTIVE"
        }
        project_ids.update(
            project.project_id
            for project in projects
            if project.workspace_id in allowed_workspaces and project.status == "ACTIVE"
        )
    return {
        project_id
        for project_id in project_ids
        if project_id in {item.project_id for item in projects if item.status == "ACTIVE"}
        and workspace_by_id.get(next(item.workspace_id for item in projects if item.project_id == project_id), None) is not None
    }


def project_roles(store: Any, principal: Principal, project_id: str) -> set[str]:
    projects = {item.project_id: item for item in store.list_projects()}
    project = projects.get(project_id)
    if project is None or project.status != "ACTIVE":
        return set()
    workspaces = {item.workspace_id: item for item in store.list_workspaces()}
    workspace = workspaces.get(project.workspace_id)
    if workspace is None or workspace.status != "ACTIVE":
        return set()
    roles: set[str] = set()
    for membership in _memberships(store, principal):
        if str(membership["organization_id"]) != workspace.organization_id:
            continue
        membership_project = membership.get("project_id")
        membership_workspace = membership.get("workspace_id")
        if membership_project and str(membership_project) != project_id:
            continue
        if not membership_project and membership_workspace and str(membership_workspace) != workspace.workspace_id:
            continue
        roles.add(str(membership["role"]).upper())
    return roles


def require_project_read(store: Any, principal: Principal, project_id: str) -> set[str]:
    roles = project_roles(store, principal, project_id)
    if not roles:
        raise AuthorizationError("project is outside the caller tenancy scope")
    return roles


def require_execution_create(store: Any, principal: Principal, project_id: str) -> set[str]:
    roles = require_project_read(store, principal, project_id)
    if not roles.intersection(_EXECUTION_CREATE_ROLES):
        raise AuthorizationError("caller role cannot create execution jobs")
    return roles


def require_execution_manage(store: Any, principal: Principal, project_id: str) -> set[str]:
    roles = require_project_read(store, principal, project_id)
    if not roles.intersection(_EXECUTION_MANAGE_ROLES):
        raise AuthorizationError("caller role cannot manage execution jobs")
    return roles
