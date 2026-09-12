from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest

from rasai.improvement_intelligence import (
    DEFAULT_DOMAINS,
    ImprovementConfig,
    ImprovementPersistence,
    _TargetContext,
    _html_diff,
    _security_findings,
    _structure_findings,
    parse_domains,
    validate_analysis_language,
    write_improvement_report,
)
from rasai.persistence import AuditWorkspace


def _context(html: str = "<html><body><h1>Teste</h1></body></html>") -> _TargetContext:
    return _TargetContext(
        page_id="P1",
        url="https://example.test/",
        input_url="https://example.test/",
        snapshot_id="S1",
        device="MOBILE",
        snapshot_rows=(),
        audit_language="pt-BR",
        market="BR",
        title="Teste",
        description="Descrição",
        canonical="https://example.test/",
        html=html,
        structured_data=None,
    )


def test_language_and_domain_contract() -> None:
    assert validate_analysis_language("auto") == "auto"
    assert validate_analysis_language("PT-br") == "pt-BR"
    assert parse_domains("security,content,security") == ("SECURITY", "CONTENT")
    with pytest.raises(ValueError):
        validate_analysis_language("português")
    with pytest.raises(ValueError):
        parse_domains("UNKNOWN")


def test_deep_config_requires_explicit_configured_provider() -> None:
    env = {"OPENAI_API_KEY": "sk-test"}
    config = ImprovementConfig(
        enabled=True,
        provider="openai",
        model="gpt-5.6-luna",
        reasoning="HIGH",
        domains=("CONTENT", "SECURITY"),
    ).validate(env)
    assert config.provider == "openai"
    assert config.model == "gpt-5.6-luna"
    assert config.reasoning == "HIGH"

    with pytest.raises(ValueError, match="explícito"):
        ImprovementConfig(enabled=True, provider="auto").validate(env)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        ImprovementConfig(
            enabled=True,
            provider="openai",
            model="gpt-5.6-luna",
            reasoning="HIGH",
        ).validate({})


def test_structure_analysis_is_deterministic_and_element_bound() -> None:
    html = (
        "<html><body><h1>Produto</h1><h3>Detalhes</h3>"
        "<img src='x.png'><button class='icon'></button><a>sem destino</a></body></html>"
    )
    findings, summary = _structure_findings(_context(html))
    ids = {item["finding_id"] for item in findings}
    assert any(item.startswith("HTML:HEADING_JUMP") for item in ids)
    assert any(item.startswith("HTML:IMG_ALT") for item in ids)
    assert any(item.startswith("HTML:BUTTON_NAME") for item in ids)
    assert any(item.startswith("HTML:ANCHOR_HREF") for item in ids)
    assert "HTML:LANG_MISSING" in ids
    assert "HTML:MAIN_LANDMARK_MISSING" in ids
    assert summary["h1_count"] == 1
    assert summary["visible_word_count"] >= 3
    assert any(item.get("original_html") for item in findings)


def test_security_posture_is_passive_and_does_not_claim_exploitation() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE evidence (evidence_id TEXT,audit_id TEXT,page_id TEXT,evidence_type TEXT,observed_value TEXT,captured_at TEXT)"
    )
    connection.execute(
        "INSERT INTO evidence VALUES (?,?,?,?,?,?)",
        (
            "EV1",
            "AUD-1",
            "P1",
            "HTTP_HEADER",
            json.dumps({"headers": [["content-type", "text/html"], ["server", "Example/1.2.3"]]}),
            "2026-09-12T00:00:00+00:00",
        ),
    )
    findings, summary = _security_findings(connection, "AUD-1", _context())
    ids = {item["finding_id"] for item in findings}
    assert "SECURITY:CSP" in ids
    assert "SECURITY:HSTS" in ids
    assert "SECURITY:SERVER_VERSION" in ids
    assert summary["mode"] == "PASSIVE_ONLY"
    assert summary["active_exploitation"] is False
    assert "não equivale" in summary["note"].casefold()


def test_html_diff_highlights_original_and_suggestion() -> None:
    original, suggested = _html_diff(
        '<img src="hero.webp">',
        '<img src="hero.webp" width="1200" height="630" alt="Produto">',
    )
    assert "diff-add" in suggested
    assert "width" in suggested
    assert "img" in original


