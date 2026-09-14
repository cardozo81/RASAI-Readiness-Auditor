import type { AuditSummary, ClientAccount, ConfigValue, CredentialReference, ExecutionJob, ReportSummary, SaasClientContract, Schedule, UsageEvent, UserIdentity } from '@rasai/prototype-contracts';

const wait = (ms=180) => new Promise(resolve => setTimeout(resolve, ms));
const now = new Date();
const iso = (minutes: number) => new Date(now.getTime() + minutes*60000).toISOString();

const stages = [
  {id:'discovery',label:'Descoberta',status:'done' as const},
  {id:'crawl',label:'Crawling e extração',status:'done' as const,completedUnits:120,totalUnits:120},
  {id:'lighthouse',label:'Lighthouse',status:'done' as const,completedUnits:24,totalUnits:24},
  {id:'crux',label:'CrUX / field data',status:'running' as const,completedUnits:17,totalUnits:24},
  {id:'search',label:'Search Intelligence',status:'pending' as const},
  {id:'ai',label:'Análise IA',status:'pending' as const},
  {id:'reports',label:'Consolidação e relatórios',status:'pending' as const},
];

let runningPercent = 68;
const jobs: ExecutionJob[] = [
  {jobId:'JOB-01982',projectId:'PRJ-PORTAL',propertyId:'PROP-WWW',environmentId:'ENV-PROD',jobType:'AUDIT',title:'Auditoria completa · portal.example',status:'RUNNING',requestedBy:'USR-ANA',origin:'SCHEDULE',priority:100,startedAt:iso(-7),auditId:'AUD-20260913-004',progress:{jobId:'JOB-01982',percent:runningPercent,currentStage:'crux',message:'Coletando dados de campo',stages,updatedAt:iso(0)}},
  {jobId:'JOB-01983',projectId:'PRJ-LOJA',propertyId:'PROP-LOJA',environmentId:'ENV-PROD',jobType:'AUDIT',title:'Auditoria pós-deploy · loja.example',status:'QUEUED',requestedBy:'USR-CARLOS',origin:'MANUAL',priority:120,scheduledFor:iso(-2)},
  {jobId:'JOB-01984',projectId:'PRJ-PORTAL',propertyId:'PROP-WWW',environmentId:'ENV-PROD',jobType:'SEARCH_MONITOR',title:'Monitoramento SERP · marca',status:'QUEUED',requestedBy:'USR-SCHEDULER',origin:'SCHEDULE',priority:100,scheduledFor:iso(-1)},
  {jobId:'JOB-01980',projectId:'PRJ-PORTAL',propertyId:'PROP-WWW',environmentId:'ENV-PROD',jobType:'AUDIT',title:'Auditoria rápida · portal.example',status:'SUCCEEDED',requestedBy:'USR-ANA',origin:'MANUAL',priority:100,startedAt:iso(-190),completedAt:iso(-178),auditId:'AUD-20260913-002'},
  {jobId:'JOB-01979',projectId:'PRJ-LOJA',propertyId:'PROP-LOJA',environmentId:'ENV-PROD',jobType:'AUDIT',title:'Auditoria completa · loja.example',status:'PARTIAL',requestedBy:'USR-MARINA',origin:'SCHEDULE',priority:100,startedAt:iso(-350),completedAt:iso(-331),auditId:'AUD-20260913-001'},
];

const schedules: Schedule[] = [
  {scheduleId:'SCH-1001',projectId:'PRJ-PORTAL',name:'Auditoria completa produção',jobType:'AUDIT',recurrenceLabel:'Seg e Sex · 06:00',timezone:'America/Sao_Paulo',overlapPolicy:'QUEUE',status:'ACTIVE',nextRunAt:iso(740),lastRunStatus:'SUCCESS'},
  {scheduleId:'SCH-1002',projectId:'PRJ-PORTAL',name:'Search Monitor marca',jobType:'SEARCH_MONITOR',recurrenceLabel:'Diário · 07:00',timezone:'America/Sao_Paulo',overlapPolicy:'SKIP',status:'ACTIVE',nextRunAt:iso(840),lastRunStatus:'SUCCESS'},
  {scheduleId:'SCH-1003',projectId:'PRJ-LOJA',name:'Performance mobile',jobType:'AUDIT',recurrenceLabel:'Domingo · 08:30',timezone:'America/Sao_Paulo',overlapPolicy:'QUEUE',status:'PAUSED',nextRunAt:iso(1220),lastRunStatus:'PARTIAL'},
];

