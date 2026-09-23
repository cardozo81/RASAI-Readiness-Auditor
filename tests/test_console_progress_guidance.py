from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rasai.console_m23 import State, observe_m23_workspace
from rasai.console_runtime import clear_runtime_progress, render_header, runtime_progress_summary, set_runtime_progress
from rasai.interactive_console import _configure, _configure_apdex, _configure_timezone, _menu
from rasai.report_consistency_v2 import _sanitize_presentation
from rasai.time_contract import PRESENTATION_TIMEZONE_ENV, configured_presentation_timezone


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

    def test_runtime_progress_accepts_explicit_stage_and_pipeline_projection(self) -> None:
        state = State(status="REPROCESSING")
        set_runtime_progress(
            state,
            "Executando requisitos selecionados",
            0.0,
            detail="consultando provider",
            exact=False,
            stage_index=1,
            stage_count=3,
            stage_percent_override=80.0,
            stage_exact_override=True,
            overall_percent_override=80.0 / 3.0,
            overall_exact_override=False,
        )
        progress = runtime_progress_summary(state)
        assert progress is not None
        self.assertEqual(progress.stage_percent, 80.0)
        self.assertTrue(progress.stage_exact)
        self.assertAlmostEqual(progress.overall_percent or 0.0, 80.0 / 3.0)
        self.assertFalse(progress.overall_exact)
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
        self.assertEqual(progress.label, "Synthetic Navigation Apdex")
        self.assertAlmostEqual(progress.percent or 0.0, 40.0)
        self.assertAlmostEqual(progress.stage_percent or 0.0, 40.0)
        self.assertAlmostEqual(progress.overall_percent or 0.0, 94.0)
        self.assertTrue(progress.stage_exact)
        self.assertFalse(progress.overall_exact)
        rows = dict(progress.detail_rows)
        self.assertEqual(rows["Contexto"], "2 de 4")
        self.assertEqual(rows["Amostras válidas"], "3 de 5")
        self.assertEqual(rows["Tentativas realizadas"], "3")
        self.assertEqual(rows["Limite de tentativas"], "7")
        clear_runtime_progress(state)

    def test_canonical_renderer_shows_previous_current_next_and_stage_position(self) -> None:
        from rasai.execution_progress_presentation import render_canonical_progress

        output = io.StringIO()
        with redirect_stdout(output):
            render_canonical_progress(
                current_label="Gerando relatório",
                current_status="EM EXECUÇÃO",
                stage_index=5,
                stage_count=6,
                stage_count_planned=False,
                previous_label="Análise complementar / IA",
                next_label="Validação e conclusão",
                stage_percent=72.0,
                stage_exact=True,
                overall_percent=88.0,
                overall_exact=False,
                message="renderizando HTML e gravando arquivos em disco",
                detail_rows=(("Fonte", "dados persistidos"), ("Nova coleta da URL", "NÃO")),
            )
        rendered = output.getvalue()
        self.assertIn("5 de 6", rendered)
        self.assertIn("Anterior", rendered)
        self.assertIn("Análise complementar / IA", rendered)
        self.assertIn("Atual", rendered)
        self.assertIn("Gerando relatório", rendered)
        self.assertIn("Próxima", rendered)
        self.assertIn("Validação e conclusão", rendered)
        self.assertIn("72% [medido na etapa]", rendered)
        self.assertIn("~88% [projeção]", rendered)
        self.assertIn("Nova coleta da URL", rendered)
        self.assertIn("NÃO", rendered)

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

    def test_header_summarizes_environment_and_logs_full_snapshot_once(self) -> None:
        with TemporaryDirectory() as directory:
            audits_root = Path(directory) / "audits"
            state = State(audits_root=str(audits_root))
            variables = (
                "OPENAI_API_KEY=[SET]",
                "RASAI_LOG_LEVEL=INFO",
                "RASAI_WEB_PERFORMANCE=true",
            )
            output = io.StringIO()
            with patch("rasai.console_runtime.clear_screen"), patch(
                "rasai.console_runtime.environment_summary",
                return_value=variables,
            ), patch(
                "rasai.console_runtime._LAST_ENVIRONMENT_LOG_SNAPSHOT",
                None,
            ), redirect_stdout(output):
                render_header(state)
                render_header(state)

            rendered = output.getvalue()
            self.assertNotIn("Ambiente    :", rendered)
            self.assertNotIn("OPENAI_API_KEY", rendered)
            self.assertNotIn("RASAI_LOG_LEVEL=INFO", rendered)
            self.assertNotIn("RASAI_WEB_PERFORMANCE=true", rendered)

            log_path = audits_root / ".rasai" / "logs" / "console.log"
            self.assertTrue(log_path.is_file())
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["event"], "CONSOLE_ENVIRONMENT_SNAPSHOT")
            self.assertEqual(payload["configured_count"], 3)
            self.assertIn("OPENAI_API_KEY=[REDACTED]", payload["variables"])
            self.assertNotIn("OPENAI_API_KEY=[SET]", payload["variables"])
            self.assertIn("RASAI_LOG_LEVEL=INFO", payload["variables"])
            self.assertIn("RASAI_WEB_PERFORMANCE=true", payload["variables"])

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

    def test_timezone_menu_uses_iana_and_shows_numeric_offset_as_guidance(self) -> None:
        state = State()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            with patch("builtins.input", return_value="2"), redirect_stdout(output):
                _configure_timezone(state)
            self.assertEqual(configured_presentation_timezone(), "UTC")
        rendered = output.getvalue()
        self.assertIn("America/Sao_Paulo", rendered)
        self.assertIn("UTC-03:00", rendered)
        self.assertIn("offset numérico", rendered)
        self.assertIn("valor salvo é IANA", rendered)

    def test_timezone_menu_accepts_valid_custom_iana_and_rejects_fixed_offset(self) -> None:
        state = State()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            answers = iter(["C", "Pacific/Auckland"])
            with patch("builtins.input", side_effect=lambda _prompt="": next(answers)), redirect_stdout(io.StringIO()):
                _configure_timezone(state)
            self.assertEqual(configured_presentation_timezone(), "Pacific/Auckland")
            answers = iter(["C", "-03:00"])
            with patch("builtins.input", side_effect=lambda _prompt="": next(answers)), redirect_stdout(io.StringIO()):
                _configure_timezone(state)
            self.assertIn("timezone IANA inválido", state.error)
            self.assertEqual(configured_presentation_timezone(), "Pacific/Auckland")

    def test_public_menu_does_not_expose_milestone_labels(self) -> None:
        state = State()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            with patch("builtins.input", return_value="Q"), redirect_stdout(output):
                _menu(state)
        rendered = output.getvalue()
        self.assertIn("11. Synthetic Apdex", rendered)
        self.assertIn("12. Timezone apresentação: America/Sao_Paulo", rendered)
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
