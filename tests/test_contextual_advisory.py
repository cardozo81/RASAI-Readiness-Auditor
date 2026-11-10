import json
from pathlib import Path
import socket
import sqlite3

import pytest

from rasai import contextual_advisory as advisory
from rasai.contextual_advisory_html import PAGES, contextual_panel
from rasai.contextual_documents import digest
from rasai.contextual_editorial import recommendations, ai_availability
from tests.test_document_advisory import source
from tests.test_contextual_content import observed


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize("ai,state", [("none", "DISABLED"), ("requested", "NOT_AUTHORIZED")])
def test_companion_e2e_no_documents_no_ai_and_full_hash_parity(tmp_path, ai, state):
    root = source(tmp_path)
    html = '<main><p>Produto Alpha.</p><details><summary>Qual prazo?</summary></details>'
    html += '<a href="/terms.pdf">Regulamento</a><a href="/terms.pdf">Regulamento</a></main>'
    (root / "artifacts/raw.html").write_text(html, encoding="utf-8")
    before = advisory._inventory(root)
    out = tmp_path / "private"
    result = advisory.build_companion(root, out, ai=ai)
    assert advisory._inventory(root) == before == result["source_inventory"]
    assert result["source_unchanged"] is True
    assert result["ai"]["state"] == state
    assert result["network_requests"] == result["audit_writes"] == result["ai"]["provider_calls"] == 0
    assert len(result["recommendations"]) == 4  # two contexts, one per question and document
    assert any(len(r["evidence_refs"]) == 2 for r in result["recommendations"])
    assert set(p.name for p in out.glob("*.html")) == set(PAGES)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["source_inventory"] == before
    for name, seal in manifest["output_inventory"].items():
        assert digest((out / name).read_bytes()) == seal
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "<table" not in index and "Regulamento" not in index
    assert "Content-Security-Policy" in index
    assert "Regulamento" in (out / "capture-context.html").read_text(encoding="utf-8")
    assert "N/D" in (out / "geo.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        advisory.build_companion(root, out)


def test_canonical_panels_exclude_arbitrary_sensitive_literals(tmp_path):
    root = source(tmp_path)
    secret = "person@example.test sk-abcdefghijklmnop"
    (root / "artifacts/raw.html").write_text('<main><a href="/terms.pdf?token=secret">Regulamento ' + secret + '</a></main>')
    result = advisory.load_projection(root)
    for page in PAGES:
        html = contextual_panel(result, page)
        assert secret not in html and "token=secret" not in html
        assert "contextual-content" in html


def test_hostile_html_is_text_not_script_or_link(tmp_path):
    root = source(tmp_path)
    (root / "artifacts/raw.html").write_text('<main><p>&lt;script&gt;fetch(https://evil.test)&lt;/script&gt;</p>'
                                            '<a href="javascript:alert(1)">Ação</a></main>')
    out = tmp_path / "private"
    advisory.build_companion(root, out)
    html = (out / "capture-context.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "href='javascript:" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("target", ["../outside.html", "artifacts/../../outside.html", "C:/private.html", "artifacts\\raw.html"])
def test_snapshot_traversal_refused(tmp_path, target):
    root = source(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE page_snapshots SET rendered_artifact_ref=?", (target,))
    before = advisory._inventory(root)
    with pytest.raises(ValueError):
        advisory.build_companion(root, tmp_path / "private")
    assert advisory._inventory(root) == before


def test_budget_and_parser_failure_are_nd(tmp_path, monkeypatch):
    root = source(tmp_path)
    def failed(*args):
        raise ValueError("synthetic resource failure")
    monkeypatch.setattr(advisory, "_worker", failed)
    result = advisory.load_projection(root)
    assert result["captures"][0]["counts"]["observed_occurrences"] is None
    assert "PROCESSING_RESOURCE_LIMIT_ND" in result["captures"][0]["limitations"]
    assert result["search"]["reason"] == "SEARCH_RESOURCE_OR_SCHEMA_LIMIT_ND"


def test_source_mutation_refuses_publication(tmp_path, monkeypatch):
    root = source(tmp_path)
    original = advisory.load_projection
    def mutated(*args, **kwargs):
        result = original(*args, **kwargs)
        (root / "report-catalog/index.html").write_text("concurrent mutation")
        return result
    monkeypatch.setattr(advisory, "load_projection", mutated)
    with pytest.raises(ValueError, match="AUD changed"):
        advisory.build_companion(root, tmp_path / "private")
    assert not (tmp_path / "private").exists()


def test_no_template_opportunities_and_no_ai_mode_escalation():
    capture = observed('<nav><a href="/terms.pdf">Regulamento</a></nav><footer><a href="#x">Política</a></footer>')
    assert recommendations([capture]) == []
    assert ai_availability("requested")["provider_calls"] == 0
    with pytest.raises(ValueError):
        ai_availability("live")


def test_cli_outputs_counts_only(tmp_path, capsys):
    root = source(tmp_path)
    assert advisory.main(["--audit-dir", str(root), "--output", str(tmp_path / "private")]) == 0
    output = capsys.readouterr().out
    assert "source_unchanged" in output and "https://" not in output and "Conditions" not in output


def test_one_aud_product_faq_document_and_persisted_search_end_to_end(tmp_path):
    from tests.test_geo_query_ledger import _audit
    root = source(tmp_path)
    seed_parent = tmp_path / "search-seed"
    seed_parent.mkdir()
    seed = _audit(seed_parent, multi=False)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("ATTACH DATABASE ? AS fixture", (str(seed / "audit.db"),))
        for table in ("perplexity_search_runs", "perplexity_search_sources", "serp_observations", "serp_results"):
            con.execute("CREATE TABLE " + table + " AS SELECT * FROM fixture." + table)
        con.execute("UPDATE perplexity_search_runs SET audit_id=?,started_at='2026-11-10T00:00:00Z'", (root.name,))
        con.execute("UPDATE serp_observations SET audit_id=?,collected_at='2026-11-10T00:00:00Z'", (root.name,))
    (root / "artifacts/raw.html").write_text('<nav><a href="/home">Menu</a></nav><main><p>Produto Alpha.</p>'
        '<details><summary>Como ativar?</summary><p>Use o painel Alpha.</p></details>'
        '<a href="/terms.pdf">Regulamento Alpha</a></main>', encoding="utf-8")
    before = advisory._inventory(root)
    result = advisory.build_companion(root, tmp_path / "private")
    row = result["search"]["observations"][0]
    assert row["source_run_ids"] == ["PX-A"]
    assert row["status"] == "DESCRIPTIVE_ONLY" and len(row["local_references"]) == 2
    assert result["search"]["status"] == "NOT_COMPARABLE"
    assert any(o["category"] == "FAQ_ANSWER" for o in result["captures"][0]["occurrences"])
    assert advisory._inventory(root) == before
