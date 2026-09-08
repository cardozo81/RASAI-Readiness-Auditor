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
- relatórios consolidados/históricos read-only;
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

`SCORE-GEO-004` **não depende de model artifact externo**. `SCORE-GEO-003` permanece histórico e não é o runtime vigente.

Para inspecionar o contrato atual:

```powershell
rasai scoring inspect
```

Documentação: [docs/SCORE_GEO_004.md](docs/SCORE_GEO_004.md), [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md) e [docs/SARI_READINESS_INDEX.md](docs/SARI_READINESS_INDEX.md).

## Relatórios HTML

Entrada principal por auditoria:

```text
report/index.html
```

Páginas centrais:

```text
index.html               síntese executiva
readiness.html           SARI-001
scoring.html             metodologia de scoring e versão efetiva
mobile.html              findings/evidências Mobile, quando aplicável
desktop.html             findings/evidências Desktop, quando aplicável
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

### Por que `scoring.html` não tem a versão no nome?

O path canônico é propositalmente estável. A versão pertence ao campo persistido `scoring_version` e ao conteúdo da página. Isso evita quebrar bookmarks, integrações, automações e futuras rotas SaaS a cada revisão metodológica.

`score-geo-004.html` pode ser gerado como **alias de compatibilidade** para links antigos, mas novas integrações devem usar `scoring.html`.

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

## IA

Providers concretos/aliases são definidos pelo registry atual e documentados em:

- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

Credencial configurada não comprova saldo, quota, acesso ao modelo ou disponibilidade do provider.

Remediações por IA são advisory e não alteram Score, Coverage, Confidence ou Consolidation por si só.

## Web Performance e Acessibilidade

Exemplo:

```powershell
rasai audit https://example.com --ai-provider none --web-performance
```

Lighthouse é medição de laboratório; CrUX é dado agregado de campo quando disponível. Acessibilidade automatizada usa evidência disponível e não equivale a certificação WCAG integral.

Esses indicadores permanecem separados do `SARI-001/SCORE-GEO-004`.

## Apdex

RASAi possui dois domínios sintéticos separados:

- **Synthetic Navigation Apdex** - navegação sintética controlada;
- **Synthetic User Experience Apdex** - população sintética configurável, inclusive Mobile/Desktop/Tablet.

Nenhum deles é RUM. A configuração deve ser comparada com o perfil do sistema de referência antes de interpretar divergências com Dynatrace ou outra plataforma real-user monitoring.

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

Essas superfícies são read-only sobre a evidência fonte e não criam um segundo readiness score.

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

A arquitetura alvo para SaaS usa control plane PostgreSQL e workers Linux/containerizados, mantendo compatibilidade com o runtime Windows local.

Detalhes: [docs/PRODUCT_PLATFORM_ARCHITECTURE.md](docs/PRODUCT_PLATFORM_ARCHITECTURE.md).

## Fonte de verdade e segurança

Princípios:

- `audit.db` + artifacts são evidência imutável da auditoria;
- HTML é projeção humana, não segunda fonte de verdade;
- sidecars e índices consolidados são derivados/reconstruíveis;
- secrets não devem ser persistidos em reports, SQLite, INI ou logs;
- resultados externos `NULL` não viram zero;
- nenhuma referência externa homologa automaticamente o SARI completo;
- nenhuma temporalidade isolada prova causalidade;
- relatórios históricos preservam `scoring_version` e diferenças metodológicas.

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
