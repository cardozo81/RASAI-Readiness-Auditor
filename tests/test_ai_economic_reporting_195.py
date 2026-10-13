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


def _two_priced_ai_attempts_fixture(tmp_path):
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

    return database, data


def test_ai_integrations_projects_mixed_currency_without_implicit_fx(tmp_path) -> None:
    database, data = _two_priced_ai_attempts_fixture(tmp_path)
    html = _ai_integrations_body(database, data)

    assert "Custo observado" in html
    assert "custo técnico contabilizado" in html
    assert "EUR 0.20000000" in html
    assert "USD 0.10000000" in html
    assert "USD/EUR" not in html
    assert "EUR/USD" not in html
    assert "Tokens totais" in html
    assert ">200<" in html


def test_final_report_explains_point_deviation_without_false_currency_conversion(
    tmp_path, monkeypatch,
) -> None:
    from rasai import catalog_report_integrations as i

    database, data = _two_priced_ai_attempts_fixture(tmp_path)
    original_bytes = database.read_bytes()
    forecast = {
        "currency": "USD", "expected_cost": 0.2, "actual_cost": 0.3,
        "likely_low": 0.1, "likely_high": 0.4, "potential": 0.5,
        "status": "CRÍTICO", "confidence": "MODERADA",
    }
    monkeypatch.setattr(i, "_cost_forecast", lambda *_: forecast)

    # A successful multi-currency ledger is still not a USD total.
    mixed = _ai_integrations_body(database, data)
    assert "Moedas dos custos" in mixed
    assert "Posição do custo na faixa histórica: N/D" in mixed
    assert "dentro da faixa histórica provável" not in mixed
    assert "Desvio frente à estimativa pontual persistida" not in mixed

    # Same sample, physically priced in USD, can now be reconciled.
    with sqlite3.connect(database) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET cost_currency='USD' "
            "WHERE provider='ANTHROPIC'"
        )
    after_normalization = database.read_bytes()
    matched = _ai_integrations_body(database, data)
    assert "dentro da faixa histórica provável" in matched
    assert "Desvio frente à estimativa pontual persistida: +50.00%" in matched
    assert "não constitui fatura" in matched

    # Persisted fields cannot coerce INVALID -> 0 or surface NaN/Infinity
    # as a forecast percentage, P90 or monetary total in the human report.
    forecast.update(
        actual_cost="NOT_A_COST",
        deviation_amount=float("inf"),
        deviation_percent=float("nan"),
        likely_low=-1.0,
        potential=float("inf"),
    )
    invalid = _ai_integrations_body(database, data)
    assert "Não calculável" in invalid
    assert "não possui um único total monetário comparável" in invalid
    assert "O custo pós-execução persistido coincide" not in invalid
    assert "nan%" not in invalid.lower()
    assert "USD nan" not in invalid
    assert "USD inf" not in invalid
    assert "Posição do custo na faixa histórica: N/D" in invalid
    forecast.update(
        actual_cost=0.3,
        deviation_amount=0.1,
        deviation_percent=50.0,
        likely_low=0.1,
        potential=0.5,
    )

    # An explicitly persisted total inconsistent with the ledger is
    # not a legitimate forecast interval comparison.
    forecast["actual_cost"] = 0.1
    unreconciled = _ai_integrations_body(database, data)
    assert "Posição do custo na faixa histórica: N/D" in unreconciled
    assert "Desvio frente à estimativa pontual persistida" not in unreconciled

    # A directed/post-AUD call cannot be retrofitted into the central
    # pre-execution expected-cost population.
    forecast["actual_cost"] = 0.3
    with sqlite3.connect(database) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET "
            "semantic_contract_version='DIRECTED-ANALYSIS-001' "
            "WHERE provider='OPENAI'"
        )
    after_directed = database.read_bytes()
    directed = _ai_integrations_body(database, data)
    assert "1 tentativa(s) de análise complementar/direcionada" in directed
    assert "Posição do custo na faixa histórica: N/D" in directed
    assert "Desvio frente à estimativa pontual persistida" not in directed
    assert database.read_bytes() == after_directed
    assert original_bytes != after_normalization