const audits: AuditSummary[] = [
  {auditId:'AUD-20260913-004',projectName:'Portal',propertyName:'portal.example',status:'PARTIAL',eventTime:iso(-7),urlCount:120,devices:['mobile','desktop'],sari:81,geo:73,apdex:.89,reports:6},
  {auditId:'AUD-20260913-002',projectName:'Portal',propertyName:'portal.example',status:'SUCCESS',eventTime:iso(-190),urlCount:120,devices:['mobile','desktop'],sari:79,geo:70,apdex:.87,reports:9},
  {auditId:'AUD-20260912-005',projectName:'Loja',propertyName:'loja.example',status:'SUCCESS',eventTime:iso(-1450),urlCount:82,devices:['mobile'],sari:76,geo:68,apdex:.84,reports:9},
  {auditId:'AUD-20260911-003',projectName:'Portal',propertyName:'portal.example',status:'SUCCESS',eventTime:iso(-2900),urlCount:120,devices:['mobile','desktop'],sari:74,geo:64,apdex:.82,reports:9},
];

const credentials: CredentialReference[] = [
  {credentialId:'CRD-USER-OPENAI',label:'Minha OpenAI',provider:'OpenAI',source:'USER_PRIVATE',ownerLabel:'Ana Martins',status:'ACTIVE',configured:true,lastUsedAt:iso(-7)},
  {credentialId:'CRD-PLAT-GEMINI-01',label:'RASAi Gemini Shared #01',provider:'Gemini',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'ACTIVE',configured:true,lastUsedAt:iso(-3),consumers:43},
  {credentialId:'CRD-PLAT-CRUX-01',label:'RASAi CrUX Shared',provider:'Google CrUX',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'ACTIVE',configured:true,lastUsedAt:iso(-11),consumers:28},
  {credentialId:'CRD-ORG-SERP-01',label:'SERP corporativa',provider:'SerpAPI',source:'ORGANIZATION_SHARED',ownerLabel:'ACME Digital',status:'DEGRADED',configured:true,lastUsedAt:iso(-84),consumers:6},
];

const config: ConfigValue[] = [
  {key:'RASAI_DEVICE_CONTEXT',label:'Dispositivos',category:'Auditoria',value:'mobile + desktop',origin:'TEMPLATE',scopeLabel:'Auditoria completa corporativa',overridden:true,secret:false,editable:true},
  {key:'RASAI_AI_PROVIDER',label:'Provider IA',category:'IA',value:'AUTO',origin:'PROJECT',scopeLabel:'Projeto Portal',overridden:false,secret:false,editable:true},
  {key:'RASAI_AI_ANALYSIS_LANGUAGE',label:'Idioma da análise',category:'IA',value:'pt-BR',origin:'SYSTEM',scopeLabel:'Default RASAi',overridden:false,secret:false,editable:true},
  {key:'RASAI_WEB_PERFORMANCE',label:'Web Performance',category:'Performance',value:true,origin:'TEMPLATE',scopeLabel:'Auditoria completa corporativa',overridden:true,secret:false,editable:true},
  {key:'RASAI_WEB_PERFORMANCE_MAX_PAGES',label:'Máx. páginas Web Performance',category:'Performance',value:24,origin:'PROJECT',scopeLabel:'Projeto Portal',overridden:true,secret:false,editable:true},
  {key:'RASAI_PRESENTATION_TIMEZONE',label:'Timezone',category:'Apresentação',value:'America/Sao_Paulo',origin:'ORGANIZATION',scopeLabel:'ACME Digital',overridden:false,secret:false,editable:true},
  {key:'OPENAI_API_KEY',label:'Credencial OpenAI',category:'Credenciais',value:'Configurada · USER_PRIVATE',origin:'JOB',scopeLabel:'Ana Martins',overridden:true,secret:true,editable:true},
];

