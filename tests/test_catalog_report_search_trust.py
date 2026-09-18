from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_catalog_state import _configuration_rows
from rasai.catalog_report_search_trust import (
    _competitive_validation_rows,
    _competitive_html,
    _external_html,
    _overview_references,
    _serp_html,
    _source_states,
)


AUDIT_ID = "AUD-CAT05"


def _audit_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            f"""
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY, started_at TEXT, created_at TEXT);
            INSERT INTO audits VALUES('{AUDIT_ID}','2026-09-17T10:00:00+00:00','2026-09-17T09:59:00+00:00');
            """
        )
        connection.commit()
    finally:
        connection.close()


def _data(configuration: dict | None = None, *, work_items=()):
    return SimpleNamespace(
        audit_id=AUDIT_ID,
        configuration=configuration or {},
        work_items=work_items,
        targets=("https://example.test/",),
    )


def test_gsc_configured_but_not_requested_remains_explicitly_not_requested(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    data = _data(
        {
            "environment": {
                "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "https://example.test/",
                "RASAI_GSC_ENABLED": "false",
                "RASAI_COMMON_CRAWL_ENABLED": "false",
                "RASAI_CLARITY_ENABLED": "false",
            }
        }
    )

    states = {item.source_id: item for item in _source_states(database, data)}
    gsc = states["GOOGLE_SEARCH_CONSOLE"]
    assert gsc.configured is True
    assert gsc.requested is False
    assert gsc.enabled is False
    assert gsc.executed is False
    assert gsc.data_available is False
    assert gsc.execution_status == "NOT_REQUESTED"
    assert "não solicitado" in gsc.detail


def test_common_crawl_errors_without_rows_are_visible_in_state(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    obs = sqlite3.connect(tmp_path / "observability.db")
    try:
        obs.executescript(
            """
            CREATE TABLE datasets(
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                capture_method TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE web_archive_observations(
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                collection TEXT NOT NULL,
                target_url TEXT NOT NULL,
                captured_at TEXT,
                status TEXT,
                mime TEXT,
                digest TEXT,
                warc_filename TEXT,
                warc_offset INTEGER,
                warc_length INTEGER,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY(dataset_id,record_id)
            );
            """
        )
        obs.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "OBS-CC",
                "COMMON_CRAWL_CDX_HISTORY",
                "DIRECT_PUBLIC_INDEX_API",
                None,
                None,
                "artifacts/observability/common-crawl.json",
                "abc",
                json.dumps({"requests": 2, "rows": 0, "errors": 2}),
                "2026-09-17T10:10:00+00:00",
            ),
        )
        obs.commit()
    finally:
        obs.close()
    data = _data({"environment": {"RASAI_COMMON_CRAWL_ENABLED": "true"}})

    states = {item.source_id: item for item in _source_states(database, data)}
    common = states["COMMON_CRAWL"]
    assert common.requested is True
    assert common.executed is True
    assert common.result_count == 0
    assert common.error_count == 2
    assert common.data_available is False
    assert common.data_status == "ERROR"
    assert common.execution_status == "PARTIAL"


