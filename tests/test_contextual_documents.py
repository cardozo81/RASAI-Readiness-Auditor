"""Synthetic offline contextual discovery contracts."""
from datetime import datetime, timezone

import pytest

from rasai.contextual_documents import DiscoveryLimits, digest, discover_references, stable_id
from rasai.domain import DeviceContext, PageSnapshot


def snapshot(**kw):
    values = dict(snapshot_id="SNP-fixture", page_id="PGE-fixture", device=DeviceContext.MOBILE,
                  requested_url="https://example.test/start", final_url="https://example.test/product/",
                  captured_at=datetime(2026, 11, 10, tzinfo=timezone.utc))
    return PageSnapshot(**(values | kw))


def discover(html=b"", **kw):
    return discover_references(audit_id="AUD-fixture", snapshot=snapshot(), original=html,
                               artifact_ref="artifacts/page.html", surface="RAW_HTML_FALLBACK", **kw)


@pytest.mark.parametrize("href,resolved,policy", [
    ("../terms.pdf", "https://example.test/terms.pdf", "REFERENCE_ONLY_NO_EGRESS"),
    ("https://example.test/terms.pdf", "https://example.test/terms.pdf", "REFERENCE_ONLY_NO_EGRESS"),
    ("#terms", None, "INVALID_REFERENCE"),
    ("javascript:alert(1)", None, "INVALID_REFERENCE"),
    ("data:text/html,x", None, "INVALID_REFERENCE"),
    ("https://[broken", None, "INVALID_REFERENCE"),
    ("https://127.0.0.1/a", "https://127.0.0.1/a", "UNSAFE_ADDRESS"),
    ("https://other.test/a", "https://other.test/a", "CROSS_ORIGIN_NOT_AUTHORIZED"),
])
def test_reference_policy(href, resolved, policy):
    row = discover(f'<a href="{href}">Conditions</a>'.encode())["occurrences"][0]
    assert (row["resolved_url"], row["url_policy"]) == (resolved, policy)
    assert row["document_final_url_observed"] is None


def test_duplicate_identity_context_and_spa_unknown():
    data = b'<p>Contract Alpha <a href="/terms">Conditions</a> end</p><a href="/terms">Conditions</a>'
    first = discover(data)
    assert first == discover(data)
    links = [x for x in first["occurrences"] if x["kind"] == "ANCHOR"]
    assert len(links) == 2
    assert links[0]["occurrence_id"] != links[1]["occurrence_id"]
    assert links[0]["document_candidate_id"] == links[1]["document_candidate_id"]
    assert "Contract Alpha" in links[0]["context"]
    assert "LATE_SPA_REFERENCES_NOT_CAPTURED_ND" in first["limitations"]
    assert all(x["applicability"] == "INSUFFICIENT_EVIDENCE" for x in links)


def test_limits_and_uncaptured():
    assert discover(b"xxx", limits=DiscoveryLimits(max_bytes=2))["limitations"][-1] == "SOURCE_BYTE_LIMIT_ND"
    result = discover(b'<a href="/a">a</a><a href="/b">b</a>', limits=DiscoveryLimits(max_occurrences=1))
    assert len(result["occurrences"]) == 1
    assert "OCCURRENCE_LIMIT_PARTIAL" in result["limitations"]


@pytest.mark.parametrize("href,text", [("/contratos/condicoes-gerais", "Condições Gerais"),
                                       ("../docs/termos.pdf", "Baixar arquivo")])
def test_document_after_large_menu_survives_cap_with_original_identity(href, text):
    menus = ''.join(f'<a href="/menu/{i}">Entrar {i}</a>' for i in range(520))
    html = f'<html><body><nav>{menus}</nav><p><a href="{href}">{text}</a></p></body></html>'.encode()
    result = discover(html)
    repeat = discover(html)
    link = next(o for o in result["occurrences"] if o["href_literal"] == href)
    assert result == repeat
    assert link["ordinal"] == 520
    assert link["occurrence_id"] == stable_id("AUD-fixture", "SNP-fixture", "MOBILE", digest(html), "ANCHOR", 520)
    tight = discover(html, limits=DiscoveryLimits(max_occurrences=1))
    assert tight["occurrences"][0]["occurrence_id"] == link["occurrence_id"]
    assert link["resolved_url"] in {"https://example.test/contratos/condicoes-gerais", "https://example.test/docs/termos.pdf"}
    assert "href" in link["documentary_signals"]
    assert link["reference_state"] == "REFERENCED_ONLY"
    assert link["applicability"] == "INSUFFICIENT_EVIDENCE"
    generic = next(o for o in result["occurrences"] if o["href_literal"] == "/menu/0")
    assert generic["documentary_signals"] == []
    assert generic["reference_state"] == "REFERENCED_ONLY"


def test_documents_duplicate_mentions_and_context_precede_generic_budget():
    menu = ''.join(f'<a href="/login/{i}">Entrar</a>' for i in range(510))
    html = ('<html><body><a href="../contrato">Contrato do produto</a>' + menu +
            '<a href="../contrato">Contrato do produto</a>'
            '<p>Consulte as condições gerais <a href="/arquivo/17">Leia mais</a> para detalhes.</p>'
            '<p>Regulamento disponível mediante solicitação.</p></body></html>').encode()
    result = discover(html, limits=DiscoveryLimits(max_occurrences=12))
    links = [o for o in result["occurrences"] if o["href_literal"] == "../contrato"]
    assert [o["ordinal"] for o in links] == [0, 511]
    assert links[0]["document_candidate_id"] == links[1]["document_candidate_id"]
    assert links[0]["occurrence_id"] != links[1]["occurrence_id"]
    context_link = next(o for o in result["occurrences"] if o["href_literal"] == "/arquivo/17")
    assert context_link["documentary_signals"] == ["adjacent_text"]
    assert "condições gerais" in context_link["context"]
    assert any(o["kind"] == "TEXT_MENTION" and "Regulamento" in o["text"] for o in result["occurrences"])
    assert result["documentary_occurrences_omitted"] == 0
    assert [o["ordinal"] for o in result["occurrences"]] == sorted(o["ordinal"] for o in result["occurrences"])


def test_excess_documentary_references_are_explicitly_partial():
    html = ('<html><body>' + ''.join(f'<a href="/contratos/{i}.pdf">Arquivo {i}</a>' for i in range(510)) + '</body></html>').encode()
    result = discover(html)
    assert len(result["occurrences"]) == 500
    assert result["documentary_occurrences_total"] == 510
    assert result["documentary_occurrences_omitted"] == 10
    assert "OCCURRENCE_LIMIT_PARTIAL" in result["limitations"]
    assert all(o["applicability"] == "INSUFFICIENT_EVIDENCE" for o in result["occurrences"])
