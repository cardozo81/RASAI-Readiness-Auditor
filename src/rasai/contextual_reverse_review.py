"""Read-only, evidence-bound editorial review queue for contextual report #690.

Projection over persisted v1/v2/v3 facts: no crawling, model calls, scoring or
promotion of historical technical hypotheses into verified SEO issues.
"""
from __future__ import annotations

from collections import Counter
import re
import unicodedata

from rasai.contextual_documents import stable_id

CONTRACT = "contextual-reverse-editorial-projection-v1"
_CLAIM = re.compile(r"(?i)(?:100\s*%|sem tarifas|marca líder|exclusiv[oa]s?|até\s+\d+)")



_TITLE_SEPARATOR = re.compile(r"\s+(?:[|·•—–]|--?)\s+")


def _plain_topic(value: str) -> str:
    """Normalize typography, never infer semantic equivalence from synonyms."""
    folded = unicodedata.normalize("NFKD", str(value).casefold())
    without_accents = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _title_contains_exact_heading_segment(title: str, heading: str) -> bool:
    """An exact title segment matching H1 is not evidence of intent divergence.

    Typical title: "Seguro de vida | Nome da marca". Do not suppress cases
    whose difference requires editorial judgment (product or scope changes).
    """
    normalized_heading = _plain_topic(heading)
    return bool(normalized_heading) and any(
        _plain_topic(segment) == normalized_heading
        for segment in _TITLE_SEPARATOR.split(title)
    )