def test_ai_overview_is_projected_from_persisted_serp_artifact(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    artifact = tmp_path / "artifacts" / "serp" / "SERP-1" / "raw.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "provider": "serpapi",
                "pages": [
                    {
                        "ai_overview": {
                            "text": "Resumo gerado para a consulta.",
                            "sources": [
                                {"link": "https://example.test/guide"},
                                {"link": "https://other.example/source"},
                            ],
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                query TEXT NOT NULL,
                query_origin TEXT NOT NULL,
                engine TEXT NOT NULL,
                country TEXT NOT NULL,
                region TEXT,
                language TEXT NOT NULL,
                device TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_request_id TEXT,
                requested_depth INTEGER NOT NULL,
                result_count INTEGER NOT NULL,
                data_mode TEXT NOT NULL,
                observation_status TEXT NOT NULL,
                domain_of_interest TEXT,
                customer_position INTEGER,
                domain_status TEXT NOT NULL,
                raw_evidence_ref TEXT,
                raw_evidence_sha256 TEXT,
                config_metadata TEXT NOT NULL,
                quality_metadata TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                snippet TEXT,
                result_type TEXT NOT NULL,
                serp_features TEXT NOT NULL,
                metadata TEXT NOT NULL,
                PRIMARY KEY(observation_id,position,url)
            );
            CREATE TABLE serp_evidence_provenance(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                temporal_mode TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_audit_id TEXT,
                source_observation_id TEXT,
                reused_at TEXT,
                reuse_reason TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "SERP-1", AUDIT_ID, "RUN-1", "rasai", "MANUAL", "google", "BR", None,
                "pt-BR", "desktop", "2026-09-17T10:05:00+00:00", "serpapi", "REQ-1", 20,
                1, "OBSERVED_API", "OBSERVED", "example.test", 1, "FOUND",
                "artifacts/serp/SERP-1/raw.json", "abc", "{}", "{}", None, None,
            ),
        )
        connection.execute(
            "INSERT INTO serp_results VALUES (?,?,?,?,?,?,?,?,?)",
            ("SERP-1",1,"example.test","https://example.test/","Example",None,"organic","[]","{}"),
        )
        connection.execute(
            "INSERT INTO serp_evidence_provenance VALUES (?,?,?,?,?,?,?,?,?)",
            ("SERP-1",AUDIT_ID,"LIVE_RECOLLECTION","2026-09-17T10:05:00+00:00",AUDIT_ID,"SERP-1",None,None,"2026-09-17T10:05:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    html = _serp_html(database, _data())
    assert "AI Overview detectado" in html
    assert "Resumo gerado para a consulta" in html
    assert "https://example.test/guide" in html
    assert "Site auditado entre as referências" in html
    assert "Sim" in html


def test_ai_overview_reference_count_excludes_icons_and_thumbnails() -> None:
    references = _overview_references([
        {
            "references": [
                {
                    "index": 0,
                    "link": "https://example.test/source",
                    "source": "Example",
                    "source_icon": "https://assets.test/favicon.png",
                    "thumbnail": "https://assets.test/thumb.png",
                },
                {
                    "index": 1,
                    "link": "https://other.test/source",
                    "source": "Other",
                },
            ]
        }
    ])
    assert [row["link"] for row in references] == [
        "https://example.test/source",
        "https://other.test/source",
    ]


def test_common_crawl_error_modal_exposes_exception_and_recovery_steps(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    artifact = tmp_path / "artifacts" / "observability" / "common-crawl.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "errors": ["CC-MAIN-TEST:https://example.test/:RuntimeError:HTTP 503"],
            "error_details": [{
                "collection": "CC-MAIN-TEST",
                "target_url": "https://example.test/",
                "endpoint": "https://index.commoncrawl.org/CC-MAIN-TEST-index",
                "error_type": "RuntimeError",
                "message": "HTTP 503",
            }],
        }),
        encoding="utf-8",
    )
    obs = sqlite3.connect(tmp_path / "observability.db")
    try:
        obs.executescript(
            """
            CREATE TABLE datasets(
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                capture_method TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE web_archive_observations(
                record_id TEXT,dataset_id TEXT,collection TEXT,target_url TEXT,captured_at TEXT,
                status TEXT,mime TEXT,digest TEXT,warc_filename TEXT,warc_offset INTEGER,
                warc_length INTEGER,metadata_json TEXT
            );
            CREATE TABLE behavioral_observations(record_id TEXT,dataset_id TEXT);
            """
        )
        obs.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "OBS-CC", "COMMON_CRAWL_CDX_HISTORY", "DIRECT_PUBLIC_INDEX_API",
                None, None, "artifacts/observability/common-crawl.json", "abc",
                json.dumps({"requests": 1, "rows": 0, "errors": 1}),
                "2026-09-18T10:00:00+00:00",
            ),
        )
        obs.commit()
    finally:
        obs.close()

    html = _external_html(database, _data())
    assert "Ver erro e como corrigir" in html
    assert "HTTP 503" in html
    assert "index.commoncrawl.org/CC-MAIN-TEST-index" in html
    assert "reprocessamento seletivo" in html
    assert "Falha do Common Crawl não implica erro no site" in html


