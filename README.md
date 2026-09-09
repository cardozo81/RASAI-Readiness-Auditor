# RASAi - Search & AI Readiness Auditor

> **RASAi** é a identidade pública do produto. O acrônimo formal **RASAI** deriva de **Readiness Assessment for Search & AI**.

**Descriptor:** Search & AI Readiness Auditor  
**Framework:** RASAi Framework  
**Índice público:** `SARI-001` - Search & AI Readiness Index  
**Scoring vigente:** `SCORE-GEO-004`

RASAi é um auditor de **Search & AI Readiness** com evidência persistida, scoring reproduzível, análise semântica opcional por IA, remediação advisory, diagnósticos de crawling/discovery, Acessibilidade, Web Performance/Lighthouse/CrUX, Apdex sintético, observabilidade e comparação longitudinal.

O produto avalia sinais técnicos e semânticos úteis para Search e sistemas generativos sem prometer ranking, tráfego, conversão, citação ou presença em respostas de IA. **Readiness, visibilidade observada, ranking, citação, performance, acessibilidade e tráfego são metodologias distintas.**

## Estado funcional

Capacidades integradas em `main`:

- auditoria por URL única, conjunto explícito ou arquivo TXT;
- `mobile`, `desktop` ou `both`;
- persistência em SQLite + artifacts + log operacional;
- mini-site HTML estático com navegação canônica;
- `SARI-001` com `SCORE-GEO-004`, Coverage, Confidence e Consolidation separados;
- análise semântica opcional por IA e fallback provider-neutral;
- remediação textual/JSON-LD advisory e evidence-bound;
- crawling/discovery e controles de crawlers;
- PageSpeed/Lighthouse + Core Web Vitals/CrUX como domínio externo separado;
- Acessibilidade automatizada separada do SARI e sem alegar conformidade WCAG integral;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex, inclusive perfis Mobile/Desktop/Tablet;
- Observed Generative Visibility import-first;
- Search & AI Observability com sidecar próprio;
- Quality, Fix Verification e Evidence Timeline;
- Monitoring, comparação baseline/current e release gate;
- control plane local para multiusuário, multiprojeto, multidomínio, milestones/deployments e comparação before/after;
- relatórios consolidados read-only;
- console interativo Windows com preflight, custos/quota e persistência de configuração não sensível.

## Scoring vigente

Novas auditorias usam:

```text
SCORE-GEO-004
```

O Overall usa o contrato:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

As dimensões são calculadas deterministicamente a partir de `RuleExecution` e evidências persistidas. Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador. Estados insuficientes não são convertidos em zero.

Para inspecionar o contrato atual:

```powershell
rasai scoring inspect
```

Fluxos de dataset/calibração associados ao método anterior de desenvolvimento 003 não são requisitos do runtime 004.

Documentação: [docs/SCORE_GEO_004.md](docs/SCORE_GEO_004.md), [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md) e [docs/SARI_READINESS_INDEX.md](docs/SARI_READINESS_INDEX.md).

## Relatórios HTML

Entrada principal por auditoria:

```text
report/index.html
```

Páginas canônicas, materializadas quando aplicáveis:

```text
index.html               síntese executiva
readiness.html           SARI-001
scoring.html             metodologia de scoring e versão efetiva
mobile.html              findings/evidências Mobile
desktop.html             findings/evidências Desktop
remediation.html         remediação
content-suggestions.html conteúdo/JSON-LD advisory
crawling-discovery.html  crawling/discovery
accessibility.html       acessibilidade automatizada
web-performance.html     Lighthouse/Core Web Vitals
apdex.html               Synthetic Navigation Apdex
apdex-experience.html    Synthetic User Experience Apdex
ai-visibility.html       Observed Generative Visibility
observability.html       Search & AI Observability
quality.html             qualidade da evidência/decisão
ai-usage.html            uso/custo estimado de IA
references.html          referências e metodologia
```

A ordem e os filenames vêm de um contrato estruturado único (`ReportSurface`). Páginas opcionais só entram no menu quando materializadas. O item ativo é único e o mesmo catálogo é usado para navegação, testes, aliases, manifest e validação de completude.

### `scoring.html` é estável

A versão pertence ao campo persistido `scoring_version` e ao conteúdo da página, não ao filename. Isso evita quebrar bookmarks, integrações, automações e futuras rotas SaaS a cada revisão metodológica.

### Manifest do report

Após a normalização do mini-site, o RASAi materializa:

```text
report/report-manifest.json
```

O manifest é **metadado de projeção**, não segunda fonte de verdade. Ele registra, quando disponível:

