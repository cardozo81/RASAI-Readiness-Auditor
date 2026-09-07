# Referência da CLI

Referência operacional da linha de comando do SearchGEO Readiness Auditor.

## Entrada principal

A superfície pública possui três fluxos:

```text
searchgeo [-h] [--version] [--config PATH] audit ...
searchgeo visibility import|report ...
searchgeo scoring calibrate|inspect ...
```

O router superior intercepta `visibility` e `scoring`; os demais comandos continuam delegados ao pipeline de auditoria existente.

Tokens canônicos do contrato público: `-h`, `--help`, `--version`, `--config PATH`.

Ajuda: `-h`, `--help`.

Versão: `--version`.

Configuração geral de aplicação/logging: `--config PATH`.

## Comando `audit`

Forma geral:

```powershell
searchgeo audit target [target ...] [opções]
```

`target` pode ser domínio ou URL HTTP(S). Também é possível usar `--urls-file PATH`.

## Entrada e contexto

| Opção | Uso |
|---|---|
| `target` | um ou mais domínios/URLs da mesma origem normalizada |
| `--urls-file PATH` | TXT UTF-8 com uma URL/domínio por linha |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | contexto de idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas auditadas |
| `--audits-root PATH` | diretório raiz dos workspaces; default `audits` |
| `--device-context` | `mobile`, `desktop` ou `both` |

Default de dispositivo: `mobile`.

Override por ambiente: `SEARCHGEO_DEVICE_CONTEXT`.

## Scoring padrão

Novas auditorias usam `SCORE-GEO-003` por padrão.

As dimensões continuam determinísticas. O `OVERALL_READINESS` exige um model artifact `VALIDATED`; sem ele, permanece `NOT_CONSOLIDATED` e não existe fallback silencioso para `SCORE-GEO-002`.

Artifact padrão:

```text
.searchgeo/scoring/score-geo-003-model.json
```

Override de localização:

```text
SEARCHGEO_SCORE_GEO_003_MODEL
```

### Calibrar SCORE-GEO-003

```powershell
searchgeo scoring calibrate `
  --audits-root audits `
  --dataset-version GEO-CAL-001 `
  --output .searchgeo\scoring\score-geo-003-model.json
