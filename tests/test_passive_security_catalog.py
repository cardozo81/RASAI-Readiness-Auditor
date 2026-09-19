from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import URLError

from rasai import passive_security as security
from rasai.catalog_report_analysis import _passive_security_html
from rasai import console_catalog_plan as catalog_plan


AUDIT_ID = "AUD-PASSIVE-SECURITY"
PAGE_ID = "P1"


def _workspace(tmp_path: Path, *, html: str, second_html: str | None = None):
    root = tmp_path / AUDIT_ID
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    first_ref = "artifacts/rendered-1.html"
    (root / first_ref).write_text(html, encoding="utf-8")
    second_ref = None
    if second_html is not None:
        second_ref = "artifacts/rendered-2.html"
        (root / second_ref).write_text(second_html, encoding="utf-8")

    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE pages(
                page_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                normalized_url TEXT NOT NULL
            );
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL REFERENCES pages(page_id),
                requested_url TEXT,
                final_url TEXT,
                device TEXT,
                rendered_artifact_ref TEXT,
                raw_artifact_ref TEXT,
                browser_metadata TEXT
            );
            CREATE TABLE evidence(
                evidence_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                page_id TEXT,
                evidence_type TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                captured_at TEXT NOT NULL
            );
            """
        )
        connection.execute("INSERT INTO audits VALUES (?)", (AUDIT_ID,))
        connection.execute(
            "INSERT INTO pages VALUES (?,?,?)",
            (PAGE_ID, AUDIT_ID, "https://audited.example/"),
        )
        runtime = {
            "runtime_diagnostics": {
                "items": [
                    {
                        "type": "PAGE_ERROR",
                        "message": "Traceback (most recent call last) /var/www/app.py",
                    },
                    {
                        "type": "REQUEST_FAILED",
                        "message": "net::ERR_FAILED",
                        "url": "https://cdn.example/missing.js",
                    },
                ]
            }
        }
        connection.execute(
            """INSERT INTO page_snapshots
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                "S1",
                PAGE_ID,
                "https://audited.example/",
                "https://audited.example/",
                "MOBILE",
                first_ref,
                None,
                json.dumps(runtime),
            ),
        )
        if second_ref is not None:
            connection.execute(
                """INSERT INTO page_snapshots
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    "S2",
                    PAGE_ID,
                    "https://audited.example/",
                    "https://audited.example/",
                    "DESKTOP",
                    second_ref,
                    None,
                    json.dumps({"runtime_diagnostics": {"items": []}}),
                ),
            )
        headers = {
            "headers": [
                ["content-type", "text/html; charset=utf-8"],
                ["server", "ExampleServer/1.2.3"],
                ["set-cookie", "session=VERY-SECRET-COOKIE; SameSite=None; Path=/"],
                ["access-control-allow-origin", "*"],
                ["access-control-allow-credentials", "true"],
            ]
        }
        response = {
            "requested_url": "https://audited.example/",
            "final_url": "https://audited.example/",
            "redirect_chain": [],
        }
        connection.execute(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?)",
            ("EV-H", AUDIT_ID, PAGE_ID, "HTTP_HEADER", json.dumps(headers), "2026-09-18T12:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?)",
            ("EV-R", AUDIT_ID, PAGE_ID, "HTTP_RESPONSE", json.dumps(response), "2026-09-18T12:00:01+00:00"),
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root, artifacts=artifacts, database=database)


def _security_html(*, nonce: str = "same-nonce") -> str:
    return f"""
    <html><head>
      <meta name="generator" content="ExampleCMS 4.5.6">
      <script nonce="{nonce}" src="http://cdn.third.example/jquery-3.5.1.min.js?token=SIGNED-RESOURCE-SECRET"
              integrity="sha1-deadbeef"></script>
    </head><body>
      <form action="/login?api_key=FORM-QUERY-SECRET" method="get">
        <input type="password" name="password">
      </form>
      <iframe src="https://frame.third.example/widget"></iframe>
    </body></html>
    """


def test_passive_security_reuses_persisted_evidence_without_active_scanning(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        html=_security_html(),
        second_html=_security_html(),
    )
    monkeypatch.setenv(security.ENABLED_ENV, "true")
    monkeypatch.setenv(security.OSV_ENV, "false")
    monkeypatch.setenv(security.KEV_ENV, "false")

    result = security.analyze_passive_security(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )

    assert result["status"] == "COMPLETED"
    assert result["pages"] == 1
    assert result["resources"] > 0
    assert result["findings"] > 0

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM passive_security_findings WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchall()
        titles = {str(row["title"]) for row in rows}
        assert "Strict-Transport-Security não observado" in titles
        assert "Content-Security-Policy não observada" in titles
        assert any("Mixed" in str(row["category"]) for row in rows)
        assert "Formulário com campo sensível utiliza GET" in titles
        assert "Nonce de script reutilizado entre snapshots" in titles
        assert "Runtime aparenta expor detalhe interno" in titles
        assert "Meta generator aparenta expor tecnologia/versionamento" in titles
        assert "SRI de recurso third-party script sem hash suportado" in titles

        persisted = "\n".join(
            str(row["details_json"]) + "\n" + str(row["description"])
            for row in rows
        )
        assert "VERY-SECRET-COOKIE" not in persisted
        assert "same-nonce" not in persisted

        inventory_text = "\n".join(
            str(row["page_url"]) + "\n" + str(row["resource_url"]) + "\n" + str(row["attributes_json"])
            for row in connection.execute(
                "SELECT page_url,resource_url,attributes_json FROM passive_security_resources WHERE audit_id=?",
                (AUDIT_ID,),
            ).fetchall()
        )
        assert "SIGNED-RESOURCE-SECRET" not in inventory_text
        assert "FORM-QUERY-SECRET" not in inventory_text
        assert "%5BREDACTED%5D" in inventory_text or "[REDACTED]" in inventory_text

        run = connection.execute(
            "SELECT coverage_json FROM passive_security_runs WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()
        coverage = json.loads(run["coverage_json"])
        assert coverage["component_inventory"] is True
        assert coverage["osv_intelligence"] is False
        assert coverage["cisa_kev"] is False
        assert coverage["vulnerability_intelligence"] is False

        projected = security.improvement_findings(connection, AUDIT_ID, PAGE_ID)
        assert projected is not None
        findings, summary = projected
        assert findings
        assert summary["mode"] == "PASSIVE_ONLY"
        assert summary["active_exploitation"] is False
        assert summary["shared_security_core"] is True
    finally:
        connection.close()

    report_html = _passive_security_html(
        workspace.database,
        SimpleNamespace(audit_id=AUDIT_ID),
    )
    assert "análise estritamente passiva" in report_html
    assert "Contenção imediata" in report_html
    assert "Correção definitiva" in report_html
    assert "VERY-SECRET-COOKIE" not in report_html
    assert "same-nonce" not in report_html
    assert "SIGNED-RESOURCE-SECRET" not in report_html
    assert "FORM-QUERY-SECRET" not in report_html


def test_osv_and_kev_use_only_versioned_component_identifiers(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        html='<html><head><script src="https://cdn.third.example/jquery-3.5.1.min.js"></script></head></html>',
    )
    monkeypatch.setenv(security.ENABLED_ENV, "true")
    monkeypatch.setenv(security.OSV_ENV, "true")
    monkeypatch.setenv(security.KEV_ENV, "true")

    calls: list[tuple[str, object]] = []

    def fake_http_json(url: str, *, timeout: float, body=None):
        del timeout
        calls.append((url, body))
        if "osv.dev" in url:
            assert body == {
                "package": {"name": "jquery", "ecosystem": "npm"},
                "version": "3.5.1",
            }
            return {
                "vulns": [{
                    "id": "GHSA-example",
                    "aliases": ["CVE-2020-11022"],
                    "severity": [{"type": "CVSS_V3", "score": "7.0"}],
                    "references": [{"url": "https://osv.dev/vulnerability/GHSA-example"}],
                }]
            }
        return {
            "vulnerabilities": [{
                "cveID": "CVE-2020-11022",
                "vendorProject": "jQuery",
                "product": "jQuery",
            }]
        }

    monkeypatch.setattr(security, "_http_json", fake_http_json)

    collected = security.collect_external_intelligence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    assert collected["collection_state"] == "COMPLETED"
    assert collected["osv_successes"] == 1
    assert collected["cves"] == 1
    assert all("audited.example" not in json.dumps(body or {}) for _url, body in calls)

    analyzed = security.analyze_passive_security(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    assert analyzed["status"] == "COMPLETED"

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        advisory = connection.execute(
            "SELECT * FROM passive_security_advisories WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()
        assert advisory is not None
        assert advisory["kev_state"] == "MATCHED"

        finding = connection.execute(
            """SELECT * FROM passive_security_findings
               WHERE audit_id=? AND source LIKE 'OSV%'""",
            (AUDIT_ID,),
        ).fetchone()
        assert finding is not None
        assert finding["finding_type"] == "POTENTIAL_VULNERABILITY"
        assert finding["confidence"] == "MEDIUM"
        assert "CVE-2020-11022" in finding["cve_json"]
    finally:
        connection.close()


def test_external_security_failure_reduces_coverage_not_target_truth(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        html='<html><head><script src="https://cdn.third.example/jquery-3.5.1.min.js"></script></head></html>',
    )
    monkeypatch.setenv(security.ENABLED_ENV, "true")
    monkeypatch.setenv(security.OSV_ENV, "true")
    monkeypatch.setenv(security.KEV_ENV, "true")

    def unavailable(*_args, **_kwargs):
        raise URLError("provider unavailable")

    monkeypatch.setattr(security, "_http_json", unavailable)
    collected = security.collect_external_intelligence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    assert collected["collection_state"] == "PARTIAL"

    analyzed = security.analyze_passive_security(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    assert analyzed["status"] == "PARTIAL"
    assert "OSV_REDUCED_COVERAGE" in analyzed["limitations"]

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        integration = connection.execute(
            """SELECT * FROM passive_security_integrations
               WHERE audit_id=? AND integration_id='OSV'""",
            (AUDIT_ID,),
        ).fetchone()
        assert integration is not None
        assert integration["state"] == "UNAVAILABLE"

        run = connection.execute(
            "SELECT coverage_json FROM passive_security_runs WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()
        coverage = json.loads(run["coverage_json"])
        assert coverage["component_inventory"] is True
        assert coverage["osv_intelligence"] is False
        assert coverage["vulnerability_intelligence"] is False

        external_findings = connection.execute(
            """SELECT COUNT(*) FROM passive_security_findings
               WHERE audit_id=? AND source LIKE 'OSV%'""",
            (AUDIT_ID,),
        ).fetchone()[0]
        assert external_findings == 0
    finally:
        connection.close()


def test_catalog_plan_projects_cat10_and_optional_ai_only_inside_execution(monkeypatch) -> None:
    state = SimpleNamespace(
        target="https://audited.example/",
        web_performance=False,
        search_queries=(),
        synthetic_apdex=False,
        apdex_experience=False,
        improvement_enabled=False,
        improvement_domains=("CONTENT",),
        content_remediation=False,
        technical_remediation=False,
        ai_provider="auto",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
        error="",
    )
    catalog_plan.set_selected_catalog_ids(state, ["CAT-10"])
    catalog_plan.set_ai_execution_enabled(state, True)
    monkeypatch.setenv(security.ENABLED_ENV, "false")

    with catalog_plan.project_plan(state):
        assert security.enabled() is True
        assert state.improvement_enabled is True
        assert state.improvement_domains == ("SECURITY",)
        assert state.ai_provider == "auto"

    assert state.improvement_enabled is False
    assert state.improvement_domains == ("CONTENT",)
    assert security.enabled() is False


def test_saas_cat10_reuses_improvement_engine_without_parallel_ai_contract() -> None:
    code = r'''
from rasai.improvement_intelligence_saas import install as install_improvement
from rasai.passive_security_saas import install as install_security
from rasai.improvement_intelligence import ENABLED_ENV as IMPROVEMENT_ENABLED
from rasai.improvement_intelligence import DOMAINS_ENV as IMPROVEMENT_DOMAINS
from rasai.passive_security import ENABLED_ENV as SECURITY_ENABLED
from rasai import audit_execution_contract as contract

install_improvement()
install_security()

base = {
    "urls": ["https://audited.example/"],
    "ai_provider": "auto",
    "passive_security": True,
    "passive_security_ai": True,
}
env = contract.audit_job_environment_overrides(base)
assert env[SECURITY_ENABLED] == "true"
assert env[IMPROVEMENT_ENABLED] == "true"
assert env[IMPROVEMENT_DOMAINS] == "SECURITY"

combined = dict(base)
combined.update({
    "improvement_intelligence": True,
    "improvement_domains": "CONTENT",
})
env = contract.audit_job_environment_overrides(combined)
assert env[IMPROVEMENT_ENABLED] == "true"
assert env[IMPROVEMENT_DOMAINS].split(",") == ["CONTENT", "SECURITY"]
print("OK")
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_packaged_defaults_keep_cat10_opt_in_with_safe_subcontrols() -> None:
    from rasai.system_defaults import load_system_defaults

    parser = load_system_defaults()
    assert parser.getboolean("environment", "RASAI_PASSIVE_SECURITY") is False
    for name in (
        "RASAI_SECURITY_HEADERS",
        "RASAI_SECURITY_COOKIES",
        "RASAI_SECURITY_RESOURCES",
        "RASAI_SECURITY_THIRD_PARTY",
        "RASAI_SECURITY_RUNTIME_CORRELATION",
        "RASAI_SECURITY_OSV",
        "RASAI_SECURITY_CISA_KEV",
    ):
        assert parser.getboolean("environment", name) is True
    assert parser.getfloat("environment", "RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS") == 15.0


def test_cookie_sensitivity_hint_does_not_persist_cookie_name_or_value() -> None:
    ordinary = security._cookie_attributes("theme=dark; Path=/")
    sensitive = security._cookie_attributes("session=TOP-SECRET; HttpOnly; Path=/")

    assert ordinary["sensitive_name_hint"] is False
    assert sensitive["sensitive_name_hint"] is True
    serialized = json.dumps({"ordinary": ordinary, "sensitive": sensitive})
    assert "theme" not in serialized
    assert "session" not in serialized
    assert "dark" not in serialized
    assert "TOP-SECRET" not in serialized
