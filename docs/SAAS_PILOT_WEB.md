# RASAi SaaS Pilot Web

**Estado:** implementado como piloto local/arquitetural sobre a fundação Web/API, Product Platform e Identity & Access existentes.

## Objetivo

O SaaS Pilot Web cria a superfície de navegador do RASAi sem transformar o piloto em uma infraestrutura SaaS completa e sem duplicar lógica do core.

Composição:

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
  |-- SQLite       local/default
  |-- PostgreSQL   opt-in/hosted target
  |
Execution jobs / managed schedules
  |
Workers separados
  |
Audit / Search Monitoring / report refresh
```

O browser não calcula `SARI-001`, não executa `SCORE-GEO-004`, não faz crawling e não reimplementa Search Intelligence. Ele projeta dados autorizados e cria comandos duráveis pelos contratos existentes.

## Princípios preservados

- `SARI-001` continua sendo a identidade pública do readiness index;
- `SCORE-GEO-004` continua sendo o método de scoring vigente;
- `AUD-*/audit.db` e artifacts continuam sendo evidência imutável de execução;
- o control plane continua separado da evidência do AUD;
- SQLite continua backend local/default;
- PostgreSQL continua opt-in e alvo de autoridade centralizada;
- Search Intelligence permanece non-scoring;
- HTTP nunca executa auditoria/crawling dentro da request;
- nenhuma credencial de provider de auditoria é armazenada pela UI;
- OIDC não cria banco de senhas próprio;
- autenticação externa não concede membership automaticamente;
- UI não introduz Node, npm, bundler, CDN, framework JavaScript ou serviço externo obrigatório ao runtime CLI.

## Superfície de usuário

Em desenvolvimento local:

```text
http://127.0.0.1:8000/app
```

O piloto oferece, conforme autorização:

- visão geral do escopo selecionado;
- histórico de auditorias do Project e abertura de reports materializados;
- criação de durable `AUDIT` jobs pelo contrato canônico do runtime;
- Query Registry e criação de `SEARCH_MONITOR` jobs;
- milestones e resolução before/after;
- acompanhamento/cancelamento de execution jobs conforme role;
- usage ledger e Consumption Analytics;
- criação, edição, pausa, retomada, duplicação e desativação de managed schedules;
- configuração `AUDIT` derivada do mesmo contrato usado pelo worker.

## Hierarquia e tenancy

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
```

A UI não filtra tenant apenas no browser. Todo endpoint volta a validar o `Principal` no servidor. Conhecer IDs de outro tenant não concede acesso.

## Identity & Access

Modos vigentes:

| Modo | Default | Permitido | Recomendado |
|---|---|---|---|
| `deny` | sim | sim | estado fail-closed enquanto autenticação não estiver configurada |
| `trusted-header` | não | sim | somente desenvolvimento local ou gateway autenticado confiável |
| `oidc` | não | sim | recomendado para implantação hospedada |

Com `RASAI_API_AUTH_MODE=oidc`, `/app` exige sessão válida. O fluxo usa OIDC discovery por issuer HTTPS, Authorization Code, PKCE S256, `state`, `nonce`, validação de `id_token` por JWKS, sessão Web curta e vínculo explícito `(issuer, sub) -> USR-*`.

Bearer JWT pode autenticar diretamente a API quando atende ao contrato configurado. Autenticar no Identity Provider não cria `USR-*`, membership ou role.

Detalhes: `IDENTITY_AND_ACCESS.md`.

## Desenvolvimento local com `trusted-header`

```powershell
rasai api `
  --host 127.0.0.1 `
  --port 8000 `
  --auth-mode trusted-header
```

Sem gateway local, a tela pode usar temporariamente um `USR-*` já existente no `sessionStorage` da aba e enviá-lo no header `x-rasai-user-id`. Isso é conveniência de desenvolvimento em loopback, não autenticação de produção.

Em gateway autenticado, o gateway deve remover qualquer header equivalente recebido do cliente, injetar identidade somente após autenticação e impedir acesso direto ao processo RASAi.

## Provisionamento de identidade

Modelo atual:

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

E-mail pode ser metadado informativo, mas não substitui `issuer + subject` como chave de identidade.

## Reports no browser

Endpoints:

```text
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

Regras:

- o AUD é autorizado novamente no servidor;
- somente arquivos sob `AUD-*/report/` podem ser servidos;
- `..`, traversal e saída por symlink/resolve são recusados;
- extensões ficam limitadas a assets de apresentação Web;
- `audit.db`, artifacts privados e paths internos não são expostos;
- respostas usam `Cache-Control: no-store`.

O HTML continua sendo projeção; a fonte de verdade é `audit.db + artifacts`.

## Endpoints e contratos aditivos

Identidade:

```text
GET  /auth/config
GET  /auth/login
GET  /auth/callback
POST /auth/logout
```

Superfícies de produto:

