"""Runtime composition for the CAT-03 semantic-corpus invariant."""
from __future__ import annotations

from typing import Any

from rasai.semantic import NoneProvider
from rasai.semantic_corpus import CorpusGuardProvider, prepare_semantic_corpus


def install() -> None:
    """Require a READY whole-audit semantic corpus before M7 can call external AI.

    The selected provider object is not replaced by a CAT-specific adapter. The guard
    delegates to the exact provider/routing session already produced by the global AI
    orchestration, preserving retries, AUTO routing, cost accounting and exchange logs.
    """
    from rasai import audit_runner

    if getattr(audit_runner, "_rasai_semantic_corpus_gate_installed", False):
        return

    original_execute_m7 = audit_runner.execute_m7

    def execute_m7_after_corpus(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        m3_result = kwargs.get("m3_result")
        m4_result = kwargs.get("m4_result")
        persistence = kwargs.get("persistence")
        workspace = kwargs.get("workspace")
        if not audit_id or m3_result is None or m4_result is None or persistence is None or workspace is None:
            raise ValueError("semantic corpus gate requires audit_id, M3/M4 results, persistence and workspace")

        manifest = prepare_semantic_corpus(
            audit_id=audit_id,
            m3_result=m3_result,
            m4_result=m4_result,
            persistence=persistence,
            workspace=workspace,
        )
        selected = kwargs.get("provider") or NoneProvider()
        kwargs["provider"] = CorpusGuardProvider(selected, manifest)
        return original_execute_m7(*args, **kwargs)

    audit_runner.execute_m7 = execute_m7_after_corpus
    audit_runner._rasai_semantic_corpus_gate_installed = True
