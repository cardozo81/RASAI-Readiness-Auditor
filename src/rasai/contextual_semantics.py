"""Additive v2 dispositions over immutable v1 occurrences and the same markup.

Question punctuation, a fragment or details/summary alone proves no editorial
FAQ or gap. No v1 field or recommendation is rewritten; no capture/provider IO.
"""
from __future__ import annotations

from collections import Counter
import re

from rasai.contextual_documents import stable_id

CONTRACT = "contextual-semantic-overlay-v2"
_QUESTION = re.compile(r"^(?:como|qual|quais|quando|onde|quem|quanto|quantos|quantas|por\s+que|o\s+que|posso|é\s+possível|"
                       r"what|how|when|where|who|why|which)\b", re.I)
_NAV_LABELS = frozenset({"menu", "produtos", "navegação", "navegacao", "serviços", "servicos"})
_NAV_TAGS = frozenset({"nav", "header", "footer", "menu"})
_NAV_ROLES = frozenset({"navigation", "menu", "menubar", "contentinfo"})
_FAQ_MARKER = re.compile(r"(?:^|[\s_-])(?:faq|perguntas[-_]frequentes)(?:$|[\s_-])", re.I)

DISPLAY_LABELS = {
    "NAVIGATION_DISCLOSURE": "Disclosure de navegação",
    "NAVIGATION_CONTEXT": "Contexto de navegação ou template",
    "FAQ_EDITORIAL_QUESTION": "FAQ editorial: pergunta observada",
    "FAQ_EDITORIAL_ANSWER": "FAQ editorial: resposta fisicamente vinculada",
    "POTENTIAL_FAQ_QUESTION": "Possível pergunta editorial; resposta N/D",
    "POTENTIAL_FAQ_ANCHOR": "Possível âncora de FAQ; sem prova de lacuna",
    "DISCLOSURE_UNDETERMINED": "Função editorial do disclosure N/D",
    "OBSERVED_CONTROL": "Controle observado; sem falha editorial comprovada",
    "DOCUMENT_CANDIDATE": "Referência documental candidata, não autenticada",
    "OBSERVED_CONTENT": "Conteúdo capturado; sem autenticação de produto ou entidade",
    "UNDETERMINED": "Qualificação N/D",
}
BASIS_LABELS = {
    "V2_MARKUP_UNAVAILABLE": "Markup necessário à qualificação indisponível.",
    "V2_NAVIGATION_ANCESTRY": "Ancestralidade de navegação/template observada.",
    "V2_MENU_LABEL_AND_LINK_BODY": "Rótulo de menu combinado com corpo composto por links.",
    "V2_CLOSED_EDITORIAL_QUESTION_AND_PROSE": "Pergunta contextual, corpo em prosa e vínculo fechado na mesma captura.",
    "V2_QUESTION_WITHOUT_OBSERVED_PROSE_ANSWER": "A resposta editorial não ficou comprovada; isso não prova falha no site.",
    "V2_DISCLOSURE_ROLE_UNPROVEN": "Details/summary não comprova por si só função de FAQ.",
    "V2_FRAGMENT_NOT_EDITORIAL_FAILURE": "Fragmento ou ação não comprova lacuna de conteúdo ou de resposta.",
    "V2_REFERENCE_NOT_DOCUMENT_AUTHENTICATION": "A referência permanece candidata; documento e aplicabilidade não autenticados.",
    "V2_OBSERVED_CONTENT_ONLY": "Trecho local observado, sem diagnóstico novo de motor.",
    "V2_NO_NEW_EDITORIAL_GAP_PROVEN": "Nenhuma falha editorial adicional foi fisicamente comprovada.",
    "V2_V1_HYPOTHESIS_NOT_ACTIONABLE": "A hipótese técnica v1 é preservada; controle ou navegação não sustenta ação editorial.",
    "V2_V1_HYPOTHESIS_CONTEXTUAL_ONLY": "A hipótese técnica v1 permanece contextual; insuficiente para ação editorial v2.",
}


def _question(text):
    # Combined with structure/prose below; never sufficient on its own.
    return len(text.split()) >= 2 and text.rstrip().endswith("?") and bool(_QUESTION.match(text.strip()))


def _navigation(node):
    return node["tag"] in _NAV_TAGS or str(node["attrs"].get("role") or "").casefold() in _NAV_ROLES