```text
GET /api/v1/audit-job-options
GET /api/v1/projects/{project_id}/milestones
GET /api/v1/milestones/{milestone_id}/deployment-pair
GET /api/v1/organizations/{organization_id}/usage
GET /api/v1/organizations/{organization_id}/consumption
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

`GET /api/v1/audit-job-options` é a superfície canônica, autenticada e não secreta para materializar na Web defaults e opções aceitos por durable `AUDIT` jobs. A UI não mantém uma segunda lista independente desses parâmetros.

## Criação de auditoria e schedules

A UI cria `AUDIT` execution job com payload estruturado dentro do contrato canônico aceito pelo worker. O contrato cobre, quando aplicável:

- idioma, mercado, limite de páginas e device context;
- provider/modelo de IA e opções não secretas de remediação;
- Web Performance e categorias Lighthouse;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex, incluindo KPM, device mix, error scope e thresholds;
- contexto de conteúdo/YMYL e demais opções expostas pelo runtime.

Defaults de Synthetic User Experience Apdex são os mesmos do CLI/runtime. Omissão de valores padrão não deve ser tratada como customização.

Payloads de execution jobs e managed schedules são validados **antes da persistência**. Opção desconhecida, combinação inválida ou segredo inline falha antes de entrar na fila.

Nenhum shell command/argv arbitrário é enviado pelo browser.

O job só progride quando existe worker separado, por exemplo:

```powershell
rasai worker run-once --worker-id worker-01 --audits-root audits
```

## Dynatrace no SaaS

O runtime local pode importar configuração Dynatrace pelas opções próprias do CLI. O worker SaaS genérico não deve habilitar importação a partir de secrets process-wide, porque ambiente multi-tenant precisa resolver configuração/credencial por integração vinculada ao tenant.

Credencial Dynatrace não pertence a `payload_json`. Uma implantação hosted deve usar referência segura de Integration/secret e resolver o segredo somente no worker autorizado.

## Compatibilidade SQLite/PostgreSQL

As rotas usam `app.state.store_factory`, não SQLite diretamente:

```text
SQLite       -> piloto local/default
PostgreSQL   -> piloto centralizado/hosted
```

O contrato de payload é validado antes da persistência e independe do backend. Opções não secretas podem permanecer em `payload_json` sem exigir migration relacional por cada nova opção.

Vínculo externo de identidade pertence ao control plane, não ao `audit.db`.

PostgreSQL exige migration explícita para a extensão de identidade:

```powershell
rasai platform database migrate
```

## Dependências

```powershell
pip install -e ".[web]"
```

A extra Web contém dependências da API e validação OIDC/JWT. Não adiciona dependência obrigatória ao runtime CLI padrão.

## Limites desta fase

O piloto não afirma prontidão completa de produção SaaS. Permanecem fora deste marco:

- Identity Provider obrigatório/específico;
- SCIM;
- Just-In-Time provisioning;
- billing/checkout;
- object storage definitivo;
- CDN;
- queue externa obrigatória;
- Kubernetes;
- multi-region/hubs regionais;
- runners privados remotos;
- importação Dynatrace hosted sem vínculo de integração tenant-scoped;
- migração dos `AUD-*/audit.db` para PostgreSQL;
- frontend framework/build pipeline dedicado.

Identity & Access OIDC/JWT já é contrato funcional; o item “Identity Provider obrigatório/específico” significa apenas que o produto não está preso a um fornecedor concreto.

## Critério técnico vigente

A superfície é aderente quando:

- `/app` abre sem dependência externa obrigatória de frontend;
- em OIDC, `/app` exige login e sessão válida;
- JWT inválido/expirado falha fechado;
- identidade externa não provisionada não recebe acesso;
- tenancy é revalidada no servidor;
- auditorias e Query Registry podem ser consultados;
- `/app` e `/app/operations` consomem o contrato canônico de configuração `AUDIT`;
- `AUDIT` e `SEARCH_MONITOR` podem ser enfileirados;
- managed schedules rejeitam payload inválido antes da persistência;
- execution jobs podem ser acompanhados/cancelados conforme autorização;
- milestones podem resolver before/after;
- usage ledger e Consumption Analytics suportam filtros tenant-aware;
- reports autorizados podem ser abertos sem expor `workspace_path`/`audit.db`;
- paridade PostgreSQL e SaaS/runtime permanece coberta pelo CI;
- regressões de tenancy, identity, report traversal e produto permanecem verdes.

## Próxima evolução recomendada

```text
SaaS Pilot Web + OIDC/JWT
  -> object storage para bundles/artifacts
  -> scheduler/queue hospedado mantendo leases/idempotência/retry
  -> integração tenant-scoped de secrets/providers externos
  -> deploy Linux do API/worker
  -> observabilidade operacional
  -> quotas/billing
  -> SCIM/JIT quando demanda enterprise justificar
  -> runners privados e distribuição regional quando necessário
```

Nenhum desses passos exige alterar `SARI-001` ou `SCORE-GEO-004`.