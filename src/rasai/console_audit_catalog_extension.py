"""Interactive additive catalog extension for an already-complete AUD."""
from __future__ import annotations

import os
from pathlib import Path
import traceback
from typing import Any

from rasai.audit_catalog import AI_NONE, CATALOGS
from rasai.audit_configuration_reuse import KIND_CONSOLE, load_reusable_audit_configuration
from rasai.audit_catalog_extension import (
    apply_catalog_extension,
    effective_catalog_ids,
    extension_readiness,
)
from rasai.console_confirmation_contract import confirm_continue
from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint
from rasai.persistence import AuditWorkspace


def _load_audit_configuration(state: Any, audit_id: str, console_module: Any) -> tuple[str, ...]:
    """Load the immutable AUD snapshot for extension without arming a new-AUD lineage."""
    from rasai import audit_configuration_reuse_console as reuse
    from rasai.console_catalog_plan import set_selected_catalog_ids

    source = load_reusable_audit_configuration(
        state.audits_root,
        audit_id,
        expected_kind=KIND_CONSOLE,
    )
    warnings = list(reuse._apply_settings(state, source.configuration, source.audit_id))
    try:
        warnings.extend(reuse._dependency_warnings(state, console_module))
    except Exception:
        pass

    workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
    set_selected_catalog_ids(state, effective_catalog_ids(workspace, audit_id))
    return tuple(dict.fromkeys(str(value) for value in warnings if str(value)))


def availability(state: Any, audit_id: str) -> tuple[bool, str]:
    root = Path(state.audits_root) / audit_id
    if not (root / "audit.db").is_file():
        return False, "audit.db não encontrado"
    try:
        workspace = AuditWorkspace.open(root)
        selected = set(effective_catalog_ids(workspace, audit_id))
    except (OSError, ValueError):
        return False, "não foi possível ler o catálogo efetivo da AUD"
    missing = tuple(item.id for item in CATALOGS if item.id not in selected)
    if not missing:
        return False, "todos os catálogos já pertencem a esta AUD"
    try:
        load_reusable_audit_configuration(
            state.audits_root,
            audit_id,
            expected_kind=KIND_CONSOLE,
        )
    except (FileNotFoundError, OSError, ValueError):
        return False, "snapshot canônico de configuração indisponível"
    return True, f"{len(missing)} catálogo(s) ainda podem ser acrescentados"


def _added_catalogs(state: Any, base: set[str]) -> tuple[str, ...]:
    from rasai.console_catalog_plan import selected_catalog_ids
    selected = set(selected_catalog_ids(state))
    return tuple(item.id for item in CATALOGS if item.id in selected - base)


