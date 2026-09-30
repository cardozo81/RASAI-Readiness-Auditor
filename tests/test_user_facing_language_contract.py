from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MILESTONE = re.compile(r"(?<![\w-])M\d{1,2}(?![\w-])")

# Internal architecture matrices legitimately use physical collector names; these
# are not help pages or report templates and must not be rewritten for end users.
_INTERNAL_ARCHITECTURE_DOCS = frozenset({"docs/AUD_RPR_PARITY_MATRIX_110.md"})


def _public_documentation_paths() -> tuple[Path, ...]:
    candidates = (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))
    return tuple(
        path for path in candidates
        if path.relative_to(ROOT).as_posix() not in _INTERNAL_ARCHITECTURE_DOCS
    )



def test_documentation_has_no_standalone_delivery_milestone_labels() -> None:
    failures = []
    for path in _public_documentation_paths():
        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))
        if matches:
            failures.append(f"{path.relative_to(ROOT)}: {matches}")
    assert not failures, "\n".join(failures)


def test_technical_parity_matrix_is_not_scanned_as_public_documentation() -> None:
    matrix = ROOT / "docs" / "AUD_RPR_PARITY_MATRIX_110.md"
    assert matrix.exists()
    assert "M21" in matrix.read_text(encoding="utf-8")
    assert matrix not in _public_documentation_paths()
    assert ROOT / "README.md" in _public_documentation_paths()


def test_user_facing_templates_have_no_standalone_delivery_milestone_labels() -> None:
    names = ["m20_reporting.py", "m21_reporting.py", "m22_quality_domains.py", "m23_reporting.py", "m24_reporting.py", "report_navigation.py", "report_semantics.py", "indicator_provenance.py", "console_help.py"]
    failures = []
    for name in names:
        path = ROOT / "src/rasai" / name
        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))
        if matches:
            failures.append(f"{name}: {matches}")
    assert not failures, "\n".join(failures)


def test_accessibility_zero_is_not_presented_as_proof_of_no_failures() -> None:
    from rasai.report_semantics import enhance_report_html
    html = "<div class='metric'><small>Falhas automatizadas</small><strong>0</strong></div>"
    rendered = enhance_report_html(html, page_name="accessibility.html", report_dir=ROOT)
    assert "Nenhuma ocorrência registrada" in rendered
    assert "Sem falhas detectadas" not in rendered


def test_unavailable_cwv_is_neutral() -> None:
    from rasai.report_semantics import enhance_report_html
    html = "<div class='metric'><small>CWV</small><strong>UNAVAILABLE</strong></div>"
    rendered = enhance_report_html(html, page_name="web-performance.html", report_dir=ROOT)
    assert "Dados de campo indisponíveis" in rendered
    assert "result-state-neutral" in rendered


def test_legacy_milestone_chrome_is_sanitized_without_touching_audited_copy() -> None:
    from rasai.report_consistency_v2 import _sanitize_presentation
    html = "<p>Produto M20 com motor M23 permanece conteúdo auditado.</p><div>M22 · diagnóstico técnico</div>"
    rendered = _sanitize_presentation(html)
    assert "Produto M20 com motor M23 permanece conteúdo auditado." in rendered
    assert "Diagnóstico técnico" in rendered


def test_single_provider_strategy_is_not_exposed_as_raw_enum() -> None:
    from rasai.report_presentation import humanize_report_html
    rendered = humanize_report_html("<div><span>SINGLE_PROVIDER</span></div>")
    assert "Provedor único" in rendered
    assert ">SINGLE_PROVIDER<" not in rendered


def test_common_report_machine_values_are_humanized() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<table><tr><td>INTERNAL_LINKS</td><td>PAGE_ACCESS</td><td>SPA_NAVIGATION</td>"
        "<td>SPA_ROUTE</td><td>DEGRADED</td><td>EXISTING_REVIEW</td>"
        "<td>AUTH_ERROR</td><td>NAVIGATION_TIMEOUT</td></tr></table>"
    )
    rendered = humanize_report_html(html)
    assert "Links internos" in rendered
    assert "Acesso à página" in rendered
    assert "Navegação SPA" in rendered
    assert "Rota SPA" in rendered
    assert "Execução com limitações" in rendered
    assert "Revisão do JSON-LD existente" in rendered
    assert "Erro de autenticação" in rendered
    assert "Tempo limite de navegação excedido" in rendered
    for raw in ("INTERNAL_LINKS", "PAGE_ACCESS", "SPA_NAVIGATION", "SPA_ROUTE", "DEGRADED", "EXISTING_REVIEW"):
        assert f">{raw}<" not in rendered


