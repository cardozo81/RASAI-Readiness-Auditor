"""G1 persistent setting validation and fail-closed authorization."""
import pytest
from rasai.network_active_policy import validate_network_setting, authorized_hostname, max_hops


def test_settings_reject_unsafe_hosts_and_unbounded_limits():
    assert validate_network_setting("RASAI_NETWORK_ACTIVE_HOST", "www.hetzner.com") == "www.hetzner.com"
    for host in ("localhost", "192.168.1.10", "example.local", "a/b.example"):
        with pytest.raises(ValueError):
            validate_network_setting("RASAI_NETWORK_ACTIVE_HOST", host)
    for hops in ("0", "17", "4.5", "true"):
        with pytest.raises(ValueError):
            validate_network_setting("RASAI_NETWORK_MAX_HOPS", hops)


def test_network_authorization_is_explicit_exact_and_revocable():
    settings = {"RASAI_NETWORK_ACTIVE_ENABLED": "false",
                "RASAI_NETWORK_ACTIVE_HOST": "www.hetzner.com"}
    assert authorized_hostname(settings) is None
    settings["RASAI_NETWORK_ACTIVE_ENABLED"] = "true"
    assert authorized_hostname(settings) == "www.hetzner.com"
    settings.pop("RASAI_NETWORK_ACTIVE_HOST")
    assert authorized_hostname(settings) is None
    assert authorized_hostname({"RASAI_NETWORK_ACTIVE_ENABLED": "true",
                                "RASAI_NETWORK_ACTIVE_HOST": "127.0.0.1"}) is None
    assert max_hops({"RASAI_NETWORK_MAX_HOPS": "16"}) == 16
    assert max_hops({"RASAI_NETWORK_MAX_HOPS": "300"}) == 8


def test_exact_hostname_derived_from_current_http_url_without_scheme_or_path():
    from rasai.network_active_policy import hostname_from_audit_url
    assert hostname_from_audit_url("https://loja.bradescoseguros.com.br/seguro?x=1") == "loja.bradescoseguros.com.br"
    assert hostname_from_audit_url("loja.bradescoseguros.com.br") == "loja.bradescoseguros.com.br"
    assert hostname_from_audit_url("HTTP://WWW.HETZNER.COM:80/path") == "www.hetzner.com"
    assert validate_network_setting(
        "RASAI_NETWORK_ACTIVE_HOST", "https://www.hetzner.com/page"
    ) == "www.hetzner.com"
    for url in (
        "ftp://www.hetzner.com/",
        "https://name:secret@www.hetzner.com/",
        "https://localhost/",
        "http://192.168.1.7/",
        "https://www.hetzner.com:invalid/",
        "https://www.hetzner.com/invalid path",
    ):
        with pytest.raises(ValueError):
            hostname_from_audit_url(url)


