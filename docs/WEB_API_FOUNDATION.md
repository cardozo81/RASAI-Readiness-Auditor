# Fundação Web/API do RASAi

## Objetivo

A camada Web/API expõe o control plane do RASAi para aplicações Web e integrações sem mover crawling, scoring ou regra de auditoria para o processo HTTP.

A arquitetura vigente é:

```text
Browser / API client
  |
Identity & Access
  |-- OIDC/JWT
  |-- trusted-header controlado
  |
Web UI (/app e /app/operations)
  |
RASAi API tenant-aware
  |
Control plane
  |-- SQLite local
  |-- PostgreSQL centralizado
  |
Execution jobs / schedules
  |
Workers
  |
Audit / Search Monitoring / report refresh
```

O processo HTTP não executa crawling ou auditoria dentro da requisição. Operações de execução criam jobs duráveis; workers separados reivindicam e executam o trabalho autorizado.

## Dependências opcionais

Instalação local sem Web/API:

```powershell
pip install -e .
```

Para API, UI Web e OIDC/JWT:

```powershell
pip install -e ".[web]"
```

PostgreSQL é opcional separadamente por `.[postgresql]`.

## Inicialização

```powershell
rasai api --host 127.0.0.1 --port 8000
```

O bind padrão é loopback. Bind público exige `--allow-public-bind` e infraestrutura externa adequada de TLS, firewall, reverse proxy e gestão de secrets.

Superfícies principais:

```text
/app                  UI Web do RASAi
/app/operations       scheduling e consumo
/auth/...             identidade OIDC quando configurada
/health/live          liveness do processo
/health/ready         readiness do control plane
/api/v1/...           API tenant-aware
```

A documentação OpenAPI fica desabilitada por default. `RASAI_API_DOCS_ENABLED=true` habilita `/docs` e `/openapi.json` para ambiente controlado.

## Autenticação

O RASAi não mantém banco próprio de senhas nem define formato proprietário de bearer token.

`RASAI_API_AUTH_MODE`:

| Modo | Uso | Comportamento |
|---|---|---|
| `deny` | default fail-closed | endpoints protegidos respondem indisponibilidade de autenticação |
| `trusted-header` | desenvolvimento local ou gateway autenticado | lê o header configurado somente em fronteira confiável |
| `oidc` | Web/SaaS | valida OIDC/JWT e sessão Web |

### OIDC/JWT

No modo `oidc`, o RASAi:

- descobre metadata OIDC por issuer HTTPS;
- usa Authorization Code + PKCE S256 no login Web;
- valida `state` e `nonce`;
- valida assinatura JWT por JWKS;
- valida `iss`, `aud`, `exp` e `sub`;
- permite somente algoritmos assimétricos configurados;
- atualiza JWKS quando necessário para rotação de `kid`;
- cria sessão Web curta cifrada/autenticada;
- não persiste access token, ID token ou refresh token;
- resolve `(issuer, sub)` para um `USR-*` provisionado no control plane.

Autenticação válida não cria usuário, membership ou role automaticamente.

