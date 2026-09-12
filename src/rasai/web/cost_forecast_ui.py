"""SaaS pilot UI adapter for pre-execution financial cost confirmation."""
from __future__ import annotations

from typing import Any


def inject_cost_forecast_ui(html: str) -> str:
    """Inject a forecast/confirm step into the existing zero-build audit action."""
    formatter = (
        "function formatCostForecast(f){"
        "const money=v=>v==null?'-':`${f.currency||''} ${Number(v).toFixed(6)}`;"
        "const notes=(f.notes||[]).map(x=>`• ${x}`).join('\\n');"
        "return `Estimativa financeira antes da execução\\n\\n"
        "Base histórica: ${f.sample_runs} execução(ões), ${f.sample_calls} chamada(s)\\n"
        "Volume estimado: ${f.target_pages} página(s)\\n"
        "Custo só sucessos: ${money(f.success_baseline)}\\n"
        "Custo esperado: ${money(f.expected)}\\n"
        "Faixa provável: ${money(f.likely_low)} - ${money(f.likely_high)}\\n"
        "Cenário potencial: ${money(f.potential)}\\n"
        "Confiança: ${f.confidence}\\n\\n${notes}\\n\\n"
        "Confirmar e enfileirar a auditoria?`; }"
    )
    if "function formatCostForecast(f)" not in html:
        html = html.replace("async function queueAudit(){", formatter + "\nasync function queueAudit(){", 1)

    needle = (
        "const payload={property_id:propertyId,environment_id:environmentId,job_type:'AUDIT',"
        "payload:auditConfig,idempotency_key:'web-audit-'+Date.now()};"
        "await api(`/api/v1/projects/${encodeURIComponent(projectId)}/execution-jobs`,"
    )
    replacement = (
        "const payload={property_id:propertyId,environment_id:environmentId,job_type:'AUDIT',"
        "payload:auditConfig,idempotency_key:'web-audit-'+Date.now()};"
        "const forecast=await api(`/api/v1/projects/${encodeURIComponent(projectId)}/execution-cost-estimate`,"
        "{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({"
        "property_id:propertyId,environment_id:environmentId,job_type:'AUDIT',payload:auditConfig})});"
        "if(forecast.show_confirmation&&!window.confirm(formatCostForecast(forecast))){"
        "message('Auditoria não iniciada. Revise a configuração e execute novamente quando desejar.');return;}"
        "await api(`/api/v1/projects/${encodeURIComponent(projectId)}/execution-jobs`,"
    )
    return html.replace(needle, replacement, 1)


def install_cost_forecast_ui(app: Any) -> None:
    """Transform only the successful /app HTML response; API and reports are untouched."""
    # Starlette belongs to the optional Web/SaaS dependency profile. Keep the pure HTML
    # transformer importable by the local/minimal runtime and load Response only when
    # an ASGI application actually installs this adapter.
    from starlette.responses import Response

    @app.middleware("http")
    async def cost_forecast_ui_middleware(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path != "/app" or response.status_code != 200:
            return response
        content_type = str(response.headers.get("content-type") or "")
        if "text/html" not in content_type:
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        html = body.decode("utf-8")
        rendered = inject_cost_forecast_ui(html)
        if rendered == html:
            return Response(
                content=body,
                status_code=response.status_code,
                headers={key: value for key, value in response.headers.items() if key.lower() != "content-length"},
                media_type=None,
            )
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-length", "content-type"}
        }
        return Response(
            content=rendered,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
