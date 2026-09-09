# Fundação Web/API do RASAi

## Objetivo

A camada Web/API transforma o control plane já existente em uma superfície utilizável por uma aplicação SaaS sem alterar o motor de auditoria, o índice `SARI-001`, o método `SCORE-GEO-004` ou a natureza imutável dos workspaces `AUD-*`.

A arquitetura inicial é:

```text
Web/UI
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

## Dependências opcionais

A instalação local padrão não depende da stack Web:

```powershell
pip install -e .
```

Para habilitar a API:

```powershell
pip install -e ".[web]"
```

A stack opcional inclui FastAPI, Uvicorn e HTTPX. PostgreSQL continua opcional separadamente por `.[postgresql]`.

## Inicialização

```powershell
rasai api --host 127.0.0.1 --port 8000
```

ou:

```powershell
rasai-api --host 127.0.0.1 --port 8000
```

O bind padrão é `127.0.0.1`. Exposição em interface pública deve ocorrer somente atrás de infraestrutura de autenticação, TLS e reverse proxy/gateway apropriada.

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
```

Auditorias e Search Intelligence:

```text
GET /api/v1/projects/{project_id}/audits
GET /api/v1/projects/{project_id}/search-queries
GET /api/v1/search-queries/{query_id}/runs
```

Execução:

```text
GET  /api/v1/projects/{project_id}/execution-jobs
POST /api/v1/projects/{project_id}/execution-jobs
GET  /api/v1/execution-jobs/{job_id}
POST /api/v1/execution-jobs/{job_id}/cancel
```

O catálogo de auditorias exposto por HTTP não publica `workspace_path` interno.

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

## PostgreSQL

A tabela de execution jobs é uma extensão PostgreSQL versionada e aplicada apenas pela operação explícita:

```powershell
rasai platform database migrate
```

Não existe auto-DDL no startup da API ou do worker.

`/health/ready` e o health do store informam tanto a versão principal do schema quanto a versão da extensão de execution jobs.

## SQLite portátil

O modo local permanece válido sem FastAPI, Uvicorn, Psycopg, Docker ou servidor PostgreSQL.

```text
RASAi local
  -> SQLite
  -> execution queue local
  -> worker local
```

A existência da API no código não transforma a stack Web em requisito do programa portátil.

## Secrets

Nenhum endpoint, exception handler, job ou worker deve expor:

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

## Limites desta fundação

Esta camada ainda não define:

- frontend visual do SaaS;
- provedor definitivo de identidade;
- cobrança;
- object storage definitivo;
- orquestração Kubernetes;
- hubs regionais;
- queue externa obrigatória;
- migração de `AUD-*/audit.db` para PostgreSQL.

Essas decisões podem evoluir sem substituir os contratos de tenancy, execution job e worker definidos aqui.
