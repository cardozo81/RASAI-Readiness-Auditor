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
    return re.sub(
        r'<select id="audit-ai">.*?</select>',
        f'<select id="audit-ai">{_provider_options_html()}</select>',
        html,
        count=1,
        flags=re.DOTALL,
    )


def _guided_configuration_html() -> str:
    return (
        '<div class="full guided-config">'
        '<div class="guided-head"><div><strong>Configuração guiada de métricas e integrações</strong>'
        '<div class="muted">Parâmetros não secretos do AuditJob. Secrets são resolvidos no worker/deployment e nunca são digitados aqui.</div></div>'
        '<span class="pill">sem secrets</span></div>'
        '<div class="guided-grid">'
        '<label>Máximo de URLs para padrões<input id="cfg-standards-max-urls" data-config-field="standards_max_urls" data-config-type="number" type="number" min="0" max="100000"><span>W3C/GSC bounded; 0 = todas as URLs auditadas.</span></label>'
        '<label>Timeout de padrões (s)<input id="cfg-standards-timeout" data-config-field="standards_timeout_seconds" data-config-type="number" type="number" min="1" max="3599" step="1"><span>Timeout por request externo desta família.</span></label>'
        '<label class="full">Property Google Search Console<input id="cfg-gsc-site" data-config-field="gsc_site_url" data-config-type="text" placeholder="sc-domain:example.com ou https://www.example.com/"><span>Não é segredo. Necessária para GSC AUTO/ligado; o OAuth token fica somente no worker/secret store.</span></label>'
        '<label>Dias de Search Analytics<input id="cfg-gsc-days" data-config-field="gsc_search_analytics_days" data-config-type="number" type="number" min="0" max="31"><span>0 desliga somente Search Analytics.</span></label>'
        '<label>Máximo de linhas GSC<input id="cfg-gsc-rows" data-config-field="gsc_search_max_rows" data-config-type="number" type="number" min="1" max="50000"><span>Teto de returned rows persistidas por auditoria.</span></label>'
        '<label>Defasagem de dados finais (dias)<input id="cfg-gsc-lag" data-config-field="gsc_final_data_lag_days" data-config-type="number" type="number" min="0" max="30"><span>Janela para preferir dados Search Analytics finalizados.</span></label>'
        '<div class="guided-note"><strong>Como funciona:</strong> mantenha serviços em <em>Auto/Padrão</em> para usar o registry. Use <em>Ligado</em> ou <em>Desligado</em> apenas para override explícito. PageSpeed/CrUX/GSC mostram requisitos ausentes na tabela abaixo.</div>'
        '</div>'
        '<details class="advanced-config"><summary>Configuração avançada do AuditJob (JSON)</summary>'
        '<p class="muted">Use somente para parâmetros que ainda não possuem controle visual. Alterações válidas são sincronizadas com os campos guiados.</p>'
        '<textarea id="audit-config" rows="16" class="mono"></textarea></details>'
        '</div>'
    )