```

`--dataset-version` é obrigatório e identifica o conjunto de calibração de forma versionada.

O calibrador lê apenas `AUD-*/audit.db`; não chama engines nem websites. Query-runs controlados elegíveis do Observed Generative Visibility fornecem o outcome `CITED/NOT_CITED`.

Se o dataset não atender ao promotion gate, o artifact é gravado como `EXPERIMENTAL` e **não** é usado para consolidar o Overall.

### Inspecionar model artifact

```powershell
searchgeo scoring inspect
```

Com path explícito:

```powershell
searchgeo scoring inspect --model .searchgeo\scoring\score-geo-003-model.json
```

O comando informa status, model version, dataset version, engines, Confidence da calibração e SHA-256.

Contrato e gates: [SCORE_GEO_003.md](SCORE_GEO_003.md).

## IA

Seleção: `--ai-provider`.

Valores aceitos pela superfície pública:

```text
none
openai
deepseek
mimo
auto
xai
grok
qwen
gemini
anthropic
claude
```

AUTO permanece limitado a:

```text
OpenAI -> DeepSeek -> MiMo
```

Providers adicionais são seleção explícita.

Modelo explícito: `--ai-model MODEL_ID`.

`--ai-model` não deve ser usado com `auto`; AUTO usa configuração por provider.

### Defaults públicos de modelo

Sem override explícito:

```text
OPENAI     gpt-5.6-luna
DEEPSEEK   deepseek-v4-flash
MIMO       mimo-v2.5
XAI        grok-4.6
QWEN       qwen3.8-flash
GEMINI     gemini-3.8-flash
ANTHROPIC  claude-sonnet-5
```

### Esforço/profundidade

O produto usa o menor esforço suportado quando o usuário não fornece override:

```text
OPENAI     NONE
DEEPSEEK   NONE
MIMO       NONE
XAI        LOW
QWEN       PROVIDER_DEFAULT
GEMINI     LOW
ANTHROPIC  LOW
```

Overrides de reasoning/thinking usam as variáveis específicas do provider expostas pelo registry/console quando suportadas.

### Timeout IA

`SEARCHGEO_AI_TIMEOUT_SECONDS`. Default público: `180` segundos por tentativa.

## Remediação textual por IA

```text
--ai-content-remediation
--no-ai-content-remediation
```

Default: OFF. A remediação exige provider de IA apto. É advisory/evidence-bound e não altera automaticamente o SearchGEO Readiness Index.

## Remediação técnica de rastreamento e descoberta por IA

```text
--ai-technical-remediation
--no-ai-technical-remediation
```

Default: OFF.

Variável equivalente: `SEARCHGEO_AI_TECHNICAL_REMEDIATION`.

Valores de ambiente aceitos: `true/false`, `1/0`, `yes/no`, `on/off`.

Precedência: argumento CLI explícito > variável de ambiente > OFF.

Essa opção não habilita os diagnósticos determinísticos de rastreamento e descoberta; eles já executam no pipeline normal. Ela habilita somente explicação/remediação opcional por IA sobre diagnósticos persistidos.

A IA técnica:

- exige provider compatível/configurado;
- não altera `RuleExecution`, Finding, Score, Coverage, Confidence ou Consolidation;
- não decide automaticamente políticas de treinamento/crawler;
- não transforma `llms.txt` em requisito;
- exige revisão humana.

Página: `report/crawling-discovery.html`; telemetria pode aparecer em `report/ai-usage.html`.

## Web Performance / PageSpeed / Lighthouse / CrUX

Habilitação:

```text
--web-performance
--no-web-performance
```

Default: OFF.

Limite: `--web-performance-max-pages N`. `0` significa todas as páginas auditadas, respeitando o limite geral.

Timeout: `--web-performance-timeout-seconds SECONDS`. Default: `120` segundos.

Variável: `SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS`.

Field data: `--web-performance-field-source auto|pagespeed|crux|none`. Default: `auto`. `crux` direto exige `SEARCHGEO_CRUX_API_KEY`.

Categorias Lighthouse: `--lighthouse-categories performance,accessibility,best-practices,seo`.

Variáveis relacionadas:

```text
SEARCHGEO_WEB_PERFORMANCE
SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES
SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS
SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE
SEARCHGEO_LIGHTHOUSE_CATEGORIES
SEARCHGEO_PAGESPEED_API_KEY
SEARCHGEO_CRUX_API_KEY
```

Esses indicadores permanecem domínios próprios e não entram diretamente no Overall `SCORE-GEO-003`.

## Synthetic Navigation Apdex

Habilitação:

```text
--synthetic-apdex
--no-synthetic-apdex
```

Default: OFF.

Parâmetros:

- `--apdex-threshold-seconds SECONDS`: `T`, obrigatório quando habilitado;
- `--apdex-samples-per-context N`: default `100`;
- `--apdex-max-attempts-per-context N`: default `ceil(1.25 × alvo)`;
- `--apdex-max-pages N`: default `1`; `0` usa todas dentro do limite geral;
- `--apdex-timeout-seconds SECONDS`: deve ser `> 4T`; default `max(45, 4T + 5)`;
- `--apdex-delay-seconds SECONDS`: default `1`;
- `--apdex-concurrency N`: `1` ou `2`, default `1`.

Variáveis equivalentes:

```text
SEARCHGEO_SYNTHETIC_APDEX
SEARCHGEO_APDEX_THRESHOLD_SECONDS
SEARCHGEO_APDEX_SAMPLES_PER_CONTEXT
SEARCHGEO_APDEX_MAX_ATTEMPTS_PER_CONTEXT
SEARCHGEO_APDEX_MAX_PAGES
SEARCHGEO_APDEX_TIMEOUT_SECONDS
SEARCHGEO_APDEX_DELAY_SECONDS
SEARCHGEO_APDEX_CONCURRENCY
```

## Synthetic User Experience Apdex

Habilitação:

```text
--apdex-experience
--no-apdex-experience
```

Default: OFF. É um segundo domínio Apdex, sintético e calibrável. Não substitui Synthetic Navigation Apdex e não representa RUM.

Principais parâmetros:

```text
--apdex-experience-samples N
--apdex-experience-max-attempts N
--apdex-experience-max-pages N
--apdex-experience-device-mix mobile=60,desktop=35,tablet=5
--apdex-experience-session-mode cold|warm
--apdex-experience-kpm KPM
--apdex-experience-satisfied-seconds SECONDS
--apdex-experience-frustrated-seconds SECONDS
--apdex-experience-errors / --no-apdex-experience-errors
--apdex-experience-error-scope navigation|first-party|all
--apdex-experience-settle-seconds SECONDS
--apdex-experience-delay-seconds SECONDS
--apdex-experience-concurrency 1|2
```

Quando habilitado, `device-mix` deve somar 100.

### Calibração Dynatrace

```text
--apdex-dynatrace-import
--dynatrace-base-url URL
--dynatrace-application-id ID
--apdex-dynatrace-config-json PATH
```

O import alinha KPM/thresholds/política quando suportado. O resultado continua sintético; não se torna RUM.

Página: `report/apdex-experience.html`.

## Observed Generative Visibility

Observed Generative Visibility não é parte do comando `audit`; atua sobre workspace `AUD-*` existente e importa outcomes observados.

### Importar dataset

```powershell
searchgeo visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Contrato: `OGV-IMPORT-001`.

