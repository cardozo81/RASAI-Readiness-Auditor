from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from rasai.consolidation.cons4 import request_fingerprint
from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.service import generate, normalize_filter
from rasai.consolidation.specialist import build_evolution, preview_specialist
from tests.test_monitoring_observability import _workspace


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_consolidated_report_adds_deterministic_evolution_and_fix_verification_read_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", rule_result="FAIL", score=70)
        current = _workspace(root, "AUD-CURRENT", rule_result="PASS", score=82)
        before = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}

        result = generate(root, normalize_filter(domains=("example.test",), devices=("MOBILE",)))

        after = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}
        assert before == after
        html = result.report_path.read_text(encoding="utf-8")
        assert "Evolução determinística" in html
        assert "Fix Verification" in html
        assert "BR-GEO-011" in html
        assert "FIXED" in html
        assert "Análise especialista por IA" not in html
        artifact = json.loads((result.report_dir / "specialist-analysis.json").read_text(encoding="utf-8"))
        assert artifact["ai"]["requested"] is False
        assert artifact["comparison"]["baseline_audit_id"] == "AUD-BASE"
        assert artifact["comparison"]["current_audit_id"] == "AUD-CURRENT"
        assert any(item["status"] == "FIXED" for item in artifact["fix_verification"])


def test_comparison_modes_select_expected_pair() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-001", rule_result="FAIL", score=70)
        _workspace(root, "AUD-002", rule_result="FAIL", score=75)
        _workspace(root, "AUD-003", rule_result="PASS", score=85)
        index = ConsolidationIndex(root)
        index.refresh()

        first_last = build_evolution(root, normalize_filter(comparison_mode="FIRST_LAST"))
        assert first_last.comparison.baseline.audit_id == "AUD-001"
        assert first_last.comparison.current.audit_id == "AUD-003"

        latest = build_evolution(root, normalize_filter(comparison_mode="LATEST_PREVIOUS"))
        assert latest.comparison.baseline.audit_id == "AUD-002"
        assert latest.comparison.current.audit_id == "AUD-003"

        manual = build_evolution(
            root,
            normalize_filter(comparison_mode="MANUAL", baseline_audit_id="AUD-001", current_audit_id="AUD-002"),
        )
        assert manual.comparison.baseline.audit_id == "AUD-001"
        assert manual.comparison.current.audit_id == "AUD-002"


def test_ai_choice_changes_request_identity_without_persisting_secrets() -> None:
    base = normalize_filter(domains=("example.test",), comparison_mode="FIRST_LAST")
    ai = normalize_filter(
        domains=("example.test",),
        comparison_mode="FIRST_LAST",
        specialist_ai=True,
        ai_provider="openai",
        ai_model="gpt-5.6-luna",
        ai_reasoning="LOW",
        ai_timeout_seconds=180,
    )
    assert request_fingerprint("source", base) != request_fingerprint("source", ai)
    canonical = ai.canonical()
    assert canonical["specialist_ai"] is True
    assert canonical["ai_provider"] == "openai"
    assert not any("key" in key.casefold() or "secret" in key.casefold() for key in canonical)


def test_cost_preview_uses_canonical_pricing_and_request_token_hints() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-BASE", rule_result="FAIL", score=70)
        _workspace(root, "AUD-CURRENT", rule_result="PASS", score=82)
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(
            specialist_ai=True,
            ai_provider="openai",
            ai_model="gpt-5.6-luna",
            ai_reasoning="LOW",
        )
        provider = SimpleNamespace(
            name="OPENAI",
            model="gpt-5.6-luna",
            reasoning_profile="LOW",
            requested_reasoning_effort="LOW",
        )
        with patch("rasai.consolidation.specialist._build_ai", return_value=provider):
            preview = preview_specialist(root, filters)
        assert preview.available is True
        assert preview.selected is not None
        assert preview.selected.provider == "OPENAI"
        assert preview.selected.estimated_input_tokens >= 2000
        assert preview.selected.estimated_output_tokens > 0
        assert preview.selected.estimated_cost is not None
        assert preview.selected.currency == "USD"


def test_one_audit_keeps_consolidation_available_without_false_evolution() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-ONLY", rule_result="PASS", score=80)
        result = generate(root, normalize_filter())
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["evolution_analysis"]["status"] == "UNAVAILABLE"
        assert result.report_path.is_file()