```text
audit_id
auditor_version
ruleset_version
sari_version
scoring_version
report_contract_version
observability_contract_version
generated_pages
aliases
generated_at
source_db
```

Ele não duplica score, findings ou evidence. É produzido a partir de `audit.db` em modo read-only e facilita debugging, completude e evolução para API/SaaS.

## Como os reports se relacionam

O fluxo abaixo representa dependência de evidência/projeção, **não causalidade entre métricas**:

```text
Audit Evidence
   |
   +--> SARI / SCORE-GEO-004        participa do readiness
   |
   +--> Remediation                 derivado read-only
   |
   +--> Web Performance
   |      +--> Accessibility        usa o artifact Lighthouse disponível
   |
   +--> Synthetic Navigation Apdex  complementar
   |
   +--> Synthetic UX Apdex          complementar
   |
   +--> Observed AI Visibility      observacional/import-first
   |
   +--> Observability               resultados externos pós-auditoria
   |
   +--> Quality                     derivado read-only
   |
   +--> AI Usage                    telemetria de IA
```

Cada página HTML declara **Inputs, Outputs, dependências obrigatórias/opcionais, uso de IA, impacto no SARI/SCORE e fonte de verdade**. Isso evita inferir, por exemplo, que Lighthouse, Acessibilidade ou Apdex alterem o `SCORE-GEO-004`.

## Versões e contratos são conceitos diferentes

O RASAi não trata toda evolução como uma única “versão”. Os eixos relevantes são:

| Conceito | Finalidade | Exemplo atual |
|---|---|---|
| `auditor_version` | versão do produto/runtime | versão do pacote RASAi |
| `ruleset_version` | versão do conjunto de regras | persistida no AUD |
| `sari_version` | identidade pública do índice | `SARI-001` |
| `scoring_version` | fórmula/contrato de scoring | `SCORE-GEO-004` |
| `report_contract_version` | contrato das superfícies HTML/manifest | `REPORT-CONTRACT-001` |
| `observability_contract_version` | contrato do sidecar observacional | `OBSERVABILITY-CONTRACT-001` |

A comparação longitudinal deve manter `scoring_version` compatível entre baseline e current. Nesta fase de desenvolvimento, a única metodologia de scoring suportada é `SCORE-GEO-004`.

## Instalação rápida - Windows

Forma recomendada:

```cmd
iniciar.cmd
```

O launcher prepara o ambiente conforme a documentação de instalação e abre o console interativo.

