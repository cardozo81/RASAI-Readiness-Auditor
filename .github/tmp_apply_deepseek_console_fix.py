from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) DeepSeek provider wire contract: required object keys instead of unsupported array cardinality.
m18 = ROOT / "src/searchgeo/m18_ai.py"
insert_anchor = '\n\nclass ResponsesSemanticProvider(_HardenedOpenAIProvider):\n'
helpers = r'''

def _deepseek_semantic_output_schema() -> dict[str, Any]:
    # Provider-wire schema that guarantees all 22 semantic rules without
    # array cardinality keywords. The SearchGEO canonical model remains an
    # ordered assessment array after local normalization.
    schema = json.loads(json.dumps(hardened_semantic_output_schema()))
    canonical_assessment = schema["properties"]["assessments"]["items"]
    assessment_value = json.loads(json.dumps(canonical_assessment))
    assessment_value["properties"].pop("rule_id", None)
    assessment_value["required"] = [
        field for field in assessment_value["required"] if field != "rule_id"
    ]
    schema["properties"]["assessments"] = {
        "type": "object",
        "properties": {
            rule_id: json.loads(json.dumps(assessment_value))
            for rule_id in SEMANTIC_RULE_IDS
        },
        "required": list(SEMANTIC_RULE_IDS),
        "additionalProperties": False,
    }
    # DeepSeek documents maxItems/minItems as unsupported in its strict schema
    # subset. Local SearchGEO validation continues to enforce <= 5 intents.
    schema["properties"]["secondary_intents"].pop("maxItems", None)
    return schema


def _canonicalize_deepseek_wire_payload(payload: Any) -> Any:
    # Convert the DeepSeek keyed assessment object to the canonical SearchGEO array.
    if not isinstance(payload, Mapping):
        return payload
    assessments = payload.get("assessments")
    if not isinstance(assessments, Mapping):
        # Backward-compatible acceptance of an already-canonical array response.
        return payload

    expected = frozenset(SEMANTIC_RULE_IDS)
    received = frozenset(str(key) for key in assessments)
    if received != expected or len(assessments) != len(SEMANTIC_RULE_IDS):
        raise SemanticSchemaError("INCOMPLETE_SEMANTIC_OUTPUT")

    canonical_assessments: list[dict[str, Any]] = []
    for rule_id in SEMANTIC_RULE_IDS:
        raw = assessments.get(rule_id)
        if not isinstance(raw, Mapping):
            raise SemanticSchemaError(f"INVALID_ASSESSMENT_OBJECT_{rule_id}")
        if "rule_id" in raw:
            raise SemanticSchemaError(f"UNEXPECTED_RULE_ID_FIELD_{rule_id}")
        canonical_assessments.append({"rule_id": rule_id, **dict(raw)})

    canonical = dict(payload)
    canonical["assessments"] = canonical_assessments
    return canonical
'''
replace_once(m18, insert_anchor, helpers + insert_anchor)

old_format = r'''        format_payload: dict[str, Any]
        if self.structured_mode == "json_object":
            instructions += "\n\nThe complete JSON Schema below is normative and will be validated locally:\n" + json.dumps(hardened_semantic_output_schema(), ensure_ascii=False, separators=(",", ":"))
            format_payload = {"type": "json_object"}
        else:
            format_payload = {
                "type": "json_schema",
                "name": "searchgeo_semantic_assessment",
                "schema": hardened_semantic_output_schema(),
            }
            if self.name == "OPENAI":
                format_payload["strict"] = True
'''
new_format = r'''        semantic_schema = hardened_semantic_output_schema()
        if self.name == "DEEPSEEK":
            semantic_schema = _deepseek_semantic_output_schema()
            instructions += (
                "\n\nDeepSeek wire contract: assessments MUST be a JSON object keyed by every "
                "rule id BR-GEO-028 through BR-GEO-049 exactly once. Each keyed value contains "
                "the assessment fields except rule_id; SearchGEO derives rule_id from the key."
            )

        format_payload: dict[str, Any]
        if self.structured_mode == "json_object":
            instructions += "\n\nThe complete JSON Schema below is normative and will be validated locally:\n" + json.dumps(semantic_schema, ensure_ascii=False, separators=(",", ":"))
            format_payload = {"type": "json_object"}
        else:
            format_payload = {
                "type": "json_schema",
                "name": "searchgeo_semantic_assessment",
                "schema": semantic_schema,
            }
            if self.name == "OPENAI":
                format_payload["strict"] = True
'''
replace_once(m18, old_format, new_format)

replace_once(
    m18,
    '            payload = _extract_json_payload(dict(raw))\n            normalized = normalize_provider_payload(\n',
    '            payload = _extract_json_payload(dict(raw))\n            if self.name == "DEEPSEEK":\n                payload = _canonicalize_deepseek_wire_payload(payload)\n            normalized = normalize_provider_payload(\n',
)

