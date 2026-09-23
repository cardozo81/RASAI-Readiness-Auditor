# RASAi - Search & AI Readiness Auditor

> **RASAi** é a identidade pública do produto. O acrônimo formal **RASAI** deriva de **Readiness Assessment for Search & AI**.

**Descritor:** Search & AI Readiness Auditor  
**Framework:** RASAi Framework  
**Versão pública:** `001`  
**Índice público:** **Search & AI Readiness Index - Índice de Prontidão Search & IA** · ID técnico `SARI-001`  
**Método de pontuação:** **Método de Pontuação de Prontidão** · versão pública `001` · contrato técnico `SCORE-GEO-004`

RASAi é um auditor de **Search & AI Readiness** com evidência persistida, scoring reproduzível, análise semântica opcional por IA, remediação advisory, diagnósticos de crawling/discovery, Acessibilidade, Web Performance/Lighthouse/CrUX, métricas e padrões Web, Apdex sintético, observabilidade e comparação longitudinal.

O produto avalia sinais técnicos e semânticos úteis para Search e sistemas generativos sem prometer ranking, tráfego, conversão, citação ou presença em respostas de IA. **Readiness, visibilidade observada, ranking, citação, performance, acessibilidade e tráfego são metodologias distintas.**

## Estado funcional

Capacidades integradas no contrato atual:

- auditoria por URL única, conjunto explícito ou arquivo TXT;
- `mobile`, `desktop` ou `both`;
- persistência em SQLite + artefatos + log operacional;
- relatório HTML pertencente à auditoria em `report-catalog/`, derivado da evidência persistida;
- Índice de Prontidão Search & IA com Método de Pontuação de Prontidão, Cobertura, Confiança e Consolidação separados; IDs técnicos `SARI-001` e `SCORE-GEO-004` preservados;
- análise semântica opcional por IA e fallback independente de provedor;
- remediação textual/JSON-LD advisory e evidence-bound;
- Análise profunda e melhorias (Improvement Intelligence) opcional para uma URL, reutilizando a seleção principal de IA e a política canônica de `AI=auto`, com análise técnica/conteúdo/SERP/segurança passiva e backlog priorizado;
- crawling/discovery e controles de crawlers;
- PageSpeed/Lighthouse + Core Web Vitals/CrUX como domínio externo separado;
- Acessibilidade automatizada separada do SARI e sem alegar conformidade WCAG integral;
- W3C HTML/CSS, MDN Observatory, Web Platform Baseline/WebDX e métricas derivadas conforme configuração/disponibilidade;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex, inclusive perfis Mobile/Desktop/Tablet;
- Observed Generative Visibility import-first;
- Search & AI Observability com sidecar próprio;
- qualidade, verificação de correção (Fix Verification) e linha do tempo de evidências (Evidence Timeline);
- monitoramento, comparação baseline/current e release gate;
- control plane local para multiusuário, multiprojeto, multidomínio, milestones/deployments e comparação before/after;
- relatórios consolidados somente leitura;
- console interativo Windows com pré-verificação (preflight), custos/quota e persistência de configuração não sensível.

## Método de Pontuação de Prontidão

O método apresentado ao usuário inicia na **versão pública 001**. O contrato técnico preservado pelo runtime é:

```text
SCORE-GEO-004
```

O Overall usa o contrato:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

O cálculo é hierárquico e ponderado por grupos/dimensões conforme o contrato vigente. As dimensões são calculadas deterministicamente a partir de `RuleExecution` e evidências persistidas. Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador. Estados insuficientes não são convertidos em zero.

Para inspecionar o contrato atual:

```powershell
rasai scoring inspect
```

Documentação: [docs/SCORE_GEO_004.md](docs/SCORE_GEO_004.md), [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md) e [docs/SARI_READINESS_INDEX.md](docs/SARI_READINESS_INDEX.md).

Glossário e taxonomia: [docs/GLOSSARY.md](docs/GLOSSARY.md).

