# Referência da CLI

Referência operacional do **RASAi - Search & AI Readiness Auditor**.

## Entradas públicas

```text
rasai audit ...
rasai search ...
rasai search-history ...
rasai search-monitor ...
rasai visibility import|report ...
rasai scoring inspect
rasai monitor compare|impact|gate ...
rasai observe ...
rasai observability ...
rasai quality report|verify|timeline ...
rasai platform ...
rasai-console
```

## Opções globais

- `-h`, `--help` - ajuda da superfície/comando.
- `--version` - identificador técnico do pacote.
- `--config PATH` - arquivo TOML quando suportado pela superfície.

## `audit`

Forma geral:

```powershell
rasai audit target [target ...] [opções]
```

### Entrada e contexto

| Opção | Uso |
|---|---|
| `target` | domínio/URL HTTP(S) |
| `--urls-file PATH` | TXT UTF-8 com URL/domínio por linha |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas |
| `--audits-root PATH` | raiz dos workspaces; default `audits` |
| `--device-context` | `mobile`, `desktop` ou `both` |
| `--ai-provider` | `none`, provider explícito ou `auto` |
| `--ai-model MODEL_ID` | override de modelo para provider explícito |

Default de dispositivo: `mobile`. Override: `RASAI_DEVICE_CONTEXT`.

## SARI-001 / SCORE-GEO-004

A metodologia vigente é `SCORE-GEO-004`; a identidade pública do índice é `SARI-001`.

Inspeção local do contrato:

```powershell
rasai scoring inspect
```

Relatórios canônicos:

```text
report/readiness.html
report/scoring.html
```

## IA no audit

Providers do registry:

```text
none
openai
deepseek
mimo
xai / grok
qwen
gemini
anthropic / claude
auto
```

`AI=auto` considera todos os providers registrados como elegíveis para AUTO que estejam aptos na execução. Aptidão exige credencial e configuração válidas. O runtime usa round-robin compartilhado entre necessidades, tenta cada provider no máximo uma vez por necessidade, remove imediatamente condições terminais e aplica circuit breaker para falhas temporárias.

O timeout principal é `RASAI_AI_TIMEOUT_SECONDS`, default 180 segundos por tentativa.

### Remediação textual

```text
--ai-content-remediation
--no-ai-content-remediation
RASAI_AI_CONTENT_REMEDIATION
```

Default OFF. A camada gera sugestões evidence-bound e não recalcula score.

### Remediação técnica

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

Default OFF. A IA técnica explica/remedia diagnósticos já determinados pelo runtime e permanece advisory.

### Contexto editorial / YMYL / E-E-A-T

Os campos `RASAI_CONTENT_*`, `RASAI_YMYL_CATEGORY`, `RASAI_PAGE_PURPOSE`, `RASAI_INTENDED_AUDIENCE`, `RASAI_EXPERIENCE_REQUIREMENT` e `RASAI_FRESHNESS_SENSITIVITY` aceitam configuração editorial contextual.

Quando um campo está em `auto` e IA está ligada, a configuração persistida continua `AUTO`. A IA pode produzir interpretação transitória para o relatório, baseada apenas no conteúdo/evidências fornecidos. Essa leitura não sobrescreve banco, não vira evidência determinística e não altera diretamente SARI/SCORE-GEO-004.

### Telemetria de IA

Cada chamada externa pode ser auditada em `report/ai-usage.html`. O runtime registra request/response sanitizados, provider/modelo, finalidade, duração, status, hashes e truncamento. Secrets e raciocínio privado do provider não são persistidos.

Controle de tamanho:

```text
RASAI_AI_EXCHANGE_LOG_MAX_BYTES
```

Default: 524288 bytes por lado da comunicação; faixa aceita pelo runtime: 4096 a 4194304.

Documentos:

- [AI_GUIDE.md](AI_GUIDE.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md)
- [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md)

## Web Performance