def test_network_preparation_cancel_never_changes_auth_scope(monkeypatch):
    import os
    from types import SimpleNamespace
    from rasai.console_network_settings import network_settings_menu
    from rasai.console_session import clear_session_meta

    monkeypatch.setenv("RASAI_NETWORK_ACTIVE_ENABLED", "true")
    monkeypatch.setenv("RASAI_NETWORK_ACTIVE_HOST", "www.hetzner.com")
    state = SimpleNamespace(target="https://loja.bradescoseguros.com.br/", error="")
    console = SimpleNamespace(
        render_header=lambda _: None,
        _save_configuration=lambda _: (_ for _ in ()).throw(AssertionError("must not save")),
    )
    try:
        monkeypatch.setattr("builtins.input", lambda *_: "V")
        network_settings_menu(console, state)
        assert os.environ["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
        assert os.environ["RASAI_NETWORK_ACTIVE_ENABLED"] == "true"
    finally:
        clear_session_meta(state)


def test_network_preparation_authorization_is_explicit_and_revocable(monkeypatch):
    import os
    from types import SimpleNamespace
    from rasai.console_network_settings import network_settings_menu, _status
    from rasai.console_session import clear_session_meta

    monkeypatch.delenv("RASAI_NETWORK_ACTIVE_HOST", raising=False)
    monkeypatch.setenv("RASAI_NETWORK_ACTIVE_ENABLED", "false")
    state = SimpleNamespace(target="https://www.hetzner.com/path", error="")
    saves = []
    console = SimpleNamespace(
        render_header=lambda _: None,
        _save_configuration=lambda _: saves.append(True) or True,
    )
    try:
        assert _status(state)[0].startswith("DESABILITADA")
        answers = iter(["1", "N", "V"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        network_settings_menu(console, state)
        assert os.environ["RASAI_NETWORK_ACTIVE_ENABLED"] == "false"

        answers = iter(["1", "S", "1", "V"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        network_settings_menu(console, state)
        assert os.environ["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
        assert os.environ["RASAI_NETWORK_ACTIVE_ENABLED"] == "true"
        assert not saves

        state.target = "https://loja.bradescoseguros.com.br/"
        assert _status(state)[0].startswith("NÃO AUTORIZADA")
        answers = iter(["2", "1", "V"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        network_settings_menu(console, state)
        assert os.environ["RASAI_NETWORK_ACTIVE_ENABLED"] == "false"
        assert "RASAI_NETWORK_ACTIVE_HOST" not in os.environ
    finally:
        clear_session_meta(state)


def test_network_preparation_failed_persistence_rolls_back(monkeypatch):
    import os
    from types import SimpleNamespace
    from rasai.console_network_settings import network_settings_menu
    from rasai.console_session import clear_session_meta

    monkeypatch.setenv("RASAI_NETWORK_ACTIVE_ENABLED", "false")
    monkeypatch.delenv("RASAI_NETWORK_ACTIVE_HOST", raising=False)
    state = SimpleNamespace(target="https://www.hetzner.com/", error="")
    console = SimpleNamespace(render_header=lambda _: None, _save_configuration=lambda _: False)
    try:
        answers = iter(["1", "S", "2", "V"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        network_settings_menu(console, state)
        assert os.environ["RASAI_NETWORK_ACTIVE_ENABLED"] == "false"
        assert "RASAI_NETWORK_ACTIVE_HOST" not in os.environ
        assert "não foi aplicada" in state.error
    finally:
        clear_session_meta(state)


def test_session_network_consent_not_leaked_by_unrelated_save_but_reaches_audit(monkeypatch, tmp_path):
    import os
    from configparser import ConfigParser
    from types import SimpleNamespace
    from unittest.mock import patch
    from rasai import console_settings
    from rasai.console_complete_persistence import install
    from rasai.console_network_settings import _apply_consent
    from rasai.console_session import (
        clear_session_meta, get_volatile_network_consent, set_config_path,
    )
    from rasai.audit_configuration_reuse_console import _export_settings
    from rasai.console_search_intelligence import SearchConsoleState

    install()
    ini = tmp_path / "rasai-console.ini"
    state = SearchConsoleState()
    state.target = "https://www.hetzner.com/"
    with patch.dict(os.environ, {"RASAI_CONSOLE_INI": str(ini)}, clear=True):
        set_config_path(state, ini)
        try:
            console_settings.save_console_config(state, ini)
            original = ini.read_bytes()
            monkeypatch.setattr("rasai.console_ui_catalog._destination", lambda secret: "1")
            console = SimpleNamespace(_save_configuration=lambda _: True)
            assert _apply_consent(console, state, host="www.hetzner.com")
            assert get_volatile_network_consent(state) is not None
            assert os.environ["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
            assert _export_settings(state, ["https://www.hetzner.com/"])["settings"]["environment"][
                "RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"

            # Save a completely unrelated preference. No implicit persistence of consent.
            os.environ["RASAI_NETWORK_MAX_HOPS"] = "16"
            console_settings.save_console_config(state, ini)
            parser = ConfigParser(interpolation=None)
            parser.optionxform = str
            parser.read(ini, encoding="utf-8")
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_HOST"] == ""
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_ENABLED"] == "false"
            assert parser["environment"]["RASAI_NETWORK_MAX_HOPS"] == "16"
            assert original != ini.read_bytes()

            # Explicit persistence is a separate user choice.
            monkeypatch.setattr("rasai.console_ui_catalog._destination", lambda secret: "2")
            console._save_configuration = lambda s: bool(console_settings.save_console_config(s, ini))
            assert _apply_consent(console, state, host="www.hetzner.com")
            assert get_volatile_network_consent(state) is None
            parser.read(ini, encoding="utf-8")
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_ENABLED"] == "true"

            # Revocation limited to this session must not mutate the saved grant.
            monkeypatch.setattr("rasai.console_ui_catalog._destination", lambda secret: "1")
            assert _apply_consent(console, state, host=None)
            assert _export_settings(state, ["https://www.hetzner.com/"])["settings"]["environment"][
                "RASAI_NETWORK_ACTIVE_ENABLED"] == "false"
            console_settings.save_console_config(state, ini)
            parser.read(ini, encoding="utf-8")
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_ENABLED"] == "true"
            assert parser["environment"]["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
        finally:
            clear_session_meta(state)


def test_network_consent_persistent_failure_restores_session_override(monkeypatch, tmp_path):
    import os
    from types import SimpleNamespace
    from unittest.mock import patch
    from rasai.console_network_settings import _apply_consent
    from rasai.console_session import (
        clear_session_meta, get_volatile_network_consent, set_config_path,
    )
    ini = tmp_path / "does-not-exist.ini"
    state = SimpleNamespace(target="https://www.hetzner.com/", error="")
    with patch.dict(os.environ, {}, clear=True):
        set_config_path(state, ini)
        try:
            console = SimpleNamespace(_save_configuration=lambda s: False)
            monkeypatch.setattr("rasai.console_ui_catalog._destination", lambda secret: "1")
            assert _apply_consent(console, state, host="www.hetzner.com")
            before = get_volatile_network_consent(state)
            monkeypatch.setattr("rasai.console_ui_catalog._destination", lambda secret: "2")
            assert not _apply_consent(console, state, host="www.hetzner.com")
            assert get_volatile_network_consent(state) == before
            assert os.environ["RASAI_NETWORK_ACTIVE_HOST"] == "www.hetzner.com"
        finally:
            clear_session_meta(state)
