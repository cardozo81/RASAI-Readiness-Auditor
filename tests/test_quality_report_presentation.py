from __future__ import annotations

from rasai.quality_report_presentation import _canonical_quality_shell, _localize_quality_html


def test_quality_shell_uses_shared_css_and_ptbr_copy() -> None:
    shell = _canonical_quality_shell(
        "<aside class='app-nav'>menu</aside>",
        "<header class='hero'><div class='metric'><span>Audit health</span><strong>WARNING</strong></div></header>",
    )
    localized = _localize_quality_html(shell)

    assert "css/site.css" in localized
    assert "<div class='app-shell'>" in localized
    assert "<main class='app-main'>" in localized
    assert "<small>Saúde da auditoria</small>" in localized
    assert "<strong>Alerta</strong>" in localized
    assert "Audit health" not in localized