def test_competitive_report_projects_persisted_ai_result_without_calling_ai(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                query TEXT NOT NULL
            );
            CREATE TABLE serp_competitive_analyses(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                methodology TEXT NOT NULL,
                comparison_status TEXT NOT NULL,
                customer_url TEXT,
                candidate_count INTEGER NOT NULL,
                observed_competitor_pages INTEGER NOT NULL,
                gap_count INTEGER NOT NULL,
                gaps_json TEXT NOT NULL,
                evidence_ref TEXT,
                evidence_sha256 TEXT
            );
            CREATE TABLE serp_competitive_ai_analyses(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT,
                provider TEXT,
                model TEXT,
                contract_version TEXT NOT NULL,
                prompt_id TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                provider_request_id TEXT,
                query_intent TEXT,
                ymyl_assessment TEXT,
                summary TEXT,
                opportunity_count INTEGER NOT NULL,
                opportunities_json TEXT NOT NULL,
                evidence_ref TEXT,
                evidence_sha256 TEXT
            );
            """
        )
        connection.execute("INSERT INTO serp_observations VALUES(?,?)", ("SERP-COMP-1", "seguro de vida"))
        connection.execute(
            "INSERT INTO serp_competitive_analyses VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("SERP-COMP-1", AUDIT_ID, "DETERMINISTIC_CORRELATIONAL_001", "CONSOLIDATED",
             "https://example.test/", 3, 3, 1, "[]",
             "artifacts/search-intelligence/competitive/SERP-COMP-1.json", "det-sha"),
        )
        opportunities = json.dumps([
            {
                "priority": "HIGH",
                "category": "TOPIC_COVERAGE",
                "title": "Cobrir condição observada",
                "recommendation": "Detalhar a condição com base nas evidências observadas.",
                "evidence_ids": ["CE-GAP-001"],
                "confidence": 0.84,
            }
        ])
        connection.execute(
            "INSERT INTO serp_competitive_ai_analyses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("SERP-COMP-1", AUDIT_ID, "AVAILABLE", None, "OPENAI", "gpt-test",
             "COMPETITIVE-AI-001", "rasai-competitive-search", "1", "REQ-1",
             "informational", "LOW", "Resumo competitivo baseado nas evidências.", 1,
             opportunities, "artifacts/search-intelligence/competitive-ai/SERP-COMP-1.json", "ai-sha"),
        )
        connection.commit()
    finally:
        connection.close()

    html = _competitive_html(database, _data())

    assert "Análise competitiva por IA" in html
    assert "Resumo competitivo baseado nas evidências" in html
    assert "Cobrir condição observada" in html
    assert "CE-GAP-001" in html
    assert "OPENAI" in html



def test_competitive_report_exposes_effective_contract_http_evidence_and_ai_governance(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    artifact = tmp_path / "artifacts" / "search-intelligence" / "competitive" / "OBS.json"
    artifact.parent.mkdir(parents=True)
    artifact_payload=json.dumps({
        "acquisition_policy":{
            "content_enabled":True,
            "max_competitor_pages":1,
            "timeout_seconds":12.5,
            "max_bytes":1500000,
            "max_redirects":2,
            "customer_source":"AUDIT_RENDERED_ARTIFACT",
        }
    },sort_keys=True)
    artifact.write_text(artifact_payload, encoding="utf-8")
    digest = __import__("hashlib").sha256(artifact_payload.encode("utf-8")).hexdigest()
    ai_artifact = tmp_path / "artifacts" / "search-intelligence" / "competitive-ai" / "OBS.json"
    ai_artifact.parent.mkdir(parents=True)
    ai_artifact.write_text("{}", encoding="utf-8")
    ai_digest = __import__("hashlib").sha256(b"{}").hexdigest()

    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,query TEXT,result_count INTEGER,
                customer_position INTEGER,domain_status TEXT
            );
            CREATE TABLE serp_competitive_analyses(
                observation_id TEXT PRIMARY KEY,audit_id TEXT,methodology TEXT,comparison_status TEXT,
                customer_url TEXT,candidate_count INTEGER,observed_competitor_pages INTEGER,
                gap_count INTEGER,gaps_json TEXT,evidence_ref TEXT,evidence_sha256 TEXT
            );
            CREATE TABLE serp_competitive_results(
                observation_id TEXT,position INTEGER,domain TEXT,url TEXT,classification TEXT,
                eligible_for_content_comparison INTEGER,selected_for_content_comparison INTEGER,reason TEXT
            );
            CREATE TABLE serp_competitive_pages(
                observation_id TEXT,role TEXT,domain TEXT,requested_url TEXT,final_url TEXT,
                fetch_status TEXT,http_status INTEGER,content_type TEXT,content_sha256 TEXT,bytes_read INTEGER,
                title TEXT,meta_description TEXT,headings_json TEXT,word_count INTEGER,query_terms_json TEXT,
                query_terms_title_json TEXT,query_terms_description_json TEXT,query_terms_headings_json TEXT,
                query_terms_body_json TEXT,jsonld_types_json TEXT,error_code TEXT,error_message TEXT,redirects_json TEXT
            );
            CREATE TABLE serp_competitive_ai_analyses(
                observation_id TEXT PRIMARY KEY,audit_id TEXT,state TEXT,reason TEXT,provider TEXT,model TEXT,
                contract_version TEXT,prompt_id TEXT,prompt_version TEXT,provider_request_id TEXT,
                query_intent TEXT,ymyl_assessment TEXT,summary TEXT,opportunity_count INTEGER,
                opportunities_json TEXT,evidence_ref TEXT,evidence_sha256 TEXT
            );
            CREATE TABLE ai_evidence_versions(
                evidence_snapshot_id TEXT PRIMARY KEY,sealed_at TEXT
            );
            CREATE TABLE ai_tasks(
                ai_task_id TEXT PRIMARY KEY,audit_id TEXT,purpose TEXT,scope_type TEXT,scope_key TEXT,
                evidence_snapshot_id TEXT,semantic_contract_version TEXT,prompt_id TEXT,prompt_version TEXT,
                requirements_json TEXT,status TEXT,created_at TEXT
            );
            CREATE TABLE ai_request_rounds(
                ai_round_id TEXT PRIMARY KEY,ai_task_id TEXT,round_index INTEGER,status TEXT,
                started_at TEXT,finished_at TEXT,input_hash TEXT,output_hash TEXT,missing_json TEXT
            );
            CREATE TABLE ai_provider_attempts(
                attempt_id TEXT PRIMARY KEY,audit_id TEXT,provider TEXT,model TEXT,reasoning_profile TEXT,
                status TEXT,decision TEXT,input_tokens INTEGER,output_tokens INTEGER,total_tokens INTEGER,
                estimated_cost REAL,cost_currency TEXT,error_code TEXT,ai_task_id TEXT,ai_round_id TEXT
            );
            """
        )
        connection.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?)",("OBS","seguro de vida",9,4,"FOUND"))
        gaps=json.dumps([{
            "code":"QUERY_BODY_COVERAGE_LOWER",
            "severity":"MEDIUM",
            "message":"Menor cobertura observada da query no body.",
            "customer_value":0.25,
            "leader_reference":0.75,
            "evidence_urls":["https://competitor.test/vida"],
        }])
        connection.execute(
            "INSERT INTO serp_competitive_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("OBS",AUDIT_ID,"DETERMINISTIC_CORRELATIONAL_001","CONSOLIDATED","https://example.test/",1,1,1,gaps,
             "artifacts/search-intelligence/competitive/OBS.json",digest),
        )
        connection.executemany(
            "INSERT INTO serp_competitive_results VALUES (?,?,?,?,?,?,?,?)",
            [
                ("OBS",1,"competitor.test","https://competitor.test/vida","ORGANIC_CANDIDATE",1,1,"external organic result; business equivalence is not inferred"),
                ("OBS",2,"gov.br","https://gov.br/info","PUBLIC_AUTHORITY",0,0,"public-authority domain heuristic"),
            ],
        )
        connection.executemany(
            "INSERT INTO serp_competitive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("OBS","CUSTOMER","example.test","https://example.test/","https://example.test/","OBSERVED",200,"text/html","c"*64,12000,
                 "Seguro","Vida","[]",900,"[]","[]","[]","[]","[]","[]",None,None,"[]"),
                ("OBS","COMPETITOR_CANDIDATE","competitor.test","https://competitor.test/vida","https://competitor.test/vida","OBSERVED",200,"text/html","d"*64,15000,
                 "Seguro de vida","Vida","[]",1500,"[]","[]","[]","[]","[]","[]",None,None,json.dumps(["https://competitor.test/r"])),
            ],
        )
        opportunities=json.dumps([{
            "priority":"HIGH","category":"TOPIC_COVERAGE","title":"Aprofundar cobertura",
            "recommendation":"Cobrir a condição observada.","rationale":"A diferença foi observada nas páginas comparadas.",
            "evidence_ids":["CE-GAP-001"],"confidence":0.88,
            "causality_note":"Diferença correlacional; não implica causa de ranking.",
        }])
        connection.execute(
            "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("OBS",AUDIT_ID,"AVAILABLE",None,"OPENAI","gpt-5.6-luna","COMPETITIVE-AI-001",
             "rasai-competitive-search","1","REQ","informational","financial-security","Resumo",1,opportunities,
             "artifacts/search-intelligence/competitive-ai/OBS.json",ai_digest),
        )
        connection.execute("INSERT INTO ai_evidence_versions VALUES (?,?)",("EVIDENCE-1","2026-09-18T12:00:00+00:00"))
        connection.execute(
            "INSERT INTO ai_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("TASK-1",AUDIT_ID,"COMPETITIVE_INTELLIGENCE","SERP_OBSERVATION","OBS","EVIDENCE-1",
             "COMPETITIVE-AI-001","rasai-competitive-search","1",json.dumps(["competitive_semantic_opportunities"]),
             "COMPLETE","2026-09-18T12:00:01+00:00"),
        )
        connection.execute(
            "INSERT INTO ai_request_rounds VALUES (?,?,?,?,?,?,?,?,?)",
            ("AIR-1","TASK-1",1,"COMPLETE","2026-09-18T12:00:02+00:00","2026-09-18T12:00:03+00:00","in","out","[]"),
        )
        connection.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AIA-1",AUDIT_ID,"OPENAI","gpt-5.6-luna","HIGH","SUCCESS","SUCCESS",100,40,140,0.001,"USD",None,"TASK-1","AIR-1"),
        )
        connection.commit()
    finally:
        connection.close()

    work_items=({
        "component":"SEARCH_INTELLIGENCE",
        "configuration":json.dumps({
            "queries":["seguro de vida"],"region":"BR","depth":20,"device":"mobile",
            "competitive":True,"compare_content":True,"max_content_pages":1,
            "content_timeout_seconds":12.5,"content_max_bytes":1500000,"content_max_redirects":2,
            "ai_competitive":True,"ymyl_mode":"AUTO","mode":"live","provider":"serpapi","engine":"google",
            "max_queries":5,"max_requests":10,"max_depth":100,"max_competitors":5,"retries":1,
            "timeout_seconds":30.0,"min_interval_seconds":1.0,"market":"BR","language":"pt-BR",
            "ai_provider":"auto","ai_model":"",
        }),
    },)

    html=_competitive_html(database,_data(work_items=work_items))
    assert "Contrato competitivo efetivo desta AUD" in html
    assert "Validação ponta a ponta - configuração, evidência e IA" in html
    assert "Análise de concorrentes" in html
    assert "Comparação de conteúdo" in html
    assert "Evidence seal" in html
    assert "IA pós-selo" in html
    assert "artifact.acquisition_policy.timeout_seconds" in html
    assert "Fonte do conteúdo do site auditado" in html
    assert "Captura renderizada da própria AUD" in html
    assert "artifact.acquisition_policy.customer_source" in html
    assert "runtime max_competitor_pages=1" in html
    assert "Máx. páginas concorrentes" in html
    assert "1500000" in html
    assert "Resultados SERP recebidos" in html
    assert "Candidato orgânico" in html
    assert "Autoridade pública" in html
    assert "URL solicitada" in html
    assert "QUERY_BODY_COVERAGE_LOWER" in html
    assert "Diferença correlacional; não implica causa de ranking." in html
    assert "Governança da IA competitiva" in html
    assert "EVIDENCE-1" in html
    assert "IA iniciou após o selo" in html
    assert "Tentativas de provider" in html
    assert "USD 0.00100000" in html
    assert "Íntegro - SHA-256 confere" in html


