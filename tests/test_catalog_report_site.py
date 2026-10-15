from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import shutil
from types import SimpleNamespace

from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import (
    CATALOG_REPORT_CONTRACT_VERSION,
    CATALOG_REPORT_FILENAMES,
    CATALOG_REPORT_PAGES,
)
from rasai.catalog_report_site import materialize_catalog_report_site


AUDIT_ID = "AUD-CATALOG-REPORT"


def _workspace(tmp_path: Path):
    root = tmp_path / AUDIT_ID
    root.mkdir()
    non_catalog = root / "report"
    non_catalog.mkdir()
    (non_catalog / "index.html").write_text("NON-CATALOG-REPORT-BOUNDARY", encoding="utf-8")
    database = root / "audit.db"
    configuration = {
        "targets": ["https://example.test/"],
        "search_intelligence": {
            "enabled": True,
            "queries": ["seguro auto", "seguro residencial"],
            "depth": 20,
            "region": "Porto Alegre, RS, Brazil",
            "device": "mobile",
            "competitive": True,
        },
        "settings": {
            "environment": {
                # Defensive fixture: even malformed historical input containing secret
                # material must never be dumped by the new report projection.
                "RASAI_OPENAI_API_KEY": "DO-NOT-LEAK-THIS-SECRET",
                "RASAI_SERP_MAX_DEPTH": "20",
            }
        },
        "audit_catalog": {
            "version": "1",
            "selected": ["CAT-01", "CAT-04", "CAT-05", "CAT-06"],
            "ai_enabled": False,
            "items": [
                {
                    "id": "CAT-01",
                    "selected": True,
                    "status": "APTO",
                    "detail": "baseline técnico",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["domain-discovery"],
                },
                {
                    "id": "CAT-04",
                    "selected": True,
                    "status": "APTO",
                    "detail": "web performance apto",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["web-performance"],
                },
                {
                    "id": "CAT-05",
                    "selected": True,
                    "status": "APTO",
                    "detail": "SERP solicitada",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["search-intelligence", "google-search-console"],
                },
                {
                    "id": "CAT-06",
                    "selected": True,
                    "status": "APTO",
                    "detail": "Apdex solicitado",
                    "ai_mode": "NONE",
                    "capability_ids": ["apdex-navigation"],
                },
            ],
        },
    }
    digest = configuration_hash(configuration)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY, project_name TEXT, status TEXT,
                completion_status TEXT, created_at TEXT, started_at TEXT, completed_at TEXT
            );
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY, configuration_json TEXT, configuration_hash TEXT
            );
            CREATE TABLE scores(
                audit_id TEXT, device TEXT, dimension TEXT, value REAL, coverage REAL,
                confidence TEXT, consolidation_status TEXT, scoring_version TEXT, limitations TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT, performance_score REAL, accessibility_score REAL,
                lcp_ms REAL, inp_ms REAL, cls REAL, ttfb_ms REAL
            );
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY, audit_id TEXT, query TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT, position INTEGER, url TEXT
            );
            CREATE TABLE synthetic_apdex_summaries(
                audit_id TEXT, apdex REAL, threshold_seconds REAL,
                satisfied_count INTEGER, tolerating_count INTEGER,
                frustrated_count INTEGER, sample_count INTEGER
            );
            CREATE TABLE audit_fulfillment_work_items(
                audit_id TEXT, component TEXT, scope_key TEXT, status TEXT,
                attempt_count INTEGER, effective_result_ref TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, "Projeto catálogo", "SUCCESS", "COMPLETE", "2026-09-15T20:00:00Z", "2026-09-15T20:01:00Z", "2026-09-15T20:03:00Z"),
        )
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?,?)",
            (AUDIT_ID, json.dumps(configuration, ensure_ascii=False), digest),
        )
        connection.executemany(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (AUDIT_ID, "MOBILE", "OVERALL_READINESS", 74.2, 0.92, "HIGH", "CONSOLIDATED", "SARI-TEST-1", "[]"),
                (AUDIT_ID, "MOBILE", "DISCOVERY_ACCESS", 82.0, 1.0, "HIGH", "CONSOLIDATED", "SARI-TEST-1", "[]"),
                (AUDIT_ID, "MOBILE", "STRUCTURED_DATA", 68.0, 0.8, "MEDIUM", "CONSOLIDATED", "SARI-TEST-1", "[]"),
            ],
        )
        connection.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, 0.68, 0.92, 3100, 184, 0.08, 820),
        )
        connection.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?)",
            [("SERP-1", AUDIT_ID, "seguro auto"), ("SERP-2", AUDIT_ID, "seguro residencial")],
        )
        connection.executemany(
            "INSERT INTO serp_results VALUES (?,?,?)",
            [("SERP-1", 8, "https://example.test/a"), ("SERP-1", 12, "https://example.test/b"), ("SERP-2", 5, "https://example.test/c")],
        )
        connection.execute(
            "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, 0.78, 3.0, 36, 6, 8, 50),
        )
        connection.executemany(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?,?,?,?)",
            [
                (AUDIT_ID, "WEB_PERFORMANCE", "mobile", "SUCCESS", 1, "web-performance"),
                (AUDIT_ID, "SEARCH_INTELLIGENCE", "mobile", "SUCCESS", 1, "search-intelligence"),
                (AUDIT_ID, "SYNTHETIC_APDEX", "mobile", "SUCCESS", 1, "synthetic-apdex"),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root, database=database), non_catalog


