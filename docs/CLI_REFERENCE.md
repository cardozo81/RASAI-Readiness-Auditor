# Referência da CLI

Referência operacional do **RASAI — Search & AI Readiness Auditor**.

## Entradas públicas

```text
rasai audit ...
rasai visibility import|report ...
rasai scoring dataset|calibrate|inspect ...
rasai monitor compare|impact|gate ...
rasai observe report|status|import|bing-import|gsc-search|gsc-inspect|crux-history ...
rasai observability ...                 # alias de `observe`
rasai-console
```

Os aliases legados `searchgeo`/`searchgeo-console` permanecem por compatibilidade, mas a identidade pública é RASAI.

## `audit`

Forma geral:

```powershell
rasai audit target [target ...] [opções]
```

`target` pode ser domínio ou URL HTTP(S). Também é possível usar `--urls-file PATH`.

### Entrada/contexto

| Opção | Uso |
|---|---|
| `target` | um ou mais domínios/URLs da mesma origem normalizada |
| `--urls-file PATH` | TXT UTF-8 com URL/domínio por linha |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas |
| `--audits-root PATH` | raiz dos workspaces; default `audits` |
| `--device-context mobile|desktop|both` | contexto de dispositivo |

Default público de dispositivo: `mobile`. Override de ambiente: `SEARCHGEO_DEVICE_CONTEXT`.

## SARI-001 / SCORE-GEO-003

Novas auditorias usam `SCORE-GEO-003`. `SCORE-GEO-002` é histórico e não existe fallback silencioso para ele.

Artifact padrão de modelo:

```text
.searchgeo/scoring/score-geo-003-model.json
```

Override:

```text
SEARCHGEO_SCORE_GEO_003_MODEL
```

As dimensões permanecem evidence-bound. `OVERALL_READINESS` só é materializado conforme o contrato/model artifact vigente; se os gates não forem atendidos, permanece não consolidado/limitado.

### Dataset pré-fit

```powershell
rasai scoring dataset `
  --audits-root audits `
  --dataset-version GEO-CAL-001
```

O comando inspeciona a suficiência da base antes do fitting, gera manifest/fingerprint e expõe gates de domínios, engines, queries, repetições, dias e observações. `READY_FOR_MODEL_FIT` não significa `VALIDATED`.

### Calibrar

```powershell
rasai scoring calibrate `
  --audits-root audits `
  --dataset-version GEO-CAL-001 `
  --output .searchgeo\scoring\score-geo-003-model.json
```

O calibrador lê `AUD-*/audit.db` e query-runs observados elegíveis; não chama website nem engine durante o fitting. Dataset insuficiente produz artifact `EXPERIMENTAL`, que não deve consolidar Overall como validado.

### Inspecionar modelo

```powershell
rasai scoring inspect
rasai scoring inspect --model .searchgeo\scoring\score-geo-003-model.json
```

Exibe status, model/dataset version, engines, Confidence de calibração e SHA-256.

## IA no `audit`

Seleção: `--ai-provider`.

Valores públicos suportados pelo registry/CLI incluem:

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

AUTO permanece limitado à cadeia configurada para providers elegíveis. Providers adicionais exigem seleção explícita quando assim definido pelo registry.

Modelo explícito: `--ai-model MODEL_ID`. Não usar `--ai-model` com `auto` quando AUTO resolve modelo por provider.

Timeout principal: `SEARCHGEO_AI_TIMEOUT_SECONDS`; default atual `180` segundos por tentativa.

### Remediação textual por IA

```text
--ai-content-remediation
--no-ai-content-remediation
```

Default OFF. Advisory/evidence-bound; não altera automaticamente SARI/SCORE-GEO.

### Remediação técnica de crawling por IA

```text
--ai-technical-remediation
--no-ai-technical-remediation
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Default OFF. Precedência: CLI explícito > ambiente > OFF. Valores booleanos de ambiente: `true/false`, `1/0`, `yes/no`, `on/off`.

## Web Performance

```text
--web-performance / --no-web-performance
--web-performance-max-pages N
--web-performance-timeout-seconds SECONDS
--web-performance-field-source auto|pagespeed|crux|none
--lighthouse-categories performance,accessibility,best-practices,seo
```

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

Default de coleta externa: OFF. Lab e field data permanecem separados e não entram automaticamente em `SCORE-GEO-003`.

## Synthetic Navigation Apdex

```text
--synthetic-apdex / --no-synthetic-apdex
--apdex-threshold-seconds SECONDS
--apdex-samples-per-context N
--apdex-max-attempts-per-context N
--apdex-max-pages N
--apdex-timeout-seconds SECONDS
--apdex-delay-seconds SECONDS
--apdex-concurrency 1|2
```

Default OFF. `T` é obrigatório quando habilitado. Variáveis equivalentes usam prefixo `SEARCHGEO_APDEX_`/`SEARCHGEO_SYNTHETIC_APDEX` conforme `ENVIRONMENT_VARIABLES.md`.

## Synthetic User Experience Apdex