def test_competitive_validation_matrix_flags_contract_divergence_without_guessing_execution() -> None:
    configuration = {
        "competitive": True,
        "compare_content": True,
        "max_content_pages": 1,
        "content_timeout_seconds": 8.0,
        "content_max_bytes": 1000,
        "content_max_redirects": 1,
        "ai_competitive": True,
        "ymyl_mode": "AUTO",
    }
    item = {
        "comparison_status": "CONTENT_COMPARISON_DISABLED",
        "evidence_ref": "artifacts/search-intelligence/competitive/OBS.json",
    }
    candidates = [
        {"selected_for_content_comparison": 1},
        {"selected_for_content_comparison": 1},
    ]
    pages = [
        {"bytes_read": 1500, "redirects_json": json.dumps(["a", "b"])},
    ]

    rows = _competitive_validation_rows(
        configuration,
        item,
        candidates,
        pages,
        None,
        None,
        (),
        None,
        {},
    )
    by_control = {row[0]: row for row in rows}

    assert by_control["Comparação de conteúdo"][-1] == "INCONSISTENTE"
    assert by_control["Máx. páginas concorrentes"][-1] == "INCONSISTENTE"
    assert by_control["Timeout conteúdo"][-1] == "COM LIMITAÇÃO"
    assert by_control["Máx. bytes por página"][-1] == "INCONSISTENTE"
    assert by_control["Máx. redirects"][-1] == "INCONSISTENTE"
    assert by_control["IA competitiva"][-1] == "NÃO ELEGÍVEL"
    assert by_control["Evidence seal"][-1] == "NÃO ELEGÍVEL"
    assert by_control["IA pós-selo"][-1] == "NÃO ELEGÍVEL"


