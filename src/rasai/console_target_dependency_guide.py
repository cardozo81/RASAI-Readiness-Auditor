"""Guided same-screen editing of target-related independent inputs.

The only executable URL is state.target. This UI delegates to existing CAT-05
editors and canonical GSC variable editor; it does not copy requests or secrets.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from rasai.target_scope_reconciliation import related_scope_summary, adjustment_guidance


def review_target_dependencies(console: ModuleType, state: Any) -> None:
    from rasai import console_search_intelligence as search_module

    while True:
        print("\n[ REVISÃO DE URL E PARÂMETROS RELACIONADOS ]")
        for line in related_scope_summary(state):
            print("  " + line)
        print("\n1. Revisar termos e localidade SERP (CAT-05)")
        print("2. Revisar consultas e rascunhos Perplexity (CAT-05)")
        print("3. Revisar propriedade Google Search Console (GSC)")
        print("V. Voltar sem iniciar auditoria ou provedores")
        selected = input("Ajustar configuração [1/2/3/V]: ").strip().upper()
        if selected == "V":
            return
        if selected == "1":
            from rasai.console_search_parameter_menu import configure_search_parameters
            configure_search_parameters(search_module, state)
        elif selected == "2":
            from rasai.console_search_parameter_menu import _configure_perplexity
            _configure_perplexity(search_module, state)
        elif selected == "3":
            from rasai import console_provider_environment as provider_env
            from rasai.console_ui_catalog import variable_editor
            spec = next(
                (item for item in provider_env.refresh_specs()
                 if item.name == "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"),
                None,
            )
            if spec is None:
                print("  Configuração GSC não encontrada. " + adjustment_guidance("GSC"))
            else:
                variable_editor(console, state, spec)
        else:
            print("  Escolha inválida. Use 1, 2, 3 ou V.")