```text
--apdex-experience / --no-apdex-experience
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

Default OFF. Quando habilitado, `device-mix` deve somar 100. Continua sintético; não se torna RUM.

Calibração Dynatrace quando suportada:

```text
--apdex-dynatrace-import
--dynatrace-base-url URL
--dynatrace-application-id ID
--apdex-dynatrace-config-json PATH
```

Página: `report/apdex-experience.html`.

## Observed Generative Visibility (`visibility`)

Atua sobre `AUD-*` existente e não faz parte do scoring automático.

### Importar

```powershell
rasai visibility import `
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

Métodos de captura suportados:

```text
MANUAL_TRANSCRIPTION
NORMALIZED_EXPORT
CONTROLLED_PROTOCOL
EXTERNAL_AUTOMATION
```

A importação preserva artifact/SHA-256, exige URLs compatíveis com a origem auditada e não recalcula SARI/SCORE-GEO. Query-runs controlados elegíveis podem alimentar calibração posterior.

### Report

```powershell
rasai visibility report --audit-id AUD-... --audits-root audits
```

Página: `report/ai-visibility.html`.

## RASAI Monitor

Monitoring é read-only sobre os `audit.db` fonte.

### Compare

```powershell
rasai monitor compare `
  --audits-root audits `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT
```

Opcional: `--report-root PATH`.

Gera `MON-*/report.html` + `manifest.json`. Classificações incluem `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `UNCHANGED`, `DATA_UNAVAILABLE` e `NOT_COMPARABLE` conforme aplicável.

### Impact

```powershell
rasai monitor impact `
  --audits-root audits `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT
```

Gera também `impact.html` quando aplicável. O resultado usa linguagem de **associação temporal**, nunca causalidade automática.

### Release gate

```powershell
rasai monitor gate `
  --audits-root audits `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT
```

Opções:

```text
--include-semantic
--max-high-regressions N          # default 0
--max-medium-regressions N        # default 3
--dimension-drop-points POINTS    # default 5.0
```

Exit codes:

```text
0 PASS
1 regressão bloqueante
2 erro de execução/configuração
```

Por padrão o gate é determinístico; regras semânticas/LLM não bloqueiam release sem `--include-semantic`.

## Search & AI Observability (`observe`)

Alias: `rasai observability ...`.

Todas as operações apontam para um AUD existente:

```text
--audits-root audits
--audit AUD-...|PATH
```

Dados externos ficam em `observability.db` + `artifacts/observability/`; `audit.db` não é migrado.

### Status

```powershell
rasai observe status --audit AUD-...
```

### Gerar report

```powershell
rasai observe report --audit AUD-...
```

Página: `report/observability.html`.

### Importar contrato genérico

```powershell
rasai observe import --audit AUD-... --file observability.json
```

Contrato: `RASAI-OBS-IMPORT-001`.

### Importar Bing Search Performance

```powershell
rasai observe bing-import `
  --audit AUD-... `
  --file bing-search-performance.csv `
  [--surface SURFACE]
```

Import-first: o RASAI não inventa endpoint nem faz scraping do portal quando não existe contrato direto implementado/documentado.

### Google Search Console Search Analytics

```powershell
rasai observe gsc-search `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31 `
  [--search-type web] `
  [--max-rows 100000]
```

Bearer token é lido por default de:

```text
GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

Override do nome da variável: `--token-env NAME`.

### Google URL Inspection

```powershell
rasai observe gsc-inspect `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  [--max-urls 25] `
  [--language-code pt-BR]
```

`--max-urls` protege quota. As URLs vêm do `audit.db` fonte em modo read-only.

### CrUX History

```powershell
rasai observe crux-history `
  --audit AUD-... `
  --target https://example.com/ `
  --scope url `
  [--form-factor PHONE|DESKTOP|TABLET] `
  [--periods 40]
```

API key é lida de `SEARCHGEO_CRUX_API_KEY` por default; `--key-env NAME` permite outro nome de variável.

## Credenciais de observability

Credenciais nunca são persistidas no sidecar/report.

```text
GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN   # OAuth bearer token em runtime
SEARCHGEO_CRUX_API_KEY               # CrUX History/direct CrUX
```

## Exemplos rápidos

### Auditoria sem IA

```powershell
rasai audit https://example.com --ai-provider none --device-context mobile
```

### Monitorar duas auditorias

```powershell
rasai monitor compare --baseline AUD-OLD --current AUD-NEW
```

### Gerar observability sem APIs externas

```powershell
rasai observe report --audit AUD-NEW
```

### Inspecionar suficiência de calibração

```powershell
rasai scoring dataset --dataset-version GEO-CAL-001
```

## Console interativo

```powershell
rasai-console
```

O console mantém configurações não sensíveis em `rasai-console.ini`. Secrets não são gravados no INI.

Monitoring, observability e calibração são superfícies especializadas da CLI nesta versão; não devem ser interpretadas como execução automática em toda auditoria.

Consulte também:

- `MONITORING_OBSERVABILITY.md`;
- `CONFIGURATION.md`;
- `ENVIRONMENT_VARIABLES.md`;
- `SCORE_GEO_003.md`;
- `INTERACTIVE_CONSOLE.md`;
- `specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md`;
- `specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`;
- `specification/26_OBSERVED_GENERATIVE_VISIBILITY.md`.
