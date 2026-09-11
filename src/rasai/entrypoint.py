"""Top-level RASAi command router.

Specialist commands are intercepted here. Audit commands are delegated to the
current audit CLI composition and finalized through the canonical report gate.
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Sequence

from rasai import cli_extensions
from rasai.ai_efficiency_policy import install as install_ai_efficiency_policy
from rasai.context_scope_runtime import install as install_context_scope_runtime
from rasai.external_measurement_runtime import install as install_external_measurement_runtime
from rasai.integration_state_contract import install as install_integration_state_contract
from rasai.integration_state_refinements import install as install_integration_state_refinements
from rasai.provider_presentation_alignment import install as install_provider_presentation_alignment
from rasai.report_observation_reconciliation import install as install_report_observation_reconciliation
from rasai.report_registry import install as install_report_registry
from rasai.runtime_adherence_extensions import install_runtime_adherence_extensions
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.runtime_contract_compatibility import install_runtime_contract_compatibility

_LOGGER = logging.getLogger(__name__)
_REPORT_PROJECTION_INCOMPLETE_EXIT = 3


def _audits_root(argv: list[str]) -> Path:
    for index, value in enumerate(argv):
        if value == "--audits-root" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--audits-root="):
            return Path(value.split("=", 1)[1])
    return Path("audits")


def _try_refresh_platform_index(argv: list[str]) -> None:
    try:
        from rasai.platform.database import open_platform_store
        from rasai.platform.indexing import index_audits
        root = _audits_root(argv)
        with open_platform_store(audits_root=root) as store:
            index_audits(store, root, strict=False)
    except Exception:
        _LOGGER.exception("RASAi platform index refresh failed after successful audit")


def _run_audit_and_finalize(effective: list[str]) -> int:
    from rasai import m9
    from rasai.ai_exchange_log import persist_ai_exchange_log
    from rasai.ai_execution_state import consume_current_ai_execution
    from rasai.m18_ai import provider_session_snapshot
    from rasai.persistence import AuditWorkspace
    from rasai.report_completion import finalize_audit_report_site
    from rasai.score_geo_004_reporting import REPORT_FILE

    original_run_audit = cli_extensions._audit_cli.run_audit
    original_score_writer = m9.write_score_geo_004_report
    captured: list[object] = []

    def capture_run(*args, **kwargs):
        result = original_run_audit(*args, **kwargs)
        captured.append(result)
        return result

    def defer_score_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
        return workspace.root / "report" / REPORT_FILE

    cli_extensions._audit_cli.run_audit = capture_run
    m9.write_score_geo_004_report = defer_score_report
    try:
        code = cli_extensions.main(effective)
    finally:
        cli_extensions._audit_cli.run_audit = original_run_audit
        m9.write_score_geo_004_report = original_score_writer

    execution = consume_current_ai_execution()
    if code != 0 or not captured:
        return code

    result = captured[-1]
    try:
        workspace = AuditWorkspace.open(result.audit_root)
        context_interpretations = ()
        routing_snapshot = None
        if execution is not None:
            persist_ai_exchange_log(audit_id=result.audit_id, workspace=workspace, recorder=execution.recorder)
            context_interpretations = execution.recorder.context_interpretations
            routing_snapshot = provider_session_snapshot(execution.provider)
        completion = finalize_audit_report_site(
            audit_id=result.audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
    except Exception:
        _LOGGER.exception("Final audit report materialization gate failed")
        print("Relatórios HTML: INCOMPLETOS - falha ao validar/materializar o mini-site final. O audit.db já persistido foi preservado; consulte logs/audit.log.")
        return _REPORT_PROJECTION_INCOMPLETE_EXIT

    for issue in completion.renderer_errors:
        _LOGGER.warning("Audit report renderer issue during final repair: %s", issue)
    if completion.missing_pages:
        missing = ", ".join(completion.missing_pages)
        _LOGGER.error("Expected audit report pages were not materialized: %s", missing)
        print(f"Relatórios HTML: INCOMPLETOS - páginas esperadas não foram materializadas: {missing}. O audit.db foi preservado.")
        return _REPORT_PROJECTION_INCOMPLETE_EXIT
    print(f"Relatórios HTML: COMPLETOS ({len(completion.expected_pages)} página(s) esperada(s) para esta execução).")
    if completion.renderer_errors:
        print("Relatórios HTML: houve falha de enriquecimento reparável em um ou mais renderizadores; as páginas canônicas esperadas existem e o detalhe foi registrado no log.")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    install_report_registry()
    install_context_scope_runtime()
    install_external_measurement_runtime()
    install_ai_efficiency_policy()
    install_runtime_completion_extensions()
    install_report_observation_reconciliation()
    install_runtime_adherence_extensions()
    install_integration_state_contract()
    install_integration_state_refinements()
    install_runtime_contract_compatibility()
    install_provider_presentation_alignment()
    effective = list(argv) if argv is not None else list(sys.argv[1:])
    if effective and effective[0] in {"search", "serp"}:
        from rasai.search_intelligence.cli import main as search_main
        return search_main(effective[1:])
    if effective and effective[0] in {"search-history", "search_history"}:
        from rasai.search_intelligence.history_cli import main as search_history_main
        return search_history_main(effective[1:])
    if effective and effective[0] in {"search-monitor", "search_monitor"}:
        from rasai.search_intelligence.monitoring_cli import main as search_monitor_main
        return search_monitor_main(effective[1:])
    if effective and effective[0] in {"property-config", "property_config"}:
        from rasai.property_config_cli import main as property_config_main
        return property_config_main(effective[1:])
    if effective and effective[0] == "api":
        try:
            from rasai.web.cli import main as api_main
        except ImportError as exc:
            raise SystemExit("RASAi web dependencies are not installed; install with: pip install -e '.[web]'") from exc
        return api_main(effective[1:])
    if effective and effective[0] == "worker":
        from rasai.worker_cli import main as worker_main
        return worker_main(effective[1:])
    if effective and effective[0] == "visibility":
        from rasai.m26_cli import main as visibility_main
        return visibility_main(effective[1:])
    if effective and effective[0] == "scoring":
        from rasai.score_geo_004_cli import main as scoring_main
        return scoring_main(effective[1:])
    if effective and effective[0] == "monitor":
        from rasai.monitoring.cli import main as monitoring_main
        return monitoring_main(effective[1:])
    if effective and effective[0] in {"observe", "observability"}:
        from rasai.observability.cli import main as observability_main
        return observability_main(effective[1:])
    if effective and effective[0] == "quality":
        from rasai.quality.cli import main as quality_main
        return quality_main(effective[1:])
    if effective and effective[0] == "platform":
        from rasai.platform.canonical_cli import main as platform_main
        return platform_main(effective[1:])
    if effective and effective[0] == "audit":
        code = _run_audit_and_finalize(effective)
        if code == 0:
            _try_refresh_platform_index(effective)
        return code
    return cli_extensions.main(effective)
