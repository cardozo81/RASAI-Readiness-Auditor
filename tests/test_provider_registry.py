from __future__ import annotations

import unittest

from rasai.m18_ai import DEFAULT_MODELS, KEY_ENV, MODEL_ENV, SUPPORTED_MODELS
from rasai.provider_extensions import (
    EXTENDED_DEFAULT_MODELS,
    EXTENDED_ENDPOINT_ENV,
    EXTENDED_KEY_ENV,
    EXTENDED_MODEL_ENV,
    EXTENDED_SUPPORTED_MODELS,
    _PROVIDER_ALIASES,
)
from rasai.provider_registry import (
    auto_provider_ids,
    cli_provider_choices,
    extension_cli_choices,
    get_provider_registration,
    provider_environment_names,
    provider_registrations,
)
from rasai.provider_runtime_policy import REASONING_OPTIONS, SIMPLE_DEFAULT_MODELS


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_contains_every_concrete_provider_once(self) -> None:
        registrations = provider_registrations()
        self.assertEqual(
            tuple(item.id for item in registrations),
            ("openai", "deepseek", "mimo", "xai", "qwen", "gemini", "anthropic", "copilot"),
        )
        self.assertEqual(len(registrations), len({item.id for item in registrations}))

    def test_legacy_metadata_is_derived_from_m18_sources(self) -> None:
        for provider_name in ("OPENAI", "DEEPSEEK", "MIMO"):
            registration = get_provider_registration(provider_name)
            self.assertIsNotNone(registration)
            assert registration is not None
            self.assertEqual(registration.key_env, KEY_ENV[provider_name])
            self.assertEqual(registration.model_env, MODEL_ENV[provider_name])
            self.assertEqual(registration.supported_models, SUPPORTED_MODELS[provider_name])
            self.assertEqual(registration.default_model, DEFAULT_MODELS[provider_name])
            self.assertTrue(registration.auto_eligible)
            self.assertFalse(registration.explicit_only)

    def test_extension_metadata_is_derived_from_adapter_sources_and_auto_eligible(self) -> None:
        provider_names = tuple(dict.fromkeys(_PROVIDER_ALIASES.values()))
        for provider_name in provider_names:
            registration = get_provider_registration(provider_name)
            self.assertIsNotNone(registration)
            assert registration is not None
            self.assertEqual(registration.key_env, EXTENDED_KEY_ENV[provider_name])
            self.assertEqual(registration.model_env, EXTENDED_MODEL_ENV[provider_name])
            self.assertEqual(registration.endpoint_env, EXTENDED_ENDPOINT_ENV[provider_name])
            self.assertEqual(registration.supported_models, EXTENDED_SUPPORTED_MODELS[provider_name])
            self.assertEqual(registration.default_model, EXTENDED_DEFAULT_MODELS[provider_name])
            self.assertTrue(registration.auto_eligible)
            self.assertFalse(registration.explicit_only)

    def test_registry_reasoning_contract_matches_runtime_exactly(self) -> None:
        for registration in provider_registrations():
            self.assertEqual(
                registration.reasoning_values,
                REASONING_OPTIONS[registration.provider_name],
                registration.id,
            )
        self.assertEqual(
            get_provider_registration("deepseek").reasoning_values,
            ("NONE", "LOW", "HIGH", "MAX"),
        )

    def test_public_runtime_defaults_are_supported_by_registry(self) -> None:
        for registration in provider_registrations():
            public_default = SIMPLE_DEFAULT_MODELS[registration.provider_name]
            self.assertIn(public_default, registration.supported_models, registration.id)

    def test_copilot_metadata_is_explicit_only(self) -> None:
        registration = get_provider_registration("copilot")
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertEqual(registration.provider_name, "COPILOT")
        self.assertEqual(registration.aliases, ("github-copilot",))
        self.assertEqual(registration.key_env, "COPILOT_GITHUB_TOKEN")
        self.assertEqual(registration.model_env, "RASAI_COPILOT_MODEL")
        self.assertEqual(registration.default_model, "auto")
        self.assertTrue(registration.explicit_only)
        self.assertFalse(registration.auto_eligible)

    def test_extension_aliases_and_cli_choices_are_registry_driven(self) -> None:
        self.assertEqual(
            extension_cli_choices(),
            (
                "xai", "grok", "qwen", "gemini", "anthropic", "claude",
                "copilot", "github-copilot",
            ),
        )
        self.assertEqual(get_provider_registration("grok").id, "xai")
        self.assertEqual(get_provider_registration("claude").id, "anthropic")
        self.assertEqual(get_provider_registration("github-copilot").id, "copilot")
        self.assertEqual(
            cli_provider_choices(),
            (
                "none", "openai", "deepseek", "mimo", "xai", "qwen", "gemini",
                "anthropic", "copilot", "auto", "grok", "claude", "github-copilot",
            ),
        )

    def test_auto_pool_is_registry_driven(self) -> None:
        self.assertEqual(
            auto_provider_ids(),
            ("openai", "deepseek", "mimo", "xai", "qwen", "gemini", "anthropic"),
        )
        self.assertNotIn("copilot", auto_provider_ids())

    def test_mimo_payg_key_constraint_is_exposed_to_consumers(self) -> None:
        registration = get_provider_registration("mimo")
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertEqual(registration.required_key_prefixes, ("sk-",))

    def test_environment_names_are_unique_and_include_extension_keys(self) -> None:
        names = provider_environment_names()
        self.assertEqual(len(names), len(set(names)))
        for required in (
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "MIMO_API_KEY",
            "XAI_API_KEY",
            "DASHSCOPE_API_KEY",
            "GEMINI_API_KEY",
            "ANTHROPIC_API_KEY",
            "COPILOT_GITHUB_TOKEN",
        ):
            self.assertIn(required, names)


if __name__ == "__main__":
    unittest.main()
