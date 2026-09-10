# Fundação Web/API do RASAi

## Objetivo

A camada Web/API transforma o control plane já existente em uma superfície utilizável por uma aplicação SaaS sem alterar o motor de auditoria, o índice `SARI-001`, o método `SCORE-GEO-004` ou a natureza imutável dos workspaces `AUD-*`.

A arquitetura atual é:

```text
Web UI zero-build (/app)
  |
RASAi API
  |
Control plane
  |-- SQLite local
  |-- PostgreSQL hospedado
  |
Execution jobs
  |
Workers
  |
Audit / Search Monitoring / report refresh
```

O processo HTTP nunca executa crawling ou auditoria diretamente. Requisições de execução criam jobs duráveis; workers separados reivindicam e executam esses jobs.

A primeira superfície de navegador está documentada em `SAAS_PILOT_WEB.md`. Ela é uma projeção sobre esta API e não redefine contratos de domínio.

## Dependências opcionais

A instalação local padrão não depende da stack Web:

```powershell
pip install -e .
```

Para habilitar API e SaaS Pilot Web:

```powershell
pip install -e ".[web]"
```

A stack opcional inclui FastAPI, Uvicorn e HTTPX. PostgreSQL continua opcional separadamente por `.[postgresql]`.

A UI do piloto não adiciona Node, npm, bundler, CDN ou framework JavaScript obrigatório.

## Inicialização

```powershell
rasai api --host 127.0.0.1 --port 8000
```

Superfícies principais:

```text
/app             SaaS Pilot Web
/health/live     liveness
/health/ready    readiness do control plane
/api/v1/...      API tenant-aware
```

A superfície Web permanece sob o entrypoint público canônico `rasai`; a instalação não adiciona um executável público separado para a API.

O bind padrão é `127.0.0.1`. Um bind fora de loopback exige `--allow-public-bind` e deve ocorrer somente atrás de infraestrutura de autenticação, TLS e reverse proxy/gateway apropriada.

A documentação OpenAPI fica desativada por padrão. Para desenvolvimento controlado:

```text
RASAI_API_DOCS_ENABLED=1
```

## Autenticação

O RASAi não cria um banco próprio de senhas nem um formato proprietário de token.

O modo padrão é:

```text
RASAI_API_AUTH_MODE=deny
```

Nesse estado, endpoints protegidos falham fechado.

A fundação também suporta:

```text
RASAI_API_AUTH_MODE=trusted-header
RASAI_API_TRUSTED_USER_HEADER=x-rasai-user-id
```

`trusted-header` deve ser usado somente quando um gateway/reverse proxy autenticado:

- autentica o usuário;
- remove qualquer header de identidade recebido do cliente externo;
- injeta o header de identidade somente após autenticação bem-sucedida;
- protege o tráfego entre gateway e RASAi;
- impede acesso direto do cliente ao processo Uvicorn.

Sem essas garantias, `trusted-header` não é seguro para exposição pública.

Para smoke humano estritamente local em loopback, `/app` permite manter temporariamente um `USR-*` existente em `sessionStorage` e enviá-lo no trusted header. Essa conveniência é somente de desenvolvimento e não constitui autenticação para ambiente hospedado.

OIDC/JWT pode ser adicionado posteriormente implementando o mesmo resolvedor de principal, sem alterar as regras de tenancy.

## Tenancy e autorização

A fonte de verdade continua sendo o control plane:

```text
Organization
  -> Workspace
     -> Project
        -> Property
           -> Environment
```

A autorização deriva de `memberships`. Um membership pode ser organizacional, limitado a workspace ou limitado a projeto.

Permissões iniciais de execução:

| Role | Ler projeto | Criar job | Cancelar/gerenciar job |
|---|---:|---:|---:|
| OWNER | Sim | Sim | Sim |
| ADMIN | Sim | Sim | Sim |
| ANALYST | Sim | Sim | Não |
| OPERATOR | Sim | Sim | Sim |
| VIEWER | Sim | Não | Não |
| INTEGRATION_MANAGER | Sim quando membro | Não | Não |
| BILLING | Sim quando membro | Não | Não |

A API nunca retorna recursos de outro tenant apenas porque o ID é conhecido pelo cliente.

## Endpoints iniciais

Health:

```text
GET /health/live
GET /health/ready
```

Identidade e portfólio:

```text
GET /api/v1/me
GET /api/v1/organizations
GET /api/v1/organizations/{organization_id}/workspaces
GET /api/v1/workspaces/{workspace_id}/projects
GET /api/v1/projects/{project_id}/properties
GET /api/v1/properties/{property_id}/environments
GET /api/v1/organizations/{organization_id}/usage
```

Auditorias e Search Intelligence:

```text
GET /api/v1/projects/{project_id}/audits
GET /api/v1/projects/{project_id}/search-queries
GET /api/v1/search-queries/{query_id}/runs
```