def _align_standards_surface(html: str) -> str:
    """Project standards AUTO semantics, guided job config and capability visibility."""
    html = html.replace(
        '<select id="audit-performance"><option value="false">Não</option><option value="true">Sim</option></select>',
        '<select id="audit-performance"><option value="auto">Auto por serviços/requisitos</option><option value="false">Desligado</option><option value="true">Ligado agregado</option></select>',
        1,
    )
    html = html.replace(
        "</style>",
        ".guided-config{border:1px solid #dbe3ef;border-radius:10px;padding:12px;background:#fbfcfe}.guided-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.guided-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.guided-grid label{display:grid;gap:5px;font-size:.76rem;color:#667085}.guided-grid input{width:100%;border:1px solid #d0d5dd;background:#fff;border-radius:8px;padding:8px 9px;color:#172033}.guided-grid .full,.guided-note{grid-column:1/-1}.guided-note{padding:10px 12px;border-radius:8px;background:#eff6ff;color:#1e3a8a;font-size:.78rem}.advanced-config{margin-top:12px;border-top:1px solid #e4e7ec;padding-top:10px}.advanced-config summary{cursor:pointer;font-weight:650}.advanced-config textarea{width:100%;margin-top:8px;border:1px solid #d0d5dd;border-radius:8px;padding:8px}.service-help{font-size:.72rem;color:#667085;max-width:320px}@media(max-width:760px){.guided-grid{grid-template-columns:1fr}.guided-grid .full,.guided-note{grid-column:auto}}</style>",
        1,
    )
    html = html.replace(
        '<label class="full">Configuração AUDIT completa (JSON, sem credenciais)<textarea id="audit-config" rows="16" class="mono"></textarea><span>Carregada do contrato canônico; inclui Lighthouse, Apdex, Experience Apdex, IA e contexto de conteúdo.</span></label>',
        _guided_configuration_html(),
        1,
    )
    html = html.replace(
        "const state={me:null,organizations:[],workspaces:[],projects:[],properties:[],environments:[],audits:[],queries:[],jobs:[],milestones:[],usage:[],auditDefaults:{}};",
        "const state={me:null,organizations:[],workspaces:[],projects:[],properties:[],environments:[],audits:[],queries:[],jobs:[],milestones:[],usage:[],auditDefaults:{},standardServices:[]};",
        1,
    )
    html = html.replace(
        "function resetAuditConfig(){if($('audit-config'))$('audit-config').value=JSON.stringify(state.auditDefaults||{},null,2)}",
        "function defaultAuditConfig(){const config={...(state.auditDefaults||{})};delete config.web_performance;for(const s of state.standardServices||[]){if(s.job_field)delete config[s.job_field]}return config}function resetAuditConfig(){if($('audit-config')){$('audit-config').value=JSON.stringify(defaultAuditConfig(),null,2);syncGuidedFromJson()}}",
        1,
    )
    html = html.replace(
        "const [organizations,contract]=await Promise.all([api('/api/v1/organizations'),api('/api/v1/audit-job-options')]);state.organizations=organizations;state.auditDefaults=contract.defaults||{};",
        "const [organizations,contract,standards]=await Promise.all([api('/api/v1/organizations'),api('/api/v1/audit-job-options'),api('/api/v1/standards/services')]);state.organizations=organizations;state.auditDefaults=contract.defaults||{};state.standardServices=standards.services||[];",
        1,
    )
    html = html.replace(
        '  </section>\n\n  <section class="panel" id="panel-audits">',
        '    <div class="card" style="margin-top:14px"><h2>Serviços de métricas e padrões</h2><p class="muted">O estado mostra a capacidade do deployment. Workers podem possuir credenciais próprias; valores secretos nunca são exibidos nem entram no AuditJob. O controle abaixo vale somente para o job em edição.</p><div class="notice">Use <strong>Padrão/Auto</strong> na operação normal. <strong>Ligado</strong> força a solicitação (ainda exige requisitos) e <strong>Desligado</strong> é hard-off explícito.</div><div id="standards-table"></div></div>\n  </section>\n\n  <section class="panel" id="panel-audits">',
        1,
    )
    controls = (
        "function auditConfigObject(){try{const v=JSON.parse($('audit-config').value||'{}');if(!v||Array.isArray(v)||typeof v!=='object')throw new Error('deve ser objeto');return v}catch(err){throw new Error('Configuração JSON inválida: '+err.message)}}\n"
        "function configValue(name,fallback=''){try{const cfg=auditConfigObject();return Object.prototype.hasOwnProperty.call(cfg,name)?cfg[name]:fallback}catch(_){return fallback}}\n"
        "function syncGuidedFromJson(){if(!$('audit-config'))return;let cfg;try{cfg=auditConfigObject()}catch(_){return}document.querySelectorAll('[data-config-field]').forEach(el=>{const name=el.dataset.configField;const fallback=(state.auditDefaults||{})[name];const value=Object.prototype.hasOwnProperty.call(cfg,name)?cfg[name]:fallback;el.value=value==null?'':String(value)})}\n"
        "function setGuidedField(el){try{const cfg=auditConfigObject();const name=el.dataset.configField;const type=el.dataset.configType||'text';const raw=String(el.value??'').trim();if(type==='number'){if(raw==='')delete cfg[name];else{const n=Number(raw);if(!Number.isFinite(n))throw new Error(name+' deve ser numérico');cfg[name]=n}}else{if(raw==='')delete cfg[name];else cfg[name]=raw}$('audit-config').value=JSON.stringify(cfg,null,2);renderStandards()}catch(err){message(err.message,'error')}}\n"
        "function serviceConfigMode(field){if(!field)return'default';try{const cfg=auditConfigObject();if(!(field in cfg)||cfg[field]===null)return'default';return cfg[field]===true?'true':'false'}catch(_){return'default'}}\n"
        "function setServiceMode(field,mode){if(!field)return;try{const cfg=auditConfigObject();if(field==='gsc_enabled'&&mode==='true'&&!String(cfg.gsc_site_url||'').trim()){message('Para ligar GSC explicitamente, informe a property na configuração guiada.','error');return}if(mode==='default')delete cfg[field];else cfg[field]=mode==='true';$('audit-config').value=JSON.stringify(cfg,null,2);renderStandards()}catch(err){message(err.message,'error')}}\n"
        "function bindGuidedConfig(){document.querySelectorAll('[data-config-field]').forEach(el=>{el.onchange=()=>setGuidedField(el)});if($('audit-config'))$('audit-config').addEventListener('input',()=>syncGuidedFromJson())}\n"
    )
    render_function = (
        "function renderStandards(){const rows=(state.standardServices||[]).map(s=>{const mode=serviceConfigMode(s.job_field);const autoLabel=s.auto_enable_with_credentials?'Auto':'Padrão';const control=s.job_field?`<select aria-label=\"Controle ${esc(s.label)}\" onchange=\"setServiceMode('${esc(s.job_field)}',this.value)\"><option value=\"default\" ${mode==='default'?'selected':''}>${autoLabel}</option><option value=\"true\" ${mode==='true'?'selected':''}>Ligado</option><option value=\"false\" ${mode==='false'?'selected':''}>Desligado</option></select>`:'-';const missing=(s.missing_configuration||[]).join(', ')||'-';const help=s.auto_enable_with_credentials?'AUTO executa quando credencial e contexto obrigatório existem.':'PADRÃO usa a política do registry.';return `<tr><td><strong>${esc(s.label)}</strong><br><span class=\"service-help\">${esc(s.purpose||'')} · ${esc(help)}</span></td><td>${esc((s.relation_degree||'-')+'/5')}</td><td>${esc((s.scopes||[]).join(', '))}</td><td>${pill(s.state)}</td><td>${esc(missing)}</td><td>${control}</td></tr>`});$('standards-table').innerHTML=table(['Serviço','Relação','Escopo','Estado','Configuração ausente','Controle do job'],rows)}\n"
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
    html = html.replace("connect();\n</script>", "bindGuidedConfig();connect();\n</script>", 1)
    return html


def render_pilot_ui(auth_mode: str) -> str:
    """Return the pilot shell aligned to provider, service and authentication contracts."""
    html = _align_standards_surface(_align_provider_selector(PILOT_UI_HTML))
    if auth_mode != "oidc":
        return html
    html = html.replace("const state=", "sessionStorage.removeItem('rasai-dev-user');\nconst state=", 1)
    return re.sub(
        r"function renderDevLogin\(err\)\{.*?\}\nasync function chooseOrganization",
        "function renderDevLogin(err){sessionStorage.removeItem('rasai-dev-user');location.assign('/auth/login')}\nasync function chooseOrganization",
        html,
        count=1,
        flags=re.DOTALL,
    )