# Arquitetura da RASAi Product Platform

**Estado:** arquitetura de Product Platform implementada, com persistência local/padrão em SQLite e backend PostgreSQL 18 explícito para o control plane centralizado, sob validação de regressão multiplataforma.

## Objetivo

O RASAi é estruturado como plataforma de produto para operação multiusuário, multicliente, multiprojeto e multidomínio, preservando a evidência imutável das auditorias como responsabilidade separada.

A regra arquitetural é explícita:

> `AUD-*/audit.db` é evidência imutável da execução. Metadados de produto, tenant, milestone, schedule, integração, custo e histórico longitudinal pertencem a um banco separado de control plane.

Nenhum backend do control plane altera `SARI-001` ou `SCORE-GEO-004`.

## Modos de persistência suportados

```text
RASAi Product Platform
        |
        +-- SQLite
        |     local/padrão
        |     audits/.rasai/platform.db
        |
        +-- PostgreSQL 18
              alvo centralizado/hospedado explícito
```

Configuração:

| Item | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; aliases de runtime `postgres` e `pg` | `sqlite` em uso local de máquina única; `postgresql` no control plane centralizado |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | DSN PostgreSQL válida quando backend=`postgresql` | secret/env; TLS em ambiente remoto |
| `--platform-db` | `audits/.rasai/platform.db` no fluxo padrão | caminho SQLite; incompatível com PostgreSQL | omitir no uso normal |

SQLite é selecionado quando nenhum backend é configurado.

PostgreSQL é selecionado explicitamente com:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

Um backend PostgreSQL configurado nunca faz fallback silencioso para SQLite. `--platform-db` é override de caminho exclusivo de SQLite.

## Arquitetura local Windows

O runtime local é Windows/Python nativo. Docker não é necessário para operação SQLite.

```text
Windows
  rasai / rasai-console
        |
        +-- engine Audit / Quality / Monitor / Observability
        |      |
        |      +-- audits/AUD-*/audit.db      evidência imutável
        |      +-- audits/AUD-*/artifacts/    evidência persistida
        |
        +-- Product Platform
               |
               +-- audits/.rasai/platform.db  SQLite padrão
               +-- audits/platform-report/
               +-- audits/deployments/
```

O control plane SQLite usa foreign keys, journaling WAL, busy timeout limitado, transações explícitas de escrita, IDs opacos estáveis, metadados de schema, validação SHA-256 dos `audit.db` indexados e vínculos canônicos de escopo multipropriedade.

Esse modo é apropriado para operação offline/em uma única máquina.

## Arquitetura PostgreSQL

PostgreSQL 18 é o backend centralizado do control plane. Desenvolvimento local pode usar container PostgreSQL 18 em Docker; a aplicação consome apenas o contrato de conexão do banco.

```text
aplicação RASAi
        |
RASAI_PLATFORM_DATABASE_URL
        |
PostgreSQL 18
```

Migration de schema PostgreSQL é explícita:

```powershell
rasai platform database status
rasai platform database migrate
```

Startup normal de Product Platform/Search Monitoring não cria nem atualiza tabelas PostgreSQL.

Consulte `POSTGRESQL_CONTROL_PLANE.md` e `POSTGRESQL_MIGRATION_STRATEGY.md`.

## Governança e autoridade dos dados

### Control plane

O backend relacional selecionado é autoritativo para:

- Organization / Workspace / Project;
- Property / Environment;
- users e memberships;
- vínculos de identidade externa;
- catálogo de auditorias e vínculos de escopo multipropriedade;
- Milestones / Deployments;
- Golden Baselines;
- linhagem de PageIdentity;
- registros de comparação;
- schedules e alert rules;
- metadados de integração sem segredos;
- datasets/outcomes externos;
- usage ledger e consumption analytics;
- Search Query Registry;
- resumos de execuções de Search Monitoring;
- execution jobs duráveis.

No modo local, essa autoridade é `audits/.rasai/platform.db`. No modo PostgreSQL, é o banco PostgreSQL configurado.

### Cache analítico derivado

```text
audits/.rasai/consolidated-index.db
```

Quando presente, esse arquivo é estado analítico derivado e reconstruível. Não é um segundo control plane e não é autoritativo para tenancy, milestones, integrações, Query Registry ou estado de ciclo de vida.

### Evidência imutável da auditoria

```text
audits/AUD-*/audit.db
audits/AUD-*/artifacts/
```

