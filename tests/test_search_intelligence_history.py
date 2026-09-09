from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rasai.entrypoint import main as rasai_main
from rasai.search_intelligence.history import compare_search_workspaces


def _workspace(
    root: Path,
    name: str,
    *,
    position: int | None,
    domain_status: str,
    provider: str = "fixture",
    data_mode: str = "FIXTURE",
    device: str = "desktop",
    body_terms: tuple[str, ...] = ("seguro",),
    gaps: tuple[str, ...] = (),
) -> Path:
    workspace = root / name
    workspace.mkdir()
    db = sqlite3.connect(workspace / "audit.db")
    db.executescript(
        """
        CREATE TABLE audits (audit_id TEXT PRIMARY KEY);
        CREATE TABLE serp_observations (
            observation_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            query TEXT NOT NULL,
            engine TEXT NOT NULL,
            country TEXT NOT NULL,
            region TEXT,
            language TEXT NOT NULL,
            device TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            provider TEXT NOT NULL,
            requested_depth INTEGER NOT NULL,
            data_mode TEXT NOT NULL,
            observation_status TEXT NOT NULL,
            domain_of_interest TEXT,
            customer_position INTEGER,
            domain_status TEXT NOT NULL
        );
        CREATE TABLE serp_competitive_analyses (
            observation_id TEXT PRIMARY KEY,
            comparison_status TEXT NOT NULL,
            gaps_json TEXT NOT NULL
        );
        CREATE TABLE serp_competitive_pages (
            observation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            requested_url TEXT NOT NULL,
            fetch_status TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            query_terms_json TEXT NOT NULL,
            query_terms_title_json TEXT NOT NULL,
            query_terms_headings_json TEXT NOT NULL,
            query_terms_body_json TEXT NOT NULL,
            jsonld_types_json TEXT NOT NULL
        );
        """
    )
    audit_id = name.upper()
    observation_id = f"OBS-{name.upper()}"
    db.execute("INSERT INTO audits(audit_id) VALUES (?)", (audit_id,))
    db.execute(
        """INSERT INTO serp_observations(
            observation_id,audit_id,query,engine,country,region,language,device,
            collected_at,provider,requested_depth,data_mode,observation_status,
            domain_of_interest,customer_position,domain_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            observation_id,
            audit_id,
            "seguro auto online",
            "google",
            "BR",
            None,
            "pt-BR",
            device,
            "2026-09-09T12:00:00+00:00",
            provider,
            20,
            data_mode,
            "OBSERVED",
            "customer.example",
            position,
            domain_status,
        ),
    )
    db.execute(
        "INSERT INTO serp_competitive_analyses VALUES (?,?,?)",
        (
            observation_id,
            "CONSOLIDATED",
            json.dumps([{"code": code} for code in gaps]),
        ),
    )
    db.execute(
        """INSERT INTO serp_competitive_pages VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            observation_id,
            "CUSTOMER",
            "https://customer.example/seguro",
            "OBSERVED",
            400 if len(body_terms) == 1 else 700,
            json.dumps(["seguro", "auto", "online"]),
            json.dumps(["seguro"]),
            json.dumps(["seguro", "auto"]),
            json.dumps(list(body_terms)),
            json.dumps(["Product"]),
        ),
    )
    db.commit()
    db.close()
    return workspace


def test_history_reports_position_improvement_and_content_changes(tmp_path: Path) -> None:
    baseline = _workspace(
        tmp_path,
        "baseline",
        position=8,
        domain_status="FOUND",
        body_terms=("seguro",),
        gaps=("QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS",),
    )
    current = _workspace(
        tmp_path,
        "current",
        position=4,
        domain_status="FOUND",
        body_terms=("seguro", "auto", "online"),
        gaps=(),
    )

    result = compare_search_workspaces(baseline, current)
    statuses = [event.status for event in result.events]

    assert result.method == "SEARCH-HISTORY-001"
    assert result.comparable_contexts == 1
    assert result.non_comparable_contexts == 0
    assert "POSITION_IMPROVED" in statuses
    assert "CONTENT_SIGNAL_CHANGED" in statuses
    assert "DETERMINISTIC_GAP_RESOLVED" in statuses
    position_event = next(event for event in result.events if event.status == "POSITION_IMPROVED")
    assert position_event.before == 8
    assert position_event.after == 4
    assert position_event.delta == -4.0


def test_history_distinguishes_entering_observed_depth_from_absolute_rank(tmp_path: Path) -> None:
    baseline = _workspace(
        tmp_path,
        "baseline",
        position=None,
        domain_status="NOT_FOUND_WITHIN_DEPTH",
    )
    current = _workspace(tmp_path, "current", position=17, domain_status="FOUND")

    result = compare_search_workspaces(baseline, current)
    event = next(event for event in result.events if event.status == "ENTERED_OBSERVED_DEPTH")

    assert event.before == "NOT_FOUND_WITHIN_DEPTH"
    assert event.after == 17
    assert "previous absolute rank remains unknown" in (event.note or "")


def test_history_rejects_provider_change_as_not_comparable(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path, "baseline", position=5, domain_status="FOUND", provider="fixture")
    current = _workspace(tmp_path, "current", position=3, domain_status="FOUND", provider="serpapi")

    result = compare_search_workspaces(baseline, current)

    assert result.comparable_contexts == 0
    assert result.non_comparable_contexts == 1
    assert [event.status for event in result.events] == ["NOT_COMPARABLE"]
    assert any("provider changed" in note for note in result.compatibility_notes)


def test_history_requires_exact_context_identity(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path, "baseline", position=5, domain_status="FOUND", device="desktop")
    current = _workspace(tmp_path, "current", position=3, domain_status="FOUND", device="mobile")

    result = compare_search_workspaces(baseline, current)

    assert result.comparable_contexts == 0
    assert result.non_comparable_contexts == 2
    assert {event.status for event in result.events} == {"NEW_CONTEXT", "MISSING_CURRENT_CONTEXT"}


def test_search_history_cli_direct_mode_writes_json(tmp_path: Path, capsys) -> None:
    baseline = _workspace(tmp_path, "baseline", position=9, domain_status="FOUND")
    current = _workspace(tmp_path, "current", position=6, domain_status="FOUND")
    output = tmp_path / "history.json"

    code = rasai_main(
        [
            "search-history",
            "--baseline-workspace",
            str(baseline),
            "--current-workspace",
            str(current),
            "--json",
            str(output),
        ]
    )

    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["method"] == "SEARCH-HISTORY-001"
    assert payload["events"][0]["status"] == "POSITION_IMPROVED"
    assert "SEARCH-HISTORY-001" in capsys.readouterr().out
