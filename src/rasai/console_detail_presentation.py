"""Small presentation refinements for console detail rows.

This module changes presentation only. It does not alter diagnostics, routing, retries,
fulfillment, scoring or persisted evidence.
"""
from __future__ import annotations

from typing import Any


def detail_text(code: Any, detail: Any) -> str:
    """Join an optional technical code and detail without producing a leading colon."""
    normalized_code = str(code or "").strip().strip(":")
    normalized_detail = str(detail or "").strip()
    while normalized_detail.startswith(":"):
        normalized_detail = normalized_detail[1:].lstrip()
    if normalized_code and normalized_detail:
        return f"{normalized_code}: {normalized_detail}"
    return normalized_code or normalized_detail


def _render_network_assessment(assessment: Any) -> None:
    if assessment is None:
        return

    from rasai import integration_network_diagnostics as network
    from rasai.console_ui import DIM, GREEN, RED, YELLOW, paint, semantic_text, title_text

    ok = assessment.classification in {network.NETWORK_PATH_OK, network.NETWORK_PATH_OK_AFTER_RETRY}
    inconclusive = assessment.classification in {
        network.HTTP_PATH_INCONCLUSIVE,
        network.NETWORK_INCONCLUSIVE_PROXY_OR_VPN,
        network.NETWORK_NOT_TESTED,
    }
    color = GREEN if ok else YELLOW if inconclusive else RED
    print("\n" + title_text("REDE / CONECTIVIDADE"))
    print(f"Endpoint     : {assessment.host or '<não aplicável>'}:{assessment.port}")
    print("DNS          : " + semantic_text(assessment.dns_status, bold=True))
    print(f"TCP {assessment.port:<5} : " + semantic_text(assessment.tcp_status, bold=True))
    print("TLS          : " + semantic_text(assessment.tls_status, bold=True))
    if assessment.http_status is not None:
        print(f"HTTP         : {assessment.http_status}")
    print(f"Tentativas   : {assessment.attempt_count}")
    if assessment.latencies_ms:
        print("Latências    : " + " / ".join(f"{value} ms" for value in assessment.latencies_ms))
    print("Classificação: " + paint(network._network_label(assessment.classification), color, bold=True))
    if assessment.control_host:
        print(f"Controle     : {assessment.control_host} = {assessment.control_status}")
    if assessment.proxy_configured:
        print(paint("Proxy detectado no ambiente; uma VPN/proxy pode alterar a rota e limitar a certeza do diagnóstico direto.", YELLOW))
    if assessment.error_detail:
        print(paint(f"Detalhe      : {detail_text(assessment.error_code, assessment.error_detail)}", DIM))