def test_competitive_validation_matrix_accepts_governed_post_seal_ai() -> None:
    configuration = {
        "competitive": True,
        "compare_content": True,
        "max_content_pages": 2,
        "content_timeout_seconds": 8.0,
        "content_max_bytes": 2000,
        "content_max_redirects": 2,
        "ai_competitive": True,
        "ymyl_mode": "AUTO",
    }
    item = {
        "comparison_status": "CONSOLIDATED",
        "evidence_ref": "artifacts/search-intelligence/competitive/OBS.json",
    }
    candidates = [{"selected_for_content_comparison": 1}]
    pages = [{"bytes_read": 1500, "redirects_json": json.dumps(["a"])}]
    ai = {
        "state": "AVAILABLE",
        "ymyl_assessment": "financial-security",
        "evidence_ref": "artifacts/search-intelligence/competitive-ai/OBS.json",
    }
    task = {"ai_task_id": "TASK-1", "evidence_snapshot_id": "EVIDENCE-1"}
    rounds = [{"started_at": "2026-09-18T12:00:02+00:00"}]
    snapshot = {"sealed_at": "2026-09-18T12:00:00+00:00"}

    rows = _competitive_validation_rows(
        configuration,
        item,
        candidates,
        pages,
        ai,
        task,
        rounds,
        snapshot,
        {
            "content_enabled": True,
            "max_competitor_pages": 2,
            "timeout_seconds": 8.0,
            "max_bytes": 2000,
            "max_redirects": 2,
        },
    )
    by_control = {row[0]: row for row in rows}

    assert by_control["Análise de concorrentes"][-1] == "OK"
    assert by_control["Comparação de conteúdo"][-1] == "OK"
    assert by_control["Máx. páginas concorrentes"][-1] == "OK"
    assert by_control["Máx. bytes por página"][-1] == "OK"
    assert by_control["Timeout conteúdo"][-1] == "OK"
    assert by_control["Máx. redirects"][-1] == "OK"
    assert by_control["IA competitiva"][-1] == "OK"
    assert by_control["YMYL"][-1] == "OK"
    assert by_control["Evidence seal"][-1] == "OK"
    assert by_control["IA pós-selo"][-1] == "OK"