## Relatórios HTML

A saída HTML pertencente a uma execução `rasai audit` é `report-catalog/`, com entrada em:

```text
<AUD>/report-catalog/index.html
```

`report-catalog/` é uma projeção somente leitura derivada de `audit.db` + artefatos persistidos. Collectors, scoring, findings, evidências, recomendações, causa raiz, precisão, IA, custos e rastreabilidade pertencem ao processamento/persistência; a renderização HTML não executa nova coleta nem recalcula esses dados.

A fonte de verdade para nomes, ordem e navegação das páginas públicas dessa projeção é `src/rasai/catalog_report_contract.py`. A taxonomia e os títulos dos CAT-01 a CAT-10 vêm de `src/rasai/audit_catalog.py`.

### Como os relatórios se relacionam

- **Auditoria individual (`AUD-*`)**: `report-catalog/` apresenta o estado de uma única execução, seus catálogos, Índice de Prontidão Search & IA, evidências e páginas de governança.
- **Catálogos (`CAT-01` a `CAT-10`)**: são superfícies funcionais dentro do `report-catalog/`; seus títulos devem seguir a taxonomia canônica do programa.
- **Relatório consolidado (`CONS-*`)**: é uma saída longitudinal separada, construída somente a partir de auditorias persistidas e compatíveis. Não pertence ao `report-catalog/` de uma AUD.
- **Saídas especializadas**: monitoramento, verificação, linhas do tempo, históricos e outras projeções com contrato próprio permanecem fora do contrato HTML da auditoria individual.

### Superfícies canônicas de uma execução `rasai audit`

| Arquivo em `report-catalog/` | Título/finalidade exibida |
|---|---|
| `index.html` | Visão geral |
| `sari.html` | Índice de Prontidão Search & IA |
| `cat-01.html` | CAT-01 · Fundamentos técnicos e descoberta |
| `cat-02.html` | CAT-02 · Acessibilidade |
| `cat-03.html` | CAT-03 · Conteúdo, semântica e dados estruturados |
| `cat-04.html` | CAT-04 · Web Performance |
| `cat-05.html` | CAT-05 · Search & AI Intelligence |
| `cat-06.html` | CAT-06 · Apdex de navegação |
| `cat-07.html` | CAT-07 · Apdex de experiência |
| `cat-08.html` | CAT-08 · Análise profunda e melhorias |
| `cat-09.html` | CAT-09 · Remediações |
| `cat-10.html` | CAT-10 · Segurança passiva |
| `directed-analysis.html` | Análise Direcionada |
| `capture-context.html` | Captura e contexto |
| `execution-evidence.html` | Evidências da execução |
| `ai-integrations.html` | IA e integrações |
| `methodology.html` | Metodologia e scoring |
| `metrics.html` | Índices e métricas |

Os nomes acima refletem o contrato atualmente materializado pelo programa. Termos técnicos consolidados, como SARI, Web Performance, Search & AI Intelligence, Apdex e scoring, permanecem quando sua tradução reduziria precisão ou romperia a correspondência com o produto.

A materialização continua pela rotina canônica `materialize_catalog_report_site(...)` e preserva as regras CAT-*, a Matriz de encerramento estrutural e o conteúdo funcional definido pelo contrato vigente.

### Relatório consolidado longitudinal

O **Relatório Consolidado Longitudinal**, formato público **001**, compara auditorias `AUD-*` compatíveis sem reexecutar coleta, crawl, pontuação ou integrações. O identificador técnico do formato permanece `CONS-5`. A entrada HTML materializada é:

```text
audits/consolidated/CONS-*/report.html
```

Estrutura principal do pacote:

```text
audits/consolidated/CONS-*/
├── report.html
├── rules-reference.html        # quando houver regras de avaliação de prontidão citadas (IDs BR-GEO-*)
├── manifest.json
├── decision-context.json
├── longitudinal-evidence.json
├── execution.json
├── specialist-analysis.json   # somente quando a IA for solicitada
└── ai-exchanges.json          # somente quando a IA for solicitada
```

