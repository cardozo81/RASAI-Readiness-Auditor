import builtins
from types import SimpleNamespace

from rasai import console_configuration_guidance as guidance
from rasai.console_guided_input_fix import install


def _spec(value_type="enum"):
    return SimpleNamespace(
        name="RASAI_AI_CONTENT_REMEDIATION",
        accepted=("true", "false"),
        default="false",
        value_type=value_type,
        purpose="Default da remediação de conteúdo por IA.",
    )


def test_guided_prompt_resolves_builtin_input_at_interaction_time(monkeypatch):
    calls = []

    def runtime_input(prompt: str) -> str:
        calls.append(prompt)
        return "1"

    def single_choice(spec, input_fn):
        assert input_fn is runtime_input
        return input_fn("Escolha: ")

    monkeypatch.setattr(guidance, "_single_choice", single_choice)
    monkeypatch.setattr(builtins, "input", runtime_input)
    install()

    assert guidance.prompt_guided_value(_spec()) == "1"
    assert calls == ["Escolha: "]


def test_provider_environment_alias_uses_same_runtime_prompt(monkeypatch):
    from rasai import console_provider_environment as provider_environment

    answers = iter(("1",))

    def runtime_input(prompt: str) -> str:
        return next(answers)

    def single_choice(spec, input_fn):
        assert input_fn is runtime_input
        return input_fn("Escolha: ")

    monkeypatch.setattr(guidance, "_single_choice", single_choice)
    monkeypatch.setattr(builtins, "input", runtime_input)
    install()

    assert provider_environment.prompt_guided_value(_spec()) == "1"
