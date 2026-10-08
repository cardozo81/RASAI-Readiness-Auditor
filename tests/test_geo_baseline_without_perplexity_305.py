"""#305: GEO baseline without optional Perplexity; no extra API or AUD mutation."""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3

from rasai.geo_report import geo_body


def _database(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript("""
        CREATE TABLE serp_observations (
          observation_id TEXT, audit_id TEXT, query TEXT, engine TEXT,
          country TEXT, region TEXT, language TEXT, device TEXT,
          data_mode TEXT, observation_status TEXT, collected_at TEXT
        );
        CREATE TABLE serp_results (
          observation_id TEXT, position INTEGER, url TEXT, title TEXT
        );
        CREATE TABLE serp_competitive_ai_analyses (
          observation_id TEXT, audit_id TEXT, state TEXT, provider TEXT,
          model TEXT, contract_version TEXT, prompt_id TEXT,
          prompt_version TEXT, summary TEXT, opportunities_json TEXT,
          evidence_ref TEXT, evidence_sha256 TEXT
        );
        CREATE TABLE findings (
          finding_id TEXT, audit_id TEXT, rule_id TEXT, category TEXT,
          severity TEXT, title TEXT, evidence_ids TEXT,
          observed_value TEXT, expected_condition TEXT
        );
        CREATE TABLE recommendations (
          audit_id TEXT, finding_id TEXT, title TEXT, description TEXT,
          priority_class TEXT, priority_score REAL
        );
        """)
        con.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("SERP-OK", "AUD-1", "seguro de vida", "google", "BR", "Porto Alegre",
                 "pt-BR", "mobile", "OBSERVED_API", "OBSERVED", "2026-10-08T13:27:12Z"),
                ("SERP-OTHER", "AUD-2", "private query", "google", "ES", "Madrid",
                 "es-ES", "desktop", "OBSERVED_API", "OBSERVED", "2026-10-08T13:27:14Z"),
                ("SERP-PREVIEW", "AUD-1", "preview query", "google", "BR", "São Paulo",
                 "pt-BR", "mobile", "SYNTHETIC", "OBSERVED", "2026-10-08T13:27:15Z"),
            ],
        )
        con.executemany(
            "INSERT INTO serp_results VALUES (?,?,?,?)",
            [
                ("SERP-OK", 1, "https://example.com.br/planos", "Plano & <comparação>"),
                ("SERP-OTHER", 1, "https://secret.example.org/", "private title"),
                ("SERP-PREVIEW", 1, "https://preview.example.com/", "preview only"),
            ],
        )
        con.execute(
            "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("SERP-OK", "AUD-1", "AVAILABLE", "FAKE", "fake-model",
             "COMPETITIVE-001", "prompt", "v1",
             "Hipótese de lacuna editorial por intenção, evidência disponível",
             '[{"title":"Cobertura de intenção","priority":"HIGH",'
             '"recommendation":"Revisar conteúdo da página","evidence_ids":["CE-1"]},'
             '{"title":"Sem evidência","recommendation":"Ignorar","evidence_ids":[]}]',
             "artifacts/fake.json", "hash"),
        )
        con.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
            ("F-1", "AUD-1", "BR-GEO-042", "CITATION_READINESS", "MEDIUM",
             "Afirmação factual precisa de contexto", '["EV-1"]', "A", "B"),
        )
        con.execute(
            "INSERT INTO recommendations VALUES (?,?,?,?,?,?)",
            ("AUD-1", "F-1", "Revisão factual", "Revisar fatos e atribuição", "P1", 50.0),
        )


def test_geo_works_without_optional_perplexity_with_scoped_serp_and_existing_ai(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _database(db)
    before = db.read_bytes()
    output = geo_body(db, "AUD-1")
    assert "Não há execução Perplexity Search persistida" in output
    assert "Panorama SERP existente" in output
    assert "seguro de vida" in output
    assert "Porto Alegre" in output
    assert "pt-BR" in output
    assert "SERP-OK:1" in output
    assert "Plano &amp; &lt;comparação&gt;" in output
    assert "Inteligência competitiva já produzida" in output
    assert "Revisar conteúdo da página" in output
    assert "CE-1" in output
    assert "Sem evidência</strong>" not in output
    assert "F-1" in output and "EV-1" in output
    assert "Revisar fatos e atribuição" in output
    assert "private query" not in output
    assert "preview only" not in output
    assert "citação" in output.casefold()
    assert db.read_bytes() == before


def test_geo_abstains_without_eligible_serp_and_never_leaks_cross_audit(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _database(db)
    output = geo_body(db, "AUD-2")
    assert "Madrid" in output
    assert "private title" in output
    assert "SERP-OK" not in output
    assert "Cobertura de intenção" not in output
    assert "Revisar fatos e atribuição" not in output
    with sqlite3.connect(db) as con:
        con.execute("UPDATE serp_observations SET data_mode='SIMULATED' WHERE audit_id='AUD-2'")
    unavailable = geo_body(db, "AUD-2")
    assert "Não há observação SERP live elegível" in unavailable
    assert "private title" not in unavailable


def test_geo_handles_legacy_partial_serp_without_false_positive(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE serp_observations(observation_id TEXT,audit_id TEXT)")
        con.execute("CREATE TABLE serp_results(observation_id TEXT,url TEXT)")
    result = geo_body(db, "AUD-1")
    assert "Não há observação SERP live elegível" in result
    assert "Não há execução Perplexity Search persistida" in result