def _canonical_extension_audit_device(
    workspace: AuditWorkspace,
    audits_root: str | Path,
    audit_id: str,
) -> str | None:
    """Resolve a single historical AUD device without inventing one.

    New CAT-06/CAT-07 populations may only be attached when every durable source
    agrees on one core device. Historical BOTH remains readable/reprocessable, but
    it is intentionally ambiguous for creating a new synthetic population.
    """
    devices: set[str] = set()

    try:
        source = load_reusable_audit_configuration(
            audits_root,
            audit_id,
            expected_kind=KIND_CONSOLE,
        )
        settings = source.configuration.get("settings")
        if isinstance(settings, dict):
            console = settings.get("console")
            environment = settings.get("environment")
            for raw in (
                console.get("device") if isinstance(console, dict) else None,
                environment.get("RASAI_DEVICE_CONTEXT") if isinstance(environment, dict) else None,
            ):
                normalized = str(raw or "").strip().upper()
                if normalized == "BOTH":
                    devices.update(("MOBILE", "DESKTOP"))
                elif normalized in {"MOBILE", "DESKTOP", "TABLET"}:
                    devices.add(normalized)
    except (FileNotFoundError, OSError, TypeError, ValueError):
        pass

    try:
        from rasai.audit_resume_runtime import expected_devices_for_audit

        devices.update(
            str(value).strip().upper()
            for value in expected_devices_for_audit(workspace, audit_id)
            if str(value).strip()
        )
    except (OSError, TypeError, ValueError):
        pass

    connection = None
    try:
        import sqlite3

        connection = sqlite3.connect(workspace.database)
        rows = connection.execute(
            """SELECT DISTINCT ps.device
               FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchall()
        devices.update(
            str(row[0]).strip().upper()
            for row in rows
            if row and str(row[0]).strip()
        )
    except sqlite3.OperationalError:
        pass
    finally:
        if connection is not None:
            connection.close()

    if devices == {"MOBILE"}:
        return "mobile"
    if devices == {"DESKTOP"}:
        return "desktop"
    return None


def _initialize_new_apdex_catalog_defaults(state: Any, catalog_id: str) -> None:
    """Start a newly-added APDEX catalog from current canonical defaults.

    Existing catalogs remain immutable. Once the operator edits the new catalog, its
    effective values are frozen into the extension work item and reused by every RPR.
    """
    import math
    from rasai.device_context import canonical_single_device_mix

    if catalog_id == "CAT-06":
        from rasai.m23_cli import DEFAULT_APDEX_SAMPLES_PER_CONTEXT

        state.synthetic_apdex = True
        state.apdex_samples = DEFAULT_APDEX_SAMPLES_PER_CONTEXT
        state.apdex_max_attempts = max(
            state.apdex_samples,
            int(math.ceil(state.apdex_samples * 1.25)),
        )
        if getattr(state, "apdex_threshold", None) is None:
            state.apdex_threshold = 3.0
    elif catalog_id == "CAT-07":
        from rasai.m25_cli import DEFAULT_UX_SAMPLES

        state.apdex_experience = True
        state.apdex_experience_samples = DEFAULT_UX_SAMPLES
        state.apdex_experience_max_attempts = max(
            state.apdex_experience_samples,
            int(math.ceil(state.apdex_experience_samples * 1.25)),
        )
        state.apdex_experience_device_mix = canonical_single_device_mix(
            str(getattr(state, "device", "mobile"))
        )


def _render_catalogs(state: Any, base: set[str]) -> None:
    from rasai.console_catalog_plan import catalog_status, is_selected

    print("\nCATÁLOGOS")
    print("-" * 100)
    for index, item in enumerate(CATALOGS, 1):
        selected = is_selected(state, item.id)
        if item.id in base:
            marker = "ORIGINAL/PRESERVADO"
            tone = DIM
        elif selected:
            marker = "NOVO"
            tone = GREEN
        else:
            marker = "DISPONÍVEL"
            tone = DIM
        status, _detail = catalog_status(state, item)
        print(
            f"{index:>2}. {item.id} · {item.label:<34} "
            + paint(f"[{marker}]", tone)
            + " "
            + paint(status, RED if status == "BLOQUEADO" else (YELLOW if "LIMITA" in status else DIM))
        )


def _configure_ai(console_module: Any, state: Any) -> None:
    """Reuse the canonical AI editor; no extension-specific provider surface."""
    try:
        console_module._configure(state, "4")
    except Exception as exc:
        state.error = f"Não foi possível abrir a configuração de IA: {exc}"


def _choose_ai_mode(state: Any, added: tuple[str, ...]) -> bool | None:
    from rasai.audit_catalog import CATALOG_BY_ID
    from rasai.console_catalog_plan import ai_provider_readiness

    ai_catalogs = tuple(
        CATALOG_BY_ID[catalog_id]
        for catalog_id in added
        if CATALOG_BY_ID[catalog_id].ai_mode != AI_NONE
    )
    if not ai_catalogs:
        return False

    print("\nMODO DA COMPLEMENTAÇÃO")
    print("-" * 100)
    print("1. Complementar com IA quando aplicável")
    print("2. Complementar sem IA")
    print("V. Voltar")
    while True:
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw == "2":
            return False
        if raw == "1":
            ready, detail = ai_provider_readiness(state)
            if not ready:
                state.error = (
                    "IA foi solicitada para esta complementação, mas a IA principal não está apta"
                    + (f": {detail}" if detail else "")
                    + ". Configure a IA ou escolha complementar sem IA."
                )
                return None
            return True
        state.error = "Opção inválida."


def _record_extension_console_failure(state: Any, audit_id: str, exc: BaseException) -> str:
    """Persist an unexpected extension failure and return a redacted UI message."""
    try:
        from rasai.secret_safety import redact_text

        message = redact_text(f"{type(exc).__name__}: {exc}")[:1000]
        stack = redact_text(traceback.format_exc(limit=12))[:4000]
    except Exception:
        message = f"{type(exc).__name__}: {str(exc)[:900]}"
        stack = traceback.format_exc(limit=12)[:4000]
    try:
        workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
        from rasai.operational_log import try_append_operational_event

        try_append_operational_event(
            workspace,
            "AUDIT_CATALOG_EXTENSION_CONSOLE_FAILURE",
            level="ERROR",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=message,
            traceback=stack,
        )
    except Exception:
        # UI containment must not fail because the diagnostic sink is unavailable.
        pass
    return message


def complement_audit(console_module: Any, state: Any, audit_id: str) -> bool:
    """Add CAT-* scope to the same AUD without rewriting its initial plan.

    Returns True when one extension RPR was executed/materialized.
    """
    from rasai.console_catalog_plan import (
        catalog_status,
        deselect_catalog,
        is_selected,
        select_catalog,
        select_all_unselected_catalogs,
        set_ai_execution_enabled,
        set_selected_catalog_ids,
    )
    from rasai.console_catalog_ui import catalog_menu

    workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
    base = set(effective_catalog_ids(workspace, audit_id))
    if len(base) >= len(CATALOGS):
        state.error = "Todos os catálogos já pertencem a esta AUD."
        return False

    try:
        warnings = _load_audit_configuration(state, audit_id, console_module)
    except (FileNotFoundError, OSError, ValueError) as exc:
        state.error = f"Complementação indisponível: {exc}"
        return False
    # Effective selection may include prior extensions that are not part of the
    # immutable initial snapshot loaded above.
    set_selected_catalog_ids(state, tuple(item.id for item in CATALOGS if item.id in base))
    audit_device = _canonical_extension_audit_device(
        workspace,
        state.audits_root,
        audit_id,
    )
    if audit_device is not None:
        state.device = audit_device
        if hasattr(state, "current_device"):
            state.current_device = audit_device.upper()
    bulk_notice = ""

    while True:
        console_module.render_header(state)
        print(paint("AUDITORIAS / HISTÓRICO > COMPLEMENTAR AUDITORIA", CYAN, bold=True))
        print("=" * 100)
        print(f"Audit ID             : {audit_id}")
        print("Contrato inicial     : preservado; esta operação cria uma extensão aditiva RPR-*.")
        print("Regra                : catálogos existentes não podem ser removidos nem reconfigurados.")
        if warnings:
            print(paint("Atenção              : " + "; ".join(warnings), YELLOW))
        if state.error:
            print(paint("INFO                 : " + str(state.error), YELLOW))
        _render_catalogs(state, base)

        added = _added_catalogs(state, base)
        print("\nSELEÇÃO NOVA")
        print("-" * 100)
        print(", ".join(added) if added else "<nenhum catálogo novo>")
        if bulk_notice:
            print(paint(bulk_notice, DIM))
        print("\nAÇÕES")
        print("-" * 100)
        print("1-10. Adicionar/configurar catálogo ainda não pertencente à AUD")
        print("T. Marcar todos os catálogos ainda não pertencentes à AUD")
        if added:
            print("R. Aplicar complementação nesta AUD")
            print("X. Remover um catálogo NOVO da seleção")
        print("A. Ajustar IA principal")
        print("V. Voltar sem alterar a AUD")

        raw = input("Escolha: ").strip().upper()
        state.error = ""
        if raw == "V":
            return False
        if raw == "A":
            _configure_ai(console_module, state)
            continue
        if raw == "T":
            excluded = set(base)
            if audit_device is None:
                excluded.update({"CAT-06", "CAT-07"})
            newly = select_all_unselected_catalogs(state, excluded_catalog_ids=excluded)
            current = set(_added_catalogs(state, base)) | base
            set_selected_catalog_ids(
                state,
                tuple(item.id for item in CATALOGS if item.id in current),
            )
            for catalog_id in tuple(item for item in newly if item not in base):
                _initialize_new_apdex_catalog_defaults(state, catalog_id)
            bulk_notice = f"{len(tuple(item for item in newly if item not in base))} catálogo(s) novo(s) marcado(s)."
            continue
        if raw == "X" and added:
            print("Novos selecionados: " + ", ".join(f"{i+1}={value}" for i,value in enumerate(added)))
            value = input("Número do catálogo novo a remover (V=voltar): ").strip().upper()
            if value == "V":
                continue
            try:
                catalog_id = added[int(value)-1]
            except (ValueError, IndexError):
                state.error = "Seleção inválida."
                continue
            catalog = next(item for item in CATALOGS if item.id == catalog_id)
            deselect_catalog(state, catalog)
            # Dependencies may try to cascade; immutable/base catalogs are restored.
            current = set(_added_catalogs(state, base)) | base
            set_selected_catalog_ids(state, tuple(item.id for item in CATALOGS if item.id in current))
            continue
        if raw == "R" and added:
            if set(added) & {"CAT-06", "CAT-07"} and audit_device is None:
                state.error = (
                    "CAT-06/CAT-07 não podem ser acrescentados a esta AUD: "
                    "o device histórico não é unívoco (é necessário provar somente Mobile ou somente Desktop)."
                )
                continue
            try:
                blockers = []
                for catalog_id in added:
                    catalog = next(item for item in CATALOGS if item.id == catalog_id)
                    status, detail = catalog_status(state, catalog)
                    if status == "BLOQUEADO":
                        blockers.append(f"{catalog_id}: {detail}")
                if blockers:
                    state.error = "Complementação bloqueada: " + "; ".join(blockers)
                    continue

                use_ai = _choose_ai_mode(state, added)
                if use_ai is None:
                    continue
                set_ai_execution_enabled(state, use_ai)
                if not confirm_continue(
                    "Aplicar os novos catálogos na mesma AUD preservando todos os resultados já concluídos",
                    back_label="Voltar sem complementar a AUD",
                ):
                    state.error = "Complementação cancelada; nenhum dado da AUD foi alterado."
                    continue
                result = apply_catalog_extension(state=state, audit_id=audit_id)
            except SystemExit as exc:
                # Catalog readiness/configuration helpers can also invoke nested CLI
                # surfaces. Any SystemExit in the entire apply action is recoverable
                # here and must never terminate the interactive host.
                diagnostic = _record_extension_console_failure(state, audit_id, exc)
                state.error = (
                    "Complementação interrompida por saída inesperada do runtime; "
                    "a sessão foi preservada. "
                    f"Diagnóstico registrado: {diagnostic}"
                )
                continue
            except Exception as exc:
                # Keep the interactive shell alive, but do not hide the defect:
                # type/message/traceback are persisted in the operational log.
                diagnostic = _record_extension_console_failure(state, audit_id, exc)
                state.error = (
                    "Complementação não concluída; a sessão foi preservada. "
                    f"Diagnóstico registrado: {diagnostic}"
                )
                continue
            from rasai.console_runtime import clear_runtime_progress

            state.audit_id = audit_id
            state.status = str(result.processing_status)
            clear_runtime_progress(state)
            state.operation = "LOCAL:MENU"
            state.error = ""
            return True

        try:
            index = int(raw)
        except ValueError:
            state.error = "Ação inválida."
            continue
        if not 1 <= index <= len(CATALOGS):
            state.error = "Catálogo inválido."
            continue
        catalog = CATALOGS[index-1]
        if catalog.id in {"CAT-06", "CAT-07"} and audit_device is None:
            state.error = (
                f"{catalog.id} indisponível para complemento: a AUD histórica não possui "
                "um único device comprovado (Mobile ou Desktop)."
            )
            continue
        if catalog.id in base:
            state.error = (
                f"{catalog.id} já pertence à AUD e está preservado; "
                "a complementação não altera configuração/resultados existentes."
            )
            continue
        if not is_selected(state, catalog.id):
            try:
                select_catalog(state, catalog)
                _initialize_new_apdex_catalog_defaults(state, catalog.id)
            except ValueError as exc:
                state.error = str(exc)
                continue
        catalog_menu(console_module, state, catalog)
        # Restore every immutable catalog in case a dependency action attempted to
        # modify the plan indirectly.
        current = set(_added_catalogs(state, base)) | base
        set_selected_catalog_ids(state, tuple(item.id for item in CATALOGS if item.id in current))


__all__ = ["availability", "complement_audit"]