Cada tentativa de geração também possui rastreabilidade própria em `audits/consolidated/executions/CONRUN-*/`. O modo determinístico é válido sem IA; quando IA é solicitada, ela interpreta o contexto longitudinal governado sem alterar os dados, scores ou evidências das auditorias de origem.

Detalhes: [docs/CONSOLIDATED_REPORTING.md](docs/CONSOLIDATED_REPORTING.md), [docs/CONSOLIDATED_REPORTING_VALIDATION.md](docs/CONSOLIDATED_REPORTING_VALIDATION.md) e [docs/OUTPUTS_AND_ARTIFACTS.md](docs/OUTPUTS_AND_ARTIFACTS.md).

### SaaS / Web

Os endpoints existentes de relatórios permanecem estáveis:

```text
GET /api/v1/audits/{audit_id}/reports
GET /api/v1/audits/{audit_id}/reports/{asset_path}
```

A raiz pública autorizada desses endpoints é exclusivamente `<AUD>/report-catalog/`. `audit.db`, artefatos privados e caminhos internos continuam fora da superfície HTTP.

## Versões e contratos são conceitos diferentes

O RASAi não trata toda evolução como uma única “versão”. Os eixos relevantes são:

| Conceito | Finalidade | Exemplo atual |
|---|---|---|
| `auditor_version` | versão do produto/runtime | versão do pacote RASAi |
| `ruleset_version` | versão do conjunto de regras | persistida no AUD |
| `sari_version` | identidade pública do índice | `SARI-001` |
| `scoring_version` | fórmula/contrato de scoring | `SCORE-GEO-004` |
| `catalog_report_contract` | contrato da projeção HTML audit-owned e do manifest | `CATALOG-REPORT-002` |
| `observability_contract_version` | contrato do sidecar observacional | `OBSERVABILITY-CONTRACT-001` |

A comparação longitudinal deve manter `scoring_version` compatível entre baseline e current. Nesta fase de desenvolvimento, o único **Método de Pontuação de Prontidão** suportado usa o contrato técnico `SCORE-GEO-004`.

## Instalação rápida - Windows

Forma recomendada:

```cmd
abrir-rasai-console.cmd
```

O launcher prepara o ambiente local e abre o console interativo.

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

## IA e proveniência da saída

Provedores concretos e seleções aceitas são definidos pelo registro técnico atual e documentados em:

- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/IMPROVEMENT_INTELLIGENCE.md](docs/IMPROVEMENT_INTELLIGENCE.md)

Credencial configurada não comprova saldo, quota, acesso ao modelo ou disponibilidade do provider.

Quando um conteúdo exibido foi produzido por IA, a superfície deve deixar isso explícito e, quando os dados persistidos permitirem, mostrar:

- provedor e modelo efetivamente usados;
- finalidade da chamada;
- regra/finding e URL/dispositivo associados;
- evidências ou `evidence_ids` usados como entrada;
- contexto editorial/YMYL quando ele participou do prompt;
- telemetria de tentativas, tokens e custo estimado em `report-catalog/ai-integrations.html`.

Uma resposta da IA continua **advisory/evidence-bound**. O RASAi valida o contrato do retorno e sua associação às evidências permitidas, mas não transforma texto gerado por IA em fato observado. Remediações por IA não alteram Score, Coverage, Confidence ou Consolidation por si só.

### Análise profunda e melhorias (Improvement Intelligence)

A análise profunda é opcional por escolha explícita e só fica elegível para **uma URL explícita**. Ela pode correlacionar HTML/semântica, findings, Lighthouse/PageSpeed, Search/SERP, arquivos de descoberta e postura de segurança passiva. Provedor, modelo e reasoning pertencem à seleção principal de IA da auditoria; quando a seleção é `AI=auto`, a análise profunda reutiliza o mesmo coordenador canônico de custo, elegibilidade, quarentena, circuit breaker e fallback.

