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
