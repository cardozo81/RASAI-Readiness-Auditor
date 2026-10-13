"""Issue #524: truthful progress for optional post-core Search Intelligence.

No database, subprocess, browser, HTTP request, or paid provider is used.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType
import unittest
from unittest.mock import patch

from rasai import console_progress_model, console_runtime
from rasai.console_governed_progress import _canonical_phase
from rasai.console_search_intelligence import SearchConsoleState, install
from rasai.execution_progress_presentation import render_canonical_progress


def _console(core_status: str, frames: list[tuple[str, object]]) -> ModuleType:
    module = ModuleType("fake_console_524")
    module._menu = lambda _state: "Q"
    module._configure = lambda _state, _choice: None
    module._execution_readiness = lambda _state: (True, "")
    module._render_actual_usage = lambda _state: None
    module.preflight = lambda _state: ("https://example.test/",)

    def core_run(state):
        state.status = core_status
        state.operation = "LOCAL:DONE"
        console_runtime.set_runtime_progress(
            state, "Concluído com limitações" if core_status != "COMPLETE" else "Concluído",
            100.0, exact=True, detail="processo finalizado",
            stage_index=4, stage_count=10,
            previous_label="Core Collection", next_label="Deterministic Analysis",
        )
        return 0

    def header(state):
        frames.append((state.status, console_runtime.runtime_progress_summary(state)))

    module.run_audit_from_console = core_run
    module.render_header = header
    install(module)
    return module


class PostCoreProgressTests(unittest.TestCase):
    def test_perplexity_resets_stale_terminal_and_restores_core_partial(self):
        frames = []
        module = _console("COMPLETE_WITH_LIMITATIONS", frames)
        state = SearchConsoleState(perplexity_queries=("seguro empresarial",))
        observed = []

        def fake_perplexity(current):
            progress = console_runtime.runtime_progress_summary(current)
            observed.append((current.status, current.operation, progress))
            current.perplexity_last_status = "COMPLETE"
            return 0

        try:
            with patch("rasai.console_search_intelligence.perplexity_enabled", return_value=True), patch(
                "rasai.console_search_intelligence.execute_perplexity_for_audit", side_effect=fake_perplexity
            ):
                self.assertEqual(module.run_audit_from_console(state), 0)

            self.assertEqual(len(observed), 1)
            status, operation, during = observed[0]
            self.assertEqual(status, "POST_CORE_ENRICHMENT")
            self.assertEqual(operation, "API:PERPLEXITY_SEARCH")
            self.assertEqual(during.label, "Pesquisa externa opcional: Perplexity")
            self.assertIsNone(during.stage_index)
            self.assertIsNone(during.stage_count)
            self.assertFalse(during.overall_exact)
            self.assertIsNone(during.overall_percent)
            self.assertIsNone(during.stage_percent)
            self.assertNotIn("processo finalizado", during.detail)

            self.assertEqual(state.status, "COMPLETE_WITH_LIMITATIONS")
            self.assertEqual(state.operation, "LOCAL:DONE")
            finished = console_runtime.runtime_progress_summary(state)
            self.assertEqual(finished.overall_percent, 100.0)
            self.assertTrue(finished.overall_exact)
            self.assertEqual(dict(finished.detail_rows)["Perplexity"], "COMPLETE")
            self.assertEqual(dict(finished.detail_rows)["AUD core"], "COMPLETE_WITH_LIMITATIONS")
        finally:
            console_runtime.clear_runtime_progress(state)

    def test_post_core_phase_is_not_reclassified_as_preanalysis_collection(self):
        frames = []
        module = _console("COMPLETE", frames)
        state = SearchConsoleState(perplexity_queries=("teste",), geo_ai_requested=True)

        def check_during(current):
            progress = console_runtime.runtime_progress_summary(current)
            self.assertIsNone(_canonical_phase(console_progress_model, current, progress))
            output = StringIO()
            with redirect_stdout(output):
                render_canonical_progress(
                    current_label=progress.label, stage_index=progress.stage_index,
                    stage_count=progress.stage_count,
                    stage_percent=progress.stage_percent,
                    overall_percent=progress.overall_percent,
                    overall_exact=progress.overall_exact,
                    message=progress.detail,
                )
            visible = output.getvalue()
            self.assertIn("Perplexity", visible)
            self.assertIn("Pipeline total", visible)
            self.assertIn("indisponível", visible)
            self.assertNotIn("4 de 10", visible)
            self.assertNotIn("100% [medido]", visible)
            current.perplexity_last_status = "COMPLETE"
            return 0

        try:
            with patch("rasai.console_search_intelligence.perplexity_enabled", return_value=True), patch(
                "rasai.console_search_intelligence.execute_perplexity_for_audit", side_effect=check_during
            ):
                self.assertEqual(module.run_audit_from_console(state), 0)
            self.assertEqual(state.status, "COMPLETE")
        finally:
            console_runtime.clear_runtime_progress(state)

    def test_disabled_perplexity_does_not_create_inflight_stage(self):
        frames = []
        module = _console("COMPLETE", frames)
        state = SearchConsoleState(perplexity_queries=("teste",))
        calls = []

        def disabled(current):
            calls.append(True)
            current.perplexity_last_status = "DISABLED_BY_USER"
            return 0

        try:
            with patch("rasai.console_search_intelligence.perplexity_enabled", return_value=False), patch(
                "rasai.console_search_intelligence.execute_perplexity_for_audit", side_effect=disabled
            ):
                self.assertEqual(module.run_audit_from_console(state), 0)
            self.assertEqual(calls, [True])
            self.assertEqual(frames, [])
            self.assertEqual(dict(console_runtime.runtime_progress_summary(state).detail_rows)["Perplexity"], "DISABLED_BY_USER")
        finally:
            console_runtime.clear_runtime_progress(state)

    def test_unrequested_enrichment_leaves_original_core_progress_untouched(self):
        frames = []
        module = _console("COMPLETE", frames)
        state = SearchConsoleState()
        try:
            with patch("rasai.console_search_intelligence.execute_perplexity_for_audit") as remote:
                self.assertEqual(module.run_audit_from_console(state), 0)
                remote.assert_not_called()
            progress = console_runtime.runtime_progress_summary(state)
            self.assertEqual(progress.label, "Concluído")
            self.assertEqual(progress.stage_index, 4)
            self.assertEqual(progress.stage_count, 10)
        finally:
            console_runtime.clear_runtime_progress(state)

    def test_serp_failure_and_perplexity_adapter_exception_remain_isolated(self):
        frames = []
        module = _console("COMPLETE", frames)
        state = SearchConsoleState(
            search_queries=("consulta",), perplexity_queries=("pesquisa",)
        )
        services = []

        def fake_serp(current, *, target_url):
            self.assertEqual(target_url, "https://example.test/")
            p = console_runtime.runtime_progress_summary(current)
            self.assertIsNone(p.overall_percent)
            self.assertIsNone(p.stage_index)
            services.append(current.operation)
            current.search_last_status = "COMPLETE_WITH_LIMITATIONS"
            return 1

        def broken_perplexity(current):
            p = console_runtime.runtime_progress_summary(current)
            self.assertIsNone(p.overall_percent)
            services.append(current.operation)
            raise RuntimeError("fake optional provider failure")

        try:
            with patch("rasai.console_search_intelligence.perplexity_enabled", return_value=True), patch(
                "rasai.console_search_intelligence.execute_search_for_audit", side_effect=fake_serp
            ), patch(
                "rasai.console_search_intelligence.execute_perplexity_for_audit", side_effect=broken_perplexity
            ):
                self.assertEqual(module.run_audit_from_console(state), 0)
            self.assertEqual(services, ["API:SERP", "API:PERPLEXITY_SEARCH"])
            self.assertEqual(state.status, "COMPLETE_WITH_LIMITATIONS")
            self.assertEqual(state.perplexity_last_status, "COMPLETE_WITH_LIMITATIONS")
            self.assertEqual(console_runtime.runtime_progress_summary(state).overall_percent, 100.0)
        finally:
            console_runtime.clear_runtime_progress(state)


if __name__ == "__main__":
    unittest.main()
