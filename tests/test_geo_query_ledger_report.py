"""#304: canonical GEO page consumes the physically sealed per-query ledger."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

from rasai.geo_query_ledger_report import geo_query_advisory_html
from rasai.geo_report import geo_body


def _physical(tmp_path, *, per_source=True):
    root = tmp_path / "AUD-REPORT304"
    root.mkdir()
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits(audit_id TEXT, status TEXT, completion_status TEXT);
            CREATE TABLE perplexity_search_runs(
                run_id TEXT, audit_id TEXT, query_json TEXT, search_type TEXT,
                status TEXT, started_at TEXT);
            CREATE TABLE perplexity_search_sources(
                run_id TEXT, position INTEGER, url TEXT, query TEXT,
                title TEXT, snippet TEXT);
            CREATE TABLE serp_observations(
                observation_id TEXT, audit_id TEXT, query TEXT, collected_at TEXT,
                observation_status TEXT, data_mode TEXT, engine TEXT, country TEXT,
                region TEXT, language TEXT, device TEXT);
            CREATE TABLE serp_results(observation_id TEXT, position INTEGER, url TEXT);
            INSERT INTO audits VALUES ('AUD-REPORT304','COMPLETED','COMPLETE');
            INSERT INTO perplexity_search_runs VALUES (
                'PX-1','AUD-REPORT304','["seguro <vida>","seguro casa"]',
                'web','SUCCESS','2026-10-10T12:00:00Z');
        """)
        for i, query in enumerate(("seguro <vida>", "seguro casa")):
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?)",
                ("PX-1", i, "https://exemplo.org/igual", query if per_source else None,
                 "Título", "Descrição"))
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?)",
                ("PX-1", 10+i, "https://outro.org/"+str(i),
                 query if per_source else None, "Título", "Descrição"))
            sid = "SERP-"+str(i)
            con.execute(
                "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sid, "AUD-REPORT304", query, "2026-10-10T12:04:00Z",
                 "OBSERVED", "OBSERVED_API", "google", "BR", "RS", "pt-BR", "mobile"))
            con.execute(
                "INSERT INTO serp_results VALUES (?,?,?)",
                (sid, 1, "https://exemplo.org/igual"))
            con.execute(
                "INSERT INTO serp_results VALUES (?,?,?)",
                (sid, 2, "https://serp.org/"+str(i)))
    return db


def test_canonical_geo_report_exposes_sealed_per_query_denominators_no_network(tmp_path):
    db = _physical(tmp_path)
    before = sha256(db.read_bytes()).hexdigest()
    html = geo_body(db, "AUD-REPORT304")
    assert 'data-contract="GEO-PER-QUERY-304"' in html
    assert "&lt;vida&gt;" in html
    assert "<vida>" not in html
    assert "Escopo SERP e coleta" in html
    assert html.count("50.00%") >= 2
    assert "Só URLs; mesma intenção/mercado não comprovados" in html
    assert "Recorrência de URL exata dentro do mesmo run" in html
    assert "não representa" not in html.lower() or "Não representa tendência longitudinal" in html
    assert sha256(db.read_bytes()).hexdigest() == before
    assert list(db.parent.iterdir()) == [db]


def test_canonical_geo_report_abstains_multiquery_without_physical_mapping(tmp_path):
    db = _physical(tmp_path, per_source=False)
    before = db.read_bytes()
    html = geo_body(db, "AUD-REPORT304")
    block = html.split('id="geo-per-query-304"', 1)[1].split("</section>", 1)[0]
    assert "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN" in block
    assert "50.00%" not in block
    assert block.count("N/D") >= 10
    assert db.read_bytes() == before


def test_report_refuses_mismatched_aud_identity_and_noncanonical_db(tmp_path):
    db = _physical(tmp_path)
    assert "PHYSICAL_AUD_SCOPE_NOT_VERIFIED" in geo_query_advisory_html(db, "AUD-OUTRA")
    assert "PHYSICAL_AUD_SCOPE_NOT_VERIFIED" in geo_query_advisory_html(
        tmp_path / "arbitrary.db", "AUD-REPORT304")


def test_global_integrity_abstention_does_not_leak_poisoned_numbers(monkeypatch, tmp_path):
    db = _physical(tmp_path)
    def poisoned(_):
        return {
            "audit_id": "AUD-REPORT304",
            "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-008",
            "status": "DESCRIPTIVE_ONLY",
            "source_audit_db_integrity_guard": "UNVERIFIED",
            "queries": [{"query": "x", "status": "DESCRIPTIVE_ONLY",
                         "serp_overlap_rate": 0.91}],
        }
    monkeypatch.setattr(
        "rasai.geo_query_ledger_report.inspect_geo_per_query", poisoned,
    )
    html = geo_query_advisory_html(db, "AUD-REPORT304")
    assert "SOURCE_INTEGRITY_OR_CONTRACT_UNVERIFIED" in html
    assert "91.00%" not in html

def test_canonical_geo_page_displays_attributed_source_hosts_not_competitor_claims(tmp_path):
    db = _physical(tmp_path)
    before = sha256(db.read_bytes()).hexdigest()
    page = geo_body(db, "AUD-REPORT304")
    assert "Hosts observados na consulta" in page
    assert "exemplo.org" in page
    assert "outro.org" in page
    assert "não concorrentes comerciais comprovados" in page
    assert sha256(db.read_bytes()).hexdigest() == before