def install() -> None:
    """Install the final console-only presentation layer after runtime composition."""
    from rasai import integration_network_diagnostics as network

    if not getattr(network, "_rasai_detail_presentation_installed", False):
        network._render_network_assessment = _render_network_assessment
        network._rasai_detail_presentation_installed = True

    try:
        from rasai import interactive_console as console
    except ImportError:
        return
    if not (
        getattr(console, "_rasai_integration_diagnostics_installed", False)
        and getattr(console, "_rasai_canonical_preparation_layout", False)
    ):
        return
    from rasai.console_ui_refactor import install as install_console_ui_refactor

    install_console_ui_refactor()

    from rasai.console_usability_refinements import install as install_console_usability_refinements

    install_console_usability_refinements(console)

    from rasai.console_guided_input_fix import install as install_console_guided_input_fix

    install_console_guided_input_fix()

    from rasai.console_operator_navigation_refinements import (
        install as install_console_operator_navigation_refinements,
    )

    install_console_operator_navigation_refinements(console)

    from rasai.console_content_capability_refinements import (
        install as install_console_content_capability_refinements,
    )

    install_console_content_capability_refinements(console)

    from rasai.console_configuration_detail_refinements import (
        install as install_console_configuration_detail_refinements,
    )

    install_console_configuration_detail_refinements()

    from rasai.console_observability_capability_refinements import (
        install as install_console_observability_capability_refinements,
    )

    install_console_observability_capability_refinements(console)

    # Final preparation owner: the public console exposes one stable audit catalog.
    # The runtime/core itself is not modified by this presentation layer.
    from rasai.console_catalog_workflow import install as install_console_catalog_workflow

    install_console_catalog_workflow(console)

    # Search/GSC are both part of CAT-05 but remain technically independent. Group their
    # settings by execution scope, authentication, property and collection limits so the
    # operator does not need to infer relationships from environment-variable names.
    from rasai.console_search_configuration_groups import install as install_search_configuration_groups

    install_search_configuration_groups()

    # Execution-owned Search inputs are shown as product concepts, not internal state
    # attributes, and stay visually separate from reusable provider/governance settings.
    from rasai.console_search_scope_presentation import install as install_search_scope_presentation

    install_search_scope_presentation()

    # Some GSC metadata originates from the metrics/service registry. Public ownership is
    # nevertheless Search, so the all-configurations view must not scatter GSC under Web.
    from rasai.console_search_owner_routing import install as install_search_owner_routing

    install_search_owner_routing()

    # Saving configuration materializes the complete public non-secret catalog, including
    # effective defaults. Search execution inputs remain in their dedicated INI section.
    from rasai.console_complete_persistence import install as install_complete_persistence

    install_complete_persistence()

    # Install last so history presentation remains the final owner of the audit-list surface.
    from rasai.console_history_presentation import install as install_console_history_presentation

    install_console_history_presentation(console)

    # Final RPR owner: fixes applicable-item counting, selective AI cost preview and the
    # complete result/action surface, including direct retry of remaining recoverable work.
    from rasai.console_reprocess_final_refinements import (
        install as install_console_reprocess_final_refinements,
    )

    install_console_reprocess_final_refinements(console)

    # Visual-only polish must come after the final owner so its presentation globals are
    # the last layer rebound without affecting retry/pricing semantics.
    from rasai.console_reprocess_visual_presentation import (
        install as install_console_reprocess_visual_presentation,
    )

    install_console_reprocess_visual_presentation()

    # Absolute last navigation pass: nested screens expose only actions for their current
    # context. Global destinations (configuration, help, history, exit) remain owned by
    # INÍCIO. This layer only filters/redirects console actions; core rules are untouched.
    from rasai.console_submenu_action_scope import install as install_submenu_action_scope

    install_submenu_action_scope(console)

    # Final public copy/semantic-message pass. It normalizes action descriptions and
    # ERRO/ALERTA/INFO/OK presentation after every feature-specific wrapper has already
    # been composed, without changing the action returned by any screen.
    from rasai.console_operator_ux_consistency import install as install_operator_ux_consistency

    install_operator_ux_consistency(console)

    # Last presentation pass for configuration lists. It guarantees unique public labels
    # and groups mixed variables by their functional context on catalog, capability and
    # all-configuration screens. Technical variable names remain opt-in details only.
    from rasai.console_configuration_context_presentation import (
        install as install_configuration_context_presentation,
    )

    install_configuration_context_presentation(console)

    # Absolute final catalog pass: persist the selected CAT plan, make execution-owned
    # Search inputs discoverable from CAT-05, keep source-specific settings grouped and
    # keep the public configuration table aligned. Runtime semantics remain untouched.
    from rasai.console_catalog_configuration_refinements import (
        install as install_catalog_configuration_refinements,
    )

    install_catalog_configuration_refinements()

    # CAT-05 action 1 must behave like the other configuration surfaces: first choose the
    # SERP execution field to edit, then accept only the provider/governance-supported
    # range or enum. Reusable provider settings remain in Configurações Relacionadas.
    from rasai import console_search_intelligence as search
    from rasai.console_search_parameter_menu import install as install_search_parameter_menu

    install_search_parameter_menu(search)
