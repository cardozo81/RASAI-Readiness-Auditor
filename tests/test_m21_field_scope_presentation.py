"""CrUX population scoping stays separate from URL-specific Lighthouse lab evidence."""
from rasai.m21_reporting import _field_scope_explanation


def test_crux_origin_is_not_attributed_to_observed_url() -> None:
    for scope in ("ORIGIN", "ORIGIN_ONLY"):
        text = _field_scope_explanation({"field_scope": scope})
        assert "origem agregada" in text
        assert "não medições exclusivas da URL" in text
        assert "laboratório" in text


def test_crux_url_and_unknown_scopes_have_distinct_disclaimers() -> None:
    specific = _field_scope_explanation({"field_scope": "URL"})
    unknown = _field_scope_explanation({"field_scope": None})
    assert "escopo URL" in specific
    assert "não equivale a uma sessão Lighthouse" in specific
    assert "escopo não verificado" in unknown
    assert "sem proveniência explícita" in unknown
