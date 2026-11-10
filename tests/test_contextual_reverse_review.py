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
    assert len(documents["evidence_refs"]) == 2  # grouped as one task, raw occurrences intact
    public = contextual_panel(result, "geo-content-review.html", private=False)
    private = (tmp_path / "private" / "geo-content-review.html").read_text(encoding="utf-8")
    assert "id='editorial-verification'" in public
    assert "Loja de Seguro Alpha" not in public
    assert "Sem tarifas escondidas" not in public
    assert "Sem tarifas escondidas" in private
    assert "href='geo.html#contextual-semantic-v2'" in private
    assert "Controles e fragmentos não acionáveis" in private or "Histórico técnico v1" in private
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
