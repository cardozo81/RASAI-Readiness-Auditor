# Referência da CLI

Referência operacional do **RASAI — Search & AI Readiness Auditor**.

## Entradas públicas

```text
rasai audit ...
rasai visibility import|report ...
rasai scoring dataset|calibrate|inspect ...
rasai monitor compare|impact|gate ...
rasai observe report|status|import|bing-import|gsc-search|gsc-inspect|crux-history ...
rasai observability ...                 # alias de observe
rasai-console
```

Aliases legados `searchgeo` e `searchgeo-console` permanecem por compatibilidade.

## Opções globais

- `-h`, `--help` — ajuda da superfície/comando.
- `--version` — versão do RASAI quando exposta pelo router principal.
- `--config PATH` — arquivo de configuração do audit quando suportado pela CLI principal.

## `audit`

Forma geral:

```powershell
rasai audit target [target ...] [opções]
```

### Entrada/contexto

| Opção | Uso |
|---|---|
| `target` | domínio/URL HTTP(S) |
| `--urls-file PATH` | TXT UTF-8 com URL/domínio por linha |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas |
| `--audits-root PATH` | raiz de workspaces; default `audits` |
| `--device-context` | seleciona `mobile`, `desktop` ou `both` |
| `--ai-provider` | provider semântico: `none`, provider explícito ou `auto` |
| `--ai-model MODEL_ID` | modelo explícito quando compatível |

Default público de dispositivo: `mobile`. Override: `SEARCHGEO_DEVICE_CONTEXT`.

## SARI-001 / SCORE-GEO-003

Novas auditorias usam `SCORE-GEO-003`; `SCORE-GEO-002` é histórico e não existe fallback silencioso para a aritmética anterior.

Artifact padrão:

```text
.searchgeo/scoring/score-geo-003-model.json
```

Override: `SEARCHGEO_SCORE_GEO_003_MODEL`.

### Dataset pré-fit

```powershell
rasai scoring dataset --audits-root audits --dataset-version GEO-CAL-001
```

Avalia gates pré-fit e gera manifest/fingerprint. `READY_FOR_MODEL_FIT != VALIDATED`.

### Calibrar

```powershell
rasai scoring calibrate `
  --audits-root audits `
  --dataset-version GEO-CAL-001 `
  --output .searchgeo\scoring\score-geo-003-model.json
```

Fitting é offline sobre AUDs/query-runs elegíveis. Model validation/promotion continua dependente dos gates pós-fit, incluindo AUC/Brier.

### Inspecionar

```powershell
rasai scoring inspect
rasai scoring inspect --model .searchgeo\scoring\score-geo-003-model.json
```

## IA no audit

Providers expostos pelo registry/CLI incluem:

```text
none
openai
deepseek
mimo
auto
xai/grok
qwen
gemini
anthropic/claude
```

`AUTO` permanece limitado à cadeia habilitada/configurada. Provider explícito não deve ser invalidado por credencial ausente de provider não selecionado.

Timeout principal: `SEARCHGEO_AI_TIMEOUT_SECONDS`, default atual 180 s por tentativa.

### Remediação textual

```text
--ai-content-remediation
--no-ai-content-remediation
```

Default OFF; advisory/non-scoring.

### Remediação técnica de crawling

```text
--ai-technical-remediation
--no-ai-technical-remediation
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Default OFF. Precedência: CLI explícito > ambiente > OFF.

## Web Performance

```text
--web-performance / --no-web-performance
--web-performance-max-pages N
--web-performance-timeout-seconds SECONDS
--web-performance-field-source auto|pagespeed|crux|none
--lighthouse-categories performance,accessibility,best-practices,seo
```

Variáveis principais:

```text
SEARCHGEO_WEB_PERFORMANCE
SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES
SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS
SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE
SEARCHGEO_LIGHTHOUSE_CATEGORIES
SEARCHGEO_PAGESPEED_API_KEY
SEARCHGEO_CRUX_API_KEY
```

Lab e field data permanecem separados e não entram automaticamente em SARI/SCORE-GEO-003.

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

Default OFF. `T` é obrigatório quando habilitado.

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

Continua sintético, inclusive quando calibrado contra configuração Dynatrace.

## Observed Generative Visibility

### Import

```powershell
rasai visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Contrato `OGV-IMPORT-001`. Fontes suportadas incluem dataset normalizado de Bing AI Performance e `CONTROLLED_QUERY_RUNS`. O artifact/SHA-256 é preservado; import não recalcula scoring.

### Report

```powershell
rasai visibility report --audit-id AUD-... --audits-root audits
```

Página: `report/ai-visibility.html`.

## RASAI Monitor

Todos os comandos são read-only sobre os `audit.db` fonte.

### Compare

```powershell
rasai monitor compare `
  --audits-root audits `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT
```

Opcional: `--report-root PATH`. Gera `MON-*/report.html` e `manifest.json`.

### Impact

```powershell
rasai monitor impact --baseline AUD-BASELINE --current AUD-CURRENT
```

Gera `impact.html`. Linguagem é associação temporal, nunca causalidade automática.

### Release gate

```powershell
rasai monitor gate --baseline AUD-BASELINE --current AUD-CURRENT
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

Gate default é deterministic-only.

## Search & AI Observability

Comando principal: `rasai observe`; alias `rasai observability`.

Base comum:

```text
--audits-root audits
--audit AUD-...|PATH
```

Dados externos são persistidos em `observability.db` + `artifacts/observability/`. `audit.db` não é migrado.

### Status/report

```powershell
rasai observe status --audit AUD-...
rasai observe report --audit AUD-...
```

Página: `report/observability.html`.

### Import genérico

```powershell
rasai observe import --audit AUD-... --file observability.json
```

Contrato: `RASAI-OBS-IMPORT-001`.

### Bing import-first

```powershell
rasai observe bing-import `
  --audit AUD-... `
  --file bing-search-performance.csv `
  [--surface SURFACE]
```

RASAI não inventa endpoint nem faz scraping do portal quando não existe contrato direto implementado/documentado.

### Search Console Search Analytics

```powershell
rasai observe gsc-search `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31 `
  [--search-type web] `
  [--max-rows 100000]
```

Bearer token default: `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`. Override do nome: `--token-env NAME`.

### URL Inspection

```powershell
rasai observe gsc-inspect `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  [--max-urls 25] `
  [--language-code pt-BR]
```

URLs vêm do audit fonte; `--max-urls` protege quota.

### CrUX History

```powershell
rasai observe crux-history `
  --audit AUD-... `
  --target https://example.com/ `
  --scope url `
  [--form-factor PHONE|DESKTOP|TABLET] `
  [--periods 40]
```

API key default: `SEARCHGEO_CRUX_API_KEY`. Override do nome: `--key-env NAME`.

## Credenciais observacionais

```text
GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
SEARCHGEO_CRUX_API_KEY
```

Tokens/keys são inputs de runtime e não são persistidos em sidecar/report.

## Console

```powershell
rasai-console
```

`rasai-console.ini` armazena somente configuração não sensível. Monitoring, observability e calibração permanecem superfícies especializadas da CLI nesta versão.

## Referências internas

- `MONITORING_OBSERVABILITY.md`
- `CONFIGURATION.md`
- `ENVIRONMENT_VARIABLES.md`
- `SCORE_GEO_003.md`
- `INTERACTIVE_CONSOLE.md`
- `specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md`
- `specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
- `specification/26_OBSERVED_GENERATIVE_VISIBILITY.md`
- `specification/27_MONITORING_OBSERVABILITY.md`
