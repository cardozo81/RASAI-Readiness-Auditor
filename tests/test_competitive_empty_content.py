"""Focused regression for HTTP 200 empty competitive content (#313)."""
from rasai.search_intelligence.content import (
    ContentFetchStatus, CompetitivePageFeatures, compare_content_features,
    _has_comparable_semantic_content,
)


def page(url, *, words=0, title=None, status=ContentFetchStatus.OBSERVED):
    return CompetitivePageFeatures(
        role="COMPETITOR_CANDIDATE", domain="example.com",
        requested_url=url, final_url=url, status=status,
        http_status=200, content_type="text/html",
        content_sha256="sha", bytes_read=212,
        word_count=words, title=title,
        query_terms=("seguro", "vida"),
    )


def test_http_200_empty_page_is_preserved_but_not_a_comparable_baseline():
    client = page("https://cliente.example/vida", words=250)
    empty = page("https://competidor.example/empty")
    usable = page("https://competidor.example/content", words=500)
    assert empty.status is ContentFetchStatus.OBSERVED
    assert not _has_comparable_semantic_content(empty)
    gaps = compare_content_features(client, (empty, usable))
    assert gaps
    assert all("https://competidor.example/empty" not in x.evidence_urls for x in gaps)
    assert any(x.leader_reference == 500 for x in gaps)


def test_all_empty_competitors_yield_no_gaps():
    assert compare_content_features(
        page("https://cliente.example/vida", words=150),
        (page("https://competidor.example/empty"),),
    ) == ()


def test_title_only_semantics_preserve_existing_comparison_eligibility():
    assert _has_comparable_semantic_content(page("https://example.com", title="Seguro de vida"))
