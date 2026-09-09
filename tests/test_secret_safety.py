from __future__ import annotations

import logging
from pathlib import Path
import textwrap

import pytest

from rasai.logging_config import SecretSafeFormatter
from rasai.property_config import PROPERTY_CONFIG_CONTRACT, load_property_config
from rasai.secret_safety import (
    PRIVATE_KEY_REDACTED,
    REDACTED,
    detect_secret_exposures,
    is_sensitive_name,
    redact_text,
    redact_url,
    redact_value,
    scan_repository,
)


ROOT = Path(__file__).resolve().parents[1]


def test_sensitive_names_and_recursive_redaction_are_provider_neutral() -> None:
    assert is_sensitive_name("OPENAI_API_KEY")
    assert is_sensitive_name("database.password")
    assert is_sensitive_name("Authorization")
    sanitized = redact_value({
        "provider": "openai",
        "api_key": "TEST_ONLY_NOT_REAL",
        "nested": {
            "database_url": "postgresql://user:TEST_ONLY_PASSWORD@db.example.test/app",
            "password": "TEST_ONLY_PASSWORD",
        },
        "api_key_env": "OPENAI_API_KEY",
    })
    assert sanitized["api_key"] == REDACTED
    assert sanitized["nested"]["password"] == REDACTED
    assert "TEST_ONLY_PASSWORD" not in sanitized["nested"]["database_url"]
    assert sanitized["api_key_env"] == "OPENAI_API_KEY"


def test_text_and_url_redaction_scrub_headers_tokens_credentials_and_private_keys() -> None:
    url = "postgresql://rasai_app:TEST_ONLY_PASSWORD@db.example.test:5432/app?sslmode=require&password=TEST_ONLY_QUERY"
    redacted_url = redact_url(url)
    assert "TEST_ONLY_PASSWORD" not in redacted_url
    assert "TEST_ONLY_QUERY" not in redacted_url
    assert "sslmode=require" in redacted_url

    private_key = "-----BEGIN PRIVATE KEY-----\nTEST_ONLY_PRIVATE_KEY_DATA\n-----END PRIVATE KEY-----"
    text = (
        "Authorization: Bearer TEST_ONLY_BEARER\n"
        "Cookie: session=TEST_ONLY_COOKIE\n"
        + private_key
    )
    sanitized = redact_text(text)
    assert "TEST_ONLY_BEARER" not in sanitized
    assert "TEST_ONLY_COOKIE" not in sanitized
    assert "TEST_ONLY_PRIVATE_KEY_DATA" not in sanitized
    assert PRIVATE_KEY_REDACTED in sanitized


def test_logging_formatter_redacts_message_and_exception_material() -> None:
    formatter = SecretSafeFormatter("%(levelname)s %(message)s")
    try:
        raise RuntimeError("database_password=prod-value-93af")
    except RuntimeError:
        record = logging.LogRecord(
            name="rasai.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Authorization: Bearer live-token-93af",
            args=(),
            exc_info=__import__("sys").exc_info(),
        )
    rendered = formatter.format(record)
    assert "live-token-93af" not in rendered
    assert "prod-value-93af" not in rendered
    assert REDACTED in rendered


def test_detector_allows_explicit_placeholders_but_rejects_inline_material() -> None:
    safe = "password=<password>\napi_key_env=OPENAI_API_KEY\nAuthorization: Bearer [REDACTED]"
    assert detect_secret_exposures(safe) == ()

    unsafe = "database_password=prod-value-93af\nAuthorization: Bearer live-token-93af"
    findings = detect_secret_exposures(unsafe, path="config.toml")
    assert {item.kind for item in findings} >= {"SECRET_ASSIGNMENT", "BEARER_TOKEN"}


def test_versioned_property_configuration_uses_references_not_secret_values(tmp_path: Path) -> None:
    config = tmp_path / "client.toml"
    config.write_text(textwrap.dedent("""
        [property]
        id = "client"
        name = "Client"
        origin = "https://client.example"

        [database]
        backend = "postgresql"
        database_url_env = "RASAI_PLATFORM_DATABASE_URL"

        [providers.openai]
        api_key_env = "OPENAI_API_KEY"
    """), encoding="utf-8")
    loaded = load_property_config(config)
    assert PROPERTY_CONFIG_CONTRACT == "PROPERTY-CONFIG-001"
    assert loaded.property_id == "client"
    assert loaded.origin == "https://client.example"
    assert loaded.environment_references() == ("OPENAI_API_KEY", "RASAI_PLATFORM_DATABASE_URL")
    assert loaded.missing_environment_references({}) == ("OPENAI_API_KEY", "RASAI_PLATFORM_DATABASE_URL")


def test_property_configuration_rejects_inline_secret_fields(tmp_path: Path) -> None:
    config = tmp_path / "unsafe.toml"
    config.write_text(textwrap.dedent("""
        [property]
        id = "unsafe"
        name = "Unsafe"
        origin = "https://unsafe.example"

        [providers.openai]
        api_key = "live-value-93af"
    """), encoding="utf-8")
    with pytest.raises(ValueError, match="inline secret field"):
        load_property_config(config)


def test_versioned_example_is_valid_and_repository_has_no_detected_secret() -> None:
    example = load_property_config(ROOT / "config" / "properties" / "example.toml")
    assert example.property_id == "example"
    assert scan_repository(ROOT) == ()
