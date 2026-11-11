"""Offline checks for conditional reverse editorial projection and private/public separation."""
from pathlib import Path

from rasai import contextual_advisory
from rasai.contextual_advisory_html import contextual_panel
from rasai.contextual_reverse_review import CONTRACT
from tests.test_document_advisory import source


def test_reverse_review_infers_only_conditional_tasks_with_traceable_evidence(tmp_path):
    root = source(tmp_path)
    (root / "artifacts/raw.html").write_text(
        "<!doctype html><html><head><title>Loja de Seguro Alpha</title></head>"
        "<body><main><h1>Seguros Friday</h1>"
        "<h2>Vantagens</h2><h3>Sem tarifas escondidas</h3>"
        "<button role='button' aria-controls='faq-close' aria-expanded='false'>"
        "Como funciona o seguro Alpha?</button>"
        "<a href='/terms.pdf'>Regulamento Alpha</a>"
        "<a href='/terms.pdf'>Regulamento Alpha</a>"
        "</main></body></html>", encoding="utf-8")
    before = contextual_advisory._inventory(root)
    result = contextual_advisory.build_companion(root, tmp_path / "private")
    review = result["reverse_review"]
    assert review["contract"] == CONTRACT
    by_kind = review["counts"]["by_kind"]
    assert by_kind["TITLE_H1_INTENT"] >= 1
    assert by_kind["COMMERCIAL_CLAIM_SUPPORT"] >= 1
    assert by_kind["DOCUMENT_CONTEXT"] >= 1
    assert review["counts"]["actionable_v2"] == 0
    for task in review["tasks"]:
        assert task["status"] == "VALIDACAO_NECESSARIA"
        assert task["validation"] and task["rationale"]
        assert task["evidence_refs"]
        assert all(ref["source_sha256"] for ref in task["evidence_refs"])
    documents = [t for t in review["tasks"] if t["kind"] == "DOCUMENT_CONTEXT"][0]
    assert len(documents["evidence_refs"]) == 4  # one grouped task; two links per device remain intact
    public = contextual_panel(result, "geo-content-review.html", private=False)
    private = (tmp_path / "private" / "geo-content-review.html").read_text(encoding="utf-8")
    assert "id='editorial-verification'" in public
    assert "Loja de Seguro Alpha" not in public
    assert "Sem tarifas escondidas" not in public
    assert "Sem tarifas escondidas" in private
    assert "href='geo.html#contextual-semantic-v2'" in private
    assert "Decisão editorial e histórico técnico v1" in private
    assert contextual_advisory._inventory(root) == before
    assert result["network_requests"] == result["audit_writes"] == result["ai"]["provider_calls"] == 0


def test_no_html_markup_gives_no_fabricated_editorial_tasks():
    from rasai.contextual_reverse_review import review_projection
    report = dict(content_structure_v3={"captures": []},
                  faq_aria_v3={"controls": []}, captures=[], semantic_v2={
                      "recommendation_counts": {"qualified": 0, "not_actionable": 0, "nd": 0}})
    projection = review_projection(report)
    assert projection["counts"]["verification_tasks"] == 0
    assert projection["tasks"] == []


def test_brand_suffix_or_prefix_is_not_a_title_h1_issue():
    from rasai.contextual_reverse_review import review_projection

    def report(title_text, heading_text):
        return {
            "content_structure_v3": {"captures": [{
                "coverage": "CAPTURE_INSPECTED",
                "snapshot_id": "S-1",
                "source_ref": "artifacts/rendered.html",
                "source_sha256": "a" * 64,
                "title": {"text": title_text, "text_range": [0, 30]},
                "headings": [{
                    "tag": "h1", "scope": "MAIN_OR_ARTICLE",
                    "text": heading_text, "text_range": [35, 45],
                    "heading_id": "H-1",
                }],
            }]},
            "faq_aria_v3": {"controls": []},
            "captures": [],
            "semantic_v2": {"recommendation_counts": {}},
        }

    for title in ("Seguro de vida | Marca Alpha",
                  "Marca Alpha — SEGURO DE VIDA",
                  "Seguro de vida  ·  Marca Alpha"):
        result = review_projection(report(title, "Seguro de Vida"))
        assert "TITLE_H1_INTENT" not in result["counts"]["by_kind"]

    divergent = review_projection(report("Seguro de vida | Marca Alpha", "Seguro de carro"))
    assert divergent["counts"]["by_kind"]["TITLE_H1_INTENT"] == 1
    assert divergent["tasks"][0]["status"] == "VALIDACAO_NECESSARIA"


def test_grouped_document_review_exposes_full_count_when_proof_list_is_bounded():
    from rasai.contextual_reverse_review import review_projection
    occurrences = [{
        "category": "DOCUMENT_REFERENCE",
        "occurrence_id": f"O-{i}",
        "resolved_url": "https://example.org/terms.pdf",
        "href_literal": "/terms.pdf",
        "text": "Regulamento",
        "text_range": {"start": i, "end": i + 1},
    } for i in range(20)]
    capture = {
        "page_id": "PAGE-1", "device": "mobile",
        "snapshot_id": "SNAP-1", "source_ref": "artifacts/raw.html",
        "source_sha256": "a" * 64, "occurrences": occurrences,
    }
    projection = review_projection({
        "content_structure_v3": {"captures": []},
        "faq_aria_v3": {"controls": []},
        "captures": [capture], "semantic_v2": {"recommendation_counts": {}},
    })
    task = next(t for t in projection["tasks"] if t["kind"] == "DOCUMENT_CONTEXT")
    assert task["evidence_refs_total"] == 20
    assert task["evidence_refs_omitted"] == 4
    assert len(task["evidence_refs"]) == 16
    assert len(capture["occurrences"]) == 20
    assert all(x["source_sha256"] == "a" * 64 for x in task["evidence_refs"])