Esses elementos permanecem a evidência de origem da execução, independentemente do backend do control plane. Metadados de produto não são gravados de volta em um `AUD-*` já indexado.

## Alvo SaaS hospedado

O modelo hospedado usa workloads Linux/container, PostgreSQL gerenciado, scheduling/fila duráveis e object storage.

```text
Web UI
  |
RASAi API / Control Plane
  |
  +-- PostgreSQL gerenciado
  |      organization/workspace/project/property/environment
  |      metadados memberships/RBAC
  |      vínculos de identidade
  |      milestones/deployments
  |      schedules/alerts/integrations
  |      Query Registry / monitoring runs
  |      usage ledger / audit catalog
  |      execution jobs
  |
  +-- Queue / Scheduler durável
  |      |
  |      +-- Linux audit workers
  |      +-- Search monitoring workers
  |      +-- integration workers
  |
  +-- Object Storage
         bundles AUD imutáveis / artefatos / relatórios / evidência de provider

caminho enterprise opcional:
RASAi SaaS -> Runner autorizado -> rede privada Windows/Linux
```

Linux é preferível para workers hospedados por oferecer empacotamento previsível em containers, suporte Chromium/Playwright, maior densidade de workers, orquestração e amplo suporte em nuvens. Windows nativo permanece o modo local/runner.

SQLite é adequado como autoridade em uma única máquina. SaaS exige estado centralizado de tenants e coordenação transacional concorrente; PostgreSQL é o SGBD alvo de produção.

O limite da transição de banco é o control plane, não o formato de evidência `AUD-*`.

## Hierarquia do produto

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
                  -> referências de AuditRun
                  -> Milestones
                  -> datasets externos
                  -> contextos de Search Monitoring
```

- **Organization** — tenant comercial/de segurança.
- **Workspace** — limite de cliente, unidade de negócio ou portfólio.
- **Project** — iniciativa lógica de Search & AI; pode conter múltiplas propriedades/domínios.
- **Property** — propriedade web própria ou concorrente, identificada por origem/hostname.
- **Environment** — `PRODUCTION`, `STAGING`, `QA`, `PREVIEW`, `DEVELOPMENT` ou `OTHER`.

IDs opacos estáveis são compartilhados pelos contratos de domínio SQLite/PostgreSQL.

## Multiusuário e integridade de tenant

O modelo do control plane suporta users, memberships e roles com escopo.

Roles suportadas:

- `OWNER`;
- `ADMIN`;
- `ANALYST`;
- `OPERATOR`;
- `VIEWER`;
- `INTEGRATION_MANAGER`;
- `BILLING`.

Memberships entre organizations distintas e gravações inconsistentes de Project/Property/Environment são rejeitadas no limite do control plane e reforçadas por constraints relacionais.

Identidade hospedada é resolvida pela camada de autenticação Web/API; persistência no control plane, isoladamente, não autentica uma requisição.

## Modelo AUD multidomínio

Um `AUD-*` pode conter mais de uma origem/domínio alvo.

`audit_index` registra a referência principal de Property/Environment no catálogo, enquanto `audit_scope_links` é a relação canônica muitos-para-muitos que torna o mesmo `AUD-*` localizável por toda Property/Environment incluída em seu escopo.

```text
AUD
  -> Property A / Environment
  -> Property B / Environment
  -> Property C / Environment
