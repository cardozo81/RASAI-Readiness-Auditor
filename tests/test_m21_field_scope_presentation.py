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


def test_invalid_lighthouse_score_cannot_poison_aggregate() -> None:
    from rasai.m21_reporting import _average_score
    assert _average_score([{"score": 20}, {"score": 80}], "score") == 50
    for invalid in (True, -1, 101, "invalid", float("nan"), float("inf")):
        assert _average_score([{"score": 20}, {"score": invalid}], "score") is None


def test_unavailable_cwv_does_not_assume_url_population() -> None:
    from rasai.m21_reporting import _cwv_explanation
    notice = _cwv_explanation({"cwv_assessment": "UNAVAILABLE", "field_scope": "ORIGIN"})
    assert "URL ou ORIGIN" in notice
    assert "ausência de amostra não demonstra falha" in notice
