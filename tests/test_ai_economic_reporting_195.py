import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_final_refinements import _ai_integrations_body
from rasai.m20_reporting import _telemetry_summary
from rasai.m24_reporting import _ai_block
from rasai.consolidation.presentation import specialist_usage_summary


def _attempt(
    *,
    provider: str,
    currency: str,
    cost: float,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None,
):
    return {
        "provider": provider,
        "model": "model",
        "reasoning_profile": "NONE",
        "duration_ms": 100,
        "input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "output_tokens": output_tokens,
        "reasoning_tokens": 17,
        "total_tokens": total_tokens,
        "estimated_cost": cost,
        "cost_currency": currency,
    }


def test_m20_summary_keeps_currencies_separate_and_derives_missing_total() -> None:
    attempts = [
        _attempt(
            provider="OPENAI",
            currency="USD",
            cost=0.1,
            input_tokens=100,
            output_tokens=40,
            total_tokens=None,
        ),
        _attempt(
            provider="ANTHROPIC",
            currency="EUR",
            cost=0.2,
            input_tokens=30,
            output_tokens=30,
            total_tokens=60,
        ),
    ]

    summary = _telemetry_summary(attempts)  # type: ignore[arg-type]

    assert summary["tokens"] == 200
    assert summary["cost"] == "0.20000000 EUR | 0.10000000 USD"
    assert "EUR/USD" not in summary["cost"]
    assert "USD/EUR" not in summary["cost"]


def test_m24_block_does_not_force_usd_or_double_count_reasoning() -> None:
    attempts = [
        _attempt(
            provider="OPENAI",
            currency="USD",
            cost=0.1,
            input_tokens=100,
            output_tokens=40,
            total_tokens=None,
        ),
        _attempt(
            provider="ANTHROPIC",
            currency="EUR",
            cost=0.2,
            input_tokens=30,
            output_tokens=30,
            total_tokens=60,
        ),
    ]
    html = _ai_block(
        {
            "ai": {
                "state": "COMPLETE",
                "provider": "AUTO",
                "model": None,
                "artifact_reference": None,
            },
            "attempts": attempts,
        }
    )

    assert ">200<" in html
    assert "0.200000 EUR" in html
    assert "0.100000 USD" in html
    assert "0.300000 USD" not in html


def test_consolidated_usage_respects_provider_total_and_currency_boundaries(tmp_path) -> None:
    payload = {
        "ai": {
            "requested": True,
            "status": "COMPLETE",
            "attempts": [
                {
                    "provider": "OPENAI",
                    "model": "model-a",
                    "status": "SUCCESS",
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "reasoning_tokens": 17,
                    "total_tokens": 150,
                    "estimated_cost": 0.1,
                    "currency": "USD",
                },
                {
                    "provider": "ANTHROPIC",
                    "model": "model-b",
                    "status": "SUCCESS",
                    "input_tokens": 30,
                    "output_tokens": 30,
                    "reasoning_tokens": 5,
                    "total_tokens": None,
                    "estimated_cost": 0.2,
                    "currency": "EUR",
                },
            ],
        }
    }
    (tmp_path / "specialist-analysis.json").write_text(
        __import__("json").dumps(payload),
        encoding="utf-8",
    )

    summary = specialist_usage_summary(tmp_path)

    assert summary is not None
    assert summary.total_tokens == 210
    assert summary.reasoning_tokens == 22
    assert summary.costs == (("EUR", 0.2), ("USD", 0.1))


def test_ai_integrations_projects_mixed_currency_without_implicit_fx(tmp_path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE ai_provider_attempts(
                audit_id TEXT,
                semantic_contract_version TEXT,
                provider TEXT,
                model TEXT,
                status TEXT,
                input_tokens INTEGER,
                cached_input_tokens INTEGER,
                output_tokens INTEGER,
                reasoning_tokens INTEGER,
                total_tokens INTEGER,
                estimated_cost REAL,
                cost_currency TEXT,
                attempt_index INTEGER,
                started_at TEXT,
                finished_at TEXT,
                duration_ms INTEGER,
                decision TEXT,
                fallback_reason TEXT,
                error_detail TEXT,
                error_code TEXT,
                request_message_summary TEXT,
                request_payload_hash TEXT
            );
            CREATE TABLE audit_reprocess_runs(
                reprocess_id TEXT,
                audit_id TEXT,
                started_at TEXT,
                completed_at TEXT
            );
            """
        )
        rows = [
            (
                "AUD", "M18-SEMANTIC-22-v1", "OPENAI", "model-a", "SUCCESS",
                100, 0, 40, 17, None, 0.1, "USD", 1,
                "2026-10-04T12:00:00+00:00", "2026-10-04T12:00:01+00:00",
                100, "SUCCESS", None, None, None, "rules=22;evidence=8", "hash-a",
            ),
            (
                "AUD", "M18-SEMANTIC-22-v1", "ANTHROPIC", "model-b", "SUCCESS",
                30, 0, 30, 5, 60, 0.2, "EUR", 2,
                "2026-10-04T12:00:02+00:00", "2026-10-04T12:00:03+00:00",
                100, "SUCCESS", None, None, None, "rules=22;evidence=8", "hash-b",
            ),
        ]
        connection.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()

    data = SimpleNamespace(
        audit_id="AUD",
        targets=("https://example.test/",),
        selected={"CAT-03"},
        audit={"project_name": "Projeto", "status": "COMPLETED"},
        fulfillment={"processing_status": "COMPLETE"},
    )

    html = _ai_integrations_body(database, data)

    assert "Custo técnico contabilizado" in html
    assert "EUR 0.20000000" in html
    assert "USD 0.10000000" in html
    assert "USD/EUR" not in html
    assert "EUR/USD" not in html
    assert "Tokens totais" in html
    assert ">200<" in html