old_contract_error = r'''        except (SemanticSchemaError, SemanticEvidenceError) as exc:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__), AttemptStatus.CONTRACT_ERROR, usage=usage)
'''
new_contract_error = r'''        except (SemanticSchemaError, SemanticEvidenceError) as exc:
            return self._failure_result(
                semantic_input,
                started_at,
                started_perf,
                summary,
                payload_hash,
                ProviderDiagnostic(
                    ProviderErrorClass.CONTRACT_ERROR,
                    error_type=type(exc).__name__,
                    error_code=_safe_token(str(exc)),
                ),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )
'''
replace_once(m18, old_contract_error, new_contract_error)

# 2) Main console: action items are one per line; consolidated option belongs to the core menu.
console = ROOT / "src/searchgeo/interactive_console.py"
old_actions = r'''    print("\nS. Salvar configuração INI [SEM CHAVES] | H. Ajuda / custos | E. Variáveis de ambiente / credenciais")
    print(f"R. Executar [{marker}] {reason_text} | Q. Sair")
    workspace, report = artifact_status(state)
    if workspace or report:
        print(f"P. Abrir última pasta [{availability_badge(bool(workspace))}] | I. Abrir último relatório [{availability_badge(bool(report))}]")
    return input("Escolha: ").strip().upper()
'''
new_actions = r'''    print("\nAÇÕES")
    print("S. Salvar configuração INI [SEM CHAVES]")
    print("H. Ajuda / custos")
    print("E. Variáveis de ambiente / credenciais")
    print("C. Histórico / relatórios consolidados [OFFLINE | sem APIs]")
    print(f"R. Executar [{marker}] {reason_text}")
    print("Q. Sair")
    workspace, report = artifact_status(state)
    if workspace or report:
        print("\nARTEFATOS")
        print(f"P. Abrir última pasta [{availability_badge(bool(workspace))}]")
        print(f"I. Abrir último relatório [{availability_badge(bool(report))}]")
    return input("Escolha: ").strip().upper()
'''
replace_once(console, old_actions, new_actions)

# 3) Consolidation integration no longer injects a duplicate C line at input time.
integration = ROOT / "src/searchgeo/consolidation/integration.py"
replace_once(integration, "import builtins\n", "")
old_menu_wrapper = r'''    def menu_with_consolidation(state: Any) -> str:
        had_module_input = hasattr(interactive_console, "input")
        original_input = getattr(interactive_console, "input", builtins.input)

        def input_with_option(prompt: str = "") -> str:
            if prompt == "Escolha: ":
                print("C. Histórico / relatórios consolidados [OFFLINE | sem APIs]")
            return original_input(prompt)

        interactive_console.input = input_with_option
        try:
            return original_menu(state)
        finally:
            if had_module_input:
                interactive_console.input = original_input
            else:
                delattr(interactive_console, "input")
'''
new_menu_wrapper = r'''    def menu_with_consolidation(state: Any) -> str:
        # The core menu renders option C so all actions share one vertical layout.
        # This wrapper remains only to preserve the integration boundary.
        return original_menu(state)
'''
replace_once(integration, old_menu_wrapper, new_menu_wrapper)

# 4) Regression tests.
test_path = ROOT / "tests/test_deepseek_semantic_contract_and_console_actions.py"
test_path.write_text(r'''from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from searchgeo.console_config import State
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
''', encoding="utf-8")

# 5) Documentation stays explicit about the UI and provider-wire distinction.
doc_console = ROOT / "docs/INTERACTIVE_CONSOLE.md"
text = doc_console.read_text(encoding="utf-8")
marker = "Cada ação do menu principal é exibida em linha própria"
if marker not in text:
    text += (
        "\n\n### Layout das ações\n\n"
        "Cada ação do menu principal é exibida em linha própria. O caractere `|` pode aparecer "
        "em metadados/configurações, mas não é usado para agrupar ações selecionáveis. "
        "`V. Voltar` permanece o padrão de retorno em submenus; `Q. Sair` é reservado ao encerramento do console.\n"
    )
    doc_console.write_text(text, encoding="utf-8")

doc_m18 = ROOT / "docs/specification/18_MULTI_AI_PROVIDER_ROUTING.md"
text = doc_m18.read_text(encoding="utf-8")
marker = "DeepSeek wire contract por chaves obrigatórias"
if marker not in text:
    text += (
        "\n\n## DeepSeek wire contract por chaves obrigatórias\n\n"
        "Para DeepSeek via Responses API, o contrato de transporte das 22 avaliações semânticas usa "
        "um objeto cujas chaves obrigatórias são `BR-GEO-028` até `BR-GEO-049`. Isso evita depender "
        "de `minItems`/`maxItems` para cardinalidade de arrays, restrições que a documentação do "
        "DeepSeek declara não suportadas em seu subconjunto estrito de JSON Schema. Antes da "
        "persistência, o adapter converte o objeto para o array canônico SearchGEO e reaplica todas "
        "as validações locais de schema, evidência, completude e duplicidade. A alteração não muda "
        "scoring nem a semântica das regras.\n"
    )
    doc_m18.write_text(text, encoding="utf-8")

print("patch applied")