```

Golden Baselines e comparações de deployment validam pertencimento ao escopo solicitado, em vez de depender apenas da referência principal do catálogo.

## Imutabilidade de AUD

O catálogo do control plane armazena o SHA-256 de cada `audit.db` indexado.

Reindexar um `AUD-*` com hash diferente é rejeitado. Isso impede que uma auditoria indexada seja silenciosamente reescrita depois de se tornar baseline ou fonte de evidência de deployment.

Testes de integração PostgreSQL indexam arquivos SQLite `AUD-*/audit.db`, executam comparações da Product Platform e verificam que os bytes da auditoria de origem permanecem inalterados.

## Indexação automática

Um `rasai audit` bem-sucedido dispara uma atualização *best effort* pelo backend selecionado do control plane.

- o `AUD-*` persistido é a evidência autoritativa;
- falha de indexação de produto não transforma auditoria bem-sucedida em falha da auditoria;
- erro de indexação é registrado e pode ser reparado com `rasai platform index`.

Quando PostgreSQL é selecionado, seu schema deve estar previamente atualizado; a indexação automática nunca executa migration de schema.

## Milestones e deployments

`Milestone` é uma entidade de produto de primeira classe.

Tipos suportados incluem:

- `DEPLOYMENT`;
- `RELEASE`;
- `CMS_MIGRATION`;
- `REDESIGN`;
- `CONTENT_RELEASE`;
- `SEO_CHANGE`;
- `INFRASTRUCTURE`;
- `INCIDENT`;
- `CAMPAIGN`;
- `MANUAL`;
- `OTHER`.

Um milestone pode registrar timestamp, release/versão, commit SHA, branch/tag, descrição, tags e origem.

## Resolução before/after de deployment

Modo default: `AUTO`.

O RASAi pesquisa a mesma Property + Environment e seleciona:

1. o `AUD-*` tecnicamente comparável mais próximo antes do milestone;
2. o primeiro `AUD-*` tecnicamente comparável depois dele.

Se o par mais próximo não for comparável, o RASAi não normaliza silenciosamente dados incompatíveis. As limitações de comparabilidade são preservadas.

Modos alternativos:

- `GOLDEN` — Golden Baseline aprovado × primeiro `AUD-*` compatível posterior ao milestone;
- `EXPLICIT` — par baseline/current selecionado pelo operador.

Deployment Impact pode exibir `AUD-*` before/after selecionados, motivo da resolução de baseline, regressões materiais, melhorias/resoluções, estado alterado de páginas, resultado do release gate e limitações de comparabilidade.

Ordenação temporal não é apresentada como prova causal.

## Page Compare e PageIdentity

`Page Compare` suporta análise before/after da mesma URL e de migração/URLs diferentes, usando sinais persistidos em nível de página.

`PageIdentity` separa uma página/entidade lógica de uma URL específica. Múltiplas URLs observadas podem ser vinculadas à mesma identidade para redirects, mudanças de URL e replatforming.

## HTML de portfólio

`rasai platform site` gera projeções da Product Platform, incluindo:

- índice de portfólio;
- timeline;
- deployments;
- linhagem de páginas;
- visões de uso/custo.

Contadores de Property são resolvidos pelos escopos canônicos multipropriedade dos `AUD-*`.

Essas páginas permanecem separadas do site de relatório contido dentro de um `AUD-*` imutável.

## Scheduling

Schedules armazenam arrays de argumentos, nunca strings de shell brutas.

A execução usa:

```text
<current-python> -m rasai <argv...>
```

com `shell=False`.

Semânticas de schedule suportadas incluem:

- `INTERVAL`;
- `DAILY`;
- `MANUAL`;
- `DEPLOYMENT_TRIGGERED`;
- `API_TRIGGERED`.

Execução local ocorre em uma única máquina. Scheduling respaldado por PostgreSQL é centralizado; execução horizontal distribuída exige adicionalmente claim atômico da ocorrência, leases/locks, idempotência, estado de retry/dead-letter e limites por tenant/provider.

## Search Monitoring

`SEARCH-MONITOR-001` usa a autoridade selecionada do control plane da Product Platform.

```text
Query Registry
  -> schedule
  -> observação Search
  -> intelligence determinística/IA opcional
  -> resumo longitudinal da execução
  -> detecção de mudança
