# RASAi SaaS Pilot Web

Status: **implementado como piloto local/arquitetural** sobre a fundação Web/API e o Product Platform existentes.

## Objetivo

O SaaS Pilot Web cria a primeira superfície de navegador do RASAi sem transformar o piloto em uma infraestrutura SaaS de produção e sem duplicar lógica do core.

A composição é:

```text
Browser
  |
  +-- /app                         zero-build UI
  |
RASAi HTTP API                     tenant-aware
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

O browser não calcula `SARI-001`, não executa `SCORE-GEO-004`, não faz crawling e não implementa novamente Search Intelligence. Ele apenas projeta dados autorizados e cria comandos duráveis por meio dos contratos já existentes.

## Princípios preservados

- `SARI-001` continua sendo a identidade pública do readiness index;
- `SCORE-GEO-004` continua sendo o método de scoring vigente;
- `AUD-*/audit.db` e artifacts continuam sendo evidência imutável de execução;
- o control plane continua separado da evidência do AUD;
- SQLite continua sendo o backend local/default;
- PostgreSQL continua opt-in e é o alvo de autoridade centralizada;
- Search Intelligence permanece non-scoring;
- HTTP nunca executa auditoria/crawling dentro da request;
- nenhuma credencial é armazenada pela UI;
- a UI não introduz Node, npm, bundler, CDN, framework JavaScript ou serviço externo obrigatório.

## Superfície de usuário

A aplicação é aberta em:

```text
http://127.0.0.1:8000/app
```

O primeiro piloto oferece:

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
   - criação de um durable `AUDIT` job.
3. **Search Intelligence**
   - Query Registry do Project;
   - provider/engine e domínio de interesse quando materializados;
   - criação de `SEARCH_MONITOR` job para uma query registrada.
4. **Deployments**
   - milestones do Project;
   - resolução determinística do par before/after usando o contrato Product Platform existente.
5. **Execuções**
   - jobs `QUEUED`, `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED` e `CANCELLED`;
   - attempts/max attempts;
   - cancelamento conforme role.
6. **Uso e custo**
   - agregação do usage ledger já persistido no control plane;
   - quantidade/unidade/provider;
   - custo estimado e moeda quando existentes.

## Hierarquia e tenancy

A UI navega a hierarquia já canônica:

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
```

Ela não filtra tenant apenas no browser. Todo dado vem de endpoints que voltam a validar o `Principal` no servidor.

Conhecer um `organization_id`, `project_id`, `audit_id` ou `milestone_id` de outro tenant não concede leitura do recurso.

## Autenticação

O piloto não cria usuário/senha próprio e não introduz token proprietário.

O contrato continua sendo o definido em `WEB_API_FOUNDATION.md`:

```text
default        RASAI_API_AUTH_MODE=deny
hosted target  trusted gateway agora / OIDC-JWT posteriormente
```

### Desenvolvimento local

Para exercício manual em loopback pode ser usado:

```powershell
rasai api `
  --host 127.0.0.1 `
  --port 8000 `
  --auth-mode trusted-header
```

Em seguida abra `/app`. Quando não existe gateway local injetando identidade, a tela permite informar temporariamente um `USR-*` já existente. O valor é mantido somente em `sessionStorage` do browser e enviado no header `x-rasai-user-id` durante aquela sessão.

Este mecanismo é **somente conveniência de desenvolvimento em loopback**. Não é autenticação de produção e não deve ser usado com bind público.

### Ambiente hospedado

Quando houver exposição pública, o browser não deve fornecer livremente o header de identidade. Um gateway autenticado deve:

- autenticar a identidade real;
- remover qualquer identity header vindo do cliente externo;
- injetar o header confiável para o RASAi;
- usar TLS;
- bloquear acesso direto ao processo Uvicorn.

OIDC/JWT permanece a evolução recomendada para o piloto hospedado sem alterar os contratos de tenancy.

## Reports no browser

O catálogo HTTP continua omitindo `workspace_path`.

O SaaS Pilot adiciona um boundary específico para o report público de um AUD autorizado:

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

A UI de desenvolvimento recupera o HTML/CSS usando a mesma identidade da API e abre uma projeção navegável no browser. O HTML continua sendo somente uma projeção; a fonte de verdade segue sendo `audit.db + artifacts`.

## Endpoints aditivos do piloto

Além da API inicial, o piloto usa:

```text
GET /api/v1/projects/{project_id}/milestones
GET /api/v1/milestones/{milestone_id}/deployment-pair
GET /api/v1/organizations/{organization_id}/usage
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

Os endpoints existentes de Organizations, Workspaces, Projects, Properties, Environments, Audits, Search Queries e Execution Jobs continuam sendo reutilizados sem contrato paralelo.

## Criar auditoria pela UI

A tela cria um `AUDIT` execution job com payload estruturado dentro do allowlist que o worker já aceita, incluindo:

- `max_pages`;
- `device_context`;
- `ai_provider`;
- `web_performance`.

Nenhum shell command/argv arbitrário é enviado pelo browser.

O job somente progride se existir worker executando separadamente, por exemplo:

```powershell
rasai worker run-once --worker-id worker-01 --audits-root audits
```

Isso é intencional: request HTTP e execução pesada permanecem desacopladas.

## Compatibilidade SQLite/PostgreSQL

Nenhuma rota do piloto acessa SQLite diretamente.

As rotas usam `app.state.store_factory`, isto é, a mesma composição de backend da API. Portanto:

```text
SQLite       -> piloto local/default
PostgreSQL   -> piloto centralizado/hosted
```

O piloto não altera a estratégia de migrations e não executa auto-DDL.

## Dependências

Continua válido:

```powershell
pip install -e ".[web]"
```

Não são adicionadas dependências obrigatórias ao runtime CLI padrão.

## Limites desta fase

O SaaS Pilot Web **não** afirma prontidão de produção SaaS. Permanecem fora deste marco:

- provedor definitivo OIDC/SSO;
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

## Critério de conclusão deste marco

O marco é considerado tecnicamente concluído quando:

- `/app` abre sem dependência externa de frontend;
- a hierarquia tenant-aware pode ser navegada;
- auditorias e Search Query Registry podem ser consultados;
- um `AUDIT` e um `SEARCH_MONITOR` podem ser enfileirados pela API existente;
- execution jobs podem ser acompanhados e, quando autorizado, cancelados;
- milestones podem resolver before/after;
- usage ledger pode ser projetado;
- reports HTML autorizados podem ser abertos sem exposição de `workspace_path`/`audit.db`;
- testes de tenancy/report traversal permanecem verdes;
- regressão completa do RASAi permanece verde.

## Próxima evolução recomendada

Após validar esta superfície com uso humano, a sequência recomendada é:

```text
SaaS Pilot Web
  -> identidade OIDC/JWT + sessão Web real
  -> object storage para bundles/artifacts
  -> scheduler/queue hospedado com leases/idempotência/retry
  -> deploy Linux do API/worker
  -> observabilidade operacional
  -> quotas/billing
  -> runners privados e distribuição regional quando necessário
```

Nenhum desses passos exige alterar `SARI-001` ou `SCORE-GEO-004`.
