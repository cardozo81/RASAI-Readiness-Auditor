from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from searchgeo.console_m23 import State
from searchgeo.interactive_console import _menu
from searchgeo.m18_ai import DeepSeekProvider
from searchgeo.semantic import (
    ProviderState,
    SEMANTIC_RULE_IDS,
    SemanticEvidenceInput,
    SemanticInput,
)


def _semantic_input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-TEST",
        page_url="https://example.test/",
        title="Example",
        main_content="Example content",
        structured_data=[],
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EV-1",
                evidence_type="DOM",
                source="test",
                observed_value={"summary": "test"},
            ),
        ),
    )


def _keyed_payload() -> dict[str, object]:
    assessment = {
        "result": "UNKNOWN",
        "confidence": 0.0,
        "evidence_ids": [],
        "reasoning_summary": "Insufficient evidence.",
        "observed_value": {"summary": "Insufficient evidence.", "details": []},
    }
    return {
        "assessments": {
            rule_id: dict(assessment)
            for rule_id in SEMANTIC_RULE_IDS
        },
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


def _response(payload: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "output_text": json.dumps(payload),
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 200,
            "output_tokens_details": {"reasoning_tokens": 50},
            "total_tokens": 300,
        },
    }


class DeepSeekSemanticWireContractTests(unittest.TestCase):
    def test_deepseek_uses_required_rule_keys_and_normalizes_to_canonical_array(self) -> None:
        captured: dict[str, object] = {}

        def transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
            del url, headers, timeout
            captured["request"] = json.loads(body.decode("utf-8"))
            return _response(_keyed_payload())

        provider = DeepSeekProvider(
            model="deepseek-v4-flash",
            reasoning_effort="LOW",
            api_key="test-key",
            transport=transport,
        )
        result = provider.analyze(_semantic_input())

        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertIsNotNone(result.response)
        self.assertEqual(
            tuple(item.rule_id for item in result.response.assessments),
            SEMANTIC_RULE_IDS,
        )

        request = captured["request"]
        schema = request["text"]["format"]["schema"]
        assessments = schema["properties"]["assessments"]
        self.assertEqual(assessments["type"], "object")
        self.assertEqual(set(assessments["required"]), set(SEMANTIC_RULE_IDS))
        self.assertEqual(set(assessments["properties"]), set(SEMANTIC_RULE_IDS))
        self.assertNotIn("minItems", assessments)
        self.assertNotIn("maxItems", assessments)
        self.assertNotIn("maxItems", schema["properties"]["secondary_intents"])
        for rule_id in SEMANTIC_RULE_IDS:
            self.assertNotIn(
                "rule_id",
                assessments["properties"][rule_id]["properties"],
            )

    def test_contract_failure_exposes_sanitized_specific_code(self) -> None:
        payload = _keyed_payload()
        del payload["assessments"][SEMANTIC_RULE_IDS[-1]]

        provider = DeepSeekProvider(
            model="deepseek-v4-flash",
            reasoning_effort="LOW",
            api_key="test-key",
            transport=lambda *_: _response(payload),
        )
        result = provider.analyze(_semantic_input())

        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertIn("SemanticSchemaError", result.reason or "")
        self.assertIn("code=INCOMPLETE_SEMANTIC_OUTPUT", result.reason or "")


class ConsoleActionLayoutTests(unittest.TestCase):
    def test_main_action_menu_is_vertical_and_pipe_free(self) -> None:
        state = State()
        with patch("builtins.input", return_value="Q"), redirect_stdout(io.StringIO()) as output:
            choice = _menu(state)

        self.assertEqual(choice, "Q")
        lines = [line.strip() for line in output.getvalue().splitlines()]
        expected_prefixes = (
            "S. Salvar configuração INI",
            "H. Ajuda / custos",
            "E. Variáveis de ambiente / credenciais",
            "C. Histórico / relatórios consolidados",
            "R. Executar",
            "Q. Sair",
        )
        positions = []
        for prefix in expected_prefixes:
            matching = [index for index, line in enumerate(lines) if line.startswith(prefix)]
            self.assertEqual(len(matching), 1, prefix)
            positions.append(matching[0])
            self.assertNotIn("|", lines[matching[0]])
        self.assertEqual(positions, sorted(positions))
        self.assertIn("AÇÕES", lines)


if __name__ == "__main__":
    unittest.main()