O resultado é um backlog priorizado com evidência, impacto potencial, esforço, justificativa e, quando aplicável, comparação entre HTML original e HTML sugerido. Search/SERP é usado como contexto competitivo observacional: nenhuma recomendação promete posição futura. Segurança é passiva; a funcionalidade não executa exploração ou pentest ativo.

O ganho só é comprovado por nova medição/before-after após o deploy. Detalhes: [docs/IMPROVEMENT_INTELLIGENCE.md](docs/IMPROVEMENT_INTELLIGENCE.md).

## Web Performance e Acessibilidade

Exemplo:

```powershell
rasai audit https://example.com --ai-provider none --web-performance
```

Lighthouse é medição de laboratório; CrUX é dado agregado de campo quando disponível. Acessibilidade automatizada reutiliza o artefato Lighthouse persistido e não equivale a certificação WCAG integral.

Esses indicadores permanecem separados do `SARI-001/SCORE-GEO-004`. Web Performance e Acessibilidade não exigem IA. No relatório audit-owned, Web Performance é projetada em `report-catalog/cat-04.html` e acessibilidade automatizada em `report-catalog/cat-02.html`; ausência, indisponibilidade ou coleta parcial devem permanecer explícitas, sem inventar resultado.

## Apdex

RASAi possui dois domínios sintéticos separados:

- **Synthetic Navigation Apdex** - navegação sintética controlada;
- **Synthetic User Experience Apdex** - população sintética configurável, inclusive Mobile/Desktop/Tablet.

No relatório audit-owned, Synthetic Navigation Apdex é projetado em `report-catalog/cat-06.html` e Synthetic User Experience Apdex em `report-catalog/cat-07.html`. Nenhum deles é RUM ou depende de IA. Quando não executados, as páginas permanecem disponíveis em estado neutro e não criam amostras sintéticas. O Experience Apdex permite distribuir percentualmente as amostras sintéticas entre Mobile/Desktop/Tablet; a soma deve ser exatamente 100%. Essa distribuição representa a população de ações de usuário/amostras, não o número bruto de subrequests HTTP disparados por cada página.

A configuração deve ser comparada com o perfil do sistema de referência antes de interpretar divergências com Dynatrace ou outra plataforma de real-user monitoring.

## Visibilidade generativa observada e observabilidade

Observed Generative Visibility é import-first e permanece fora do SARI. Quando houver dados aplicáveis à AUD, a projeção correspondente permanece no domínio de Search & AI Intelligence, principalmente `report-catalog/cat-05.html` e `report-catalog/metrics.html`, sem criar uma página audit-owned paralela.

Search & AI Observability usa `artifacts/observability/observability.db` + artefatos observacionais para resultados externos. Dados ausentes não viram zero e correlação temporal não é tratada como causalidade. A projeção audit-owned correspondente fica no `report-catalog/`, principalmente CAT-05 e métricas.

Comandos principais:

```powershell
rasai visibility import ...
rasai observe status ...
rasai observe report ...
```

Detalhes: [docs/MONITORING_OBSERVABILITY.md](docs/MONITORING_OBSERVABILITY.md).

## Monitoramento e qualidade

Comparação entre auditorias:

```powershell
rasai monitor compare --baseline AUD-BASELINE --current AUD-CURRENT
rasai monitor impact --baseline AUD-BASELINE --current AUD-CURRENT
rasai monitor gate --baseline AUD-BASELINE --current AUD-CURRENT
```

Qualidade/verificação:

```powershell
rasai quality report --audit AUD-...
rasai quality verify --baseline AUD-A --current AUD-B
rasai quality timeline --audits-root audits
```

