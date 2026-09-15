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
    from rasai.console_ui import DIM, GREEN, RED, YELLOW, paint

    ok = assessment.classification in {network.NETWORK_PATH_OK, network.NETWORK_PATH_OK_AFTER_RETRY}
    inconclusive = assessment.classification in {
        network.HTTP_PATH_INCONCLUSIVE,
        network.NETWORK_INCONCLUSIVE_PROXY_OR_VPN,
        network.NETWORK_NOT_TESTED,
    }
    color = GREEN if ok else YELLOW if inconclusive else RED
    print("\nREDE / CONECTIVIDADE")
    print(f"Endpoint     : {assessment.host or '<não aplicável>'}:{assessment.port}")
    print(f"DNS          : {assessment.dns_status}")
    print(f"TCP {assessment.port:<5} : {assessment.tcp_status}")
    print(f"TLS          : {assessment.tls_status}")
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

    # Final pass after the information-architecture wrapper: keep these changes strictly
    # in the presentation layer so runtime, persistence and reprocessing contracts stay
    # owned by their canonical modules.
    from rasai.console_usability_refinements import install as install_console_usability_refinements

    install_console_usability_refinements(console)

    # Guided-choice prompts must resolve builtins.input at interaction time.  The final
    # information-architecture wrapper temporarily replaces input so buffered modal text
    # is flushed before reading; import-time defaults bypass that wrapper and hide the
    # option list from the operator.
    from rasai.console_guided_input_fix import install as install_console_guided_input_fix

    install_console_guided_input_fix()

    # Keep the last navigation layer focused on operator ergonomics: capability help is
    # actionable, IDs are never swallowed by a pause prompt, service toggle domains are
    # reflected correctly in the UI, and manual AUD lookup can be cancelled with V.
    from rasai.console_operator_navigation_refinements import (
        install as install_console_operator_navigation_refinements,
    )

    install_console_operator_navigation_refinements(console)

    # Conteúdo e JSON-LD share one top-level capability but have distinct functional
    # components. Segment those components only in the presentation layer; deterministic
    # analysis, editorial context and optional AI remediation keep their existing runtime.
    from rasai.console_content_capability_refinements import (
        install as install_console_content_capability_refinements,
    )

    install_console_content_capability_refinements(console)
