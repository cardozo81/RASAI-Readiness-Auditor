# RASAi SaaS Pilot Web

Status: **implementado como piloto local/arquitetural** sobre a fundação Web/API, Product Platform e Identity & Access existentes.

## Objetivo

O SaaS Pilot Web cria a primeira superfície de navegador do RASAi sem transformar o piloto em uma infraestrutura SaaS completa e sem duplicar lógica do core.

A composição é:

```text
Browser / API client
  |
Identity & Access
  |-- OIDC/JWT
  |-- trusted-header compatível
  |
/app + RASAi HTTP API
  |
Control plane
  |-- SQLite                       local/default
  |-- PostgreSQL                   opt-in/hosted target
  |
Execution jobs
  |
Workers separados
  |
Audit / Search Monitoring / report refresh
```

O browser não calcula `SARI-001`, não executa `SCORE-GEO-004`, não faz crawling e não implementa novamente Search Intelligence. Ele projeta dados autorizados e cria comandos duráveis por meio dos contratos já existentes.

## Princípios preservados

- `SARI-001` continua sendo a identidade pública do readiness index;
- `SCORE-GEO-004` continua sendo o método de scoring vigente;
- `AUD-*/audit.db` e artifacts continuam sendo evidência imutável de execução;
- o control plane continua separado da evidência do AUD;
- SQLite continua sendo o backend local/default;
- PostgreSQL continua opt-in e é o alvo de autoridade centralizada;
- Search Intelligence permanece non-scoring;
- HTTP nunca executa auditoria/crawling dentro da request;
- nenhuma credencial de provider de auditoria é armazenada pela UI;
- OIDC não cria password database próprio;
- autenticação externa não concede membership automaticamente;
- a UI não introduz Node, npm, bundler, CDN, framework JavaScript ou serviço externo obrigatório ao runtime CLI.

## Superfície de usuário

Em desenvolvimento local a aplicação pode ser aberta em:

```text
http://127.0.0.1:8000/app
```

O piloto oferece:

1. **Visão geral**
   - contagem de auditorias;
   - queries registradas;
   - execution jobs ativos;
   - milestones;
   - estado operacional do escopo selecionado.
2. **Auditorias**
   - histórico do Project;
   - status e versão de scoring persistida;
   - quantidade de URLs;
   - abertura do mini-site HTML já materializado no AUD;
   - criação de durable `AUDIT` job.
3. **Search Intelligence**
   - Query Registry do Project;
   - provider/engine e domínio de interesse quando materializados;
   - criação de `SEARCH_MONITOR` job para query registrada.
4. **Deployments**
   - milestones do Project;
   - resolução determinística do par before/after usando o contrato Product Platform existente.
5. **Execuções**
   - jobs `QUEUED`, `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED` e `CANCELLED`;
   - attempts/max attempts;
   - cancelamento conforme role.
6. **Uso e custo**
   - agregação do usage ledger persistido no control plane;
   - quantidade/unidade/provider;
   - custo estimado e moeda quando existentes.

## Hierarquia e tenancy

A UI navega a hierarquia canônica:

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
```

Ela não filtra tenant apenas no browser. Todo dado vem de endpoints que voltam a validar o `Principal` no servidor.

Conhecer `organization_id`, `project_id`, `audit_id` ou `milestone_id` de outro tenant não concede leitura do recurso.

## Identity & Access

O piloto não cria usuário/senha próprio nem formato proprietário de bearer token.

Modos vigentes:

```text
deny            fail-closed/default
trusted-header  desenvolvimento local ou gateway autenticado
oidc            login Web + JWT direto
```

### OIDC

Com `RASAI_API_AUTH_MODE=oidc`, `/app` exige sessão válida. Um browser não autenticado é redirecionado para `/auth/login`.

O fluxo usa:

- OIDC discovery por issuer HTTPS;
- Authorization Code;
- PKCE S256;
- `state`;
- `nonce`;
- validação de `id_token` por JWKS;
- sessão Web curta cifrada/autenticada;
- vínculo explícito `(issuer, sub) -> USR-*`.

Bearer JWT também pode autenticar diretamente a API quando atende a issuer, audience, assinatura, algoritmo e validade configurados.

Autenticar no Identity Provider não cria `USR-*`, membership ou role.

Detalhes completos: `IDENTITY_AND_ACCESS.md`.

### Desenvolvimento local com trusted-header

Para exercício manual em loopback:

```powershell
rasai api `
  --host 127.0.0.1 `
  --port 8000 `
  --auth-mode trusted-header
```

Quando não existe gateway local, a tela permite informar temporariamente um `USR-*` já existente. O valor fica somente no `sessionStorage` da aba e é enviado no header `x-rasai-user-id`.

Esse mecanismo é somente conveniência de desenvolvimento em loopback. Não deve ser confundido com autenticação de produção.

### Gateway autenticado

`trusted-header` permanece compatível com ambientes em que um gateway externo é a autoridade de autenticação. Nesse caso o gateway deve remover o header recebido do cliente, injetá-lo somente após autenticar a requisição e impedir acesso direto ao Uvicorn.