Essas capacidades são somente leitura sobre a evidência fonte e não criam um segundo score de readiness. Seus relatórios especializados possuem contratos próprios fora de `report-catalog/` e não são superfícies audit-owned da execução `rasai audit`. Quando `scoring_version` é incompatível entre baseline/current, a comparação de score deve permanecer `NOT_COMPARABLE`; nenhum conversor silencioso é permitido.

## Plataforma do produto - Windows primeiro, preparada para SaaS

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

A arquitetura alvo para SaaS usa control plane PostgreSQL e workers Linux/containerizados. O runtime Windows local permanece um alvo operacional do produto, enquanto IDs/filenames estáveis, manifests, schemas versionados, persistência histórica imutável e metadados API-friendly sustentam a evolução para operação centralizada sem introduzir infraestrutura SaaS pesada no runtime desktop.

Detalhes: [docs/PRODUCT_PLATFORM_ARCHITECTURE.md](docs/PRODUCT_PLATFORM_ARCHITECTURE.md).

## Fonte de verdade e segurança

Princípios:

- `audit.db` + artefatos são evidência imutável da auditoria;
- `report-catalog/` é projeção reconstruível, não segunda fonte de verdade;
- `<AUD>/report/`, `<AUD>/report.html` e `<AUD>/remediation.html` não pertencem ao contrato de saída de `rasai audit`;
- superfície HTML presente não prova que a capacidade, API, provedor ou IA correspondente foi executada;
- sidecars e índices consolidados são derivados/reconstruíveis;
- secrets não devem ser persistidos em relatórios, SQLite, INI ou logs;
- resultados externos `NULL` não viram zero;
- nenhuma referência externa homologa automaticamente o SARI completo;
- nenhuma temporalidade isolada prova causalidade;
- relatórios preservam `scoring_version`; nesta fase de desenvolvimento, a única metodologia suportada é `SCORE-GEO-004`.

## Documentação principal

- [docs/CATALOG_AND_REPORT_SURFACES.md](docs/CATALOG_AND_REPORT_SURFACES.md)
- [docs/REPORT_GUIDE.md](docs/REPORT_GUIDE.md)
- [docs/OUTPUTS_AND_ARTIFACTS.md](docs/OUTPUTS_AND_ARTIFACTS.md)
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)
- [docs/EXECUTION_SCHEDULING.md](docs/EXECUTION_SCHEDULING.md)
- [docs/SCORE_GEO_004.md](docs/SCORE_GEO_004.md)
- [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md)
- [docs/SARI_READINESS_INDEX.md](docs/SARI_READINESS_INDEX.md)
- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/IMPROVEMENT_INTELLIGENCE.md](docs/IMPROVEMENT_INTELLIGENCE.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/MONITORING_OBSERVABILITY.md](docs/MONITORING_OBSERVABILITY.md)
- [docs/CONSOLIDATED_REPORTING.md](docs/CONSOLIDATED_REPORTING.md)
- [docs/CONSOLIDATED_REPORTING_VALIDATION.md](docs/CONSOLIDATED_REPORTING_VALIDATION.md)
- [docs/PRODUCT_PLATFORM_ARCHITECTURE.md](docs/PRODUCT_PLATFORM_ARCHITECTURE.md)
- [docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md](docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md) - avaliação arquitetural futura; não integra o contrato funcional vigente. Rastreabilidade: Issue #163.
- [docs/specification/00_SPEC_INDEX.md](docs/specification/00_SPEC_INDEX.md)

## Limite de validade

RASAi fornece auditoria técnica/semântica, evidência, heurísticas proprietárias, métricas externas separadas e suporte à decisão. Não garante ranking, citação, tráfego, conversão, conformidade integral ou causalidade de resultado externo.

<!-- rasai-doc-index-20260908 -->
## Contrato da documentação

A documentação está organizada em [`docs/README.md`](docs/README.md). O projeto está em desenvolvimento e validação; o **Método de Pontuação de Prontidão**, versão pública **001**, é a única metodologia vigente nesta fase; `SCORE-GEO-004` permanece como contrato técnico.