def test_catalog_report_is_isolated_from_non_catalog_tree(tmp_path: Path) -> None:
    workspace, non_catalog = _workspace(tmp_path)
    index = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace)

    assert index == workspace.root / "report-catalog" / "index.html"
    assert (non_catalog / "index.html").read_text(encoding="utf-8") == "NON-CATALOG-REPORT-BOUNDARY"
    assert set(path.name for path in index.parent.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)
    assert (index.parent / "manifest.json").is_file()
    assert (index.parent / "css" / "site.css").is_file()


def test_catalog_report_materializes_without_non_catalog_report_tree(tmp_path: Path) -> None:
    workspace, non_catalog = _workspace(tmp_path)
    shutil.rmtree(non_catalog)

    index = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace)

    assert index == workspace.root / "report-catalog" / "index.html"
    assert index.is_file()
    assert not (workspace.root / "report").exists()
    assert not (workspace.root / "report.html").exists()
    assert not (workspace.root / "remediation.html").exists()
    assert set(path.name for path in index.parent.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)


def test_every_new_page_uses_the_same_menu_and_one_active_item(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    expected_links = tuple(page.filename for page in CATALOG_REPORT_PAGES)
    for page in CATALOG_REPORT_PAGES:
        html = (report / page.filename).read_text(encoding="utf-8")
        assert f"data-shared-report-menu='{CATALOG_REPORT_CONTRACT_VERSION}'" in html
        assert html.count("aria-current='page'") == 1
        positions = [html.index(f"href='{filename}'") for filename in expected_links]
        assert positions == sorted(positions)





def test_unified_report_633_core_color_pairs_meet_wcag_aa_text_contrast() -> None:
    """Offline verification of typography/identity colors, not a full AX audit."""
    import re

    from rasai.catalog_report_style import _CSS

    root = re.search(r":root\{([^}]+)\}", _CSS)
    assert root is not None
    tokens = dict(re.findall(r"--([\w-]+):(#(?:[0-9A-Fa-f]{6}))", root.group(1)))
    for required in ("ink", "muted", "nav-bg", "bg", "blue", "cyan"):
        assert required in tokens

    def luminance(color: str) -> float:
        rgb = (int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
        channels = tuple(
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in rgb
        )
        return sum(weight * part for weight, part in zip((0.2126, 0.7152, 0.0722), channels))

    def contrast(foreground: str, background: str) -> float:
        a, b = luminance(foreground), luminance(background)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)

    for foreground, background in (
        (tokens["ink"], tokens["bg"]),
        (tokens["muted"], "#ffffff"),
        (tokens["blue"], "#ffffff"),
        (tokens["cyan"], "#ffffff"),
        ("#ffffff", tokens["nav-bg"]),
        ("#8798ae", tokens["nav-bg"]),
        ("#875411", "#fff3d7"),
    ):
        assert contrast(foreground, background) >= 4.5, (
            f"WCAG AA text contrast below 4.5:1 for {foreground}/{background}"
        )



def test_report_633_baseline_guard_does_not_lose_nontabular_evidence() -> None:
    """A design-only diff cannot silently delete prose, targets or source links."""
    from runpy import run_path

    smoke = run_path(str(Path(__file__).with_name("report_smoke_633.py")))
    _Tables = smoke["_Tables"]
    _check_table_parity = smoke["_check_table_parity"]

    def record(html: str):
        parsed = _Tables()
        parsed.feed(html)
        from collections import Counter

        return {
            "table_row_inventory": dict(Counter(parsed.rows)),
            "section_ids": parsed.sections,
            "element_ids": parsed.ids,
            "local_links": dict(Counter(parsed.local_links)),
            "visible_text": dict(Counter(parsed.content_fragments)),
            "dialog_count": parsed.dialogs,
        }

    old = (
        "<html><body><main>"
        "<section id='findings'><h2>Ocorrências físicas</h2>"
        "<p id='evidence-4'>Fonte identificada</p>"
        "<a href='cat-09.html#action-1'>Intervenção persistida</a>"
        "<table><tr><td>EV-123</td><td>Observado</td></tr></table>"
        "</section><dialog id='finding-detail'>Detalhe técnico preservado</dialog>"
        "</main></body></html>"
    )
    additive = old.replace(
        "<section id='findings'>",
        "<nav class='breadcrumbs'>Nova experiência</nav><section id='findings'>",
    )
    _check_table_parity({"cat-03.html": record(old)}, {"cat-03.html": record(additive)})
    for removed, changed in (
        ("Fonte identificada", "Resumo sem fonte"),
        ("cat-09.html#action-1", "cat-09.html"),
        ("id='evidence-4'", "id='evidence-other'"),
        ("Detalhe técnico preservado", "Detalhe indisponível"),
    ):
        candidate = old.replace(removed, changed)
        try:
            _check_table_parity(
                {"cat-03.html": record(old)},
                {"cat-03.html": record(candidate)},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("physical report baseline regression accepted: " + removed)



def test_new_shared_report_shell_navigation_is_accessible_in_all_canonical_pages(tmp_path: Path) -> None:
    """#633: one DOM nav, one disclosure, no second route or hidden static content."""
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    assert len(CATALOG_REPORT_PAGES) == 19
    expected_links = set(page.filename for page in CATALOG_REPORT_PAGES)
    assert expected_links == set(file.name for file in report.glob("*.html"))
    for page in CATALOG_REPORT_PAGES:
        html = (report / page.filename).read_text(encoding="utf-8")
        assert html.count("data-shared-report-menu=") == 1
        assert html.count("id='report-primary-navigation'") == 1
        assert html.count(" data-report-menu-toggle aria-controls") == 1
        assert "aria-controls='report-primary-navigation'" in html
        assert "aria-expanded='false'" in html
        assert "href='#report-main'" in html
        assert "id='report-main'" in html
        assert "class='report-breadcrumbs'" in html
        assert "aria-label='Caminho de navegação'" in html
        assert html.count("aria-current='page'") == 1
        assert "src='https://" not in html
        assert "href='css/site.css'" in html

    css = (report / "css" / "site.css").read_text(encoding="utf-8")
    assert "--nav-bg:#102f3d" in css
    assert "--ink:#142d3d" in css
    assert "--cyan:#087a77" in css
    assert ".report-menu-enhanced .app-nav{display:none}" in css
    assert ".report-menu-enhanced.report-menu-open .app-nav{display:flex" in css
    assert ".report-skip-link:focus{top:10px}" in css
    assert "@media print" in css



def test_objective_cards_are_only_navigational_and_never_add_up_repeat_actions(tmp_path: Path) -> None:
    """Repeated action IDs in different objectives remain one physical action."""
    from rasai.directed_analysis_reporting import directed_analysis_body

    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute(
            "CREATE TABLE directed_analysis_runs("
            "audit_id TEXT, status TEXT, strategic_summary_json TEXT,"
            "roadmap_json TEXT, limitations_json TEXT)"
        )
        con.execute(
            "CREATE TABLE directed_analysis_actions("
            "audit_id TEXT, action_id TEXT, title TEXT,"
            "affected_dimensions_json TEXT, priority TEXT, effort TEXT,"
            "confidence TEXT)"
        )
        con.execute(
            "INSERT INTO directed_analysis_runs VALUES(?,?,?,?,?)",
            (AUDIT_ID, "COMPLETE", "{}", "[]", "[]"),
        )
        con.executemany(
            "INSERT INTO directed_analysis_actions VALUES(?,?,?,?,?,?,?)",
            [
                (
                    AUDIT_ID, "ACT-1", "Corrigir informação",
                    json.dumps([
                        {"dimension": "DISCOVERY_ACCESS", "expected_gain": "HIGH"},
                        {"dimension": "INDEXABILITY", "expected_gain": "MEDIUM"},
                    ]),
                    "HIGH", "MEDIUM", "MEDIUM",
                ),
                (
                    AUDIT_ID, "ACT-2", "Validar evidência",
                    json.dumps([
                        {"dimension": "INDEXABILITY", "expected_gain": "LOW"},
                    ]),
                    "MEDIUM", "LOW", "MEDIUM",
                ),
            ],
        )
    data = SimpleNamespace(
        audit_id=AUDIT_ID,
        targets=("https://example.test/seguro",),
        audit={"project_name": "Projeto de teste", "status": "COMPLETE"},
        selected=(),
        fulfillment={},
    )
    html = directed_analysis_body(database, data)
    # Seven stable PoC perspectives are present even when the fixture has no
    # actions for six of them: zero linked actions is not zero findings.
    assert html.count("class='directed-goal-link'") == 7
    assert html.count("class='directed-goal-details' id='goal-") == 7
    assert html.count("href='#goal-") == 7
    assert "id='goal-descoberta'" in html
    assert "id='targets'" in html
    assert "Alvo / localização declarada" in html
    assert "Nenhuma ação da Análise Direcionada foi vinculada" in html
    assert "Uma mesma ação pode apoiar vários objetivos" in html
    assert "não são aditivas" in html
    # DISCOVERY_ACCESS and INDEXABILITY must not count ACT-1 twice.
    assert "goal-descoberta" in html
    assert "0 aceita(s) · 2 associada(s)</small>" in html
    assert html.count("class='directed-operational-item'") == 2
    assert "O que foi observado" in html
    assert "Onde intervir" in html
    assert "O que fazer" in html
    assert "Como validar" in html
    assert "Proveniência" in html
    assert "ACT-1" not in html  # evidence IDs are not promoted to visible metrics
    assert "Corrigir informação" in html and "Validar evidência" in html
    assert "data-action-priority='HIGH'" in html
    assert "data-action-priority='MEDIUM'" in html
    assert "O filtro de prioridade dos links do" in html
    assert html.count("data-action-priority=") == 2
    # Old direct links hashed from dimension values remain anchorable.
    from hashlib import sha256
    legacy = "goal-" + sha256(b"INDEXABILITY").hexdigest()[:12]
    assert f"id='{legacy}'" in html


def test_633_governance_is_matched_only_by_persisted_source(tmp_path: Path) -> None:
    from rasai.directed_analysis_reporting import _governance_for_action
    governance = {
        ("CONTENT_AI", "SRC-1"): {
            "source_kind": "CONTENT_AI", "source_id": "SRC-1",
            "decision": "ACCEPTED", "target_class": "TARGET_SITE",
        },
        ("DEEP_ANALYSIS", "SRC-2"): {
            "source_kind": "DEEP_ANALYSIS", "source_id": "SRC-2",
            "decision": "VERIFY_DECIDE", "target_class": "EXTERNAL_PROVIDER",
        },
    }
    accepted = {"source_kind": "CONTENT_AI", "source_id": "SRC-1"}
    verify = {"source_kind": "DEEP_ANALYSIS", "source_id": "SRC-2"}
    unmatched = {"source_kind": "SECURITY_REMEDIATION", "source_id": "SRC-1"}
    assert _governance_for_action(accepted, governance) == ("Aceita", "Site auditado")
    assert _governance_for_action(verify, governance) == (
        "Verificar / decidir", "Fornecedor externo"
    )
    assert _governance_for_action(unmatched, governance)[0] == "Sem decisão casada"


def test_report_633_objective_dialog_is_progressive_and_printable() -> None:
    from rasai.catalog_report_style import _CSS, _JS
    assert "report-objectives-enhanced" in _CSS
    assert "details.directed-goal-details{display:block!important}" in _CSS
    assert ".directed-operational-facts" in _CSS
    assert "objectiveDialog.showModal()" in _JS
    assert "marker.replaceWith(body)" in _JS  # exact node reused, not cloned
    assert "window.addEventListener('beforeprint'" in _JS
    assert "const goal=resolveObjective(target)" in _JS
    assert "window.addEventListener('popstate',openHash)" in _JS



def test_633_persisted_target_locations_do_not_infer_ownership(tmp_path: Path) -> None:
    from rasai.directed_analysis_reporting import _action_target_contexts, _action_target_label
    db = tmp_path / "targets.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE content_remediation_suggestions ("
            "audit_id TEXT, suggestion_id TEXT, target_location TEXT);"
            "CREATE TABLE improvement_intelligence_recommendations ("
            "audit_id TEXT, recommendation_id TEXT, selector TEXT);"
        )
        con.execute(
            "INSERT INTO content_remediation_suggestions VALUES (?,?,?)",
            (AUDIT_ID, "SUG-1", "Seção de coberturas antes de contratar"),
        )
        con.execute(
            "INSERT INTO improvement_intelligence_recommendations VALUES (?,?,?)",
            (AUDIT_ID, "REC-2", "a.logo > img"),
        )
        con.row_factory = sqlite3.Row
        actions = [
            {"action_id": "ACT-1", "source_kind": "CONTENT_AI", "source_id": "SUG-1"},
            {"action_id": "ACT-2", "source_kind": "DEEP_ANALYSIS", "source_id": "REC-2"},
            {"action_id": "ACT-3", "source_kind": "CONTENT_AI", "source_id": "SUG-MISSING"},
        ]
        contexts = _action_target_contexts(con, AUDIT_ID, actions)
        assert "Seção de coberturas" in _action_target_label(actions[0], contexts)
        assert "Seletor CSS registrado" in _action_target_label(actions[1], contexts)
        assert _action_target_label(actions[2], contexts) == "-"
        assert len(contexts) == 2


def test_633_overview_executive_facts_are_independent_and_source_bound(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    overview = (report / "index.html").read_text(encoding="utf-8")
    assert "id='snapshot'" in overview
    assert "O retrato da auditoria" in overview
    assert "Os números não compõem um novo índice" in overview
    assert "directed-analysis.html#actions" in overview
    assert "Lighthouse" in overview or "SARI" in overview
    assert set(page.name for page in report.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)


def test_633_snapshot_drilldowns_match_persisted_observations_and_priority_counts(tmp_path: Path) -> None:
    """Each overview card leads to the existing source, including exact action subsets."""
    workspace, _ = _workspace(tmp_path)
    with sqlite3.connect(workspace.database) as con:
        con.execute("ALTER TABLE web_performance_observations ADD COLUMN lcp_p75_ms REAL")
        con.execute("ALTER TABLE web_performance_observations ADD COLUMN field_scope TEXT")
        con.execute(
            "UPDATE web_performance_observations "
            "SET performance_score=1.0,lcp_p75_ms=4357.0,field_scope='ORIGIN'"
        )
        con.execute(
            "CREATE TABLE directed_analysis_actions("
            "audit_id TEXT,action_id TEXT,priority TEXT)"
        )
        con.executemany(
            "INSERT INTO directed_analysis_actions VALUES(?,?,?)",
            [
                (AUDIT_ID, "ACT-A", "HIGH"),
                (AUDIT_ID, "ACT-B", "HIGH"),
                (AUDIT_ID, "ACT-C", "LOW"),
                (AUDIT_ID, "ACT-D", None),
                (AUDIT_ID, "ACT-E", ""),
            ],
        )
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    overview = (report / "index.html").read_text(encoding="utf-8")
    cat04 = (report / "cat-04.html").read_text(encoding="utf-8")
    for destination in (
        "sari.html#composition",
        "cat-04.html#metric-lighthouse-performance",
        "cat-04.html#metric-field-lcp-p75",
        "directed-analysis.html#actions",
        "directed-analysis.html?priority=HIGH#actions",
        "directed-analysis.html?priority=UNDEFINED#actions",
    ):
        assert f"href='{destination}'" in overview
    assert "1/100" in overview  # M21 stored 1.0 ON 0..100, not 100/100
    assert "100/100" not in overview
    assert "Ver 5 ações" in overview
    assert "Ver 2 ações de prioridade alta" in overview
    assert "Ver 2 ações sem prioridade" in overview
    assert "Domínio / origem" in overview  # public-label translation of ORIGIN
    assert "id='metric-lighthouse-performance'" in cat04
    assert "id='metric-field-lcp-p75'" in cat04
    assert overview.count("class='metric report-snapshot-metric'") == 6


def test_633_lighthouse_persisted_score_contract_never_normalizes_twice(tmp_path: Path) -> None:
    """M21 stores the Lighthouse API (0..1) * 100 in the database.

    Both the snapshot and CAT-04 must show 1.0 persisted as 1/100;
    scaling this record again would falsely assert optimal performance.
    """
    from rasai.catalog_report_governance import _lighthouse_score_display_633
    from rasai.catalog_report_metrics import _web_metric_rows

    assert _lighthouse_score_display_633(1.0) == "1/100"
    assert _lighthouse_score_display_633(0.75) == "0.75/100"
    assert _lighthouse_score_display_633(100.0) == "100/100"
    assert _lighthouse_score_display_633(74.2) == "74.2/100"

    workspace, _ = _workspace(tmp_path)
    with sqlite3.connect(workspace.database) as con:
        con.execute("UPDATE web_performance_observations SET performance_score=1.0")
    metrics = _web_metric_rows(workspace.database, AUDIT_ID)
    lighthouse = next(row for row in metrics if row[0] == "Lighthouse · Desempenho")
    assert lighthouse[1] == "1 / 100"

    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    overview = (report / "index.html").read_text(encoding="utf-8")
    cat04 = (report / "cat-04.html").read_text(encoding="utf-8")
    cat07 = (report / "cat-07.html").read_text(encoding="utf-8")
    assert "1/100" in overview and "100/100" not in overview
    assert "class='result-value bad'>1/100</strong>" in overview
    assert "1 / 100" in cat04
    assert "1 / 100" in cat07  # contextual CAT-07 cross-read carries the unit


def test_633_design_system_neutral_panels_and_contextual_accents() -> None:
    """One subdued visual grammar across all 19 reports, including GEO/CAT-07."""
    import inspect
    from rasai.catalog_report_style import _CSS
    from rasai.geo_report import geo_body

    assert "--surface-subtle:#f8fafb" in _CSS
    assert "--line-strong:#c6d5db" in _CSS
    assert ".notice{border:1px solid var(--line);background:var(--surface-subtle)" in _CSS
    assert ".notice.warn{border-color:#e6cfaa" in _CSS
    assert ".notice.bad{border-color:#e9c6c3" in _CSS
    assert ".notice.good{border-color:#beddd1" in _CSS
    assert ".ref{display:inline-flex;" in _CSS
    assert "background:transparent;color:var(--blue)" in _CSS
    assert "[data-contract='CAT07-ARCHITECTURE-358']" in _CSS
    assert "background:var(--surface-subtle);" in _CSS
    geo_markup_source = inspect.getsource(geo_body)
    assert "--geo-border:var(--line" in geo_markup_source
    assert "--geo-surface:var(--card" in geo_markup_source
    assert "section:nth-of-type(even)" not in geo_markup_source
    assert "border-left:4px" not in geo_markup_source
    assert "box-shadow:none" in geo_markup_source


def test_633_priority_filter_is_reversible_and_print_preserves_every_row() -> None:
    from rasai.catalog_report_style import _CSS, _JS

    assert "new URLSearchParams(window.location.search).get('priority')" in _JS
    assert "priorityFilter==='HIGH'?raw==='HIGH':raw===''" in _JS
    assert "original.filter((row)" in _JS
    assert "Ver todas as ações" in _JS
    assert "table[data-interactive-table='true'] tbody tr{display:table-row!important}" in _CSS

    # AA body and card text against a white report surface, including links.
    def luminance(value: str) -> float:
        rgb = [int(value[pos:pos+2], 16) / 255 for pos in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return sum(component * weight for component, weight in zip(
            linear, (0.2126, 0.7152, 0.0722),
        ))

    for foreground in ("#3159a8", "#445c69", "#546c78", "#142d3d"):
        foreground_lum = luminance(foreground)
        background_lum = luminance("#ffffff")
        assert (background_lum + 0.05) / (foreground_lum + 0.05) >= 4.5


def test_overview_new_experience_is_an_index_not_a_second_report(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    overview = (report / "index.html").read_text(encoding="utf-8")
    assert overview.count("id='experience'") == 1
    assert overview.count("class='report-reading-step'") == 6
    assert "Percurso de interpretação" in overview
    for destination in (
        "directed-analysis.html#objectives",
        "directed-analysis.html#roadmap",
        "directed-analysis.html#actions",
        "cat-09.html",
        "geo.html",
        "methodology.html",
    ):
        assert f"href='{destination}'" in overview
    assert "não cria resultados adicionais" in overview
    assert set(page.name for page in report.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)
    assert overview.count("Índices e métricas evidentes") >= 1
    assert "74.2" in (report / "sari.html").read_text(encoding="utf-8")
    directed = (report / "directed-analysis.html").read_text(encoding="utf-8")
    for section in ("summary", "transversal", "roadmap", "objectives", "actions",
                    "targets", "traceability", "limitations"):
        assert f"id='{section}'" in directed
    assert "Nenhuma análise direcionada foi materializada" in directed


def test_633_all_pages_share_method_reading_patterns(tmp_path: Path) -> None:
    from rasai.catalog_report_style import _CSS
    workspace, _ = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    assert len(tuple(report.glob("*.html"))) == 19
    for page in CATALOG_REPORT_PAGES:
        body = (report / page.filename).read_text(encoding="utf-8")
        assert "href='css/site.css'" in body
        assert body.count("data-shared-report-menu=") == 1
        assert "id='report-main'" in body
    method = (report / "methodology.html").read_text(encoding="utf-8")
    assert "Separação das interpretações" in method
    assert "report-evidence-chain" in method
    assert "CrUX" in method
    assert "Governança" in method
    assert "Sem extrapolar amostras sintéticas" in method
    assert _CSS.count(":root{") == 1
    assert "report-experience-grid" not in _CSS
    assert _CSS.count(".directed-goal-grid{display:grid;") == 1
    assert "--radius:8px" in _CSS



def test_sari_and_metrics_use_persisted_values_without_recalculation(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    sari = (report / "sari.html").read_text(encoding="utf-8")
    metrics = (report / "metrics.html").read_text(encoding="utf-8")
    overview = (report / "index.html").read_text(encoding="utf-8")

    assert "74.2" in sari
    assert "SARI-TEST-1" in sari
    assert "O HTML não recalcula o índice" in sari
    assert "Acesso e descoberta" in sari
    assert "Lighthouse · Desempenho" in metrics
    assert "LCP" in metrics
    assert "Apdex" in metrics
    assert "Índices e métricas evidentes" in overview


def test_catalog_contexts_show_execution_scope_and_unselected_state(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    search = (report / "cat-05.html").read_text(encoding="utf-8")
    remediation = (report / "cat-09.html").read_text(encoding="utf-8")

    assert "seguro auto" in search
    assert "Porto Alegre, RS, Brazil" in search
    assert "Top 20" in search
    assert "Faixa de posições observada" in search
    assert "NÃO SOLICITADO" in remediation


def test_catalog_report_never_dumps_secret_configuration_values(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    combined = "\n".join(path.read_text(encoding="utf-8") for path in report.glob("*.html"))
    assert "DO-NOT-LEAK-THIS-SECRET" not in combined
    assert "RASAI_OPENAI_API_KEY" not in combined

def test_structural_assurance_is_only_in_overview_not_repeated_in_catalog_pages(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    overview = (report / "index.html").read_text(encoding="utf-8")
    assert overview.count("Matriz de encerramento estrutural") == 1
    assert "Como ler os eixos" in overview

    for catalog_id in range(1, 11):
        html = (report / f"cat-{catalog_id:02d}.html").read_text(encoding="utf-8")
        assert "Confiabilidade e governança estrutural" not in html


def test_geo_context_is_built_from_same_aud_findings_and_only_its_catalog(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    with sqlite3.connect(workspace.database) as connection:
        connection.execute(
            "CREATE TABLE findings(audit_id TEXT, finding_id TEXT, category TEXT, "
            "rule_id TEXT, title TEXT, evidence_ids TEXT)"
        )
        connection.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?)",
            (AUDIT_ID, "GEO-CAT1", "INDEXABILITY", "R-INDEX",
             "Inspecionar indexação", '["EV-INDEX"]'),
        )
        connection.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?)",
            ("AUD-PRIVATE", "GEO-OTHER", "INDEXABILITY", "R-PRIVATE",
             "NÃO REVELAR OUTRA AUD", '["EV-PRIVATE"]'),
        )
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    cat1 = (report / "cat-01.html").read_text(encoding="utf-8")
    cat3 = (report / "cat-03.html").read_text(encoding="utf-8")
    assert "GEO-CAT1" in cat1 and "EV-INDEX" in cat1
    assert "GEO-CAT1" not in cat3
    assert "GEO-OTHER" not in cat1
    assert "NÃO REVELAR OUTRA AUD" not in cat1


def test_report_633_long_monospace_card_identifiers_wrap_without_global_overflow() -> None:
    """Real-AUD mobile capture cards may contain long, unbroken evidence IDs."""
    from rasai.catalog_report_style import _CSS

    assert ".card .muted.mono{overflow-wrap:anywhere;word-break:break-word;white-space:normal}" in _CSS
    assert ".table-wrap{overflow:auto;" in _CSS


def test_633_reading_map_retains_canonical_destinations_and_compact_visual_tokens(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    html = (report / "index.html").read_text(encoding="utf-8")
    assert "class='report-reading-map'" in html
    assert html.count("class='report-reading-step'") == 6
    assert "capture-context.html" in html
    assert "execution-evidence.html" in html
    assert "ai-integrations.html" in html
    from rasai.catalog_report_style import _CSS
    assert ".report-reading-map{" in _CSS
    assert "--radius:8px" in _CSS