const clients: ClientAccount[] = [
  {organizationId:'ORG-ACME',name:'ACME Digital',plan:'Enterprise Pilot',users:18,projects:5,activeJobs:3,monthlyPlatformCost:184.32,monthlyBillable:242.10,status:'ACTIVE'},
  {organizationId:'ORG-NOVA',name:'Nova Seguros',plan:'Enterprise',users:32,projects:9,activeJobs:7,monthlyPlatformCost:412.76,monthlyBillable:571.40,status:'ACTIVE'},
  {organizationId:'ORG-VAREJO',name:'Grupo Varejo',plan:'Growth',users:11,projects:3,activeJobs:1,monthlyPlatformCost:96.12,monthlyBillable:131.50,status:'ATTENTION'},
  {organizationId:'ORG-LABS',name:'Labs Commerce',plan:'Pilot',users:5,projects:2,activeJobs:0,monthlyPlatformCost:24.88,monthlyBillable:35.00,status:'ACTIVE'},
];

const usage: UsageEvent[] = [
  {eventId:'USE-9001',organizationId:'ORG-ACME',organizationName:'ACME Digital',userId:'USR-ANA',userName:'Ana Martins',projectId:'PRJ-PORTAL',projectName:'Portal',jobId:'JOB-01982',auditId:'AUD-20260913-004',provider:'OpenAI',model:'gpt-5.6',operation:'SEMANTIC_ANALYSIS',credentialId:'CRD-USER-OPENAI',credentialSource:'USER_PRIVATE',status:'SUCCESS',quantity:1,inputTokens:12800,outputTokens:3100,providerCostEstimate:.112,platformCost:0,billableCost:0,currency:'USD',occurredAt:iso(-6)},
  {eventId:'USE-9002',organizationId:'ORG-ACME',organizationName:'ACME Digital',userId:'USR-ANA',userName:'Ana Martins',projectId:'PRJ-PORTAL',projectName:'Portal',jobId:'JOB-01982',auditId:'AUD-20260913-004',provider:'Gemini',model:'gemini-pro',operation:'FALLBACK_ANALYSIS',credentialId:'CRD-PLAT-GEMINI-01',credentialSource:'PLATFORM_SHARED',status:'SUCCESS',quantity:1,inputTokens:7400,outputTokens:1700,providerCostEstimate:.064,platformCost:.064,billableCost:.081,currency:'USD',occurredAt:iso(-5)},
  {eventId:'USE-9003',organizationId:'ORG-NOVA',organizationName:'Nova Seguros',userId:'USR-LUCAS',userName:'Lucas Reis',projectId:'PRJ-NOVA',projectName:'Institucional',jobId:'JOB-01888',auditId:'AUD-20260913-099',provider:'OpenAI',model:'gpt-5.6',operation:'CONTENT_REMEDIATION',credentialId:'CRD-PLAT-OPENAI-01',credentialSource:'PLATFORM_SHARED',status:'SUCCESS',quantity:1,inputTokens:22300,outputTokens:6300,providerCostEstimate:.194,platformCost:.194,billableCost:.245,currency:'USD',occurredAt:iso(-21)},
  {eventId:'USE-9004',organizationId:'ORG-VAREJO',organizationName:'Grupo Varejo',userId:'USR-BIA',userName:'Beatriz Lima',projectId:'PRJ-STORE',projectName:'E-commerce',jobId:'JOB-01772',auditId:'AUD-20260913-078',provider:'SerpAPI',operation:'SEARCH_MONITOR',credentialId:'CRD-PLAT-SERP-01',credentialSource:'PLATFORM_SHARED',status:'TIMEOUT',quantity:1,providerCostEstimate:.009,platformCost:.009,billableCost:.011,currency:'USD',occurredAt:iso(-54)},
];

const reports: ReportSummary[] = [
 {reportId:'REP-001',auditId:'AUD-20260913-002',name:'Visão consolidada',type:'CONSOLIDATED',status:'READY',generatedAt:iso(-176),source:'CONSOLIDATED'},
 {reportId:'REP-002',auditId:'AUD-20260913-002',name:'Domínio e descoberta',type:'DISCOVERY',status:'READY',generatedAt:iso(-177),source:'CORE'},
 {reportId:'REP-003',auditId:'AUD-20260913-002',name:'Ações e referências',type:'REMEDIATION',status:'READY',generatedAt:iso(-175),source:'AI'},
 {reportId:'REP-004',auditId:'AUD-20260913-004',name:'Web Performance',type:'PERFORMANCE',status:'PARTIAL',generatedAt:iso(-2),source:'CORE'},
];

