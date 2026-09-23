from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import io
from types import SimpleNamespace
import time
import unittest

from rasai import console_runtime, runtime_progress_gate


class RuntimeProgressGateTests(unittest.TestCase):
    def test_pending_serp_reopens_clock_and_prevents_premature_terminal_progress(self) -> None:
        original_render = console_runtime.render_header
        original_installed = runtime_progress_gate._INSTALLED
        state = SimpleNamespace(
            search_queries=("seguro auto", "seguro residencial"),
            search_last_status="PENDING",
            status="COMPLETE",
            operation="LOCAL:DONE",
            current_url="https://example.test/",
            current_device="MOBILE",
            error="",
        )
        timing = console_runtime._RunTiming(
            started_at=datetime.now().astimezone(),
            started_monotonic=time.monotonic() - 2.0,
            finished_at=datetime.now().astimezone(),
            duration_seconds=2.0,
        )
        console_runtime._RUN_TIMINGS[id(state)] = timing
        console_runtime._RUN_PROGRESS[id(state)] = console_runtime._RunProgress(
            label="Concluído",
            percent=100.0,
            detail="processo finalizado",
            exact=True,
            overall_percent=100.0,
            overall_exact=True,
        )
        try:
            runtime_progress_gate._INSTALLED = False
            runtime_progress_gate.install_search_progress_gate()
            with redirect_stdout(io.StringIO()) as captured:
                console_runtime.render_header(state)

            self.assertIsNone(timing.finished_at)
            self.assertIsNone(timing.duration_seconds)
            progress = console_runtime._RUN_PROGRESS[id(state)]
            self.assertEqual(progress.label, "Search Intelligence / SERP")
            self.assertEqual(progress.stage_percent, 0.0)
            self.assertEqual(progress.overall_percent, 97.0)
            self.assertEqual(state.status, "COMPLETE")
            self.assertEqual(state.operation, "LOCAL:DONE")
            rendered = captured.getvalue()
            self.assertIn("SEARCH_INTELLIGENCE", rendered)
            self.assertIn("97%", rendered)
            self.assertNotIn("Progresso   : 100%", rendered)
        finally:
            console_runtime.render_header = original_render
            console_runtime._RUN_TIMINGS.pop(id(state), None)
            console_runtime._RUN_PROGRESS.pop(id(state), None)
            runtime_progress_gate._INSTALLED = original_installed


if __name__ == "__main__":
    unittest.main()