def _facts(parser):
    """Linear structural indexes; no second parser and no unbounded DOM walks."""
    nodes = parser.nodes
    last = list(range(len(nodes)))
    link_count = [int(n["tag"] == "a") for n in nodes]
    coverage = [0] * (len(parser.tokens) + 1)
    for node in nodes:
        if node["tag"] == "a" and node["last"] is not None:
            coverage[node["first"]] += 1
            coverage[node["last"]] -= 1
    outside, depth = [0], 0
    for i, token in enumerate(parser.tokens):
        depth += coverage[i]
        outside.append(outside[-1] + (len(token.split()) if depth == 0 else 0))
    prose, navigation = [0], [0]
    for node in nodes:
        end = node["last"] if node["last"] is not None else len(parser.tokens)
        prose.append(prose[-1] + int(node["tag"] in {"p", "dd", "blockquote"}
            and node["end"] is not None and outside[end] - outside[node["first"]] >= 2))
        navigation.append(navigation[-1] + int(_navigation(node)))
    for i in range(len(nodes) - 1, -1, -1):
        parent = nodes[i]["parent"]
        if parent is not None:
            last[parent] = max(last[parent], last[i])
            link_count[parent] += link_count[i]
    return last, link_count, outside, prose, navigation


def qualify_capture(capture, parser=None):
    """Return a separate overlay; callers retain the entire v1 packet verbatim."""
    diagnoses, question_rows, navigation_disclosures = [], {}, set()
    facts = _facts(parser) if parser is not None else None
    for row in capture["occurrences"]:
        category, disposition, basis = "UNDETERMINED", "ND", ["V2_MARKUP_UNAVAILABLE"]
        node = None
        if parser is not None and 0 <= row["ordinal"] < len(parser.nodes):
            node = parser.nodes[row["ordinal"]]
        if node is not None and row["category"] != "FAQ_ANSWER":
            chain = parser.ancestors(node)
            nav = any(_navigation(n) or n["parent"] in navigation_disclosures for n in chain)
            if row["category"] == "FRAGMENT_ACTION":
                category = "POTENTIAL_FAQ_ANCHOR" if _question(row["text"]) else "OBSERVED_CONTROL"
                disposition, basis = "NOT_ACTIONABLE", ["V2_FRAGMENT_NOT_EDITORIAL_FAILURE"]
                if nav:
                    basis.append("V2_NAVIGATION_ANCESTRY")
            elif row["category"] in {"NAVIGATION", "FOOTER", "SOCIAL"} or nav:
                category = "NAVIGATION_DISCLOSURE" if node["tag"] == "summary" else "NAVIGATION_CONTEXT"
                disposition, basis = "NOT_ACTIONABLE", ["V2_NAVIGATION_ANCESTRY"]
            elif row["category"] == "FAQ_QUESTION":
                parent_index = node["parent"]
                parent = parser.nodes[parent_index] if parent_index is not None else None
                category, basis = "DISCLOSURE_UNDETERMINED", ["V2_DISCLOSURE_ROLE_UNPROVEN"]
                if parent is not None and parent["tag"] == "details" and parent["end"] is not None and node["end"] is not None:
                    last, links, outside, prose, navigation = facts
                    body_first, body_last = last[row["ordinal"]] + 1, last[parent_index] + 1
                    body_links = links[parent_index] - links[row["ordinal"]]
                    body_prose = prose[body_last] - prose[body_first]
                    body_words = outside[parent["last"]] - outside[node["last"]]
                    body_nav = navigation[body_last] - navigation[body_first]
                    label = parser.text(node).strip().casefold()
                    faq_scope = any(_FAQ_MARKER.search(str(n["attrs"].get(k) or ""))
                        for n in chain for k in ("id", "class")) or any(
                        "FAQPage" in str(n["attrs"].get("itemtype") or "") for n in chain)
                    main_scope = any(n["tag"] in {"main", "article"} or n["attrs"].get("role") == "main" for n in chain)
                    if body_nav or (label in _NAV_LABELS and body_links > 0 and body_prose == 0):
                        category, disposition = "NAVIGATION_DISCLOSURE", "NOT_ACTIONABLE"
                        basis = ["V2_NAVIGATION_ANCESTRY" if body_nav else "V2_MENU_LABEL_AND_LINK_BODY"]
                    elif _question(parser.text(node)) and (main_scope or faq_scope):
                        if body_words >= 2 and (body_prose > 0 or faq_scope):
                            category, disposition = "FAQ_EDITORIAL_QUESTION", "QUALIFIED_CONTEXT"
                            basis = ["V2_CLOSED_EDITORIAL_QUESTION_AND_PROSE"]
                        else:
                            category = "POTENTIAL_FAQ_QUESTION"
                            basis = ["V2_QUESTION_WITHOUT_OBSERVED_PROSE_ANSWER"]
            elif row["category"] == "DOCUMENT_REFERENCE":
                category, disposition = "DOCUMENT_CANDIDATE", "QUALIFIED_CONTEXT"
                basis = ["V2_REFERENCE_NOT_DOCUMENT_AUTHENTICATION"]
            elif row["category"] == "CTA":
                category, disposition = "OBSERVED_CONTROL", "NOT_ACTIONABLE"
                basis = ["V2_NO_NEW_EDITORIAL_GAP_PROVEN"]
            elif row["category"] in {"MAIN_CONTENT", "COMMERCIAL_CANDIDATE", "TEXT_MENTION"}:
                category, disposition, basis = "OBSERVED_CONTENT", "QUALIFIED_CONTEXT", ["V2_OBSERVED_CONTENT_ONLY"]
            if category == "NAVIGATION_DISCLOSURE" and node["tag"] == "summary":
                navigation_disclosures.add(node["parent"])
        if row["category"] == "FAQ_ANSWER":
            question = question_rows.get(row["faq_question_ref"])
            if question is not None:
                category = ("FAQ_EDITORIAL_ANSWER" if question["display_category_v2"] == "FAQ_EDITORIAL_QUESTION"
                            else question["display_category_v2"])
                disposition, basis = question["semantic_disposition_v2"], list(question["basis"])
        diagnosis = dict(diagnosis_id=stable_id(CONTRACT, row["occurrence_id"]),
            occurrence_id=row["occurrence_id"], v1_category=row["category"],
            display_category_v2=category, semantic_disposition_v2=disposition, basis=basis,
            faq_question_ref_v2=row["faq_question_ref"] if category == "FAQ_EDITORIAL_ANSWER" else None,
            evidence_refs=[dict(occurrence_id=row["occurrence_id"], snapshot_id=capture["snapshot_id"],
                source_ref=capture["source_ref"], source_sha256=capture["source_sha256"],
                text_range=dict(row["text_range"]))],
            limitations=["QUALIFICATION_NOT_RENDERED_VISIBILITY_OR_ENGINE_VERDICT",
                         "EDITORIAL_INTENT_NOT_INDEPENDENTLY_AUTHENTICATED"])
        diagnoses.append(diagnosis)
        if row["category"] == "FAQ_QUESTION":
            question_rows[row["occurrence_id"]] = diagnosis
    return dict(contract=CONTRACT, diagnoses=diagnoses)