def test_cat05_ai_policy_reflects_enabled_competitive_ai() -> None:
    data = SimpleNamespace(
        audit_id=AUDIT_ID,
        configuration={
            "search_intelligence": {
                "enabled": True,
                "queries": ["seguro auto", "cotacao seguro"],
                "depth": 20,
                "device": "mobile",
                "region": "Porto Alegre, RS",
                "ai_competitive": True,
            },
            "settings": {},
        },
        config_hash="same",
        computed_hash="same",
        selected={"CAT-05"},
        targets=("https://example.test/",),
        catalog_items={
            "CAT-05": {
                "ai_mode": "NONE",
                "ai_execution_enabled": False,
            }
        },
        work_items=(),
    )
    rows = {str(row[0]): row for row in _configuration_rows(data, "CAT-05")}
    assert rows["Uso de IA nesta capacidade"][1] == "Habilitado para inteligência competitiva"
    assert rows["Política de IA"][1] == "IA competitiva opcional e evidence-bound"

def test_serp_projection_exposes_persisted_engine(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT,
                query TEXT,
                engine TEXT,
                provider TEXT,
                country TEXT,
                language TEXT,
                device TEXT,
                requested_depth INTEGER,
                collected_at TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO serp_observations
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "SERP-ENGINE",
                AUDIT_ID,
                "seguro auto",
                "google",
                "serpapi",
                "BR",
                "pt-BR",
                "mobile",
                20,
                "2026-09-18T10:05:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    html = _serp_html(database, _data())
    assert ">Engine<" in html
    assert ">google<" in html
    assert "serpapi" in html

def test_competitive_validation_exposes_customer_content_source() -> None:
    rows = _competitive_validation_rows(
        {"competitive": True, "compare_content": True},
        {"comparison_status": "CONSOLIDATED", "evidence_ref": "artifact.json"},
        (),
        (),
        None,
        None,
        (),
        None,
        {
            "content_enabled": True,
            "customer_source": "AUDIT_RENDERED_ARTIFACT",
        },
    )
    by_control = {row[0]: row for row in rows}
    source = by_control["Fonte do conteúdo do site auditado"]
    assert source[2] == "Sim"
    assert source[3] == "Captura renderizada da própria AUD"
    assert source[5] == "artifact.acquisition_policy.customer_source"
    assert source[-1] == "OK"