```text
--web-performance
--no-web-performance
--web-performance-max-pages N
--web-performance-timeout-seconds SECONDS
--web-performance-field-source auto|pagespeed|crux|none
--lighthouse-categories performance,accessibility,best-practices,seo
```

O adapter PageSpeed vigente aceita no RASAi as categorias:

```text
performance
accessibility
best-practices
seo
```

`agentic-browsing` não é enviado ao PageSpeed. Um eventual score Agentic depende de fonte/adaptador Lighthouse direto separado. Ausência de Agentic não é score zero e não invalida as categorias PageSpeed coletadas.

Variáveis principais:

```text
RASAI_WEB_PERFORMANCE
RASAI_WEB_PERFORMANCE_MAX_PAGES
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS
RASAI_WEB_PERFORMANCE_FIELD_SOURCE
RASAI_LIGHTHOUSE_CATEGORIES
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
```

Lab e field data permanecem separados e não entram automaticamente em SARI/SCORE-GEO-004.

## Synthetic Navigation Apdex

```text
--synthetic-apdex
--no-synthetic-apdex
--apdex-threshold-seconds SECONDS
--apdex-samples-per-context N
--apdex-max-attempts-per-context N
--apdex-max-pages N
--apdex-timeout-seconds SECONDS
--apdex-delay-seconds SECONDS
--apdex-concurrency 1|2
```

Default OFF. O threshold `T` é obrigatório quando habilitado.

## Synthetic User Experience Apdex

```text
--apdex-experience
--no-apdex-experience
--apdex-experience-samples N
--apdex-experience-max-attempts N
--apdex-experience-max-pages N
--apdex-experience-device-mix mobile=60,desktop=35,tablet=5
--apdex-experience-session-mode cold|warm
--apdex-experience-kpm KPM
--apdex-experience-satisfied-seconds SECONDS
--apdex-experience-frustrated-seconds SECONDS
--apdex-experience-errors
--no-apdex-experience-errors
--apdex-experience-error-scope navigation|first-party|all
--apdex-experience-settle-seconds SECONDS
--apdex-experience-delay-seconds SECONDS
--apdex-experience-concurrency 1|2
```

A superfície continua sintética, inclusive quando calibrada contra configuração Dynatrace.

O mix acima descreve a população sintética disponível no Synthetic User Experience Apdex, mas uma execução iniciada por `rasai audit` ou `rasai-console` é sempre limitada pelo `--device-context` do audit. `mobile` executa essa experiência sintética como 100% MOBILE; `desktop`, 100% DESKTOP; `both` usa somente MOBILE e DESKTOP e renormaliza os pesos configurados, descartando TABLET para essa execução. TABLET continua disponível como perfil sintético da experiência, mas ainda não é um `DeviceContext` canônico do core; portanto não deve ser tratado como mobile nem solicitado implicitamente por um audit mobile-only.

## Search Intelligence

### Observação pontual

```powershell
rasai search "termo" --domain cliente.example [opções]
```

Opções relevantes:

```text
--mode disabled|live|fixture
--provider PROVIDER
--depth N
--country CODE
--region TEXT
--language CODE
--device desktop|mobile
--competitive
--compare-content
--customer-url URL
--max-content-pages N
--ai-competitive
--ai-provider PROVIDER
--ymyl-mode AUTO|ON|OFF
--audit-workspace PATH
--dry-run
```

`NOT_FOUND_WITHIN_DEPTH` significa apenas que o domínio não foi observado na profundidade solicitada. Search Intelligence é non-scoring.

No `rasai-console`, quando termos SERP fazem parte da sessão, a etapa Search Intelligence integra o mesmo relógio de duração e o progresso global até a consolidação dos relatórios. As consultas são acompanhadas por termo. Erros do provider permanecem fail-open para a auditoria principal: o diagnóstico original é persistido e categorizado como limitação técnica ou de conta/negócio quando identificável (por exemplo crédito, autenticação/permissão ou quota/plano), o relatório geral é disponibilizado e sinaliza a limitação. O relatório Search destaca explicitamente a posição quando o domínio derivado da URL principal é encontrado.

