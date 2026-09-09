from __future__ import annotations

import pytest

from rasai.public_report_safety import (
    PublicReportSafetyError,
    normalize_owned_public_report_text,
    public_report_markup_leaks,
)


def test_public_report_preserves_legitimate_visible_model_name() -> None:
    source = "<html><body><p>Produto M25 industrial observado na página.</p></body></html>"
    rendered = normalize_owned_public_report_text(source)
    assert rendered == source
    assert public_report_markup_leaks(rendered) == ()


def test_public_report_normalizes_known_legacy_owned_markup() -> None:
    source = (
        "<!-- rasai-m23-web-start -->"
        "<section id='m23-apdex-summary'>Estado M23</section>"
        "<!-- rasai-m23-web-end -->"
    )
    rendered = normalize_owned_public_report_text(source)
    assert "m23" not in rendered.casefold()
    assert "Estado M23" not in rendered
    assert "apdex-summary" in rendered
    assert public_report_markup_leaks(rendered) == ()


def test_public_report_rejects_unknown_internal_milestone_in_active_markup() -> None:
    source = "<section id='m42-internal-contract'>conteúdo público</section>"
    with pytest.raises(PublicReportSafetyError, match="M42"):
        normalize_owned_public_report_text(source)


def test_public_report_rejects_unknown_internal_milestone_comment() -> None:
    source = "<!-- M77 internal delivery marker --><p>conteúdo público</p>"
    with pytest.raises(PublicReportSafetyError, match="M77"):
        normalize_owned_public_report_text(source)
