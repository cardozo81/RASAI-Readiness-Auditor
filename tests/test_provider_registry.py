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


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_contains_every_concrete_provider_once(self) -> None:
        registrations = provider_registrations()
        self.assertEqual(
            tuple(item.id for item in registrations),
            ("openai", "deepseek", "mimo", "xai", "qwen", "gemini", "anthropic"),
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

    def test_extension_aliases_and_cli_choices_are_registry_driven(self) -> None:
        self.assertEqual(
            extension_cli_choices(),
            tuple(alias.casefold() for alias in _PROVIDER_ALIASES),
        )
        self.assertEqual(get_provider_registration("grok").id, "xai")
        self.assertEqual(get_provider_registration("claude").id, "anthropic")
        self.assertEqual(
            cli_provider_choices(),
            (
                "none", "openai", "deepseek", "mimo", "auto",
                "xai", "grok", "qwen", "gemini", "anthropic", "claude",
            ),
        )

    def test_auto_pool_is_registry_driven(self) -> None:
        self.assertEqual(
            auto_provider_ids(),
            ("openai", "deepseek", "mimo", "xai", "qwen", "gemini", "anthropic"),
        )

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
        ):
            self.assertIn(required, names)


if __name__ == "__main__":
    unittest.main()
