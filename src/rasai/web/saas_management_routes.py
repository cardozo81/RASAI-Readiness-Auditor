"""Tenant-aware Scheduling Management and Consumption Analytics HTTP surfaces."""
from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from rasai.secret_safety import redact_text, redact_value

from .authz import (
    AuthorizationError,
    Principal,
    accessible_organization_ids,
    require_execution_manage,
    require_project_read,
)


class RecurrenceRequest(BaseModel):
    times: list[str] = Field(default_factory=list, max_length=48)
    every_minutes: int | None = Field(default=None, ge=60, le=44640)
    window_start: str = "00:00"
    window_end: str = "23:59"
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    month_days: list[int] = Field(default_factory=list, max_length=31)
    last_day: bool = False


class ManagedScheduleCreate(BaseModel):
    property_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    job_type: Literal["AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"] = "AUDIT"
    recurrence: RecurrenceRequest
    timezone: str = Field(min_length=1, max_length=200)
    urls: list[str] = Field(default_factory=list, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    overlap_policy: Literal["SKIP", "QUEUE"] = "SKIP"
    priority: int = Field(default=100, ge=0, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=100)


class ManagedSchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    recurrence: RecurrenceRequest | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=200)
    urls: list[str] | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] | None = None
    overlap_policy: Literal["SKIP", "QUEUE"] | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    max_attempts: int | None = Field(default=None, ge=1, le=100)


class DuplicateScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _safe(value: Any) -> Any:
    return redact_value(value)


def _detail(exc: Exception) -> str:
    return redact_text(str(exc))


def _schedule_or_404(store: Any, schedule_id: str) -> dict[str, Any]:
    item = store.get_managed_schedule(schedule_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    return item


def _mutate(call: Callable[[], Any]) -> Any:
    try:
        return _safe(call())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc)) from exc