def test_canonical_geo_page_hides_hostname_roster_without_source_query(tmp_path):
    db = _physical(tmp_path, per_source=False)
    page = geo_body(db, "AUD-REPORT304")
    assert "Hosts observados na consulta" not in page



def test_geo_not_comparable_reason_remains_legible_after_final_humanization(tmp_path):
    from rasai.report_presentation import humanize_report_html
    db = _physical(tmp_path, per_source=False)
    before = db.read_bytes()
    html = humanize_report_html(
        geo_query_advisory_html(db, "AUD-REPORT304"), page_name="geo.html",
    )
    assert "Fonte externa não atribuível individualmente" in html
    assert "<code>PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN</code>" in html
    assert "Condição técnica não catalogada" not in html
    assert db.read_bytes() == before


def test_geo_global_abstention_is_causal_and_read_only(monkeypatch, tmp_path):
    from rasai.report_presentation import humanize_report_html
    db = _physical(tmp_path)
    before = db.read_bytes()
    def no_serp(_):
        return {
            "audit_id": "AUD-REPORT304",
            "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-008",
            "status": "NOT_COMPARABLE",
            "reason": "SERP_SCOPE_SCHEMA_UNVERIFIABLE",
            "source_audit_db_integrity_guard": "DOUBLE_SHA256_MATCH",
            "queries": [],
        }
    monkeypatch.setattr("rasai.geo_query_ledger_report.inspect_geo_per_query", no_serp)
    html = humanize_report_html(
        geo_query_advisory_html(db, "AUD-REPORT304"), page_name="geo.html",
    )
    assert "Estrutura de escopo SERP ausente ou incompatível" in html
    assert "<code>SERP_SCOPE_SCHEMA_UNVERIFIABLE</code>" in html
    assert "Condição técnica não catalogada" not in html
    assert db.read_bytes() == before



def test_completed_with_limitations_perplexity_only_has_one_clear_geo_message(tmp_path):
    """Reproduce the physical FAST/one-query/no-SERP case without provider calls."""
    from rasai.report_presentation import humanize_report_html

    db = _physical(tmp_path)
    with sqlite3.connect(db) as con:
        con.executescript("""
            UPDATE audits SET completion_status='COMPLETE_WITH_LIMITATIONS';
            UPDATE perplexity_search_runs
              SET query_json='["seguro <vida>"]', search_type='fast';
            DELETE FROM perplexity_search_sources WHERE query='seguro casa';
            DELETE FROM serp_results;
            DELETE FROM serp_observations;
            CREATE TABLE audit_execution_configurations (
                audit_id TEXT, configuration_kind TEXT, configuration_json TEXT
            );
            INSERT INTO audit_execution_configurations VALUES (
                'AUD-REPORT304', 'CONSOLE',
                '{"search_intelligence":{"enabled":false,"queries":[]}}'
            );
            CREATE TABLE geo_observation_runs (
                analysis_id TEXT, audit_id TEXT, projection_json TEXT,
                created_at TEXT
            );
            INSERT INTO geo_observation_runs VALUES (
                'GEO-1', 'AUD-REPORT304',
                '{"perplexity_run_id":"PX-1","serp_observation_id":null,'
                || '"descriptive_overlap":{"status":"NOT_COMPARABLE",'
                || '"reason":"NO_EQUIVALENT_OBSERVED_SERP_QUERY"}}',
                '2026-10-10T12:10:00Z'
            );
        """)
    before = sha256(db.read_bytes()).hexdigest()
    html = humanize_report_html(geo_body(db, "AUD-REPORT304"), page_name="geo.html")
    assert "Perplexity Search API realizada com sucesso" in html
    assert "1 execução persistida" in html
    assert "2 fontes materializadas" in html
    assert "Comparação: não aplicável" in html
    assert "SERP não solicitada nesta AUD" in html
    assert "NO_EQUIVALENT_OBSERVED_SERP_QUERY" in html
    assert 'data-contract="GEO-PER-QUERY-304"' not in html
    assert "Condição técnica não catalogada" not in html
    assert "sem consulta Perplexity" not in html
    assert "Síntese competitiva por IA" not in html
    assert "Consultas agrupadas em um request" not in html
    assert sha256(db.read_bytes()).hexdigest() == before


def test_no_serp_claim_requires_unambiguous_explicit_config(tmp_path):
    """No SERP observation alone must never be rewritten as no SERP request."""
    db = _physical(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM serp_results")
        con.execute("DELETE FROM serp_observations")
    html = geo_body(db, "AUD-REPORT304")
    assert "SERP não solicitada nesta AUD" not in html
    assert "Comparação: N/D" in html


def test_geo_unknown_physical_reason_retains_explanation_and_machine_code(tmp_path):
    """No generic 'uncatalogued condition' after report humanization."""
    from rasai.report_presentation import humanize_report_html

    db = _physical(tmp_path)
    rendered = humanize_report_html(
        geo_query_advisory_html(db, "AUD-OTHER"), page_name="geo.html"
    )
    assert "Escopo físico da auditoria não verificado" in rendered
    assert "PHYSICAL_AUD_SCOPE_NOT_VERIFIED" in rendered
    assert "Condição técnica não catalogada" not in rendered