def review_projection(report: dict) -> dict:
    """Generate conditional *verification tasks*, never findings of an SEO defect."""
    tasks: list[dict] = []

    def add(kind, title, rationale, validation, refs, *, confidence="PARCIAL"):
        if not refs:
            return
        tasks.append(dict(
            task_id=stable_id(CONTRACT, kind, *(str(r.get("snapshot_id", "")) +
                                                 str(r.get("occurrence_id", "")) +
                                                 str(r.get("heading_id", "")) for r in refs)),
            kind=kind, title=title, status="VALIDACAO_NECESSARIA",
            evidence_sufficiency=confidence, rationale=rationale,
            validation=validation, evidence_refs=refs[:16],
            evidence_refs_total=len(refs),
            evidence_refs_omitted=max(0, len(refs) - 16),
            limitations=["NOT_AN_ENGINE_FINDING", "NO_RANKING_OR_INDEXATION_INFERENCE"]))

    structures = (report.get("content_structure_v3") or {}).get("captures") or []
    for surface in structures:
        if surface.get("coverage") != "CAPTURE_INSPECTED":
            continue
        headings = surface.get("headings") or []
        main_h1 = [h for h in headings if h["tag"] == "h1"
                   and h["scope"] == "MAIN_OR_ARTICLE"]
        title = surface.get("title")
        if (title and main_h1 and not _title_contains_exact_heading_segment(
                title["text"], main_h1[0]["text"])):
            add("TITLE_H1_INTENT", "Conferir alinhamento de intenção entre title e H1",
                "Title e H1 principal não apresentam segmento de título literalmente equivalente; possível desalinhamento de intenção ainda exige revisão humana, sem prova de defeito SEO.",
                "Revisar se os dois títulos descrevem a intenção de busca, o produto e a página capturada.",
                [dict(snapshot_id=surface["snapshot_id"], source_ref=surface["source_ref"],
                      source_sha256=surface["source_sha256"], text=title["text"],
                      text_range=title["text_range"], label="Title"),
                 dict(snapshot_id=surface["snapshot_id"], heading_id=main_h1[0]["heading_id"],
                      source_ref=surface["source_ref"], source_sha256=surface["source_sha256"],
                      text=main_h1[0]["text"], text_range=main_h1[0]["text_range"], label="H1")])
        if len(main_h1) > 1:
            add("H1_HIERARCHY", "Revisar hierarquia de títulos na área principal",
                "Foram capturados múltiplos H1 principais; isso não determina penalidade de busca.",
                "Revisar estrutura semântica e experiência de tecnologia assistiva.",
                [dict(snapshot_id=surface["snapshot_id"], heading_id=h["heading_id"],
                      source_ref=surface["source_ref"], source_sha256=surface["source_sha256"],
                      text=h["text"], text_range=h["text_range"], label="H1") for h in main_h1])
        claims = [h for h in headings if h["scope"] == "MAIN_OR_ARTICLE"
                  and _CLAIM.search(h["text"])]
        if claims:
            add("COMMERCIAL_CLAIM_SUPPORT", "Conferir suporte para alegações comerciais",
                "Expressões materiais foram observadas em headings; não foram autenticadas, verificadas ou refutadas.",
                "Vincular cada alegação a condições, produto, escopo e evidência vigente autorizada; ajustar texto somente após revisão editorial/jurídica.",
                [dict(snapshot_id=surface["snapshot_id"], heading_id=h["heading_id"],
                      source_ref=surface["source_ref"], source_sha256=surface["source_sha256"],
                      text=h["text"], text_range=h["text_range"], label=h["tag"].upper())
                 for h in claims], confidence="INSUFICIENTE")
    # One task per observed FAQ control with an unobserved target, never an
    # assertion that the answer or target is absent from the live website.
    controls = (report.get("faq_aria_v3") or {}).get("controls") or []
    missing = [c for c in controls if c["status"] == "NOT_OBSERVED_ND"]
    if missing:
        add("FAQ_RECAPTURE", "Inspecionar controles FAQ sem alvo na captura",
            "O vínculo ARIA identifica um alvo não observado no DOM capturado; conteúdo carregado após interação permanece N/D.",
            "Em operação autorizada, acionar controles, capturar DOM após interação e confrontar HTML bruto e renderizado sem inferir indexação.",
            [dict(snapshot_id=c.get("snapshot_id"), source_ref=c.get("source_ref"),
                  source_sha256=c.get("source_sha256"), occurrence_id=c.get("occurrence_id"),
                  text=c.get("question"), label="Pergunta FAQ") for c in missing])
    # Consolidation affects display, not the original occurrence ledger.
    documents: dict[tuple, list] = {}
    for capture in report.get("captures", ()):
        for occ in capture.get("occurrences", ()):
            if occ["category"] != "DOCUMENT_REFERENCE":
                continue
            key = (capture["page_id"], capture["device"],
                   occ.get("resolved_url") or occ.get("href_literal") or occ["occurrence_id"])
            documents.setdefault(key, []).append(dict(
                snapshot_id=capture["snapshot_id"], source_ref=capture["source_ref"],
                source_sha256=capture["source_sha256"], occurrence_id=occ["occurrence_id"],
                text=occ.get("text"), destination=occ.get("resolved_url") or occ.get("href_literal"),
                text_range=occ.get("text_range"), label="Referência documental candidata"))
    if documents:
        refs = [item for rows in documents.values() for item in rows]
        add("DOCUMENT_CONTEXT", "Validar vínculo contextual de referências documentais",
            "O link foi observado no markup; isso não prova conteúdo, autenticidade, vigência ou aplicabilidade do destino.",
            "Confirmar finalidade, produto e condições do link junto a fonte autorizada, sem GET automático.",
            refs, confidence="INSUFICIENTE")
    historic = (report.get("semantic_v2") or {}).get("recommendation_counts") or {}
    return dict(contract=CONTRACT, tasks=tasks, counts=dict(
        verification_tasks=len(tasks),
        by_kind=dict(Counter(t["kind"] for t in tasks)),
        actionable_v2=historic.get("qualified", 0),
        historical_non_actionable=historic.get("not_actionable", 0),
        historical_undetermined=historic.get("nd", 0)),
        limitations=["CONSULTATIVE_VERIFICATION_ONLY", "NOT_ADDED_TO_SCORING_OR_REMEDIATION",
                     "NO_LIVE_HTTP_OR_AI_CALLS"])
