"""Runtime adaptation of the zero-build pilot shell for auth and service contracts."""
from __future__ import annotations

from html import escape
import re

from rasai.provider_registry import provider_registrations

from .ui import PILOT_UI_HTML


def _provider_options_html() -> str:
    """Project the canonical provider registry into the pilot audit selector."""

    choices = [("none", "Sem IA"), ("auto", "Auto")]
    choices.extend((registration.id, registration.display_name) for registration in provider_registrations())
    return "".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in choices
    )


def _align_provider_selector(html: str) -> str:
    """Remove the static provider-list drift from the zero-build base asset."""

    return re.sub(
        r'<select id="audit-ai">.*?</select>',
        f'<select id="audit-ai">{_provider_options_html()}</select>',
        html,
        count=1,
        flags=re.DOTALL,
    )


def _align_standards_surface(html: str) -> str:
    """Project standards-service AUTO semantics and capability visibility into the pilot.

    Credential-driven services are AUTO when their payload field is omitted/null. The
    base pilot used to force the aggregate Web Performance control to ``false`` on every
    job, which prevented worker credentials from activating PageSpeed/CrUX. The runtime
    adapter preserves explicit ON/OFF while making omission the default.
    """

    html = html.replace(
        '<select id="audit-performance"><option value="false">Não</option><option value="true">Sim</option></select>',
        '<select id="audit-performance"><option value="auto">Auto por serviços/requisitos</option><option value="false">Desligado</option><option value="true">Ligado agregado</option></select>',
        1,
    )
    html = html.replace(
        "const state={me:null,organizations:[],workspaces:[],projects:[],properties:[],environments:[],audits:[],queries:[],jobs:[],milestones:[],usage:[],auditDefaults:{}};",
        "const state={me:null,organizations:[],workspaces:[],projects:[],properties:[],environments:[],audits:[],queries:[],jobs:[],milestones:[],usage:[],auditDefaults:{},standardServices:[]};",
        1,
    )
    html = html.replace(
        "function resetAuditConfig(){if($('audit-config'))$('audit-config').value=JSON.stringify(state.auditDefaults||{},null,2)}",
        "function defaultAuditConfig(){const config={...(state.auditDefaults||{})};delete config.web_performance;for(const s of state.standardServices||[]){if(s.job_field)delete config[s.job_field]}return config}function resetAuditConfig(){if($('audit-config'))$('audit-config').value=JSON.stringify(defaultAuditConfig(),null,2)}",
        1,
    )
    html = html.replace(
        "const [organizations,contract]=await Promise.all([api('/api/v1/organizations'),api('/api/v1/audit-job-options')]);state.organizations=organizations;state.auditDefaults=contract.defaults||{};",
        "const [organizations,contract,standards]=await Promise.all([api('/api/v1/organizations'),api('/api/v1/audit-job-options'),api('/api/v1/standards/services')]);state.organizations=organizations;state.auditDefaults=contract.defaults||{};state.standardServices=standards.services||[];",
        1,
    )
    html = html.replace(
        '  </section>\n\n  <section class="panel" id="panel-audits">',
        '    <div class="card" style="margin-top:14px"><h2>Serviços de métricas e padrões</h2><p class="muted">Estado do processo API. Workers podem possuir credenciais próprias; valores secretos nunca são exibidos. O controle altera apenas o AuditJob em edição.</p><div id="standards-table"></div></div>\n  </section>\n\n  <section class="panel" id="panel-audits">',
        1,
    )
    controls = (
        "function auditConfigObject(){try{return JSON.parse($('audit-config').value||'{}')}catch(err){throw new Error('Configuração JSON inválida: '+err.message)}}\n"
        "function serviceConfigMode(field){if(!field)return'default';try{const cfg=auditConfigObject();if(!(field in cfg)||cfg[field]===null)return'default';return cfg[field]===true?'true':'false'}catch(_){return'default'}}\n"
        "function setServiceMode(field,mode){if(!field)return;try{const cfg=auditConfigObject();if(mode==='default')delete cfg[field];else cfg[field]=mode==='true';$('audit-config').value=JSON.stringify(cfg,null,2);renderStandards()}catch(err){toast(err.message,'bad')}}\n"
    )
    render_function = (
        "function renderStandards(){const rows=(state.standardServices||[]).map(s=>{const mode=serviceConfigMode(s.job_field);const autoLabel=s.auto_enable_with_credentials?'Auto':'Padrão';const control=s.job_field?`<select onchange=\"setServiceMode('${esc(s.job_field)}',this.value)\"><option value=\"default\" ${mode==='default'?'selected':''}>${autoLabel}</option><option value=\"true\" ${mode==='true'?'selected':''}>Ligado</option><option value=\"false\" ${mode==='false'?'selected':''}>Desligado</option></select>`:'-';return `<tr><td><strong>${esc(s.label)}</strong><br><span class=\"muted\">${esc(s.purpose||'')}</span></td><td>${esc((s.relation_degree||'-')+'/5')}</td><td>${esc((s.scopes||[]).join(', '))}</td><td>${pill(s.state)}</td><td>${esc((s.missing_configuration||[]).join(', ')||'-')}</td><td>${control}</td></tr>`});$('standards-table').innerHTML=table(['Serviço','Relação','Escopo','Estado','Configuração ausente','Controle do job'],rows)}\n"
    )
    html = html.replace("function renderAll(){", controls + render_function + "function renderAll(){", 1)
    html = html.replace("renderMilestones();renderUsage();$('overview-state')", "renderMilestones();renderUsage();renderStandards();$('overview-state')", 1)
    html = html.replace(
        "const klass=['SUCCEEDED','PASS','COMPLETED','SUCCESS','ACTIVE'].includes(s)?'good':['FAILED','FAIL','ERROR','CANCELLED'].includes(s)?'bad':['QUEUED','CLAIMED','RUNNING','PARTIAL'].includes(s)?'wait':'';",
        "const klass=['SUCCEEDED','PASS','COMPLETED','SUCCESS','ACTIVE','READY'].includes(s)?'good':['FAILED','FAIL','ERROR','CANCELLED'].includes(s)?'bad':['QUEUED','CLAIMED','RUNNING','PARTIAL','NOT_CONFIGURED'].includes(s)?'wait':'';",
        1,
    )
    old_queue = "auditConfig={...auditConfig,max_pages:Number($('audit-max-pages').value||100),device_context:$('audit-device').value,ai_provider:$('audit-ai').value,web_performance:$('audit-performance').value==='true'};"
    new_queue = "auditConfig={...auditConfig,max_pages:Number($('audit-max-pages').value||100),device_context:$('audit-device').value,ai_provider:$('audit-ai').value};const performanceMode=$('audit-performance').value;if(performanceMode==='auto'){delete auditConfig.web_performance}else{auditConfig.web_performance=performanceMode==='true'};"
    html = html.replace(old_queue, new_queue, 1)
    return html


def render_pilot_ui(auth_mode: str) -> str:
    """Return the pilot shell aligned to provider, service and authentication contracts."""

    html = _align_standards_surface(_align_provider_selector(PILOT_UI_HTML))
    if auth_mode != "oidc":
        return html
    html = html.replace(
        "const state=",
        "sessionStorage.removeItem('rasai-dev-user');\nconst state=",
        1,
    )
    return re.sub(
        r"function renderDevLogin\(err\)\{.*?\}\nasync function chooseOrganization",
        "function renderDevLogin(err){sessionStorage.removeItem('rasai-dev-user');location.assign('/auth/login')}\nasync function chooseOrganization",
        html,
        count=1,
        flags=re.DOTALL,
    )
