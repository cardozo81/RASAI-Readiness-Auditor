from __future__ import annotations

from rasai.consolidation_cli import build_parser as build_consolidation_parser
from rasai.reprocess_cli import build_parser as build_reprocess_parser


def test_reprocess_parser_accepts_selective_items_and_ai_policy() -> None:
    args = build_reprocess_parser().parse_args(
        [
            "AUD-TEST",
            "--audits-root",
            "audits",
            "--item",
            "WEB_PERFORMANCE::GLOBAL",
            "--item",
            "IMPROVEMENT_INTELLIGENCE::GLOBAL",
            "--use-ai",
            "--ai-provider",
            "openai",
            "--ai-model",
            "model-test",
            "--ai-reasoning",
            "HIGH",
        ]
    )

    assert args.audit_id == "AUD-TEST"
    assert args.item == [
        "WEB_PERFORMANCE::GLOBAL",
        "IMPROVEMENT_INTELLIGENCE::GLOBAL",
    ]
    assert args.use_ai is True
    assert args.ai_provider == "openai"
    assert args.ai_model == "model-test"
    assert args.ai_reasoning == "HIGH"


def test_consolidation_parser_accepts_manual_selection_and_optional_ai() -> None:
    args = build_consolidation_parser().parse_args(
        [
            "AUD-BASE",
            "AUD-CURRENT",
            "--selection-mode",
            "MANUAL",
            "--manual-audit-id",
            "AUD-MID",
            "--specialist-ai",
            "--ai-provider",
            "openai",
            "--ai-model",
            "model-test",
            "--ai-reasoning",
            "HIGH",
            "--ai-timeout-seconds",
            "90",
        ]
    )

    assert args.first_audit_id == "AUD-BASE"
    assert args.second_audit_id == "AUD-CURRENT"
    assert args.selection_mode == "MANUAL"
    assert args.manual_audit_id == ["AUD-MID"]
    assert args.specialist_ai is True
    assert args.ai_provider == "openai"
    assert args.ai_model == "model-test"
    assert args.ai_reasoning == "HIGH"
    assert args.ai_timeout_seconds == 90.0
