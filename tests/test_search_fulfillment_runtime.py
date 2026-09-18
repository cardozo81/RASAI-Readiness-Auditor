from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from rasai.audit_fulfillment import list_work_items
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.search_fulfillment_runtime import _configuration, _project


AUDIT_ID = "AUD-SEARCH-FULFILLMENT"


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="search fulfillment"))
    return workspace


def _state(root: Path, **overrides):
    values = {
        "audit_id": AUDIT_ID,
        "audits_root": str(root),
        "search_queries": ("rasai", "search readiness"),
        "search_depth": 20,
        "search_region": "RS",
        "search_device": "mobile",
        "search_competitive": True,
        "search_compare_content": True,
        "search_max_content_pages": 4,
        "search_content_timeout_seconds": 12.5,
        "search_content_max_bytes": 1_500_000,
        "search_content_max_redirects": 2,
        "search_ai_competitive": True,
        "search_ymyl_mode": "ON",
        "ai_provider": "openai",
        "ai_model": "gpt-test",
        "ai_timeout": 60.0,
        "market": "BR",
        "language": "pt-BR",
        "search_last_status": "COMPLETE",
        "search_last_detail": "2 termos observados",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_search_contract_persists_nonsecret_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_SERP_MODE", "live")
    monkeypatch.setenv("RASAI_SERP_PROVIDER", "serpapi")
    monkeypatch.setenv("RASAI_SERP_MAX_REQUESTS", "12")
    monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "secret-value")

    config = _configuration(_state(Path("audits")))

    assert config["mode"] == "live"
    assert config["provider"] == "serpapi"
    assert config["max_requests"] == 12
    assert config["queries"] == ["rasai", "search readiness"]
    assert config["compare_content"] is True
    assert config["max_content_pages"] == 4
    assert config["content_timeout_seconds"] == 12.5
    assert config["content_max_bytes"] == 1_500_000
    assert config["content_max_redirects"] == 2
    assert config["ai_competitive"] is True
    assert config["ymyl_mode"] == "ON"
    assert config["ai_provider"] == "openai"
    assert config["ai_model"] == "gpt-test"
    assert config["ai_timeout_seconds"] == 60.0
    assert "RASAI_SERPAPI_API_KEY" not in config
    assert "secret-value" not in repr(config)


def test_completed_console_search_becomes_required_success_work_item(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root)
        monkeypatch.setenv("RASAI_SERP_MODE", "live")
        monkeypatch.setenv("RASAI_SERP_PROVIDER", "serpapi")

        _project(_state(root))

        item = next(item for item in list_work_items(root / AUDIT_ID, AUDIT_ID) if item.component == "SEARCH_INTELLIGENCE")
        assert item.required is True
        assert item.status == "SUCCESS"
        assert item.attempt_count == 1
        assert item.configuration["queries"] == ["rasai", "search readiness"]
        assert item.configuration["mode"] == "live"
        assert item.configuration["provider"] == "serpapi"
        assert item.effective_result_ref == "search-intelligence:effective"


def test_limited_console_search_is_retryable_and_in_denominator(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root)
        monkeypatch.setenv("RASAI_SERP_MODE", "live")
        monkeypatch.setenv("RASAI_SERP_PROVIDER", "serpapi")

        _project(
            _state(
                root,
                search_last_status="COMPLETE_WITH_LIMITATIONS",
                search_last_detail="provider indisponível",
            )
        )

        item = next(item for item in list_work_items(root / AUDIT_ID, AUDIT_ID) if item.component == "SEARCH_INTELLIGENCE")
        assert item.status == "FAILED_RETRYABLE"
        assert item.last_error_class == "SEARCH_PROVIDER"
        assert item.last_error_code == "SEARCH_INTELLIGENCE_INCOMPLETE"
        assert item.attempt_count == 1
