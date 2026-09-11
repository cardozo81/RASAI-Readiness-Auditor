"""Small refinements layered on the universal integration-state contract.

Kept separate so the public state contract can remain additive while these details
close presentation regressions discovered by the full suite.
"""
from __future__ import annotations

import sqlite3
from typing import Any


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import integration_state_contract as contract

    original_m24_notice = contract._m24_ai_notice
    original_observability_section = contract._observability_state_section
    original_content_coverage = contract._content_ai_coverage

    def technical_ai_notice(data):
        return original_m24_notice(data).replace(
            "data-integration-state='m24-technical-ai'",
            "data-integration-state='technical-ai'",
        )

    def observability_section(attempts):
        html = original_observability_section(attempts)
        old = "Nenhum desses estados é convertido em finding do website.</p>"
        new = (
            "Nenhum desses estados é convertido em finding do website. "
            "Esses estados descrevem a coleta, não a qualidade do website.</p>"
        )
        return html.replace(old, new, 1)

    def content_coverage(connection: sqlite3.Connection, audit_id: str, Coverage: Any):
        try:
            run = connection.execute(
                "SELECT * FROM content_remediation_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            run = None
        if run is not None:
            try:
                status = str(run["status"] or "").upper()
                eligible = int(run["eligible_findings"] or 0)
                reason = str(run["reason"] or "").strip()
            except (KeyError, IndexError, TypeError, ValueError):
                status, eligible, reason = "", 0, ""
            if status == "NO_SAFE_SUGGESTIONS":
                suffix = f" Motivo persistido: {reason}." if reason else ""
                return Coverage(
                    "Remediação textual por IA",
                    "Sim",
                    "SEM SAÍDA SEGURA",
                    f"A remediação foi executada para {eligible} finding(s) elegível(is), mas nenhuma sugestão passou pelos controles de segurança/contrato. Isso não é, por si só, falha do provider.{suffix}",
                )
        return original_content_coverage(connection, audit_id, Coverage)

    contract._m24_ai_notice = technical_ai_notice
    contract._observability_state_section = observability_section
    contract._content_ai_coverage = content_coverage
    _INSTALLED = True