def _workspace(root: Path) -> AuditWorkspace:
    audit_root = root / "AUD-IMP"
    audit_root.mkdir()
    (audit_root / "artifacts").mkdir()
    workspace = AuditWorkspace(audit_root)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE audits (audit_id TEXT PRIMARY KEY);
            INSERT INTO audits VALUES ('AUD-IMP');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL REFERENCES audits(audit_id));
            INSERT INTO pages VALUES ('P1','AUD-IMP');
            CREATE TABLE page_snapshots (snapshot_id TEXT PRIMARY KEY,page_id TEXT NOT NULL REFERENCES pages(page_id));
            INSERT INTO page_snapshots VALUES ('S1','P1');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def test_report_renders_original_and_suggested_html_with_priority() -> None:
    with TemporaryDirectory() as tmp:
        workspace = _workspace(Path(tmp))
        context = _context('<html lang="pt-BR"><main><h1>Teste</h1></main></html>')
        finding = {
            "finding_id": "HTML:TEST",
            "domain": "TECHNICAL_HTML",
            "severity": "HIGH",
            "source": "HTML_STRUCTURE",
            "title": "Elemento incompleto",
            "observation": "Dimensões não observadas",
            "selector": "img.hero",
            "original_html": '<img class="hero" src="hero.webp">',
            "evidence_ids": ["HTML:STRUCTURE"],
            "impacts": {"performance": 3, "seo": 1, "best_practices": 2, "accessibility": 1, "ai_access": 1, "security": 0},
            "details": {},
        }
        recommendation = {
            "recommendation_id": "IIR-1",
            "finding_id": "HTML:TEST",
            "domain": "TECHNICAL_HTML",
            "severity": "HIGH",
            "title": "Declare dimensões",
            "recommendation": "Adicionar dimensões explícitas.",
            "rationale": "Reduz oportunidade de layout shift.",
            "evidence_ids": ["HTML:STRUCTURE"],
            "confidence": 0.95,
            "effort": "LOW",
            "selector": "img.hero",
            "original_html": finding["original_html"],
            "suggested_html": '<img class="hero" src="hero.webp" width="1200" height="630">',
            "suggested_text": None,
            "verification": "Reexecutar Lighthouse e comparar CLS.",
            "impacts": finding["impacts"],
            "source": "AI",
        }
        config = ImprovementConfig(enabled=False, domains=DEFAULT_DOMAINS)
        with ImprovementPersistence(workspace) as store:
            store.persist(
                audit_id="AUD-IMP",
                context=context,
                config=config,
                status="COMPLETE",
                findings=[finding],
                recommendations=[recommendation],
                ai_summary="Resumo evidence-bound.",
                evidence_fingerprint="abc",
                reason=None,
            )
        path = write_improvement_report(audit_id="AUD-IMP", workspace=workspace)
        html = path.read_text(encoding="utf-8")
        assert "HTML original observado" in html
        assert "HTML sugerido pela IA" in html
        assert "diff-add" in html
        assert "prioridade" in html.casefold()
        assert "advisory/non-scoring" in html


def test_console_ini_contract_is_persistable_without_secrets_in_isolated_process() -> None:
    code = r'''
from rasai import interactive_console
from rasai.improvement_intelligence_console import install
from rasai import console_settings
install(interactive_console)
state = interactive_console.State()
state.improvement_enabled = True
state.improvement_provider = "openai"
state.improvement_model = "gpt-5.6-luna"
state.improvement_reasoning = "HIGH"
values = console_settings._state_values(state)["improvement_intelligence"]
assert values["enabled"] == "true"
assert values["provider"] == "openai"
assert "API_KEY" not in str(values)
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_console_item_13_prevents_env_driven_hidden_duplicate_execution() -> None:
    code = r'''
import os
from rasai import interactive_console
from rasai.improvement_intelligence import ENABLED_ENV
from rasai.improvement_intelligence_console import install
seen = []
def base_run(state):
    seen.append(os.environ.get(ENABLED_ENV))
    return 0
interactive_console.run_audit_from_console = base_run
install(interactive_console)
os.environ[ENABLED_ENV] = "true"
state = interactive_console.State()
state.improvement_enabled = False
assert interactive_console.run_audit_from_console(state) == 0
assert seen == ["false"]
assert os.environ[ENABLED_ENV] == "true"
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_saas_contract_requires_exactly_one_url() -> None:
    # Isolated process avoids leaking additive monkey patches into unrelated tests.
    code = r'''
from rasai.improvement_intelligence_saas import install
from rasai import audit_execution_contract as contract
install()
base = {
  "urls": ["https://example.test/"],
  "improvement_intelligence": True,
  "improvement_ai_provider": "openai",
  "improvement_ai_model": "gpt-5.6-luna",
  "improvement_ai_reasoning": "HIGH",
}
normalized = contract.normalize_audit_job_payload(base)
assert normalized["improvement_intelligence"] is True
assert normalized["improvement_ai_provider"] == "openai"
try:
    contract.normalize_audit_job_payload({**base, "urls": ["https://a.test/", "https://b.test/"]})
except ValueError as exc:
    assert "exactly one explicit URL" in str(exc)
else:
    raise AssertionError("multiple URLs were accepted")
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
