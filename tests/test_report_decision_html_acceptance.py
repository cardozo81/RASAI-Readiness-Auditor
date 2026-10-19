"""#600/#604 local report decision HTML parity without browser, score or API."""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json

import pytest

from rasai.report_decision_matrix import (
    decision_evidence_matrix, decision_evidence_matrix_html,
)
from rasai.report_decision_html_acceptance import inspect_decision_html_parity


def _projection():
    return decision_evidence_matrix(
        audit_id="AUD-HTML-600",
        scores=[
            {
                "dimension": "OVERALL_READINESS", "device": "MOBILE",
                "value": 86.484962, "coverage": .974737,
                "confidence": "HIGH", "consolidation_status": "PARTIAL",
                "limitations": json.dumps([
                    "READINESS_STATUS:ATTENTION", "CRITICAL_GATE:DISCOVERY:PASS",
                    "CRITICAL_GATE:INDEXABILITY:PASS", "CRITICAL_GATE:EXTRACTION:PASS",
                ]),
            },
            {"dimension": "DISCOVERY_ACCESS", "device": "MOBILE",
             "coverage": .7, "confidence": "LOW"},
        ],
        web={"performance_score": 1, "field_scope": "ORIGIN",
             "lcp_p75_ms": 4357, "inp_p75_ms": 415, "cls_p75": .89},
        catalog_statuses={"CAT-06": "Parcial", "CAT-07": "Concluído"},
        serp_depth=(9, 20),
    )


def _package(tmp_path, projection, *, mutate_index=None, mutate_sari=None):
    root = tmp_path / "AUD-HTML-600"
    report = root / "report-catalog"
    report.mkdir(parents=True)
    full = decision_evidence_matrix_html(projection)
    sari = decision_evidence_matrix_html(decision_evidence_matrix(
        audit_id=root.name,
        scores=[
            {"dimension": "OVERALL_READINESS", "device": "MOBILE",
             "value": 86.484962, "coverage": .974737,
             "confidence": "HIGH", "consolidation_status": "PARTIAL",
             "limitations": json.dumps([
                "READINESS_STATUS:ATTENTION", "CRITICAL_GATE:DISCOVERY:PASS",
                "CRITICAL_GATE:INDEXABILITY:PASS", "CRITICAL_GATE:EXTRACTION:PASS",
             ])},
            {"dimension": "DISCOVERY_ACCESS", "device": "MOBILE",
             "coverage": .7, "confidence": "LOW"},
        ],
        include_external=False,
    ))
    if mutate_index:
        full = mutate_index(full)
    if mutate_sari:
        sari = mutate_sari(sari)
    for name, section, content in (
        ("index.html", "decision-matrix", full),
        ("sari.html", "scope", sari),
    ):
        (report / name).write_text(
            "<html><head><script>const fake = '"
            "DECISION-EVIDENCE-604-001';</script></head>"
            "<body><main id='report-main'><section id='" + section + "'>"
            + content + "</section></main></body></html>",
            encoding="utf-8",
        )
    entries = [
        {"path": name, "sha256": sha256((report / name).read_bytes()).hexdigest(),
         "size_bytes": (report / name).stat().st_size}
        for name in ("index.html", "sari.html")
    ]
    (report / "manifest.json").write_text(json.dumps({
        "audit_id": root.name, "freshness": "FINAL",
        "packaged_files": entries,
    }), encoding="utf-8")
    return root


def test_html_matrix_matches_both_rendered_tables_only_after_package_gate(tmp_path, monkeypatch):
    from rasai import catalog_report_site
    checked = []
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (checked.append(path) or True, ()))
    projection = _projection()
    root = _package(tmp_path, projection)
    before = {name: (root / "report-catalog" / name).read_bytes()
              for name in ("index.html", "sari.html", "manifest.json")}
    result = inspect_decision_html_parity(root, projection)
    assert result["status"] == "HTML_MATRIX_PARITY_VERIFIED"
    assert result["index_matrix_rows"] == len(projection["rows"])
    assert result["sari_matrix_rows"] == 2
    assert result["browser_inspection_verified"] is False
    assert result["external_requests"] == result["audit_writes"] == 0
    assert result["normative_acceptance"] is False
    assert checked == [root / "report-catalog"]
    assert {name: (root / "report-catalog" / name).read_bytes()
            for name in before} == before
    assert "86,5" not in json.dumps(result) and "4357" not in json.dumps(result)


