from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from rasai.core_reprocessing_context import (
    _CONTEXT,
    _CoreReprocessContext,
    _install_contextual_hooks,
)


def _module_and_core():
    calls: list[tuple[str, str]] = []

    def start(_workspace, audit_id, *args, **kwargs):
        calls.append(("start", audit_id))
        return f"ORIGINAL-{audit_id}"

    def finish(_workspace, reprocess_id, *args, **kwargs):
        calls.append(("finish", reprocess_id))
        return f"FINISHED-{reprocess_id}"

    def latest(_workspace, audit_id):
        return (
            SimpleNamespace(component="HTTP_ACQUISITION", scope_key=audit_id),
            SimpleNamespace(component="SEMANTIC_AI", scope_key=audit_id),
            SimpleNamespace(component="WEB_PERFORMANCE", scope_key=audit_id),
        )

    module = SimpleNamespace(
        start_reprocess_run=start,
        finish_reprocess_run=finish,
        _latest_pending=latest,
    )
    core = SimpleNamespace(
        CORE_COMPONENTS={"HTTP_ACQUISITION"},
        _AI_COMPONENTS={"SEMANTIC_AI"},
        _core_unresolved=lambda _workspace, _audit_id: True,
    )
    _install_contextual_hooks(module, core)
    return module, calls


def test_contextual_hooks_do_not_mutate_per_execution_function_bindings() -> None:
    module, _calls = _module_and_core()
    start_identity = module.start_reprocess_run
    finish_identity = module.finish_reprocess_run
    latest_identity = module._latest_pending

    token = _CONTEXT.set(_CoreReprocessContext("AUD-A", "RPR-A"))
    try:
        assert module.start_reprocess_run(object(), "AUD-A") == "RPR-A"
        pending = module._latest_pending(object(), "AUD-A")
        assert tuple(item.component for item in pending) == ("SEMANTIC_AI", "WEB_PERFORMANCE")
    finally:
        _CONTEXT.reset(token)

    assert module.start_reprocess_run is start_identity
    assert module.finish_reprocess_run is finish_identity
    assert module._latest_pending is latest_identity
    assert module.start_reprocess_run(object(), "AUD-A") == "ORIGINAL-AUD-A"


def test_two_concurrent_aud_contexts_never_share_reprocess_id_or_filter_state() -> None:
    module, calls = _module_and_core()

    def run(audit_id: str, reprocess_id: str):
        token = _CONTEXT.set(_CoreReprocessContext(audit_id, reprocess_id))
        try:
            selected = module.start_reprocess_run(object(), audit_id)
            pending = tuple(item.component for item in module._latest_pending(object(), audit_id))
            return selected, pending
        finally:
            _CONTEXT.reset(token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run, "AUD-A", "RPR-A")
        future_b = executor.submit(run, "AUD-B", "RPR-B")
        result_a = future_a.result()
        result_b = future_b.result()

    assert result_a == ("RPR-A", ("SEMANTIC_AI", "WEB_PERFORMANCE"))
    assert result_b == ("RPR-B", ("SEMANTIC_AI", "WEB_PERFORMANCE"))
    # Neither contextual execution fell through to the shared original starter.
    assert not [entry for entry in calls if entry[0] == "start"]
