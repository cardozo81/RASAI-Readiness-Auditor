from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.report_dashboard_final_polish import (
    _friendly_pagespeed_failure,
    finalize_dashboard_presentation,
)


def _card(title: str, value: str, detail: str = "detalhe") -> str:
    return (
        "<article class='ref-card indicator-card indicator-supporting condition-neutral'>"
        "<div class='kicker'>fonte</div>"
        f"<h3>{title}</h3>"
        f"<div class='score-number indicator-score'>{value}</div>"
        "<span class='indicator-condition'>Sem dados suficientes</span>"
        f"<p class='intro'>{detail}</p><p><a href='x.html'>Analisar detalhes</a></p></article>"
    )


def _index_html() -> str:
    cards = "".join(
        (
            _card("Core Web Vitals", "0/1 aprovados", "Aprovação de campo."),
            _card(
                "Lighthouse Performance",
                "NÃO DISPONÍVEL",
                "PageSpeed/Lighthouse não concluiu: WALL_CLOCK_TIMEOUT após 120s (wall-clock deadline exceeded after 120s).",
            ),
            _card("Lighthouse Accessibility", "NÃO DISPONÍVEL"),
            _card("Synthetic Navigation Apdex", "DESABILITADO", "Medição opcional não executada"),
            _card("Lighthouse Best Practices", "NÃO DISPONÍVEL"),
            _card("Lighthouse SEO técnico", "NÃO DISPONÍVEL"),
            _card("Synthetic User Experience Apdex", "DESABILITADO", "Medição opcional não executada"),
        )
    )
    return (
        "<html><head></head><body><main><header></header>"
        "<!-- rasai-executive-dashboard:start -->"
        "<section id='executive-indicator-dashboard' class='panel'>"
        "<div class='indicator-tier-label indicator-tier-supporting'>Indicadores complementares</div>"
        f"<div class='grid indicator-grid indicator-supporting-grid'>{cards}</div>"
        "</section><!-- rasai-executive-dashboard:end -->"
        "<section class='notice warn report-dependency-state' data-report-dependency-state='true'>"
        "<strong>Por que parte deste relatório pode estar sem resultado</strong>"
        "<p>A tentativa PageSpeed/Lighthouse falhou · WALL_CLOCK_TIMEOUT · wall-clock deadline exceeded after 120s.</p>"
        "</section></main></body></html>"
    )


def _prepare_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE synthetic_apdex_runs(audit_id TEXT, enabled INTEGER);
            CREATE TABLE synthetic_ux_apdex_runs(audit_id TEXT, enabled INTEGER);
            CREATE TABLE web_performance_runs(audit_id TEXT, enabled INTEGER, status TEXT, reason TEXT);
            CREATE TABLE web_performance_attempts(
                audit_id TEXT, service TEXT, status TEXT, http_status INTEGER,
                duration_ms INTEGER, error_code TEXT, error_message TEXT, created_at TEXT
            );
            INSERT INTO synthetic_apdex_runs VALUES('AUD-X',0);
            INSERT INTO synthetic_ux_apdex_runs VALUES('AUD-X',0);
            INSERT INTO web_performance_runs VALUES('AUD-X',1,'UNAVAILABLE','timeout');
            INSERT INTO web_performance_attempts VALUES(
                'AUD-X','PAGESPEED_INSIGHTS','ERROR',NULL,120000,
                'WALL_CLOCK_TIMEOUT','wall-clock deadline exceeded after 120s','2026-09-15T12:00:00Z'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_timeout_diagnostic_is_human_facing() -> None:
    detail = _friendly_pagespeed_failure(
        error_code="WALL_CLOCK_TIMEOUT",
        error_message="wall-clock deadline exceeded after 120s",
        duration_ms=120000,
    )
    assert detail == "A coleta PageSpeed/Lighthouse ultrapassou o tempo limite de 120 s."
    assert "WALL_CLOCK_TIMEOUT" not in detail
    assert "wall-clock" not in detail


def test_dashboard_groups_indicators_and_uses_effective_profile_scope(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    database = tmp_path / "audit.db"
    _prepare_database(database)
    (report_dir / "index.html").write_text(_index_html(), encoding="utf-8")
    dependency_page = (
        "<html><head></head><body><main>"
        "<section class='notice warn report-dependency-state' data-report-dependency-state='true'>"
        "<strong>Por que parte deste relatório pode estar sem resultado</strong>"
        "<p>A tentativa PageSpeed/Lighthouse falhou · WALL_CLOCK_TIMEOUT · wall-clock deadline exceeded after 120s.</p>"
        "</section></main></body></html>"
    )
    (report_dir / "web-performance.html").write_text(dependency_page, encoding="utf-8")
    (report_dir / "accessibility.html").write_text(dependency_page, encoding="utf-8")

    workspace = SimpleNamespace(root=tmp_path, database=database)
    finalize_dashboard_presentation(audit_id="AUD-X", workspace=workspace)
    rendered = (report_dir / "index.html").read_text(encoding="utf-8")

    assert "data-indicator-groups='true'" in rendered
    assert "indicator-lighthouse-grid" in rendered
    assert "indicator-apdex-grid" in rendered
    assert "Core Web Vitals / CrUX — dados de campo" in rendered
    assert "Chrome Lighthouse — laboratório" in rendered
    assert "0/1 aprovados" in rendered
    assert rendered.count("NÃO SOLICITADO") == 2
    assert "Synthetic Navigation Apdex não fez parte do perfil/configuração efetiva" in rendered
    assert "Synthetic User Experience Apdex não fez parte do perfil/configuração efetiva" in rendered
    assert "tempo limite de 120 s" in rendered
    assert "WALL_CLOCK_TIMEOUT" not in rendered
    assert "wall-clock deadline" not in rendered

    lighthouse_order = [rendered.index(title) for title in (
        "Lighthouse Performance",
        "Lighthouse Accessibility",
        "Lighthouse Best Practices",
        "Lighthouse SEO técnico",
    )]
    assert lighthouse_order == sorted(lighthouse_order)
    assert max(lighthouse_order) < rendered.index("Apdex sintético")

    specialized = (report_dir / "web-performance.html").read_text(encoding="utf-8")
    assert "tempo limite de 120 s" in specialized
    assert "WALL_CLOCK_TIMEOUT" not in specialized

    # The final pass is idempotent and must not duplicate layout/style wrappers.
    finalize_dashboard_presentation(audit_id="AUD-X", workspace=workspace)
    second = (report_dir / "index.html").read_text(encoding="utf-8")
    assert second.count("data-indicator-groups='true'") == 1
    assert second.count("rasai-indicator-cluster-layout-v1") == 1