Configuração completa: [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

### trusted-header

```text
RASAI_API_AUTH_MODE=trusted-header
RASAI_API_TRUSTED_USER_HEADER=x-rasai-user-id
```

Esse modo só é apropriado quando um gateway autenticado remove o header enviado pelo cliente, autentica a requisição, injeta a identidade confiável e impede acesso direto ao processo RASAi. Em uso humano local estritamente em loopback, a UI pode usar um `USR-*` existente para smoke controlado. Isso não constitui autenticação pública.

Não existe fallback automático de `oidc` para `trusted-header`.

## Tenancy e autorização

A autenticação termina em `Principal(user_id)`. A autorização é revalidada contra memberships e escopo do control plane:

```text
Organization
  -> Workspace
     -> Project
        -> Property
           -> Environment
```

| Role | Ler projeto | Criar job | Gerenciar execução/schedule |
|---|---:|---:|---:|
| OWNER | Sim | Sim | Sim |
| ADMIN | Sim | Sim | Sim |
| ANALYST | Sim | Sim | Não |
| OPERATOR | Sim | Sim | Sim |
| VIEWER | Sim | Não | Não |
| INTEGRATION_MANAGER | Sim quando membro | Não | Não |
| BILLING | Sim quando membro | Não | Não |

Conhecer um ID não concede acesso ao recurso.

## Catálogo de endpoints

### Health e identidade

| Método | Endpoint | Finalidade | Autenticação |
|---|---|---|---|
| `GET` | `/health/live` | confirma que o processo API está vivo | pública |
| `GET` | `/health/ready` | valida acesso ao control plane e retorna health sanitizado | pública |
| `GET` | `/auth/config` | informa modo de autenticação e disponibilidade de browser login | pública |
| `GET` | `/auth/login` | inicia Authorization Code + PKCE | somente com OIDC |
| `GET` | `/auth/callback` | valida retorno OIDC e cria sessão | somente com OIDC |
| `POST` | `/auth/logout` | encerra sessão Web | somente com OIDC |
| `GET` | `/api/v1/me` | retorna usuário interno, memberships e escopos acessíveis | protegida |

### Portfólio e tenancy

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/organizations` | organizações acessíveis ao principal |
| `GET` | `/api/v1/organizations/{organization_id}/workspaces` | workspaces autorizados da organização |
| `GET` | `/api/v1/workspaces/{workspace_id}/projects` | projetos autorizados do workspace |
| `GET` | `/api/v1/projects/{project_id}/properties` | properties do projeto |
| `GET` | `/api/v1/properties/{property_id}/environments` | environments da property |

Todas revalidam tenancy no servidor.

### Auditorias e relatórios

| Método | Endpoint | Finalidade / limite |
|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/audits` | catálogo de AUDs do projeto sem expor `workspace_path` interno |
| `GET` | `/api/v1/audits/{audit_id}/reports` | lista arquivos canônicos existentes sob `report/` do AUD autorizado |
| `GET` | `/api/v1/audits/{audit_id}/reports/{asset_path}` | serve somente asset permitido dentro da árvore pública `report/` |

Extensões permitidas no boundary de reports:

```text
.html .css .js .json .svg .png .jpg .jpeg .webp .ico
```

O endpoint rejeita path absoluto, `..`, saída do diretório resolvido e extensões fora da allowlist. `audit.db` e artifacts privados não são servidos por essa rota.

### Search Intelligence

| Método | Endpoint | Finalidade / limite |
|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/search-queries` | lista queries do projeto; `enabled_only` pode filtrar habilitadas |
| `GET` | `/api/v1/search-queries/{query_id}/runs` | histórico da query; `limit` default `20`, permitido `1..200` |

### Milestones e comparação de deployment

| Método | Endpoint | Finalidade / valores |
|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/milestones` | lista milestones autorizados |
| `GET` | `/api/v1/milestones/{milestone_id}/deployment-pair` | resolve par para comparação; `baseline_mode=AUTO|GOLDEN`, default `AUTO` |

### Execution jobs

| Método | Endpoint | Finalidade / limite |
|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/execution-jobs` | lista jobs; `limit` default `100`, permitido `1..1000` |
| `POST` | `/api/v1/projects/{project_id}/execution-jobs` | cria job durável e retorna `202` |
| `GET` | `/api/v1/execution-jobs/{job_id}` | consulta job autorizado |
| `POST` | `/api/v1/execution-jobs/{job_id}/cancel` | solicita cancelamento quando permitido |

Payload de criação:

| Campo | Obrigatório | Default | Valores/limites | Finalidade |
|---|---:|---|---|---|
| `property_id` | Sim | - | texto `1..200` | property do job |
| `environment_id` | Sim | - | texto `1..200` | environment do job |
| `job_type` | Sim | - | `AUDIT`, `SEARCH_MONITOR`, `REPORT_REFRESH` | handler permitido |
| `payload` | Não | `{}` | objeto estruturado | opções específicas do job; credenciais inline não são aceitas |
| `source_audit_id` | Não | `null` | texto `5..200`; somente `AUDIT` | reutilização/reprocessamento permitido pelo contrato |
| `idempotency_key` | Não | `null` | texto até 200 | evita duplicação lógica no mesmo projeto |
| `priority` | Não | `100` | inteiro `0..1000` | prioridade de fila |
| `max_attempts` | Não | `3` | inteiro `1..100` | limite de tentativas do job |

Para `AUDIT`, o servidor rejeita provenance controlada pelo cliente e recompõe dados server-managed quando necessário. `source_audit_id` é inválido para outros tipos de job.

Estados de execução:

```text
QUEUED
CLAIMED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

### Opções de auditoria

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/audit-job-options` | retorna catálogo de opções e defaults do contrato de AuditJob usado pelo SaaS |

Essa rota exige principal autenticado, mas não retorna valores de segredo.

### Previsão de custo antes da execução

| Método | Endpoint | Finalidade |
|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/execution-cost-estimate` | estima custo monetário com base no usage ledger e configuração solicitada |

Payload:

```text
property_id      obrigatório
 environment_id obrigatório
 job_type        AUDIT por default; aceita AUDIT, SEARCH_MONITOR, REPORT_REFRESH
 payload         objeto, default {}
```

O estimador monetário canônico dessa rota está disponível para `AUDIT`. Para outros tipos, a resposta informa `available=false`, `show_confirmation=false` e confiança `NENHUMA`, sem inventar custo.

A rota exige a mesma permissão usada para criação de execução e valida que Project, Property e Environment pertencem ao escopo informado.

### Scheduling Management

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/schedules` | lista schedules com filtros e paginação |
| `POST` | `/api/v1/projects/{project_id}/schedules` | cria schedule |
| `GET` | `/api/v1/schedules/{schedule_id}` | consulta schedule |
| `PATCH` | `/api/v1/schedules/{schedule_id}` | altera campos permitidos |
| `POST` | `/api/v1/schedules/{schedule_id}/pause` | muda estado para `PAUSED` |
| `POST` | `/api/v1/schedules/{schedule_id}/resume` | muda estado para `ACTIVE` |
| `DELETE` | `/api/v1/schedules/{schedule_id}` | desabilita schedule, estado `DISABLED` |
| `POST` | `/api/v1/schedules/{schedule_id}/duplicate` | duplica com novo nome |
| `GET` | `/api/v1/schedules/{schedule_id}/runs` | histórico de runs; `limit` default `100`, `1..1000` |
| `GET` | `/api/v1/schedules/{schedule_id}/events` | eventos do schedule; `limit` default `100`, `1..1000` |
| `GET` | `/api/v1/schedules/{schedule_id}/next-occurrences` | próximas ocorrências; `count` default `10`, `1..100` |

Filtros de listagem:

```text
property_id
 environment_id
 state=<repetível>
 limit=200, permitido 1..1000
 offset=0, inteiro >= 0
```

Contrato de criação de schedule:

| Campo | Default | Valores/limites |
|---|---|---|
| `property_id` | obrigatório | texto `1..200` |
| `environment_id` | obrigatório | texto `1..200` |
| `name` | obrigatório | texto `1..200` |
| `job_type` | `AUDIT` | `AUDIT`, `SEARCH_MONITOR`, `REPORT_REFRESH` |
| `timezone` | obrigatório | texto `1..200`; validação temporal pertence ao store/contrato de schedule |
| `urls` | `[]` | até 5000 itens |
| `payload` | `{}` | objeto estruturado |
| `overlap_policy` | `SKIP` | `SKIP`, `QUEUE` |
| `priority` | `100` | `0..1000` |
| `max_attempts` | `3` | `1..100` |

Recorrência:

| Campo | Default | Valores/limites |
|---|---|---|
| `times` | `[]` | até 48 horários |
| `every_minutes` | `null` | `60..44640` quando definido |
| `window_start` | `00:00` | horário aceito pelo contrato de schedule |
| `window_end` | `23:59` | horário aceito pelo contrato de schedule |
| `weekdays` | `[]` | até 7 valores |
| `month_days` | `[]` | até 31 valores |
| `last_day` | `false` | booleano |

Criação, alteração, pause/resume, disable e duplicação exigem permissão de gerenciamento de execução. Leitura exige acesso ao projeto.

### Usage e Consumption Analytics

Há duas projeções distintas:

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/usage` | resumo de uso da organização |
| `GET` | `/api/v1/organizations/{organization_id}/consumption` | analytics filtrável e agrupável sobre o usage ledger |

Filtros disponíveis em `consumption`:

```text
workspace_id
project_id
property_id
environment_id
domain
url
user_id
job_type
provider
integration
category
operation
event_status
model
resource_type
job_id
audit_id
period
timezone
start
end
group_by
limit
```

`limit` tem default `10000` e aceita `1..50000`.

`group_by` tem default:

```text
category,provider
```

Quando `period` é usado, `start` e `end` não podem ser informados simultaneamente. A resolução temporal usa o timezone informado ou `UTC` quando omitido.

`organization_id`, `workspace_id` e `project_id`, quando fornecidos, são revalidados contra o principal autenticado.

### Catálogo de métricas, padrões e integrações

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/v1/standards/services` | retorna catálogo de serviços, configuração exigida e estado operacional visto pelo processo API |

A resposta inclui nomes de variáveis de credencial/configuração, mas nunca seus valores. Campos de estado incluem:

```text
state
requested
configured
effective_enabled
configuration_source
missing_configuration
```

O endpoint declara `capability_scope=API_PROCESS_ENVIRONMENT_HINT`: worker pode receber secrets por fronteira diferente do processo API. Portanto, `configured=false` na API não deve ser interpretado automaticamente como incapacidade do worker remoto.

## Worker

Execução unitária:

```powershell
rasai worker run-once --worker-id worker-01 --audits-root audits
```

O worker:

1. recupera leases expirados;
2. reivindica job disponível;
3. marca o job como `RUNNING`;
4. executa somente handler permitido;
5. persiste resultado ou falha sanitizada.

Se o lease expira e `attempts < max_attempts`, o job pode retornar a `QUEUED`. Ao esgotar tentativas, torna-se `FAILED`.

Jobs não persistem shell command ou `argv` arbitrário. O worker constrói internamente a execução canônica a partir de payload estruturado e contexto autorizado.

## Segurança de sessão e CSRF

Sessão OIDC contém somente identidade externa mínima e metadados temporais cifrados/autenticados. Cookies são `HttpOnly` e `SameSite=Lax`; em implantação HTTPS também recebem `Secure`.

Operação mutável autenticada por cookie exige `Origin` correspondente à origem configurada no redirect OIDC. Bearer JWT não depende do cookie e não usa essa verificação de origem.

## PostgreSQL e migrations

Execution jobs e Identity & Access usam extensões de schema controladas pelo produto. Em PostgreSQL, aplicação de migrations é explícita:

```powershell
rasai platform database migrate
```

Startup da API ou worker não aplica DDL automaticamente.

SQLite continua válido para operação local sem FastAPI, Uvicorn, Psycopg, Docker ou servidor PostgreSQL.

## Secrets

Nenhum endpoint, exception handler, job, worker ou tela deve expor:

- API keys;
- tokens;
- passwords;
- DSNs com senha;
- Authorization headers;
- cookies de sessão;
- private keys;
- webhook secrets;
- client secrets;
- session secrets.

Payloads, resultados e erros passam pela política de redaction antes de persistência ou exposição HTTP.

## Limites do contrato Web/SaaS atual

O código não define como capacidade operacional completa:

- Identity Provider obrigatório;
- SCIM;
- Just-In-Time provisioning;
- SAML direto;
- cobrança/faturamento completo;
- object storage definitivo;
- Kubernetes obrigatório;
- multi-região;
- fila externa obrigatória;
- migração de `AUD-*/audit.db` para PostgreSQL;
- design system/frontend definitivo.

Os protótipos em `../prototypes/` podem representar contratos desejados além dessas superfícies. Tais contratos não são endpoints disponíveis até existirem no runtime da API.