```

SQLite é o adapter local. PostgreSQL é o adapter centralizado. Evidência bruta do provider e manifests com hash permanecem fora das linhas relacionais e migram naturalmente para object storage na operação hospedada.

Search Monitoring não participa do scoring.

## Alerts

Alert rules avaliam eventos materiais de comparação por status e severidade mínima.

Status default quando `--status` não é informado:

```text
REGRESSED
NEW
```

Valores `--status` explícitos substituem os defaults.

Destinos:

- `NONE` — apenas persiste a notificação;
- `JSON` — persiste notificação estruturada;
- `WEBHOOK` — faz POST de JSON estruturado.

Segredos de webhook não são armazenados como metadados comuns do produto. Entrega hospedada exige segredos gerenciados e controles SSRF/egress.

## Saídas de release gate para CI/CD

Comparações de deployment podem exportar JSON, JUnit XML e SARIF, com semântica de exit code adequada à integração CI/CD.

O contrato é independente de fornecedor.

## Outcomes externos e observabilidade de crawlers

Observações externas permanecem fora de SARI/SCORE-GEO.

Fontes incluem:

- GA4 Data API usando bearer token do ambiente de runtime;
- importação CSV do GA4;
- importação Cloudflare Logpush;
- access logs comuns/combinados compatíveis com Apache/nginx;
- classificação explícita de marcadores User-Agent conhecidos de crawlers de IA.

Classificação de crawler é classificação de evidência, não prova de identidade verificada de bot. Sinais verificados de bot management do provider/CDN devem prevalecer sobre identidade heurística quando disponíveis.

## Usage ledger e consumption analytics

Consumo de produto é armazenado separadamente de findings técnicos, incluindo categorias como:

- URLs rastreadas;
- execuções de browser;
- chamadas de API;
- consumo de LLM/provider;
- unidades de worker/storage, quando implementadas;
- custo/moeda estimados.

O mesmo ledger sustenta consumption analytics e metering SaaS futuro, preservando proveniência/atribuição BYOK.

## Segredos

Nenhum API token, webhook secret ou senha de provider é armazenado como metadado de produto em texto puro.

Operação local usa variáveis de ambiente e persiste apenas configuração não secreta ou nomes de referências a segredos.

Operação hospedada usa secret storage gerenciado/serviços respaldados por KMS, autorização com escopo de tenant e controles de rotação/auditoria.

`RASAI_PLATFORM_DATABASE_URL` pode conter segredo e deve ser redigida nas saídas de status/erro.

## Decisão sobre Docker

Docker não é necessário para operação normal SQLite no Windows. É usado no desenvolvimento/integração PostgreSQL 18 local e no CI PostgreSQL.

No deployment hospedado, API/workers podem ser containerizados; PostgreSQL de produção deve normalmente ser gerenciado, e não acoplado ao host de um container da aplicação.

## Estratégia de schema PostgreSQL

O schema PostgreSQL usa a representação de domínio esperada pelos contratos atuais de repository. Mudanças de representação são migrations explícitas e validadas quanto à paridade semântica.

Dados SQLite de desenvolvimento são estado de teste/piloto e não constituem fonte de migration obrigatória para uma autoridade PostgreSQL limpa.

## Exemplos principais de CLI

Inicialização/indexação SQLite:

```powershell
rasai platform --audits-root audits init
rasai platform --audits-root audits index
rasai platform --audits-root audits status
rasai platform --audits-root audits data status
rasai platform --audits-root audits site
```

Administração PostgreSQL:

```powershell
rasai platform database status
rasai platform database migrate
rasai platform database status
```

Users e memberships:

```powershell
rasai platform --audits-root audits user add --name "Analyst" --email analyst@example.com
rasai platform --audits-root audits member add `
  --organization ORG-... --user USR-... --role ANALYST `
  --workspace WSP-... --project PRJ-...
```

Criar milestone de deployment:

```powershell
rasai platform --audits-root audits milestone add `
  --project PRJ-... `
  --property PTY-... `
  --environment ENV-... `
  --kind DEPLOYMENT `
  --at 2026-09-07T14:35:00-03:00 `
  --title "Release 3.12" `
  --release 3.12.0 `
  --commit abc123
```

Resolver/comparar:

```powershell
rasai platform --audits-root audits deploy pair --milestone MLS-...

rasai platform --audits-root audits deploy compare `
  --milestone MLS-... `
  --json artifacts/gate.json `
  --junit artifacts/gate.xml `
  --sarif artifacts/gate.sarif
```

Golden Baseline:

```powershell
rasai platform --audits-root audits baseline set `
  --property PTY-... --environment ENV-... --audit AUD-...
```

Page Compare:

```powershell
rasai platform --audits-root audits page compare `
  --baseline AUD-BEFORE `
  --current AUD-AFTER `
  --baseline-url https://example.com/produto `
  --output page-compare.html
```

## Limite operacional

Audit, Monitor, Quality, Observability e Visibility usam o mesmo limite de evidência imutável, independentemente do backend selecionado da Product Platform.

Indexação pós-auditoria na plataforma é *best effort* e fail-open: um problema no control plane não pode invalidar uma auditoria já persistida.

## Limite metodológico

Dados de produto/portfólio, Search Monitoring, GA4, logs, milestones, marcadores de deployment, schedules e usage não alteram SARI/SCORE-GEO por default.

Associação temporal não é inferência causal. A plataforma pode afirmar que uma mudança técnica e um outcome observado ocorreram em relação temporal definida; não deve afirmar que o deployment causou o outcome, salvo se uma metodologia causal separada e validada estabelecer essa conclusão.
