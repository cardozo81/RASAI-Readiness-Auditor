"""Deterministic editorial hypotheses downstream of observed evidence only."""
from rasai.contextual_documents import stable_id

METHOD = "contextual-editorial-v1"


def ai_availability(mode="none"):
    if mode not in {"none", "requested"}:
        raise ValueError("unsupported AI mode")
    # GEO AI writes its own execution telemetry to AUD; Competitive AI requires
    # CONSOLIDATED competitive acquisition. Neither is an authorized, read-only
    # contextual task profile. Do not invent a new transport or reuse consent.
    return dict(mode=mode, state="DISABLED" if mode == "none" else "NOT_AUTHORIZED",
                reason="CONTEXTUAL_TASK_CONSENT_PROFILE_NOT_AUTHORIZED", provider_calls=0, cost=0)


def recommendations(captures):
    rules = {
        "FAQ_QUESTION": ("Resposta da pergunta não observada no vínculo físico capturado.",
            "Explicitar a resposta junto à pergunta na estrutura FAQ, após revisão editorial.",
            "Conferir pergunta e resposta na mesma captura por dispositivo."),
        "DOCUMENT_REFERENCE": ("Referência documental observada; conteúdo e aplicabilidade N/D.",
            "Explicar a finalidade do link junto ao produto e submeter o documento à revisão autorizada.",
            "Validar o contexto local; autenticidade e vigência exigem revisão independente."),
        "FRAGMENT_ACTION": ("Fragmento ou ação observada; destino textual não comprovado por este link.",
            "Conferir se o texto do controle explica a ação e se seu painel contém o contexto necessário.",
            "Inspecionar painel e controle vinculados em captura autorizada; href sozinho não prova conteúdo."),
    }
    output, grouped = [], {}
    for capture in captures:
        for occurrence in capture["occurrences"]:
            category = occurrence["category"]
            if category not in rules or (category == "FAQ_QUESTION" and occurrence["faq_answer_observed"]):
                continue
            # One opportunity per observed destination/question and device-page.
            key = (capture["page_id"], capture["device"], category,
                   occurrence["resolved_url"] or occurrence["href_literal"] or occurrence["text"])
            reference = dict(occurrence_id=occurrence["occurrence_id"], snapshot_id=capture["snapshot_id"],
                             source_ref=capture["source_ref"], source_sha256=capture["source_sha256"])
            if key in grouped:
                grouped[key]["evidence_refs"].append(reference)
                continue
            problem, suggestion, validation = rules[category]
            row = dict(recommendation_id=stable_id(METHOD, capture["audit_id"], *key),
                finding_or_opportunity="CONSULTATIVE_OPPORTUNITY", scope=dict(audit_id=capture["audit_id"],
                    page_id=capture["page_id"], device=capture["device"]), evidence_refs=[reference],
                observed_text=occurrence["text"], location=occurrence["text_range"],
                problem=problem, suggested_change=suggestion, expected_validation=validation,
                sufficiency="PARCIAL", materiality="LOCAL_PHYSICAL_REFERENCE",
                limitations=["EDITORIAL_HYPOTHESIS_NOT_ENGINE_FINDING", "NO_COMPARATIVE_INTENT_GAP_PROVEN",
                              "NO_RANKING_OR_REGULATORY_VERDICT"], method_version=METHOD)
            output.append(row)
            grouped[key] = row
    return output