def report_overlay(captures, v1_recommendations):
    """Join by physical IDs after existing caps; no v1 data or hypotheses removed."""
    diagnoses = []
    for capture in captures:
        overlay = capture.get("semantic_overlay_v2") or qualify_capture(capture)
        by_id = {d["occurrence_id"]: d for d in overlay["diagnoses"]}
        fallback = {d["occurrence_id"]: d for d in qualify_capture(capture)["diagnoses"]}
        diagnoses.extend(by_id.get(o["occurrence_id"], fallback[o["occurrence_id"]]) for o in capture["occurrences"])
    by_id = {d["occurrence_id"]: d for d in diagnoses}
    states = Counter(d["semantic_disposition_v2"] for d in diagnoses)
    classes = Counter(d["display_category_v2"] for d in diagnoses)
    history = []
    for recommendation in v1_recommendations:
        refs = [by_id[r["occurrence_id"]] for r in recommendation["evidence_refs"] if r["occurrence_id"] in by_id]
        not_actionable = bool(refs) and all(d["semantic_disposition_v2"] == "NOT_ACTIONABLE" for d in refs)
        history.append(dict(disposition_id=stable_id(CONTRACT, recommendation["recommendation_id"]),
            v1_recommendation_id=recommendation["recommendation_id"],
            semantic_disposition_v2="NOT_ACTIONABLE" if not_actionable else "CONTEXTUAL_ONLY",
            not_actionable=not_actionable, actionable=False,
            superseded_by=[d["diagnosis_id"] for d in refs],
            basis=["V2_V1_HYPOTHESIS_NOT_ACTIONABLE" if not_actionable else "V2_V1_HYPOTHESIS_CONTEXTUAL_ONLY"],
            evidence_refs=recommendation["evidence_refs"], limitations=["V1_HYPOTHESIS_RETAINED_VERBATIM"]))
    known = all(c["counts"]["observed_occurrences"] is not None for c in captures) and bool(captures)
    return dict(contract=CONTRACT, diagnoses=diagnoses,
        counts=dict(raw=len(diagnoses), qualified=states["QUALIFIED_CONTEXT"], not_actionable=states["NOT_ACTIONABLE"],
            nd=states["ND"], observed_v1=sum(c["counts"]["observed_occurrences"] for c in captures) if known else None,
            faq_questions=classes["FAQ_EDITORIAL_QUESTION"], faq_answers=classes["FAQ_EDITORIAL_ANSWER"],
            document_candidates=classes["DOCUMENT_CANDIDATE"]),
        recommendation_counts=dict(raw=len(v1_recommendations), qualified=0,
            not_actionable=sum(h["not_actionable"] for h in history), nd=sum(not h["not_actionable"] for h in history)),
        recommendation_history=history, actionable_recommendations=[],
        limitations=["V2_NO_NEW_EDITORIAL_GAP_PROVEN", "QUALIFIED_CONTEXT_IS_NOT_ACTIONABLE_OPPORTUNITY"])
