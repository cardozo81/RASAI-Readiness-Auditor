from __future__ import annotations

import sqlite3

from rasai.report_validation_reconciliation import _ai_totals, _lighthouse_class


def test_lighthouse_score_bands_follow_lighthouse_ranges() -> None:
    assert _lighthouse_class(0) == "lighthouse-score-bad"
    assert _lighthouse_class(49) == "lighthouse-score-bad"
    assert _lighthouse_class(50) == "lighthouse-score-warn"
    assert _lighthouse_class(89) == "lighthouse-score-warn"
    assert _lighthouse_class(90) == "lighthouse-score-good"
    assert _lighthouse_class(100) == "lighthouse-score-good"


def test_ai_totals_separate_accepted_contract_rejection_and_technical_errors() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE ai_provider_attempts (
            audit_id TEXT,
            status TEXT,
            total_tokens INTEGER,
            estimated_cost REAL,
            cost_currency TEXT,
            semantic_contract_version TEXT
        );
        CREATE TABLE content_remediation_attempts (
            audit_id TEXT,
            status TEXT,
            total_tokens INTEGER,
            estimated_cost REAL,
            cost_currency TEXT,
            contract_version TEXT
        );
        INSERT INTO ai_provider_attempts VALUES
            ('AUD-1','SUCCESS',13495,0.00612800,'USD','M18-SEMANTIC-V1'),
            ('AUD-1','TECHNICAL_ERROR',NULL,NULL,NULL,'M24-TECHNICAL-V1'),
            ('AUD-1','CONTRACT_ERROR',6942,0.00351172,'USD','M24-TECHNICAL-V1');
        INSERT INTO content_remediation_attempts VALUES
            ('AUD-1','TECHNICAL_ERROR',NULL,NULL,NULL,'M20-CONTENT-V1'),
            ('AUD-1','SUCCESS',16161,0.00590282,'USD','M20-CONTENT-V1');
        """
    )
    totals = _ai_totals(connection, "AUD-1")
    connection.close()

    assert totals["attempts"] == 5
    assert totals["accepted"] == 2
    assert totals["contract_rejected"] == 1
    assert totals["technical"] == 2
    assert totals["tokens"] == 36598
    assert abs(totals["costs"]["USD"] - 0.01554254) < 1e-12
    assert abs(totals["semantic_cost"] - 0.00612800) < 1e-12
    assert abs(totals["technical_cost"] - 0.00351172) < 1e-12
    assert abs(totals["content_cost"] - 0.00590282) < 1e-12
