from __future__ import annotations

from rasai.report_public_ux_guard import (
    _AGENTIC_PUBLIC_MESSAGE,
    _AI_VISIBILITY_NEW,
    _AI_VISIBILITY_OLD,
    _canonical_quality_shell,
    _install_public_state_labels,
    _localize_quality_html,
    _normalize_agentic_browsing,
    _normalize_navigation_open_state,
    _relocate_fulfillment_banner,
)


def test_navigation_expands_only_group_with_active_page() -> None:
    html = (
        "<nav>"
        "<details class='rasai-nav-group' open><summary>Visão</summary>"
        "<a class='' href='index.html'>Visão geral</a></details>"
        "<details class='rasai-nav-group'><summary>Coleta</summary>"
        "<a class='active' href='context.html'>Contexto</a></details>"
        "<details class='rasai-nav-group' open><summary>Search</summary>"
        "<a class='' href='ai-visibility.html'>IA</a></details>"
        "</nav>"
    )
    updated = _normalize_navigation_open_state(html)
    assert updated.count("<details class='rasai-nav-group' open>") == 1
    assert "<summary>Coleta</summary><a class='active'" in updated
    assert "<details class='rasai-nav-group'><summary>Visão</summary>" in updated
    assert "<details class='rasai-nav-group'><summary>Search</summary>" in updated


def test_fulfillment_banner_moves_inside_main() -> None:
    html = (
        "<body><!-- RASAI_AUDIT_FULFILLMENT_STATUS -->"
        '<section class="rasai-fulfillment-banner rasai-fulfillment-preliminary" role="status">'
        "<strong>Relatório preliminar</strong></section>"
        "<aside class='app-nav'>menu</aside>"
        "<main class='app-main'><section>conteúdo</section></main></body>"
    )
    updated = _relocate_fulfillment_banner(html)
    assert updated.index("<aside class='app-nav'>") < updated.index("<main class='app-main'>")
    assert updated.index("<main class='app-main'>") < updated.index("RASAI_AUDIT_FULFILLMENT_STATUS")
    assert updated.index("RASAI_AUDIT_FULFILLMENT_STATUS") < updated.index("<section>conteúdo</section>")


def test_public_state_labels_cover_no_data_and_fulfillment_states() -> None:
    from rasai import report_presentation as presentation

    _install_public_state_labels()
    assert presentation.public_label("NO_DATA") == "Sem dados utilizáveis"
    assert presentation.public_label("WAITING_FOR_DATA") == "Aguardando dados"
    assert presentation.public_label("PARTIAL_RETRYABLE") == "Parcial - reprocessamento disponível"
    rendered = presentation.humanize_report_html(
        "<p>NO_DATA · PARTIAL_RETRYABLE · PENDING · MEASURED</p>"
        "<code>NO_DATA</code>",
        page_name="standards.html",
    )
    assert "Sem dados utilizáveis" in rendered
    assert "Parcial - reprocessamento disponível" in rendered
    assert "Pendente" in rendered
    assert "Medido" in rendered
    assert "<code>NO_DATA</code>" in rendered


def test_quality_shell_uses_canonical_site_css_and_ptbr_copy() -> None:
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


def test_agentic_unavailable_is_explained_instead_of_looking_like_missing_score() -> None:
    html = (
        "<div class='metric lighthouse-score-unavailable'>"
        "<small>Agentic Browsing · Lighthouse experimental</small>"
        "<strong>Não retornado pelo provider</strong></div>"
    )
    updated = _normalize_agentic_browsing(html)
    assert _AGENTIC_PUBLIC_MESSAGE in updated
    assert "Não retornado pelo provider" not in updated
    assert "contrato oficial" in updated


def test_ai_visibility_empty_copy_distinguishes_analysis_ai_from_observed_visibility() -> None:
    html = f"<p>{_AI_VISIBILITY_OLD}</p>"
    updated = html.replace(_AI_VISIBILITY_OLD, _AI_VISIBILITY_NEW)
    assert "O uso dos provedores de IA durante a auditoria não gera" in updated
    assert "Google Search Console convencional alimenta métricas próprias" in updated