def install_saas_management_routes(
    app: Any,
    *,
    store_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
) -> None:
    @app.get("/api/v1/projects/{project_id}/schedules")
    def schedules(
        project_id: str,
        property_id: str | None = None,
        environment_id: str | None = None,
        state: list[str] | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        try:
            return list(_safe(store.list_managed_schedules(
                project_id=project_id,
                property_id=property_id,
                environment_id=environment_id,
                statuses=state,
                limit=limit,
                offset=offset,
            )))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc

    @app.post("/api/v1/projects/{project_id}/schedules", status_code=status.HTTP_201_CREATED)
    def create_schedule(
        project_id: str,
        request: ManagedScheduleCreate,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        require_execution_manage(store, principal, project_id)
        data = request.model_dump()
        recurrence = data.pop("recurrence")
        return _mutate(lambda: store.create_managed_schedule(
            project_id=project_id,
            created_by=principal.user_id,
            recurrence=recurrence,
            **data,
        ))

    @app.get("/api/v1/schedules/{schedule_id}")
    def schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return dict(_safe(item))

    @app.patch("/api/v1/schedules/{schedule_id}")
    def patch_schedule(
        schedule_id: str,
        request: ManagedSchedulePatch,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        changes = request.model_dump(exclude_unset=True)
        if "recurrence" in changes and changes["recurrence"] is not None:
            # Pydantic already materializes the nested object as a dict under model_dump.
            changes["recurrence"] = dict(changes["recurrence"])
        return _mutate(lambda: store.update_managed_schedule(
            schedule_id,
            actor_user_id=principal.user_id,
            **changes,
        ))

    @app.post("/api/v1/schedules/{schedule_id}/pause")
    def pause_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "PAUSED", actor_user_id=principal.user_id))

    @app.post("/api/v1/schedules/{schedule_id}/resume")
    def resume_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "ACTIVE", actor_user_id=principal.user_id))

    @app.delete("/api/v1/schedules/{schedule_id}")
    def disable_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "DISABLED", actor_user_id=principal.user_id))

    @app.post("/api/v1/schedules/{schedule_id}/duplicate", status_code=status.HTTP_201_CREATED)
    def duplicate_schedule(
        schedule_id: str,
        request: DuplicateScheduleRequest,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.duplicate_managed_schedule(
            schedule_id, name=request.name, actor_user_id=principal.user_id
        ))

    @app.get("/api/v1/schedules/{schedule_id}/runs")
    def schedule_runs(
        schedule_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return list(_safe(store.list_schedule_runs(schedule_id, limit=limit)))

    @app.get("/api/v1/schedules/{schedule_id}/events")
    def schedule_events(
        schedule_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return list(_safe(store.list_schedule_events(schedule_id, limit=limit)))

    @app.get("/api/v1/schedules/{schedule_id}/next-occurrences")
    def next_schedule_occurrences(
        schedule_id: str,
        count: int = Query(default=10, ge=1, le=100),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return {"schedule_id": schedule_id, "occurrences": list(store.schedule_next_occurrences(schedule_id, count=count))}

    @app.get("/api/v1/organizations/{organization_id}/consumption")
    def consumption(
        organization_id: str,
        project_id: str | None = None,
        property_id: str | None = None,
        environment_id: str | None = None,
        url: str | None = None,
        user_id: str | None = None,
        provider: str | None = None,
        category: str | None = None,
        operation: str | None = None,
        event_status: str | None = None,
        start: str | None = None,
        end: str | None = None,
        group_by: str = "category,provider",
        limit: int = Query(default=10000, ge=1, le=50000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        if organization_id not in accessible_organization_ids(store, principal):
            raise AuthorizationError("organization is outside the caller tenancy scope")
        if project_id:
            require_project_read(store, principal, project_id)
        groups = tuple(item.strip() for item in group_by.split(",") if item.strip())
        try:
            return dict(_safe(store.usage_analytics(
                organization_id,
                project_id=project_id,
                property_id=property_id,
                environment_id=environment_id,
                url=url,
                user_id=user_id,
                provider=provider,
                category=category,
                operation=operation,
                status=event_status,
                start=start,
                end=end,
                group_by=groups,
                limit=limit,
            )))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc

    @app.get("/app/operations", response_class=HTMLResponse, include_in_schema=False)
    def operations_ui() -> HTMLResponse:
        # A dependency-free management surface. Authentication is enforced by every
        # API call, so this shell contains no tenant data or business logic.
        return HTMLResponse(_OPERATIONS_UI, headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        })


_OPERATIONS_UI = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RASAi · Operações SaaS</title><style>
:root{font-family:system-ui,sans-serif;color:#172033;background:#f5f7fa}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1300px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center}.tabs{display:flex;gap:8px;margin:18px 0}.tabs button,.btn{border:1px solid #ccd3dd;background:white;border-radius:8px;padding:8px 11px;cursor:pointer}.btn.primary,.tabs button.active{background:#172033;color:white}.panel{display:none}.panel.active{display:block}.card{background:white;border:1px solid #e1e6ed;border-radius:12px;padding:16px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.grid label{display:grid;gap:5px;font-size:.8rem}input,select,textarea{width:100%;padding:8px;border:1px solid #ccd3dd;border-radius:7px;background:white}.wide{grid-column:span 2}.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.82rem}th,td{padding:9px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}th{background:#f8fafc}.muted{color:#667085}.error{color:#b42318}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric{background:#f8fafc;border-radius:9px;padding:12px}.metric b{display:block;font-size:1.4rem}@media(max-width:800px){.grid,.metrics{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><div class="wrap"><div class="top"><div><h1>Operações SaaS</h1><div class="muted">Scheduling Management e Consumption Analytics</div></div><a href="/app">Voltar ao RASAi</a></div><div id="msg"></div><div class="card grid"><label>Organização<select id="org"></select></label><label>Workspace<select id="ws"></select></label><label>Projeto<select id="project"></select></label><label>Property<select id="property"></select></label><label>Environment<select id="environment"></select></label></div><div class="tabs"><button class="active" data-tab="schedule">Agendamentos</button><button data-tab="usage">Consumo</button></div>
<section id="schedule" class="panel active"><div class="card"><h2>Novo agendamento</h2><div class="grid"><label>Nome<input id="s-name" value="Auditoria recorrente"></label><label>Timezone<input id="s-zone" value="America/Sao_Paulo"></label><label>Horários locais<input id="s-times" value="08:00,18:00"></label><label>Dias semana (1-7)<input id="s-weekdays" value="1,2,3,4,5"></label><label>Dias do mês<input id="s-monthdays" placeholder="1,15"></label><label>Intervalo em minutos<input id="s-every" type="number" min="60" placeholder="ex.: 240"></label><label>Janela inicial<input id="s-start" value="00:00"></label><label>Janela final<input id="s-end" value="23:59"></label><label>Overlap<select id="s-overlap"><option>SKIP</option><option>QUEUE</option></select></label><label class="wide">URLs, uma por linha<textarea id="s-urls" rows="5" placeholder="https://dominio/pagina-a"></textarea></label></div><div class="actions"><button class="btn primary" id="create">Criar schedule</button><button class="btn" id="reload">Atualizar</button></div></div><div class="card"><h2>Schedules</h2><div id="schedules"></div></div></section>
<section id="usage" class="panel"><div class="card"><h2>Consumption Analytics</h2><div class="grid"><label>Início ISO<input id="u-start" placeholder="2026-09-01T00:00:00-03:00"></label><label>Fim ISO<input id="u-end" placeholder="2026-10-01T00:00:00-03:00"></label><label>Provider<input id="u-provider"></label><label>Usuário<input id="u-user" placeholder="USR-..."></label><label class="wide">Agrupar por<input id="u-group" value="property,url,user,provider,category"></label></div><div class="actions"><button class="btn primary" id="usage-load">Consultar</button></div></div><div id="usage-metrics" class="metrics"></div><div class="card"><div id="usage-table"></div></div></section></div><script>
const $=x=>document.getElementById(x),state={};const dev=()=>sessionStorage.getItem('rasai-dev-user')||'';function headers(extra={}){let h={...extra};if(dev())h['x-rasai-user-id']=dev();return h}async function api(path,opt={}){let r=await fetch(path,{...opt,headers:headers(opt.headers||{})});let b;try{b=await r.json()}catch{b={}}if(!r.ok)throw new Error(b.detail||('HTTP '+r.status));return b}function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function msg(v,e=false){$('msg').innerHTML=v?`<p class="${e?'error':''}">${esc(v)}</p>`:''}function opts(id,a,key,label){let el=$(id),old=el.value;el.innerHTML=a.map(x=>`<option value="${esc(x[key])}">${esc(label(x))}</option>`).join('');if(a.some(x=>x[key]===old))el.value=old;return el.value}async function boot(){try{state.orgs=await api('/api/v1/organizations');let o=opts('org',state.orgs,'organization_id',x=>x.name);state.ws=await api(`/api/v1/organizations/${o}/workspaces`);await chooseWs()}catch(e){msg(e.message,true)}}async function chooseWs(){let w=opts('ws',state.ws,'workspace_id',x=>x.name);state.projects=await api(`/api/v1/workspaces/${w}/projects`);await chooseProject()}async function chooseProject(){let p=opts('project',state.projects,'project_id',x=>x.name);state.props=await api(`/api/v1/projects/${p}/properties`);await chooseProp();await loadSchedules()}async function chooseProp(){let p=opts('property',state.props,'property_id',x=>x.name+' · '+x.hostname);state.envs=await api(`/api/v1/properties/${p}/environments`);opts('environment',state.envs,'environment_id',x=>x.name)}function ints(v){return v.split(',').map(x=>x.trim()).filter(Boolean).map(Number)}async function createSchedule(){let body={property_id:$('property').value,environment_id:$('environment').value,name:$('s-name').value,job_type:'AUDIT',timezone:$('s-zone').value,overlap_policy:$('s-overlap').value,urls:$('s-urls').value.split(/\n/).map(x=>x.trim()).filter(Boolean),payload:{max_pages:100,device_context:'both',ai_provider:'none',web_performance:false},recurrence:{times:$('s-times').value.split(',').map(x=>x.trim()).filter(Boolean),weekdays:ints($('s-weekdays').value),month_days:ints($('s-monthdays').value),last_day:false,window_start:$('s-start').value,window_end:$('s-end').value}};let ev=$('s-every').value;if(ev)body.recurrence.every_minutes=Number(ev);try{await api(`/api/v1/projects/${$('project').value}/schedules`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});msg('Agendamento criado.');await loadSchedules()}catch(e){msg(e.message,true)}}async function action(id,a){try{await api(`/api/v1/schedules/${id}/${a}`,{method:'POST'});await loadSchedules()}catch(e){msg(e.message,true)}}async function disable(id){try{await api(`/api/v1/schedules/${id}`,{method:'DELETE'});await loadSchedules()}catch(e){msg(e.message,true)}}async function loadSchedules(){if(!$('project').value)return;let a=await api(`/api/v1/projects/${$('project').value}/schedules`);$('schedules').innerHTML=a.length?`<div class="table"><table><tr><th>Nome</th><th>Status</th><th>Frequência</th><th>Próxima</th><th>URLs</th><th>Ações</th></tr>${a.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.status)}</td><td>${esc(JSON.stringify(x.recurrence))}<br>${esc(x.timezone)}</td><td>${esc(x.next_run_at)}</td><td>${esc(x.urls.length)}</td><td><button onclick="action('${x.schedule_id}','pause')">Pausar</button> <button onclick="action('${x.schedule_id}','resume')">Ativar</button> <button onclick="disable('${x.schedule_id}')">Desativar</button></td></tr>`).join('')}</table></div>`:'<p class="muted">Nenhum schedule.</p>'}async function loadUsage(){let q=new URLSearchParams({group_by:$('u-group').value});if($('project').value)q.set('project_id',$('project').value);if($('property').value)q.set('property_id',$('property').value);if($('environment').value)q.set('environment_id',$('environment').value);if($('u-start').value)q.set('start',$('u-start').value);if($('u-end').value)q.set('end',$('u-end').value);if($('u-provider').value)q.set('provider',$('u-provider').value);if($('u-user').value)q.set('user_id',$('u-user').value);try{let d=await api(`/api/v1/organizations/${$('org').value}/consumption?${q}`),s=d.summary;$('usage-metrics').innerHTML=`<div class="metric">Eventos<b>${s.event_count}</b></div><div class="metric">Falhas<b>${s.failure_count}</b></div><div class="metric">Retries<b>${s.retry_count}</b></div><div class="metric">Tokens<b>${s.total_tokens}</b></div>`;$('usage-table').innerHTML=`<div class="table"><table><tr><th>Dimensões</th><th>Quantidade</th><th>Custo</th><th>Tokens</th><th>Falhas</th></tr>${d.groups.map(x=>`<tr><td>${esc(JSON.stringify(x.dimensions))}</td><td>${esc(JSON.stringify(x.quantity_by_unit))}</td><td>${esc(JSON.stringify(x.cost_by_currency))}${x.cost_unknown_events?' · '+x.cost_unknown_events+' sem custo':''}</td><td>${esc(x.total_tokens)}</td><td>${esc(x.failure_count)}</td></tr>`).join('')}</table></div>`}catch(e){msg(e.message,true)}}document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab))});$('org').onchange=async()=>{state.ws=await api(`/api/v1/organizations/${$('org').value}/workspaces`);await chooseWs()};$('ws').onchange=chooseWs;$('project').onchange=chooseProject;$('property').onchange=chooseProp;$('create').onclick=createSchedule;$('reload').onclick=loadSchedules;$('usage-load').onclick=loadUsage;boot();
</script></body></html>'''