Milestones/deployments:

```text
GET /api/v1/projects/{project_id}/milestones
GET /api/v1/milestones/{milestone_id}/deployment-pair
```

Reports de um AUD autorizado:

```text
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

Execução:

```text
GET  /api/v1/projects/{project_id}/execution-jobs
POST /api/v1/projects/{project_id}/execution-jobs
GET  /api/v1/execution-jobs/{job_id}
POST /api/v1/execution-jobs/{job_id}/cancel
```

O catálogo de auditorias exposto por HTTP não publica `workspace_path` interno. O boundary de reports serve apenas arquivos de apresentação sob o diretório `report/` do AUD autorizado e não permite acesso a `audit.db`.

## Execution jobs

Tipos iniciais:

```text
AUDIT
SEARCH_MONITOR
REPORT_REFRESH
```

Estados:

```text
QUEUED
CLAIMED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

Cada job possui:

- escopo Organization/Project/Property/Environment;
- payload estruturado;
- `requested_by`;
- chave opcional de idempotência;
- prioridade;
- contador e limite de tentativas;
- `available_at`;
- claim/lease de worker;
- resultado e metadados sanitizados;
- erro sanitizado.

Payload, resultado e erro passam pela política central de secret safety. Credenciais inline não são aceitas.

## Idempotência

A combinação `project_id + idempotency_key` identifica uma solicitação já registrada. Repetir a mesma chamada com a mesma chave devolve o job existente em vez de criar duplicação.

O cliente deve escolher chaves estáveis para operações que não podem ser duplicadas por retry HTTP.

## Worker

Um worker executa no máximo um job com:

```powershell
rasai worker run-once --worker-id worker-01 --audits-root audits
```

O worker não depende da stack FastAPI.

O processo:

1. recupera leases expirados;
2. reivindica um job disponível;
3. marca o job como `RUNNING`;
4. executa o handler permitido;
5. grava resultado ou falha sanitizada.

Se o worker morrer, o lease expira. Enquanto `attempts < max_attempts`, o job volta a `QUEUED`. Ao esgotar tentativas, passa a `FAILED`.

## Segurança de execução

Execution jobs não persistem shell commands ou `argv` arbitrário.

Para `AUDIT`, o worker aceita somente campos conhecidos e constrói internamente a CLI canônica. O destino vem da Property/Environment registrada no control plane.

Para `SEARCH_MONITOR`, o payload contém somente `query_id`, e o worker valida que a query pertence exatamente ao Project/Property/Environment do job.

Para `REPORT_REFRESH`, a fundação aceita somente a superfície `portfolio`.

A UI Web usa os mesmos endpoints e não possui caminho alternativo para executar comandos.

## Boundary de reports

O HTML de auditoria continua sendo projeção, nunca fonte de verdade.

O servidor Web pode disponibilizar o mini-site de um AUD depois de revalidar autorização do Project. O path persistido do workspace permanece interno.

A leitura é limitada a:

```text
<AUD workspace>/report/**
```

Traversal, saída do diretório resolvido e extensões fora do allowlist Web são recusados. `audit.db` e artifacts que não pertencem à superfície pública não são servidos por esse endpoint.

## PostgreSQL

A tabela de execution jobs é uma extensão PostgreSQL versionada e aplicada apenas pela operação explícita:

```powershell
rasai platform database migrate
```

Não existe auto-DDL no startup da API ou do worker.

`/health/ready` e o health do store informam tanto a versão principal do schema quanto a versão da extensão de execution jobs.

As rotas aditivas do SaaS Pilot usam a mesma `store_factory`; não criam dependência direta com SQLite e portanto preservam a paridade de backend.

## SQLite portátil

O modo local permanece válido sem FastAPI, Uvicorn, Psycopg, Docker ou servidor PostgreSQL.

```text
RASAi local
  -> SQLite
  -> execution queue local
  -> worker local
```

A existência da API/UI no código não transforma a stack Web em requisito do programa portátil.

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
- client secrets.

Mensagens HTTP derivadas de exceptions passam pela mesma política central de redaction usada por logs e persistência.

O campo local de `USR-*` usado no smoke do browser não é credencial e fica somente em `sessionStorage`; ainda assim ele não deve ser tratado como autenticação real fora de loopback.

## Limites desta fundação

A camada agora possui uma primeira UI de piloto, mas ainda não define:

- provedor definitivo de identidade/OIDC;
- cobrança;
- object storage definitivo;
- orquestração Kubernetes;
- hubs regionais;
- queue externa obrigatória;
- migração de `AUD-*/audit.db` para PostgreSQL;
- design system/frontend framework definitivo.

Essas decisões podem evoluir sem substituir os contratos de tenancy, execution job, worker, report projection e scoring definidos aqui.
