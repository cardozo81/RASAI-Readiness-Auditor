from pathlib import Path
from types import SimpleNamespace

from rasai.console_usability_refinements import (
    _can_reprocess,
    _local_timestamp,
    _multi_choice,
    _single_choice,
    configuration_id,
    value_description,
)


def _spec(**overrides):
    base = {
        "name": "RASAI_YMYL_CATEGORY",
        "accepted": ("auto", "none", "health-safety"),
        "default": "auto",
        "value_type": "enum",
        "purpose": "Categoria de risco YMYL.",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_configuration_id_is_compact_stable_and_numeric():
    first = configuration_id("RASAI_AI_CONTENT_REMEDIATION")
    second = configuration_id("RASAI_AI_CONTENT_REMEDIATION")

    assert first == second
    assert len(first) == 6
    assert first.isdigit()


def test_current_environment_catalog_has_no_compact_id_collision():
    from rasai import console_provider_environment as environment

    specs = environment.refresh_specs()
    ids = [configuration_id(spec.name) for spec in specs]

    assert len(ids) == len(set(ids))


def test_ymyl_values_have_user_facing_explanations():
    spec = _spec()

    assert "inferida" in value_description(spec, "auto").casefold()
    assert "saúde" in value_description(spec, "health-safety").casefold()


def test_single_choice_renders_options_and_requires_confirmation(capsys):
    spec = _spec()
    answers = iter(("3", "C"))

    assert _single_choice(spec, lambda _: next(answers)) == "health-safety"
    rendered = capsys.readouterr().out

    assert "Valores válidos" in rendered
    assert "health-safety" in rendered
    assert "Saúde ou segurança física" in rendered
    assert "Selecionado: health-safety" in rendered


def test_multi_choice_renders_options_and_confirms_selection(capsys):
    spec = _spec(
        name="RASAI_LIGHTHOUSE_CATEGORIES",
        accepted=("performance", "accessibility", "seo"),
        default="performance,accessibility",
        value_type="lista CSV",
        purpose="Categorias Lighthouse solicitadas.",
    )
    answers = iter(("1,3", "C"))

    assert _multi_choice(spec, lambda _: next(answers)) == "performance,seo"
    rendered = capsys.readouterr().out

    assert "seleção múltipla" in rendered
    assert "Mede desempenho" in rendered
    assert "Avalia verificações técnicas de SEO" in rendered


def test_completed_audit_is_not_reprocessable():
    summary = {
        "processing_status": "COMPLETE",
        "pending_items": 0,
        "blocked_items": 0,
        "expired_items": 0,
    }

    assert _can_reprocess(summary) is False


def test_partial_retryable_audit_remains_reprocessable():
    summary = {
        "processing_status": "PARTIAL_RETRYABLE",
        "pending_items": 1,
        "blocked_items": 0,
        "expired_items": 0,
    }

    assert _can_reprocess(summary) is True


def test_completion_timestamp_uses_configured_presentation_timezone(monkeypatch):
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "America/Sao_Paulo")

    assert _local_timestamp("2026-09-15T10:00:00+00:00") == "15/09/2026 07:00"


def test_selected_audit_detail_uses_physical_lifecycle_timestamps(
    monkeypatch, tmp_path: Path, capsys
):
    import rasai.console_artifacts as artifacts
    import rasai.console_history_presentation as history
    import rasai.console_navigation as navigation
    import rasai.console_usability_refinements as usability

    audit_id = "AUD-PHYSICAL-TIME"
    (tmp_path / audit_id).mkdir()

    monkeypatch.setattr(
        usability,
        "_safe_summary",
        lambda *_: {
            "processing_status": "COMPLETE",
            "score_status": "FINAL",
            "consolidation_eligible": True,
            "required_items": 1,
            "successful_items": 1,
            "pending_items": 0,
            "blocked_items": 0,
            "reprocess_count": 0,
            "last_reprocess_id": None,
            # Deliberately different: this logical timestamp must not be presented
            # as the physical completion of the AUD.
            "completed_at": "2026-09-15T12:59:00+00:00",
        },
    )
    monkeypatch.setattr(navigation, "_configuration_reuse_status", lambda *_: (False, "teste"))
    monkeypatch.setattr(artifacts, "report_entrypoint", lambda *_: None)
    monkeypatch.setattr(
        history,
        "process_started_at",
        lambda *_: "2026-09-15T10:00:00+00:00",
    )
    monkeypatch.setattr(
        history,
        "process_finished_at",
        lambda *_: "2026-09-15T10:30:00+00:00",
    )
    monkeypatch.setattr("builtins.input", lambda *_: "V")
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "UTC")

    state = SimpleNamespace(audits_root=tmp_path, status="", operation="", error="")
    console_module = SimpleNamespace(render_header=lambda *_: None)

    assert usability._selected_audit_menu(console_module, state, audit_id) is False
    rendered = capsys.readouterr().out

    assert "Início local   : 15/09/2026 10:00" in rendered
    assert "Conclusão local: 15/09/2026 10:30" in rendered
    assert "12:59" not in rendered