Para implantação SaaS nova com IdP compatível, `oidc` é preferível porque o RASAi valida a identidade diretamente.

## Provisionamento de identidade

O modelo atual é administrado e fail-closed:

```text
1. criar/identificar USR-*
2. criar membership/role
3. vincular issuer + subject
4. habilitar oidc
```

Exemplo:

```powershell
rasai platform identity link `
  --user USR-EXISTENTE `
  --issuer https://login.example.com `
  --subject 00u123456789
```

O e-mail pode ser armazenado como metadado operacional do vínculo, mas não substitui `issuer + subject` como chave de identidade.

## Reports no browser

O catálogo HTTP continua omitindo `workspace_path`.

O SaaS Pilot possui boundary específico para o report público de um AUD autorizado:

```text
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

Regras de segurança:

- o AUD é autorizado novamente no servidor;
- somente arquivos sob `AUD-*/report/` podem ser servidos;
- `..` e saída por symlink/resolve são recusados;
- extensões permitidas são limitadas a assets de apresentação Web;
- `audit.db`, artifacts privados e paths internos não ficam disponíveis nesse boundary;
- respostas usam `no-store`.

O HTML continua sendo somente projeção; a fonte de verdade segue `audit.db + artifacts`.

## Endpoints do piloto e identidade

Identity bootstrap/login:

```text
GET  /auth/config
GET  /auth/login
GET  /auth/callback
POST /auth/logout
```

Projeções aditivas:

```text
GET /api/v1/projects/{project_id}/milestones
GET /api/v1/milestones/{milestone_id}/deployment-pair
GET /api/v1/organizations/{organization_id}/usage
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

Os endpoints existentes de Organizations, Workspaces, Projects, Properties, Environments, Audits, Search Queries e Execution Jobs continuam reutilizados sem contrato paralelo.

## Criar auditoria pela UI

A tela cria `AUDIT` execution job com payload estruturado dentro do allowlist que o worker já aceita, incluindo:

- `max_pages`;
- `device_context`;
- `ai_provider`;
- `web_performance`.

Nenhum shell command/argv arbitrário é enviado pelo browser.

O job somente progride se existir worker executando separadamente, por exemplo:

```powershell
rasai worker run-once --worker-id worker-01 --audits-root audits
```

Request HTTP e execução pesada permanecem desacopladas.

## Compatibilidade SQLite/PostgreSQL

Nenhuma rota do piloto acessa SQLite diretamente.

As rotas usam `app.state.store_factory`, a mesma composição de backend da API:

```text
SQLite       -> piloto local/default
PostgreSQL   -> piloto centralizado/hosted
```

O vínculo externo de identidade também pertence ao control plane e não ao `audit.db`.

No PostgreSQL, a extensão de identidade exige migration explícita:

```powershell
rasai platform database migrate
```

O piloto não executa auto-DDL no backend hospedado.

## Dependências

Continua válido:

```powershell
pip install -e ".[web]"
```

A extra Web inclui as dependências necessárias à API e à validação OIDC/JWT. Não são adicionadas dependências obrigatórias ao runtime CLI padrão.

## Limites desta fase

O SaaS Pilot Web ainda não afirma prontidão completa de produção SaaS. Permanecem fora deste marco:

- Identity Provider obrigatório/específico;
- SCIM;
- Just-In-Time provisioning;
- billing/checkout;
- object storage definitivo;
- CDN;
- queue externa obrigatória;
- Kubernetes;
- multi-region;
- hubs regionais;
- runners privados remotos;
- migração dos `AUD-*/audit.db` para PostgreSQL;
- frontend framework/build pipeline dedicado.

Esses itens devem ser introduzidos somente quando houver necessidade funcional/operacional comprovada.

## Critério técnico vigente

A superfície é considerada aderente quando:

- `/app` abre sem dependência externa de frontend;
- em OIDC, `/app` exige login e sessão válida;
- JWT inválido/expirado falha fechado;
- identidade externa não provisionada não recebe acesso;
- tenancy continua sendo revalidada no servidor;
- auditorias e Search Query Registry podem ser consultados;
- `AUDIT` e `SEARCH_MONITOR` podem ser enfileirados pela API existente;
- execution jobs podem ser acompanhados e, quando autorizado, cancelados;
- milestones podem resolver before/after;
- usage ledger pode ser projetado;
- reports HTML autorizados podem ser abertos sem exposição de `workspace_path`/`audit.db`;
- regressões de tenancy, identity, report traversal e produto permanecem verdes.

## Próxima evolução recomendada

Com a fundação de Identity & Access implementada, a sequência arquitetural passa a ser:

```text
SaaS Pilot Web + OIDC/JWT
  -> object storage para bundles/artifacts
  -> scheduler/queue hospedado mantendo leases/idempotência/retry
  -> deploy Linux do API/worker
  -> observabilidade operacional
  -> quotas/billing
  -> SCIM/JIT somente quando demanda enterprise justificar
  -> runners privados e distribuição regional quando necessário
```

Nenhum desses passos exige alterar `SARI-001` ou `SCORE-GEO-004`.
