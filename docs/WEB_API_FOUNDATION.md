# Fundação Web/API do RASAi

## Objetivo

A camada Web/API transforma o control plane já existente em uma superfície utilizável por uma aplicação SaaS sem alterar o motor de auditoria, o índice `SARI-001`, o método `SCORE-GEO-004` ou a natureza imutável dos workspaces `AUD-*`.

A arquitetura atual é:

```text
Browser / API client
  |
Identity & Access
  |-- OIDC/JWT direto
  |-- trusted-header compatível
  |
Web UI zero-build (/app)
  |
RASAi API tenant-aware
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

A primeira superfície de navegador está documentada em `SAAS_PILOT_WEB.md`. A identidade Web está documentada em `IDENTITY_AND_ACCESS.md`. Essas camadas são projeções sobre contratos existentes e não redefinem scoring ou evidência.

## Dependências opcionais

A instalação local padrão não depende da stack Web:

```powershell
pip install -e .
```

Para habilitar API, SaaS Pilot Web e OIDC/JWT:

```powershell
pip install -e ".[web]"
```

A stack opcional inclui FastAPI, Uvicorn, HTTPX e bibliotecas de validação JWT/criptografia. PostgreSQL continua opcional separadamente por `.[postgresql]`.

A UI do piloto não adiciona Node, npm, bundler, CDN ou framework JavaScript obrigatório.

## Inicialização

```powershell
rasai api --host 127.0.0.1 --port 8000
```

Superfícies principais:

```text
/app             SaaS Pilot Web
/auth/...        OIDC browser flow quando habilitado
/health/live     liveness
/health/ready    readiness do control plane
/api/v1/...      API tenant-aware
```

A superfície Web permanece sob o entrypoint público canônico `rasai`; a instalação não adiciona um executável público separado para a API.

O bind padrão é `127.0.0.1`. Um bind fora de loopback exige `--allow-public-bind` e deve ocorrer somente atrás de infraestrutura de TLS/firewall/reverse proxy apropriada.

A documentação OpenAPI fica desativada por padrão. Para desenvolvimento controlado:

```text
RASAI_API_DOCS_ENABLED=1
```

## Autenticação

O RASAi não cria banco próprio de senhas e não define bearer token proprietário.

O default permanece fail-closed:

```text
RASAI_API_AUTH_MODE=deny
```

Os modos vigentes são:

```text
deny
trusted-header
oidc
```

### OIDC/JWT

`oidc` é a fundação recomendada para evolução SaaS. O RASAi:

- descobre metadata OIDC a partir de issuer HTTPS;
- usa Authorization Code + PKCE S256 para login Web;
- valida `state` e `nonce`;
- valida JWT com assinatura JWKS;
- aceita somente algoritmos assimétricos explicitamente permitidos;
- valida `iss`, `aud`, `exp` e `sub`;
- tenta refresh de JWKS quando ocorre rotação de `kid`;
- cria sessão Web curta cifrada/autenticada;
- não persiste ID token, access token ou refresh token;
- resolve `issuer + sub` para um `USR-*` provisionado no control plane.

A identidade externa válida não cria usuário, membership ou role automaticamente.

O vínculo administrativo é feito por:

```powershell
rasai platform identity link `
  --user USR-EXISTENTE `
  --issuer https://login.example.com `
  --subject 00u123456789
```

Detalhes e variáveis: `IDENTITY_AND_ACCESS.md`.

### trusted-header

O modo de compatibilidade continua disponível:

```text
RASAI_API_AUTH_MODE=trusted-header
RASAI_API_TRUSTED_USER_HEADER=x-rasai-user-id
```

Ele é seguro somente quando um gateway/reverse proxy autenticado:

- autentica o usuário;
- remove qualquer header de identidade recebido do cliente externo;
- injeta o header somente depois da autenticação;
- protege o tráfego entre gateway e RASAi;
- impede acesso direto do cliente ao processo Uvicorn.

Para smoke humano estritamente local em loopback, `/app` pode manter temporariamente um `USR-*` existente em `sessionStorage` e enviá-lo no trusted header. Essa conveniência não constitui autenticação para ambiente hospedado.

Não existe fallback automático de `oidc` para `trusted-header`.

## Tenancy e autorização

A autenticação termina em um `Principal(user_id)`. A autorização continua independente do mecanismo de login.

A fonte de verdade é o control plane:

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

Identity bootstrap/login:

```text
GET  /auth/config
GET  /auth/login              # somente quando oidc está ativo
GET  /auth/callback           # somente quando oidc está ativo
POST /auth/logout             # somente quando oidc está ativo
```

Identidade autenticada e portfólio:

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

O worker não depende da stack FastAPI nem valida tokens OIDC.

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

## Sessão Web e CSRF

A sessão OIDC contém apenas `issuer + sub` e metadados temporais cifrados/autenticados. Ela não contém access token, ID token ou client secret.

Cookies de sessão são `HttpOnly` e `SameSite=Lax`; em implantação HTTPS também são `Secure`.

Para chamadas mutáveis autenticadas por cookie, o servidor exige `Origin` igual à origem configurada no redirect OIDC. Bearer JWT não depende do cookie e não usa essa verificação de origem.

## PostgreSQL

Execution jobs e Identity & Access são extensões PostgreSQL versionadas e aplicadas apenas pela operação explícita:

```powershell
rasai platform database migrate
```

Não existe auto-DDL no startup da API ou do worker.

`/health/ready` e o health do store informam a versão principal do schema e as versões das extensões de execution e identity.

As rotas do SaaS Pilot usam a mesma `store_factory`; não criam dependência direta com SQLite e preservam a paridade de backend.

## SQLite portátil

O modo local permanece válido sem FastAPI, Uvicorn, Psycopg, Docker ou servidor PostgreSQL.

```text
RASAi local
  -> SQLite
  -> execution queue local
  -> worker local
```

A extensão de vínculo de identidade é aditiva no control plane local e não altera nenhum `AUD-*/audit.db`.

A existência da API/UI/OIDC no código não transforma a stack Web em requisito do programa portátil.

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

Mensagens HTTP derivadas de exceptions passam pela mesma política central de redaction usada por logs e persistência.

O campo local de `USR-*` usado no smoke trusted-header não é credencial e fica somente em `sessionStorage`; ainda assim ele não deve ser tratado como autenticação real fora de loopback.

## Limites desta fundação

A camada já possui UI de piloto e identidade OIDC/JWT provider-neutral. Ainda não define:

- Identity Provider obrigatório;
- SCIM;
- Just-In-Time provisioning;
- SAML direto;
- cobrança;
- object storage definitivo;
- orquestração Kubernetes;
- hubs regionais;
- queue externa obrigatória;
- migração de `AUD-*/audit.db` para PostgreSQL;
- design system/frontend framework definitivo.

Essas decisões podem evoluir sem substituir os contratos de tenancy, identity mapping, execution job, worker, report projection e scoring definidos aqui.
