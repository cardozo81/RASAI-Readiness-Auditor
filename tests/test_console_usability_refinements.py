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