def test_technical_identifiers_remain_canonical_when_they_are_traceability_data() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<div><code>RASAI_AI_CONTENT_REMEDIATION</code>"
        "<span>BR-GEO-017</span><strong>RASAI_TABLET_CONTROLLED4G_V1</strong>"
        "<pre>DEGRADED SINGLE_PROVIDER</pre></div>"
    )
    rendered = humanize_report_html(html)
    assert "RASAI_AI_CONTENT_REMEDIATION" in rendered
    assert "BR-GEO-017" in rendered
    assert "RASAI_TABLET_CONTROLLED4G_V1" in rendered
    assert "<pre>DEGRADED SINGLE_PROVIDER</pre>" in rendered

def test_reader_transparency_does_not_expose_fulfillment_enums() -> None:
    from rasai.report_reader_experience import _render_work_items

    rendered = _render_work_items(
        (
            {
                "component": "TECHNICAL_AI",
                "scope_key": "AUDIT",
                "status": "WAITING_FOR_DATA",
                "attempt_count": 1,
                "last_error_code": "AI_NOT_AUTHORIZED_FOR_EXECUTION",
            },
        )
    )
    assert "Análise técnica por IA" in rendered
    assert "Contexto da execução: escopo Auditoria" in rendered
    assert "IA não autorizada para execução nesta auditoria" in rendered
    assert "TECHNICAL_AI" not in rendered
    assert "AI_NOT_AUTHORIZED_FOR_EXECUTION" not in rendered
    assert ">AUDIT<" not in rendered


def test_serp_runtime_notice_uses_human_diagnostic_labels() -> None:
    from rasai.runtime_adherence_extensions import _issue_notice

    rendered = _issue_notice(
        (
            {
                "query": "seguro auto",
                "provider": "SerpApi",
                "error_code": "SERP_PROVIDER_ERROR",
                "error_message": "HTTP 503 unavailable",
            },
        ),
        title="Limitação de busca",
    )
    assert "Falha transitória do provedor" in rendered
    assert "Erro do provedor de SERP" in rendered
    assert "TECHNICAL_TRANSIENT_PROVIDER" not in rendered
    assert "SERP_PROVIDER_ERROR" not in rendered


def test_legacy_report_error_summaries_use_human_labels() -> None:
    from rasai.m20_reporting import _attempt_error_summary
    from rasai.report_consistency_v2 import _attempt_reason

    summary = _attempt_error_summary(
        [
            {
                "error_class": "SERVER_ERROR",
                "error_type": "TimeoutError",
                "error_code": "SERVICE_UNAVAILABLE",
            }
        ]
    )
    assert "Erro do servidor" in summary
    assert "Tempo limite excedido" in summary
    assert "Serviço indisponível" in summary
    assert "SERVER_ERROR" not in summary
    assert "TimeoutError" not in summary
    assert "SERVICE_UNAVAILABLE" not in summary

    reason = _attempt_reason(
        {
            "http_status": 503,
            "error_code": "SERVICE_UNAVAILABLE",
            "error_message": "indisponível — tente novamente",
            "status": "FAILED",
        }
    )
    assert reason == "HTTP 503 - Serviço indisponível - indisponível - tente novamente"
    assert "SERVICE_UNAVAILABLE" not in reason
    assert "—" not in reason

def test_shared_public_language_covers_known_gap_codes_and_dynamic_prerequisites() -> None:
    from rasai.catalog_report_public_labels import public_label
    from rasai.public_language import supplemental_public_label

    assert public_label("HTTP_ACQUISITION_INCOMPLETE") == "Aquisição HTTP incompleta"
    assert public_label("TECHNICAL_EVIDENCE_INSUFFICIENT") == "Evidência técnica insuficiente"
    assert (
        supplemental_public_label("TECHNICAL_PREREQUISITE_BR_GEO_009_NOT_APPLICABLE")
        == "Pré-requisito técnico BR-GEO-009: não aplicável"
    )
    assert (
        supplemental_public_label("TECHNICAL_PREREQUISITE_BR_GEO_020_UNKNOWN")
        == "Pré-requisito técnico BR-GEO-020: não determinado"
    )


def test_report_humanizer_blocks_unknown_machine_copy_but_preserves_traceability() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<p>HTTP_ACQUISITION_INCOMPLETE "
        "TECHNICAL_PREREQUISITE_BR_GEO_009_NOT_APPLICABLE "
        "BRAND_NEW_RUNTIME_ENUM</p>"
        "<span>BR-GEO-009</span>"
        "<strong>RASAI_TABLET_CONTROLLED4G_V1</strong>"
    )
    rendered = humanize_report_html(html)
    assert "Aquisição HTTP incompleta" in rendered
    assert "Pré-requisito técnico BR-GEO-009: não aplicável" in rendered
    assert "Condição técnica não catalogada" in rendered
    assert "HTTP_ACQUISITION_INCOMPLETE" not in rendered
    assert "TECHNICAL_PREREQUISITE_BR_GEO_009_NOT_APPLICABLE" not in rendered
    assert "BRAND_NEW_RUNTIME_ENUM" not in rendered
    assert "BR-GEO-009" in rendered
    assert "RASAI_TABLET_CONTROLLED4G_V1" in rendered


