"""Opt-in at launch for reusable Perplexity queries saved by the operator.

Reading a saved query must not itself initiate a commercial provider request.
A configured draft is proposed when the operator launches a new AUD. Only an
explicit choice for that AUD temporarily populates executable request fields.
This wrapper is installed outside the canonical monetary confirmation wrappers
and never touches the audit engine or existing provider adapters.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any, Callable


def draft_pending_confirmation(state: Any) -> bool:
    """A non-mutating pre-run proposal, never an execution authorization."""
    if tuple(getattr(state, "perplexity_queries", ()) or ()):
        return False  # Session request already explicitly confirmed in CAT-05.
    if bool(getattr(state, "perplexity_skip_draft_this_aud", False)):
        return False
    from rasai.console_catalog_plan import selected_catalog_ids
    from rasai.console_perplexity_readiness import inspect_perplexity_readiness

    if "CAT-05" not in selected_catalog_ids(state):
        return False
    info = inspect_perplexity_readiness(state)
    return bool(
        info["configuration_ready"]
        and info["saved_draft_available"]
        and info["configured_source"] in {"INI/RASCUNHO", "SESSÃO"}
    )


def confirm_draft_for_this_aud(state: Any, *, read: Callable[[str], str] | None = None) -> str:
    """Return C=add optional Perplexity, N=skip it, V=abort entire AUD.

    No change to state or API calls occurs while displaying/reading this gate.
    """
    reader = input if read is None else read
    queries = tuple(getattr(state, "perplexity_draft_queries", ()) or ())
    mode = str(getattr(state, "perplexity_draft_search_type", "web") or "web").upper()
    print("\n[ CONFIRMAÇÃO PERPLEXITY - CONSULTA EXTERNA OPCIONAL ]")
    print(f"Configuração salva    : {len(queries)} query(s) | {mode}")
    for index, query in enumerate(queries, 1):
        print(f"  {index}. {query}")
    from rasai.search_geo_alignment import geo_query_alignment
    aligned = geo_query_alignment(
        tuple(getattr(state, "search_queries", ()) or ()), queries,
    )
    print(f"Comparabilidade GEO : {aligned['label']}")
    if aligned["status"] == "DIVERGENT":
        print("AVISO: consultas distintas. A pesquisa pode ser bem-sucedida, "
              "mas a comparação SERP × Perplexity permanecer N/D.")
    print("A Perplexity Search API pode gerar custo adicional, não incluído na")
    print("estimativa de IA quando o preço canônico é desconhecido.")
    print("C. Solicitar Perplexity nesta AUD (sujeito também à confirmação geral)")
    print("N. Continuar AUD sem Perplexity")
    print("V. Voltar ao plano sem executar AUD")
    while True:
        option = reader("Opção Perplexity [C/N/V]: ").strip().upper()
        if option in {"C", "N", "V"}:
            return option
        print("Opção inválida. Use C, N ou V.")


def install(console_module: ModuleType) -> None:
    """Install once as the outermost run wrapper after all execution adapters."""
    if getattr(console_module, "_rasai_perplexity_run_gate_595", False):
        return
    original_run = console_module.run_audit_from_console

    def run(state: Any) -> int:
        from rasai.target_scope_reconciliation import must_review, notices, bind
        if must_review(state):
            print("\n[ REVISÃO DE ESCOPO — ALVO ALTERADO ]")
            for warning in notices(state):
                print("  - " + warning)
            print("C. Confirmar termos para novo alvo (sem API); N. Omitir pesquisas nesta AUD; V. Voltar")
            choice = input("Revisar escopo [C/N/V]: ").strip().upper()
            if choice == "N":
                old_search, old_perplexity = state.search_queries, state.perplexity_queries
                old_skip = state.perplexity_skip_draft_this_aud
                try:
                    state.search_queries = ()
                    state.perplexity_queries = ()
                    state.perplexity_skip_draft_this_aud = True
                    return int(original_run(state) or 0)
                finally:
                    state.search_queries = old_search
                    state.perplexity_queries = old_perplexity
                    state.perplexity_skip_draft_this_aud = old_skip
            if choice != "C":
                state.status = "READY"
                state.operation = "LOCAL:TARGET_SCOPE_REVIEW_REQUIRED"
                return 0
            for source in ("SERP", "PERPLEXITY"):
                bind(state, source)
        if not draft_pending_confirmation(state):
            try:
                return int(original_run(state) or 0)
            finally:
                # D/LIMPAR cancels only this AUD, not later ones in the session.
                state.perplexity_skip_draft_this_aud = False
        selection = confirm_draft_for_this_aud(state)
        if selection == "V":
            # Existing post-run decline flow must not render a new AUD.
            # Preserve no fresh request and issue no provider calls.
            state.status = "READY"
            state.operation = "LOCAL:PERPLEXITY_PROPOSAL_DECLINED"
            state.error = ""
            from rasai.console_first_run_cost_preview import _DECLINED as declined
            declined.add(id(state))
            return 0

        # The operator may skip an optional paid provider while still approving
        # deterministic AUD / AI costs in the canonical monetary gate.
        if selection == "N":
            try:
                return int(original_run(state) or 0)
            finally:
                state.perplexity_skip_draft_this_aud = False

        prior_queries = state.perplexity_queries
        prior_mode = state.perplexity_search_type
        prior_last_status = state.perplexity_last_status
        prior_last_detail = state.perplexity_last_detail
        state.perplexity_queries = tuple(state.perplexity_draft_queries)
        state.perplexity_search_type = state.perplexity_draft_search_type
        state.perplexity_last_status = "PENDING"
        state.perplexity_last_detail = "Consulta Perplexity confirmada nesta AUD; aguardando gate geral"
        try:
            return int(original_run(state) or 0)
        finally:
            # The next run must require a fresh provider-specific confirmation.
            state.perplexity_queries = prior_queries
            state.perplexity_search_type = prior_mode
            # Preserve the actual provider result when execution occurred.
            if state.perplexity_last_status == "PENDING":
                state.perplexity_last_status = prior_last_status
                state.perplexity_last_detail = prior_last_detail
            state.perplexity_skip_draft_this_aud = False

    console_module.run_audit_from_console = run
    console_module._rasai_perplexity_run_gate_595 = True