Fontes iniciais:

```text
BING_WEBMASTER_TOOLS_AI_PERFORMANCE
CONTROLLED_QUERY_RUNS
```

`source.capture_method` obrigatório:

```text
MANUAL_TRANSCRIPTION
NORMALIZED_EXPORT
CONTROLLED_PROTOCOL
EXTERNAL_AUTOMATION
```

Regras:

- JSON UTF-8 válido;
- URLs do `normalized_origin` da auditoria;
- artifact preservado com SHA-256;
- reimport idempotente;
- métricas Bing permanecem source-reported;
- Citation Presence Rate somente sobre runs `VALID`;
- runs `INVALID` fora do denominador;
- rank exige `ranking_semantics`;
- a importação não recalcula o SGRI nem o score do AUD fonte;
- `CONTROLLED_QUERY_RUNS` elegíveis podem alimentar posteriormente `searchgeo scoring calibrate`.

### Regenerar report

```powershell
searchgeo visibility report `
  --audit-id AUD-... `
  --audits-root audits
```

Página: `report/ai-visibility.html`.

Observed Generative Visibility é import-first: não faz scraping de Bing Webmaster Tools e não presume endpoint não documentado.

Contrato completo: [specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).

## Exemplos

### Sem IA

```powershell
searchgeo audit https://example.com `
  --ai-provider none `
  --device-context mobile
```

### OpenAI explícito

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-model gpt-5.6-luna
```

### Remediação técnica de rastreamento e descoberta por IA

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-technical-remediation
```

### Web Performance

```powershell
searchgeo audit https://example.com `
  --web-performance `
  --web-performance-timeout-seconds 120 `
  --web-performance-field-source auto
```

### Synthetic Navigation Apdex de smoke

```powershell
searchgeo audit https://example.com `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-concurrency 1
```

### Importar visibilidade observada

```powershell
searchgeo visibility import `
  --audit-id AUD-EXEMPLO `
  --file .\observed-visibility.json
```

### Calibrar SCORE-GEO-003

```powershell
searchgeo scoring calibrate --dataset-version GEO-CAL-001
```

## Console interativo

```powershell
searchgeo-console
```

O console configura a superfície principal da auditoria com parâmetros não sensíveis em `searchgeo-console.ini`, progresso, preflight e atalhos. Secrets não são gravados no INI.

Observed Generative Visibility e calibração `SCORE-GEO-003` permanecem superfícies CLI separadas nesta versão; não devem ser presumidas como coleta/treinamento automático no menu da auditoria.

Consulte [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONFIGURATION.md](CONFIGURATION.md), [SCORE_GEO_003.md](SCORE_GEO_003.md), [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md), [specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md](specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md) e [specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).
