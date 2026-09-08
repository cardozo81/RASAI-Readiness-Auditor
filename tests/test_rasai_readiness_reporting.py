from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from rasai.persistence import AuditWorkspace
from rasai.rasai_readiness_reporting import enrich_rasai_reporting


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, "AUD-SARI")
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY,
                project_name TEXT
            );
            INSERT INTO audits VALUES ('AUD-SARI','Projeto SARI');

            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                device TEXT NOT NULL,
                value REAL,
                coverage REAL NOT NULL,
                confidence TEXT NOT NULL,
                consolidation_status TEXT NOT NULL,
                scoring_version TEXT NOT NULL,
                calculated_at TEXT,
                limitations TEXT
            );

            INSERT INTO scores VALUES
              ('S-M-OVER','AUD-SARI','OVERALL_READINESS','MOBILE',82.5,0.94,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-M-ANS','AUD-SARI','ANSWERABILITY','MOBILE',75.0,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-M-CIT','AUD-SARI','CITATION_READINESS','MOBILE',70.0,0.9,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-M-EVI','AUD-SARI','EVIDENCE_TRUST','MOBILE',60.0,0.9,'MEDIUM','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-M-TECH','AUD-SARI','TECHNICAL_ACCESSIBILITY','MOBILE',95.0,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-D-OVER','AUD-SARI','OVERALL_READINESS','DESKTOP',88.0,0.91,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-D-ANS','AUD-SARI','ANSWERABILITY','DESKTOP',80.0,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-D-CIT','AUD-SARI','CITATION_READINESS','DESKTOP',78.0,0.9,'HIGH','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]'),
              ('S-D-EVI','AUD-SARI','EVIDENCE_TRUST','DESKTOP',72.0,0.9,'MEDIUM','CONSOLIDATED','SCORE-GEO-004','2026-09-07T00:00:00Z','[]');

            CREATE TABLE score_contributions (
                contribution_id TEXT PRIMARY KEY,
                score_id TEXT,
                rule_id TEXT,
                rule_execution_id TEXT,
                dimension TEXT,
                device TEXT,
                weight REAL,
                result TEXT,
                result_factor REAL,
                effective_contribution REAL,
                scoring_group TEXT
            );
            INSERT INTO score_contributions VALUES
              ('C1','S-M-TECH','BR-GEO-005','R1','TECHNICAL_ACCESSIBILITY','MOBILE',1,'PASS',1,1,NULL),
              ('C2','S-M-ANS','BR-GEO-039','R2','ANSWERABILITY','MOBILE',1,'WARNING',0.5,0.5,NULL);

            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                audit_id TEXT,
                normalized_url TEXT
            );
            INSERT INTO pages VALUES
              ('P1','AUD-SARI','https://example.test/a'),
              ('P2','AUD-SARI','https://example.test/b');

            CREATE TABLE web_performance_runs (
                audit_id TEXT PRIMARY KEY,
                enabled INTEGER,
                status TEXT
            );
            INSERT INTO web_performance_runs VALUES ('AUD-SARI',1,'SUCCESS');

            CREATE TABLE web_performance_observations (
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT,
                page_id TEXT,
                device TEXT,
                cwv_assessment TEXT,
                performance_score REAL,
                accessibility_score REAL
            );
            INSERT INTO web_performance_observations VALUES
              ('W1','AUD-SARI','P1','MOBILE','PASS',81.0,94.0),
              ('W2','AUD-SARI','P2','MOBILE','FAIL',88.0,97.0),
              ('W3','AUD-SARI','P1','DESKTOP','PASS',95.0,100.0);

            CREATE TABLE synthetic_apdex_runs (
                audit_id TEXT PRIMARY KEY,
                enabled INTEGER
            );
            INSERT INTO synthetic_apdex_runs VALUES ('AUD-SARI',1);

            CREATE TABLE synthetic_apdex_summaries (
                summary_id TEXT PRIMARY KEY,
                audit_id TEXT,
                url TEXT,
                device TEXT,
                apdex_score REAL,
                final_group INTEGER
            );
            INSERT INTO synthetic_apdex_summaries VALUES
              ('A1','AUD-SARI','https://example.test/a','MOBILE',0.82,1),
              ('A2','AUD-SARI','https://example.test/a','DESKTOP',0.91,1);
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = workspace.root / "report"
    (report / "css").mkdir(parents=True)
    (report / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
    nav = "<aside class='app-nav'><nav><a href='index.html'>old</a></nav></aside>"
    footer = "<footer class='footer'>f</footer>"
    index = (
        "<!doctype html><html><body>" + nav
        + "<main class='app-main'><header class='hero'><div class='eyebrow'>RASAi - Search & AI Readiness Auditor</div>"
        + "<h1>Visão geral da auditoria</h1><p class='lead'>Dashboard executivo de readiness. O índice é um modelo interno e reprodutível do RASAi; não é uma nota oficial do Google, OpenAI ou de outro mantenedor.</p>"
        + "<div class=\"score-grid\"><article class='score-card'><div>82</div></article></div>"
        + "<div class=\"metric-grid\"><div class='metric'><small>Projeto</small><strong>Projeto SARI</strong></div></div></header>"
        + "<section class='panel'><div class='kicker'>Leitura obrigatória</div><h2>Cobertura e confiabilidade</h2><p>duplicate</p></section>"
        + "<section class='panel'><div class='kicker'>Dimensões</div><h2>Readiness por dispositivo</h2><p>duplicate dimensions</p></section>"
        + "<section class='panel'><div class='kicker'>Escopo do produto</div><h2>O que este índice significa</h2><p>duplicate scope</p></section>"
        + "<section id='web-performance-summary' class='panel'><h2>Web Performance duplicate</h2></section>"
        + "<section id='accessibility-summary' class='panel'><h2>A11y duplicate</h2></section>"
        + "<!-- rasai-apdex-index-start --><section><h2>Apdex duplicate</h2></section><!-- rasai-apdex-index-end -->"
        + "<!-- rasai-external-metrics-integrity:start --><section><table><tr><td>detail duplicate</td></tr></table></section><!-- rasai-external-metrics-integrity:end -->"
        + footer + "</main></body></html>"
    )
    device = (
        "<!doctype html><html><body>" + nav
        + "<main class='app-main'><header class='hero'><div class=\"eyebrow\">Relatório por dispositivo</div><h1>Mobile</h1>"
        + "<p class='lead'>evidence</p><div class=\"score-grid\"><article class='score-card'>82</article></div></header>"
        + "<section class='panel'><div class='kicker'>Scorecard</div><h2>Dimensões Mobile</h2><table><tr><td>Score</td></tr></table></section>"
        + "<section class='panel'><div class='kicker'>Páginas</div><h2>Auditoria por URL</h2><p>finding evidence</p></section>"
        + footer + "</main></body></html>"
    )
    (report / "index.html").write_text(index, encoding="utf-8")
    (report / "mobile.html").write_text(device, encoding="utf-8")
    (report / "desktop.html").write_text(device.replace("Mobile", "Desktop"), encoding="utf-8")
    (report / "web-performance.html").write_text("<html><body>" + nav + "<main><header class='hero'><h1>Web</h1></header>" + footer + "</main></body></html>", encoding="utf-8")
    (report / "accessibility.html").write_text("<html><body>" + nav + "<main><header class='hero'><h1>A11y</h1></header>" + footer + "</main></body></html>", encoding="utf-8")
    (report / "apdex.html").write_text("<html><body>" + nav + "<main><header class='hero'><h1>Apdex</h1></header>" + footer + "</main></body></html>", encoding="utf-8")
    (report / "references.html").write_text("<html><body>" + nav + "<main><header class='hero'><h1>Referências</h1></header>" + footer + "</main></body></html>", encoding="utf-8")
    return workspace


def test_rasai_page_is_canonical_home_for_current_indicators() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        path = enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        assert path.name == "readiness.html"
        html = path.read_text(encoding="utf-8")
        assert "Search & AI Readiness Index" in html
        assert "SARI-001" in html
        assert "SCORE-GEO-004" in html
        assert "Dimensões do readiness" in html
        assert "Capacidade de resposta" in html
        assert "Preparação para citação" in html
        assert "Evidências e confiabilidade" in html
        assert "Média de igual peso" in html
        assert "calibração externa" in html


def test_index_is_compact_dashboard_without_cross_domain_detail_duplication() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        html = (workspace.root / "report" / "index.html").read_text(encoding="utf-8")
        assert html.count("rasai-executive-dashboard:start") == 1
        assert "Resultados finais por indicador" in html
        assert "Search &amp; AI Readiness - Mobile" in html
        assert "82.5/100" in html
        assert "Core Web Vitals" in html
        assert "2/3 aprovados" in html
        assert "Lighthouse Performance" in html
        assert "<small>Mobile</small><strong>81-88/100</strong>" in html
        assert "<small>Desktop</small><strong>95/100</strong>" in html
        assert "Lighthouse Accessibility" in html
        assert "Synthetic Navigation Apdex" in html
        assert "<small>Mobile</small><strong>0.820</strong>" in html
        assert "<small>Desktop</small><strong>0.910</strong>" in html
        assert "web-performance-summary" not in html
        assert "accessibility-summary" not in html
        assert "rasai-apdex-index-start" not in html
        assert "rasai-external-metrics-integrity:start" not in html
        assert "duplicate dimensions" not in html
        assert "detail duplicate" not in html


def test_device_pages_keep_findings_but_not_rasai_scorecards() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        for filename in ("mobile.html", "desktop.html"):
            html = (workspace.root / "report" / filename).read_text(encoding="utf-8")
            assert "finding evidence" in html
            assert "data-rasai-device-role='evidence-only'" in html
            assert "Search & AI Readiness" in html
            assert "score-grid" in html
            assert "<div class='kicker'>Scorecard</div>" in html
            assert "espelho read-only" in html


def test_dashboard_does_not_mix_external_metrics_into_sari() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        html = (workspace.root / "report" / "index.html").read_text(encoding="utf-8")
        assert "faixa, não média inventada" in html
        assert "Lighthouse médio" not in html
        assert "SARI-001" in html
        assert "Nenhum Lighthouse, Core Web Vitals, Accessibility ou Apdex é convertido" in html


def test_enrichment_is_structurally_idempotent_and_navigation_has_single_sari_item() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        enrich_rasai_reporting(audit_id="AUD-SARI", workspace=workspace)
        report = workspace.root / "report"
        index = (report / "index.html").read_text(encoding="utf-8")
        mobile = (report / "mobile.html").read_text(encoding="utf-8")
        readiness = (report / "readiness.html").read_text(encoding="utf-8")
        assert index.count("rasai-executive-dashboard:start") == 1
        assert mobile.count("data-rasai-device-role='evidence-only'") == 1
        assert readiness.count("href='readiness.html'") == 1
        assert "Relatório Mobile" in readiness
        assert "Relatório Desktop" in readiness