Fallback manual:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
rasai --version
```

Detalhes: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Execução básica

Sem IA:

```powershell
rasai audit https://example.com --ai-provider none
```

Mobile + Desktop:

```powershell
rasai audit https://example.com --device-context both --ai-provider none
```

Arquivo de URLs:

```powershell
rasai audit --urls-file urls.txt --device-context both --ai-provider none
```

A IA é opcional. Ausência de IA não transforma regras semânticas em `FAIL`; pode reduzir Coverage/Confidence quando evidência semântica aplicável não for obtida.

## IA e proveniência do output

Providers concretos/aliases são definidos pelo registry atual e documentados em:

- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

Credencial configurada não comprova saldo, quota, acesso ao modelo ou disponibilidade do provider.

Quando um conteúdo exibido foi produzido por IA, a superfície deve deixar isso explícito e, quando os dados persistidos permitirem, mostrar:

- provider e modelo efetivamente usados;
- finalidade da chamada;
- regra/finding e URL/dispositivo associados;
- evidências ou `evidence_ids` usados como input;
- contexto editorial/YMYL quando ele participou do prompt;
- telemetria de tentativas, tokens e custo estimado em `ai-usage.html`.

Uma resposta da IA continua **advisory/evidence-bound**. O RASAi valida o contrato do retorno e sua associação às evidências permitidas, mas não transforma texto gerado por IA em fato observado. Remediações por IA não alteram Score, Coverage, Confidence ou Consolidation por si só.

## Web Performance e Acessibilidade

Exemplo:

```powershell
rasai audit https://example.com --ai-provider none --web-performance
```

Lighthouse é medição de laboratório; CrUX é dado agregado de campo quando disponível. Acessibilidade automatizada reutiliza o artifact Lighthouse persistido e não equivale a certificação WCAG integral.

Esses indicadores permanecem separados do `SARI-001/SCORE-GEO-004`. Web Performance e Acessibilidade não exigem IA.

## Apdex

RASAi possui dois domínios sintéticos separados:

- **Synthetic Navigation Apdex** - navegação sintética controlada;
- **Synthetic User Experience Apdex** - população sintética configurável, inclusive Mobile/Desktop/Tablet.

Os dois têm URLs canônicas distintas (`apdex.html` e `apdex-experience.html`) e não aparecem duplicados no menu. Nenhum deles é RUM ou depende de IA. A configuração deve ser comparada com o perfil do sistema de referência antes de interpretar divergências com Dynatrace ou outra plataforma de real-user monitoring.

## Observed Generative Visibility e Observability

Observed Generative Visibility é import-first e permanece fora do SARI.

Search & AI Observability usa `observability.db` + `artifacts/observability/` para resultados externos pós-auditoria. Dados ausentes não viram zero e correlação temporal não é tratada como causalidade.

Comandos principais:

```powershell
rasai visibility import ...
rasai visibility report ...
rasai observe status ...
rasai observe report ...
```

Detalhes: [docs/MONITORING_OBSERVABILITY.md](docs/MONITORING_OBSERVABILITY.md).

## Monitoring e Quality

Comparação entre auditorias:

```powershell
rasai monitor compare --baseline AUD-BASELINE --current AUD-CURRENT
rasai monitor impact --baseline AUD-BASELINE --current AUD-CURRENT
rasai monitor gate --baseline AUD-BASELINE --current AUD-CURRENT
```

Quality/Verification:

```powershell
rasai quality report --audit AUD-...
rasai quality verify --baseline AUD-A --current AUD-B
rasai quality timeline --audits-root audits
```

Essas superfícies são read-only sobre a evidência fonte e não criam um segundo readiness score. Quando `scoring_version` é incompatível entre baseline/current, a comparação de score deve permanecer `NOT_COMPARABLE`; nenhum conversor silencioso é permitido.

## Product Platform - Windows first, SaaS ready

O control plane local fica separado do `audit.db` imutável:

```text
audits/.rasai/platform.db
```

Ele modela Organization, Workspace, Project, Property, Environment, usuários/memberships, milestones/deployments, golden baselines, page lineage, schedules, alerts, integrations e usage ledger.

Comandos principais:

```powershell
rasai platform --audits-root audits init
rasai platform --audits-root audits index
rasai platform --audits-root audits status
rasai platform --audits-root audits site
```

A arquitetura alvo para SaaS usa control plane PostgreSQL e workers Linux/containerizados, mantendo compatibilidade com o runtime Windows local. A preparação atual concentra-se em IDs/filenames estáveis, manifests, schemas versionados, persistência histórica imutável e metadados API-friendly; não introduz infraestrutura SaaS pesada no runtime desktop.

Detalhes: [docs/PRODUCT_PLATFORM_ARCHITECTURE.md](docs/PRODUCT_PLATFORM_ARCHITECTURE.md).

## Fonte de verdade e segurança

Princípios:

- `audit.db` + artifacts são evidência imutável da auditoria;
- HTML e `report-manifest.json` são projeções, não segunda fonte de verdade;
- sidecars e índices consolidados são derivados/reconstruíveis;
- secrets não devem ser persistidos em reports, SQLite, INI ou logs;
- resultados externos `NULL` não viram zero;
- nenhuma referência externa homologa automaticamente o SARI completo;
- nenhuma temporalidade isolada prova causalidade;
- relatórios preservam `scoring_version`; nesta fase de desenvolvimento, a única metodologia suportada é `SCORE-GEO-004`.

## Documentação principal

- [docs/REPORT_GUIDE.md](docs/REPORT_GUIDE.md)
- [docs/OUTPUTS_AND_ARTIFACTS.md](docs/OUTPUTS_AND_ARTIFACTS.md)
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)
- [docs/SCORE_GEO_004.md](docs/SCORE_GEO_004.md)
- [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md)
- [docs/SARI_READINESS_INDEX.md](docs/SARI_READINESS_INDEX.md)
- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/MONITORING_OBSERVABILITY.md](docs/MONITORING_OBSERVABILITY.md)
- [docs/PRODUCT_PLATFORM_ARCHITECTURE.md](docs/PRODUCT_PLATFORM_ARCHITECTURE.md)
- [docs/specification/00_SPEC_INDEX.md](docs/specification/00_SPEC_INDEX.md)

## Limite de validade

RASAi fornece auditoria técnica/semântica, evidência, heurísticas proprietárias, métricas externas separadas e suporte à decisão. Não garante ranking, citação, tráfego, conversão, conformidade integral ou causalidade de resultado externo.

<!-- rasai-doc-index-20260908 -->
## Contrato da documentação

A documentação está organizada em [`docs/README.md`](docs/README.md). O projeto está em desenvolvimento e validação; `SCORE-GEO-004` é a única metodologia de scoring vigente e reconhecida nesta fase.