def test_console_header_never_exposes_raw_status_or_operation(monkeypatch, capsys) -> None:
    from types import SimpleNamespace
    from rasai import console_runtime

    monkeypatch.setattr(console_runtime, "clear_screen", lambda: None)
    monkeypatch.setattr(console_runtime, "environment_summary", lambda: {})
    monkeypatch.setattr(console_runtime, "_log_environment_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(console_runtime, "timing_summary", lambda _state: None)
    monkeypatch.setattr(console_runtime, "runtime_progress_summary", lambda _state: None)

    state = SimpleNamespace(
        status="FINALIZING",
        current_url="https://example.test/",
        current_device="MOBILE",
        operation="LOCAL:DONE",
        error="",
    )
    console_runtime.render_header(state)
    rendered = capsys.readouterr().out
    assert "Finalizando auditoria" in rendered
    assert "Auditoria concluída" in rendered
    assert "FINALIZING" not in rendered
    assert "LOCAL:DONE" not in rendered


def test_reprocess_reason_uses_human_diagnostic_code() -> None:
    from types import SimpleNamespace
    from rasai.console_reprocess_parity import _reason_text

    item = SimpleNamespace(
        last_error_code="HTTP_ACQUISITION_INCOMPLETE",
        last_error_message="no effective retrievable HTTP acquisition is persisted for this page",
    )
    rendered = _reason_text(item)
    assert rendered.startswith("Aquisição HTTP incompleta - ")
    assert "HTTP_ACQUISITION_INCOMPLETE" not in rendered


def test_console_operation_literals_have_explicit_public_labels() -> None:
    from rasai.public_language import CONSOLE_OPERATION_LABELS

    root = ROOT / "src" / "rasai"
    literal = re.compile(r"""[\"']((?:LOCAL|API|BROWSER|INTEGRATION):[^\"']+)[\"']""")
    missing: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "console" not in path.name and path.name not in {
            "m3_console_progress.py",
            "m21_console_progress.py",
            "standards_gsc_console_progress.py",
            "runtime_adherence_extensions.py",
            "execution_adherence_refinement.py",
            "audit_progress_runtime.py",
        }:
            continue
        for value in literal.findall(path.read_text(encoding="utf-8")):
            if "{" in value:
                continue
            if value not in CONSOLE_OPERATION_LABELS:
                missing.append(f"{path.relative_to(ROOT)}: {value}")
    assert not missing, "\n".join(sorted(set(missing)))


def test_semantic_machine_literals_have_a_public_language_contract() -> None:
    import ast

    from rasai.catalog_report_public_labels import public_label
    from rasai.public_language import is_traceability_identifier

    semantic_fields = {
        "error_code",
        "error_class",
        "last_error_code",
        "last_error_class",
        "reason",
        "status",
        "scope_key",
        "component",
        "temporal_mode",
    }
    machine = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
    root = ROOT / "src" / "rasai"
    missing: list[str] = []

    def verify(path: Path, field: str, value: object) -> None:
        if not isinstance(value, str) or not machine.fullmatch(value):
            return
        if is_traceability_identifier(value):
            return
        if public_label(value) is None:
            missing.append(f"{path.relative_to(ROOT)}: {field}={value}")

    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in semantic_fields:
                if isinstance(node.value, ast.Constant):
                    verify(path, node.arg, node.value.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value in semantic_fields
                        and isinstance(value, ast.Constant)
                    ):
                        verify(path, key.value, value.value)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    field = None
                    if isinstance(target, ast.Name):
                        field = target.id
                    elif isinstance(target, ast.Attribute):
                        field = target.attr
                    if field in semantic_fields:
                        verify(path, field, node.value.value)
    assert not missing, "\n".join(sorted(set(missing)))

def test_diagnostic_text_humanizes_composed_machine_reason() -> None:
    from rasai.public_language import diagnostic_text

    rendered = diagnostic_text("AI_WAITING_FOR_DATA:MAIN_CONTENT_UNAVAILABLE")
    assert rendered == "IA aguardando pré-requisitos - Conteúdo principal indisponível"
    assert "WAITING_FOR_DATA" not in rendered
    assert "MAIN_CONTENT_UNAVAILABLE" not in rendered




def test_known_experience_apdex_error_codes_have_public_diagnostic_labels() -> None:
    from rasai.catalog_report_public_labels import public_label

    assert public_label("M25_RUNTIME_FAILURE") == "Falha durante a execução do Apdex de experiência"
    assert public_label("NO_AUDITED_PAGES") == "Nenhuma página auditada elegível para o Apdex de experiência"
