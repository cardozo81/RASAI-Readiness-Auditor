from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rasai.console_m23 import State, observe_m23_workspace
from rasai.console_runtime import clear_runtime_progress, render_header, runtime_progress_summary, set_runtime_progress
from rasai.interactive_console import _configure, _configure_apdex, _menu
from rasai.report_consistency_v2 import _sanitize_presentation


class ConsoleProgressGuidanceTests(unittest.TestCase):
    def test_runtime_progress_distinguishes_estimated_and_exact(self) -> None:
        state = State(status="ANALYZING")
        progress = runtime_progress_summary(state)
        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.label, "Extração, regras e análise semântica")
        self.assertFalse(progress.exact)
        self.assertEqual(progress.overall_percent, 42.0)
        self.assertIsNone(progress.stage_percent)
        set_runtime_progress(state, "Etapa mensurada", 37.5, detail="3/8", exact=True)
        progress = runtime_progress_summary(state)
        assert progress is not None
        self.assertEqual(progress.percent, 37.5)
        self.assertTrue(progress.exact)
        self.assertEqual(progress.detail, "3/8")
        clear_runtime_progress(state)

    def test_synthetic_sample_projects_global_context_progress(self) -> None:
        state = State(status="REPORTING")
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            log = workspace / "logs" / "audit.log"
            log.parent.mkdir(parents=True)
            event = {
                "event": "M23_APDEX_SAMPLE",
                "url": "https://example.com/",
                "device": "mobile",
                "context_index": 2,
                "context_total": 4,
                "attempt_count": 3,
                "max_attempts": 7,
                "valid_samples": 3,
                "target_valid_samples": 5,
                "progress_percent": 60.0,
                "classification": "SATISFIED",
            }
            log.write_text(json.dumps(event) + "\n", encoding="utf-8")
            observe_m23_workspace(workspace, state)
        progress = runtime_progress_summary(state)
        assert progress is not None
        self.assertTrue(progress.exact)
        self.assertEqual(progress.label, "Synthetic Apdex")
        self.assertAlmostEqual(progress.percent or 0.0, 40.0)
        self.assertAlmostEqual(progress.stage_percent or 0.0, 40.0)
        self.assertAlmostEqual(progress.overall_percent or 0.0, 94.0)
        self.assertTrue(progress.stage_exact)
        self.assertFalse(progress.overall_exact)
        self.assertIn("contexto 2/4", progress.detail)
        self.assertIn("válidas 3/5", progress.detail)
        clear_runtime_progress(state)

    def test_terminal_source_blocker_wins_over_synthetic_projection(self) -> None:
        state = State(status="SOURCE_BLOCKED", operation="LOCAL:APDEX_SKIPPED")
        set_runtime_progress(
            state,
            "Synthetic Apdex não executado",
            100.0,
            detail="bloqueio técnico da origem",
            exact=True,
        )
        progress = runtime_progress_summary(state)
        assert progress is not None
        self.assertEqual(progress.stage_percent, 100.0)
        self.assertEqual(progress.overall_percent, 100.0)
        self.assertTrue(progress.stage_exact)
        self.assertTrue(progress.overall_exact)
        clear_runtime_progress(state)

    def test_header_keeps_measured_stage_separate_from_estimated_whole_run(self) -> None:
        state = State(status="SYNTHETIC_APDEX", operation="BROWSER:SYNTHETIC_APDEX")
        set_runtime_progress(
            state,
            "Synthetic Apdex",
            40.0,
            detail="contexto 2/4; válidas 3/5",
            exact=True,
        )
        output = io.StringIO()
        with patch("rasai.console_runtime.clear_screen"), patch("rasai.console_runtime.environment_summary", return_value=[]), redirect_stdout(output):
            render_header(state)
        rendered = output.getvalue()
        self.assertIn("Andamento", rendered)
        self.assertIn("40%", rendered)
        self.assertIn("medido na etapa", rendered)
        self.assertIn("Progresso", rendered)
        self.assertIn("~94%", rendered)
        self.assertIn("geral estimado", rendered)
        self.assertIn("Executando", rendered)
        self.assertIn("contexto 2/4", rendered)
        clear_runtime_progress(state)

    def test_option_5_explains_dependency_on_item_4(self) -> None:
        state = State(ai_provider="none")
        output = io.StringIO()
        with patch("builtins.input", return_value="Q"), redirect_stdout(output):
            choice = _menu(state)
        self.assertEqual(choice, "Q")
        rendered = output.getvalue()
        self.assertIn("REQUER IA CONFIGURADA E ATIVA NO ITEM 4", rendered)
        with patch("rasai.interactive_console.render_header"), redirect_stdout(io.StringIO()):
            _configure(state, "5")
        self.assertFalse(state.content_remediation)
        self.assertEqual(state.error, "opção 5 requer uma IA configurada e ativa no item 4")

    def test_synthetic_configuration_explains_each_numeric_parameter(self) -> None:
        state = State()
        answers = iter(["s", "1.0", "5", "7", "1", "45", "1", "1"])
        output = io.StringIO()
        with patch("builtins.input", side_effect=lambda _prompt="": next(answers)), redirect_stdout(output):
            _configure_apdex(state)
        rendered = output.getvalue()
        self.assertTrue(state.synthetic_apdex)
        self.assertEqual(state.apdex_threshold, 1.0)
        self.assertEqual(state.apdex_samples, 5)
        self.assertEqual(state.apdex_max_attempts, 7)
        self.assertEqual(state.apdex_max_pages, 1)
        for expected in (
            "T é o tempo-alvo da Task",
            "quantidade de navegações válidas",
            "teto de navegações",
            "limita quantas páginas",
            "tempo máximo permitido",
            "intervalo mínimo",
            "navegações podem ocorrer simultaneamente",
            "Carga projetada Synthetic Apdex",
        ):
            self.assertIn(expected, rendered)

    def test_public_menu_does_not_expose_milestone_labels(self) -> None:
        state = State()
        output = io.StringIO()
        with patch("builtins.input", return_value="Q"), redirect_stdout(output):
            _menu(state)
        rendered = output.getvalue()
        self.assertIn("11. Synthetic Apdex", rendered)
        self.assertIsNone(re.search(r"\bM(?:18|20|21|22|23)\b", rendered))

    def test_report_label_sanitizer_does_not_rewrite_arbitrary_page_content(self) -> None:
        html = (
            "<p>Produto M20 com motor M23 permanece conteúdo auditado.</p>"
            "<div>M22 · diagnóstico técnico</div>"
        )
        rendered = _sanitize_presentation(html)
        self.assertIn("Produto M20 com motor M23 permanece conteúdo auditado.", rendered)
        self.assertIn("Diagnóstico técnico", rendered)
        self.assertNotIn("M22 · diagnóstico técnico", rendered)


if __name__ == "__main__":
    unittest.main()