@pytest.mark.parametrize(("change", "expected"), [
    ("replace_crux_scope", "INDEX_HTML_MATRIX_MISMATCH"),
    ("replace_apdex_status", "INDEX_HTML_MATRIX_MISMATCH"),
    ("remove_sari_cell", "SARI_HTML_MATRIX_MISMATCH"),
    ("remove_index_contract", "INDEX_HTML_MATRIX_MISMATCH"),
    ("duplicate_index_contract", "INDEX_HTML_MATRIX_MISMATCH"),
])
def test_fails_closed_on_factual_mismatch_without_score_mutation(
    tmp_path, monkeypatch, change, expected,
):
    from rasai import catalog_report_site
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (True, ()))
    projection = _projection()
    template = decision_evidence_matrix_html(projection)
    def index_mutation(value):
        if change == "replace_crux_scope":
            return value.replace("Origem agregada (ORIGIN)", "URL específica medida", 1)
        if change == "replace_apdex_status":
            return value.replace("Parcial", "Concluído", 1)
        if change == "remove_index_contract":
            return value.replace("data-contract='DECISION-EVIDENCE-604-001'",
                                 "data-contract='missing'", 1)
        if change == "duplicate_index_contract":
            return value + template
        return value
    def sari_mutation(value):
        return value.replace("<td>SARI / MOBILE</td>", "<td>SARI / DESKTOP</td>", 1)
    root = _package(tmp_path, projection, mutate_index=index_mutation,
                    mutate_sari=sari_mutation if change == "remove_sari_cell" else None)
    result = inspect_decision_html_parity(root, projection)
    assert result["status"] == expected
    assert result["audit_writes"] == 0 and not result["normative_acceptance"]


def test_requires_genuine_package_verification_and_final_manifest(tmp_path, monkeypatch):
    from rasai import catalog_report_site
    projection = _projection()
    root = _package(tmp_path, projection)
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (False, ("alterado",)))
    assert inspect_decision_html_parity(root, projection)["status"] == (
        "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"
    )
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (True, ()))
    manifest = root / "report-catalog" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["audit_id"] = "AUD-OTHER"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert inspect_decision_html_parity(root, projection)["status"] == (
        "REPORT_PACKAGE_AUD_MISMATCH"
    )
    assert inspect_decision_html_parity(tmp_path / "missing", projection)["status"] == (
        "AUD_SCOPE_MISMATCH"
    )


def test_rejects_missing_or_symlinked_html_and_wrong_aud_projection(tmp_path, monkeypatch):
    from rasai import catalog_report_site
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (True, ()))
    projection = _projection()
    root = _package(tmp_path, projection)
    other = dict(projection, audit_id="AUD-OTHER")
    assert inspect_decision_html_parity(root, other)["status"] == "AUD_SCOPE_MISMATCH"
    index = root / "report-catalog" / "index.html"
    content = index.read_bytes()
    index.unlink()
    assert inspect_decision_html_parity(root, projection)["status"] == (
        "REPORT_HTML_SOURCE_UNVERIFIABLE"
    )
    elsewhere = tmp_path / "shadow.html"
    elsewhere.write_bytes(content)
    try:
        index.symlink_to(elsewhere)
    except (OSError, NotImplementedError):
        return
    assert inspect_decision_html_parity(root, projection)["status"] == (
        "REPORT_HTML_SOURCE_UNVERIFIABLE"
    )


def test_cli_opt_in_requires_html_gate(monkeypatch, capsys, tmp_path):
    from rasai import catalog_report_site, report_decision_matrix_cli
    monkeypatch.setattr(catalog_report_site, "verify_catalog_report_package",
                        lambda path: (True, ()))
    projection = _projection()
    root = _package(tmp_path, projection)
    monkeypatch.setattr(report_decision_matrix_cli, "inspect_audit_decision_evidence",
                        lambda _path: projection)
    assert report_decision_matrix_cli.main([str(root)]) == 0
    ordinary = json.loads(capsys.readouterr().out)
    assert "html_semantic_gate" not in ordinary
    assert report_decision_matrix_cli.main([str(root), "--verify-html"]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["html_semantic_gate"]["status"] == "HTML_MATRIX_PARITY_VERIFIED"
    html = root / "report-catalog" / "sari.html"
    html.write_text(html.read_text(encoding="utf-8").replace(
        "OVERALL_READINESS", "OUTSIDE_SCOPE", 1
    ), encoding="utf-8")
    assert report_decision_matrix_cli.main([str(root), "--verify-html"]) == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["html_semantic_gate"]["status"] == "REPORT_HTML_SOURCE_UNVERIFIABLE"
