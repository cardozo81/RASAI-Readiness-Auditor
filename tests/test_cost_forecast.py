from __future__ import annotations

from types import SimpleNamespace

from rasai.cost_forecast import (
    HistoricalRunCost,
    _forecast_from_runs,
    forecast_saas_cost,
)
from rasai.web.cost_forecast_ui import inject_cost_forecast_ui


def test_forecast_uses_success_baseline_and_all_billable_calls() -> None:
    forecast = _forecast_from_runs(
        (
            HistoricalRunCost("AUD-1", 2, 0.10, 0.14, "USD", 4, 4),
            HistoricalRunCost("AUD-2", 2, 0.12, 0.20, "USD", 5, 5),
            HistoricalRunCost("AUD-3", 2, 0.08, 0.16, "USD", 4, 4),
        ),
        target_pages=4,
        source="test",
    )
    assert forecast.available is True
    assert forecast.show_confirmation is True
    assert forecast.currency == "USD"
    assert forecast.success_baseline == 0.20
    assert forecast.expected == 0.32
    assert forecast.potential >= forecast.likely_high >= forecast.expected
    assert forecast.sample_runs == 3
    assert forecast.confidence == "BAIXA"


def test_forecast_refuses_implicit_currency_conversion() -> None:
    forecast = _forecast_from_runs(
        (
            HistoricalRunCost("AUD-1", 1, 0.1, 0.1, "USD", 1, 1),
            HistoricalRunCost("AUD-2", 1, 0.1, 0.1, "BRL", 1, 1),
        ),
        target_pages=1,
        source="test",
    )
    assert forecast.available is False
    assert forecast.show_confirmation is False
    assert any("múltiplas moedas" in note for note in forecast.notes)


class _FakeStore:
    def __init__(self) -> None:
        self.job = SimpleNamespace(
            job_id="JOB-1",
            job_type="AUDIT",
            property_id="PROP-1",
            environment_id="ENV-1",
            payload={
                "urls": ["https://example.com/a"],
                "max_pages": 10,
                "device_context": "mobile",
                "ai_provider": "openai",
                "ai_model": "gpt-5.6-luna",
                "ai_content_remediation": False,
                "ai_technical_remediation": False,
            },
        )

    def list_execution_jobs(self, *, project_id: str, limit: int):
        assert project_id == "PRJ-1"
        return (self.job,)

    def usage_analytics(self, organization_id: str, **kwargs):
        assert organization_id == "ORG-1"
        if kwargs["category"] == "URL_PROCESSED":
            return {"groups": [{"dimensions": {"audit": "AUD-1", "job": "JOB-1"}, "quantity_by_unit": {"url": 2}}]}
        return {
            "groups": [
                {
                    "dimensions": {"audit": "AUD-1", "job": "JOB-1", "provider": "OPENAI", "model": "gpt-5.6-luna", "status": "SUCCESS", "operation": "SEMANTIC_ANALYSIS"},
                    "event_count": 2,
                    "input_tokens": 2000,
                    "cached_input_tokens": 0,
                    "output_tokens": 500,
                    "reasoning_tokens": 0,
                    "total_tokens": 2500,
                    "cost_by_currency": {"USD": 0.001},
                },
                {
                    "dimensions": {"audit": "AUD-1", "job": "JOB-1", "provider": "OPENAI", "model": "gpt-5.6-luna", "status": "TECHNICAL_ERROR", "operation": "SEMANTIC_ANALYSIS"},
                    "event_count": 1,
                    "input_tokens": 500,
                    "cached_input_tokens": 0,
                    "output_tokens": 100,
                    "reasoning_tokens": 0,
                    "total_tokens": 600,
                    "cost_by_currency": {"USD": 0.0002},
                },
            ]
        }


def test_saas_forecast_uses_tenant_job_configuration_and_target_url_count() -> None:
    forecast = forecast_saas_cost(
        _FakeStore(),
        organization_id="ORG-1",
        project_id="PRJ-1",
        property_id="PROP-1",
        environment_id="ENV-1",
        payload={
            "urls": ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
            "max_pages": 10,
            "device_context": "mobile",
            "ai_provider": "openai",
            "ai_model": "gpt-5.6-luna",
            "ai_content_remediation": False,
            "ai_technical_remediation": False,
        },
    )
    assert forecast.show_confirmation is True
    assert forecast.target_pages == 3
    assert forecast.sample_runs == 1
    assert forecast.expected is not None
    assert forecast.success_baseline is not None
    assert forecast.expected > forecast.success_baseline
    assert forecast.repriced_share == 1.0


def test_pilot_ui_injects_forecast_before_enqueue() -> None:
    html = (
        "<script>async function queueAudit(){"
        "const payload={property_id:propertyId,environment_id:environmentId,job_type:'AUDIT',"
        "payload:auditConfig,idempotency_key:'web-audit-'+Date.now()};"
        "await api(`/api/v1/projects/${encodeURIComponent(projectId)}/execution-jobs`,"
        "{method:'POST'});}</script>"
    )
    rendered = inject_cost_forecast_ui(html)
    assert "execution-cost-estimate" in rendered
    assert "window.confirm(formatCostForecast(forecast))" in rendered
    assert rendered.index("execution-cost-estimate") < rendered.index("/execution-jobs")
