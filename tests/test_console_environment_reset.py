from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from rasai.console_config import State
from rasai.console_environment_reset import _reset_specs, _staged_secret_value, install_environment_reset
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_runtime import install_pre_context
from rasai.synthetic_profile_console_runtime import install as install_synthetic_profile_console_runtime


def _installed_facade():
    install_pre_context()
    install_standards_console_runtime()
    install_synthetic_profile_console_runtime()
    install_runtime_completion_extensions()
    install_standards_console_runtime()
    install_synthetic_profile_console_runtime()
    from rasai import console_provider_environment as facade

    facade.refresh_specs()
    install_environment_reset()
    return facade


def test_secret_edit_can_be_cancelled_without_committing_value() -> None:
    state = SimpleNamespace(error="old", operation="")
    with patch("builtins.input", return_value="V"):
        value = _staged_secret_value(
            state=state,
            name="OPENAI_API_KEY",
            reader=lambda _: "sk-new-secret",
            validator=lambda _name, raw: raw,
        )
    assert value is None
    assert state.error == ""
    assert state.operation == "LOCAL:SECRET_EDIT_CANCELLED"


def test_secret_edit_commits_only_after_explicit_confirmation() -> None:
    state = SimpleNamespace(error="", operation="")
    with patch("builtins.input", return_value="C"):
        value = _staged_secret_value(
            state=state,
            name="OPENAI_API_KEY",
            reader=lambda _: "sk-confirmed",
            validator=lambda _name, raw: raw,
        )
    assert value == "sk-confirmed"


def test_scoped_reset_removes_session_but_preserves_machine_scope() -> None:
    facade = _installed_facade()
    state = State()
    spec = facade.SPEC_BY_NAME["RASAI_GSC_ENABLED"]
    with patch.dict(os.environ, {spec.name: "true"}, clear=False), patch(
        "rasai.console_environment_reset.user_environment_value", return_value=None
    ), patch(
        "rasai.console_environment_reset.machine_environment_value", return_value="true"
    ):
        result = _reset_specs(
            facade,
            state,
            (spec,),
            persist_ini=False,
            remove_user_persisted=False,
        )
        assert spec.name not in os.environ
    assert result.session_removed == 1
    assert result.user_removed == 0
    assert result.machine_preserved == (spec.name,)


def test_scoped_reset_can_remove_windows_user_persistence_explicitly() -> None:
    facade = _installed_facade()
    state = State()
    spec = facade.SPEC_BY_NAME["OPENAI_API_KEY"]
    with patch.dict(os.environ, {spec.name: "sk-session"}, clear=False), patch(
        "rasai.console_environment_reset.user_environment_value", return_value="sk-user"
    ), patch(
        "rasai.console_environment_reset.machine_environment_value", return_value=None
    ), patch(
        "rasai.console_environment_reset.remove_user_environment", return_value=True
    ) as remove_user:
        result = _reset_specs(
            facade,
            state,
            (spec,),
            persist_ini=False,
            remove_user_persisted=True,
        )
    remove_user.assert_called_once_with(spec.name)
    assert result.session_removed == 1
    assert result.user_removed == 1


def test_environment_menu_exposes_reset_action() -> None:
    facade = _installed_facade()
    output = io.StringIO()
    with patch.object(facade.base_environment, "render_header"), patch(
        "builtins.input", return_value="V"
    ), redirect_stdout(output):
        facade.environment_menu(State())
    rendered = output.getvalue()
    assert "Resetar variáveis por grupo ou todas" in rendered
    assert "Windows/Machine nunca é removido" in rendered
    assert "cancelados depois da digitação" in rendered


def test_web_features_dataset_metadata_is_explicit_about_path_and_current_no_data_limit() -> None:
    facade = _installed_facade()
    spec = facade.SPEC_BY_NAME["RASAI_WEB_FEATURES_DATASET"]
    assert spec.value_type == "caminho de arquivo existente"
    assert spec.accepted == ()
    assert "qualquer caminho para arquivo existente" in spec.notes
    assert "NO_DATA" in spec.notes
    assert "WEB_PLATFORM_BASELINE.md" in spec.source
    assert "web-platform-dx/web-features" in spec.source