### Histórico

```powershell
rasai search-history --baseline-workspace audits/AUD-BASELINE --current-workspace audits/AUD-CURRENT
```

Também pode operar por milestone e modos `AUTO`, `GOLDEN` ou `EXPLICIT`. Comparações só produzem delta numérico quando o contexto observado é compatível.

### Monitoramento recorrente

```text
rasai search-monitor query add ...
rasai search-monitor query list
rasai search-monitor query enable --query-id ID
rasai search-monitor query disable --query-id ID
rasai search-monitor run --query-id ID
rasai search-monitor run-due
rasai search-monitor history --query-id ID
rasai search-monitor report
```

O scheduler usa a Product Platform. Credenciais BYOK não são gravadas em schedules.

Documentos:

- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [SEARCH_INTELLIGENCE_HISTORY.md](SEARCH_INTELLIGENCE_HISTORY.md)
- [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md)

## Observed Generative Visibility

Import:

```powershell
rasai visibility import --audit-id AUD-... --audits-root audits --file observed-visibility.json
```

Report:

```powershell
rasai visibility report --audit-id AUD-... --audits-root audits
```

A importação preserva provenance/artifact e não recalcula scoring.

## RASAi Monitor

```text
rasai monitor compare ...
rasai monitor impact ...
rasai monitor gate ...
```

`compare` compara dois AUDs; `impact` descreve mudanças observadas em janelas compatíveis sem afirmar causalidade; `gate` aplica critérios de regressão configuráveis.

Exit codes do gate:

```text
0 PASS
1 regressão bloqueante
2 erro de execução/configuração
```

## Search & AI Observability

Comando principal:

```text
rasai observe ...
```

Alias:

```text
rasai observability ...
```

Subsuperfícies incluem `status`, `report`, `import`, `bing-import`, `google-ai-import`, `google-ai-control`, `gsc-sites`, `gsc-sitemaps`, `gsc-search`, `gsc-appearance`, `gsc-inspect` e `crux-history`.

Dados externos ficam em `observability.db` + `artifacts/observability/`; o `audit.db` histórico não é reescrito por essa camada.

## Quality timeline / verification

```text
rasai quality report ...
rasai quality verify ...
rasai quality timeline ...
```

Use as superfícies de quality para projeções e verificações que não devem modificar evidência histórica.

## Product Platform / SaaS

```text
rasai platform ...
```

A Product Platform gerencia Organization, Workspace, Project, Property, Environment, memberships/RBAC, jobs, schedules, milestones e usage ledger conforme o backend configurado.

SQLite continua disponível para operação local; PostgreSQL é o backend centralizado do control plane quando configurado.

## Console interativo

```text
rasai-console
```

O console monta os mesmos argumentos públicos da CLI, apresenta capacidade dos providers, exposição pré-execução, configuração editorial, Web Performance e demais opções suportadas. Secrets não são gravados no INI.

## API / execução remota

A Web/API e o console remoto possuem documentação própria porque autenticação, OIDC, control plane, jobs e workers são contratos de deployment diferentes da CLI local:

- [WEB_API_CLI.md](WEB_API_CLI.md)
- [WEB_API.md](WEB_API.md)
- [SAAS_CONTROL_PLANE.md](SAAS_CONTROL_PLANE.md)

## Princípios de segurança da CLI

- não materializar API keys ou bearer tokens em argumentos/documentação/logs;
- não transformar falha de provider externo em finding do website;
- não recalcular evidência histórica para apresentar dado externo novo;
- não misturar métricas externas com SARI sem contrato metodológico versionado;
- manter retries/fallbacks limitados e observáveis;
- exigir revisão humana para remediações de conteúdo ou crawling sugeridas por IA.