const platformDefaults: ConfigValue[] = [
  {key:'RASAI_AI_ANALYSIS_LANGUAGE',label:'Idioma padrão de análise',category:'IA',value:'pt-BR',origin:'SYSTEM',scopeLabel:'Plataforma RASAi',overridden:false,secret:false,editable:true},
  {key:'RASAI_DEVICE_CONTEXT',label:'Dispositivo padrão',category:'Auditoria',value:'mobile',origin:'SYSTEM',scopeLabel:'Plataforma RASAi',overridden:false,secret:false,editable:true},
  {key:'RASAI_WEB_PERFORMANCE_MAX_PAGES',label:'Web Performance · páginas',category:'Performance',value:10,origin:'SYSTEM',scopeLabel:'Plataforma RASAi',overridden:false,secret:false,editable:true},
  {key:'RASAI_AI_AUTO_EXCLUDE',label:'Exclusões do pool AUTO',category:'IA',value:'nenhuma',origin:'SYSTEM',scopeLabel:'Plataforma RASAi',overridden:false,secret:false,editable:true},
  {key:'RASAI_REPROCESS_LIVE_VALIDITY_MINUTES',label:'Validade de dados live',category:'Reprocessamento',value:120,origin:'SYSTEM',scopeLabel:'Plataforma RASAi',overridden:false,secret:false,editable:true},
];

const platformCredentials: CredentialReference[] = [
  {credentialId:'CRD-PLAT-OPENAI-01',label:'RASAi OpenAI Shared #01',provider:'OpenAI',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'ACTIVE',configured:true,lastUsedAt:iso(-2),consumers:67},
  {credentialId:'CRD-PLAT-GEMINI-01',label:'RASAi Gemini Shared #01',provider:'Gemini',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'ACTIVE',configured:true,lastUsedAt:iso(-3),consumers:43},
  {credentialId:'CRD-PLAT-CRUX-01',label:'RASAi CrUX Shared',provider:'Google CrUX',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'ACTIVE',configured:true,lastUsedAt:iso(-11),consumers:28},
  {credentialId:'CRD-PLAT-SERP-01',label:'RASAi SERP Shared',provider:'SerpAPI',source:'PLATFORM_SHARED',ownerLabel:'RASAi Platform',status:'DEGRADED',configured:true,lastUsedAt:iso(-54),consumers:19},
];

const user: UserIdentity = {userId:'USR-ANA',name:'Ana Martins',email:'ana@acme.example',role:'ANALYST',organizationName:'ACME Digital'};

function advanceProgress() {
  runningPercent = runningPercent >= 94 ? 68 : runningPercent + 3;
  const running = jobs[0];
  if (running.progress) {
    running.progress.percent = runningPercent;
    running.progress.message = runningPercent < 78 ? 'Coletando dados de campo' : runningPercent < 88 ? 'Executando Search Intelligence' : 'Gerando recomendações e relatórios';
    running.progress.updatedAt = new Date().toISOString();
  }
}

export function createMockSaasClient(): SaasClientContract {
  return {
    async currentUser(){ await wait(); return user; },
    async clientDashboard(){ await wait(); advanceProgress(); return {metrics:[{label:'SARI',value:'81',trend:'+7',tone:'positive',hint:'vs. baseline anterior'},{label:'GEO',value:'73',trend:'+9',tone:'positive',hint:'melhor evolução no período'},{label:'Apdex',value:'0,89',trend:'+0,05',tone:'positive',hint:'experiência calibrada'},{label:'Custo mês',value:'US$ 18,42',trend:'-11%',tone:'info',hint:'somente consumo atribuído ao SaaS'}],jobs:[...jobs],schedules:[...schedules],audits:[...audits]}; },
    async executionJobs(){ await wait(); advanceProgress(); return [...jobs]; },
    async executionJob(id){ await wait(); advanceProgress(); return jobs.find(x=>x.jobId===id); },
    async schedules(){ await wait(); return [...schedules]; },
    async audits(){ await wait(); return [...audits]; },
    async reports(){ await wait(); return [...reports]; },
    async credentials(){ await wait(); return [...credentials]; },
    async effectiveConfig(){ await wait(); return [...config]; },
    async clients(){ await wait(); return [...clients]; },
    async usage(){ await wait(); return [...usage]; },
    async platformCredentials(){ await wait(); return [...platformCredentials]; },
    async platformDefaults(){ await wait(); return [...platformDefaults]; },
  };
}

export const mockSaas = createMockSaasClient();
