# Referência da CLI

Referência operacional do **RASAi - Search & AI Readiness Auditor**.

## Entradas públicas

```text
rasai audit ...
rasai visibility import|report ...
rasai scoring inspect
rasai monitor compare|impact|gate ...
rasai observe report|status|import|bing-import|google-ai-import|google-ai-control|gsc-sites|gsc-sitemaps|gsc-search|gsc-appearance|gsc-inspect|crux-history ...
rasai observability ...                 # alias de observe
rasai quality report|verify|timeline ...
rasai platform ...
rasai-console
```

## Opções globais

- `-h`, `--help` - ajuda da superfície/comando.
- `--version` - identificador técnico do pacote quando necessário para diagnóstico; não representa uma versão comercial divulgada do produto.
- `--config PATH` - arquivo de configuração do audit quando suportado pela CLI principal.

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

Default público de dispositivo: `mobile`. Override: `RASAI_DEVICE_CONTEXT`.

## SARI-001 / SCORE-GEO-004

As novas auditorias usam `SCORE-GEO-004`. O Overall é determinístico e usa média de igual peso das dimensões aplicáveis, condicionado aos gates de Coverage e Confidence. Não existe model artifact obrigatório no runtime 004.

Para inspecionar o contrato vigente:

```powershell
rasai scoring inspect
```

O comando mostra `scoring_version`, contrato de agregação, número de dimensões e gates. Não acessa rede, não cria dataset e não realiza fitting.

Fluxos `scoring dataset` / `scoring calibrate` e model artifacts `SCORE-GEO-003` pertencem ao método anterior de desenvolvimento 003 e **não são comandos do entrypoint atual do SCORE-GEO-004**.

Relatórios por AUD:

```text
report/readiness.html
report/scoring.html
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

Timeout principal: `RASAI_AI_TIMEOUT_SECONDS`, default atual 180 s por tentativa.

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
RASAI_AI_TECHNICAL_REMEDIATION
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

Contrato `OGV-IMPORT-001`. O artifact/SHA-256 é preservado e o import não recalcula scoring.

### Report

```powershell
rasai visibility report --audit-id AUD-... --audits-root audits
```

Página: `report/ai-visibility.html`.

## RASAi Monitor

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

Gera `impact.html`. Um único dataset mais recente é selecionado por fonte em cada AUD; históricos sobrepostos não são somados. Janelas são classificadas como alinhadas, parcialmente sobrepostas, não sobrepostas ou desconhecidas. Associação temporal só é emitida para períodos comparáveis e nunca afirma causalidade.

### Release gate

```powershell
rasai monitor gate --baseline AUD-BASELINE --current AUD-CURRENT
```

Gate default = BR-GEO determinísticas elegíveis + page state. Demais famílias exigem opt-in explícito:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
--max-high-regressions N          # default 0
--max-medium-regressions N        # default 3
--dimension-drop-points POINTS    # default 5.0
```

`--include-score-dimensions` compara dimensões persistidas e respeita `scoring_version`; contratos diferentes não são convertidos silenciosamente.

Exit codes:

```text
0 PASS
1 regressão bloqueante
2 erro de execução/configuração
```

## Search & AI Observability

Comando principal: `rasai observe`; alias `rasai observability`.

Base comum:

```text
--audits-root audits
--audit AUD-...|PATH
```

Dados externos são persistidos em `observability.db` + `artifacts/observability/`. O sidecar atual é `RASAI-OBS-002`, cuja identidade de observação é `(dataset_id, record_id)`. `audit.db` não é migrado.

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

### Google Generative AI Performance import-first

Search:

```powershell
rasai observe google-ai-import --audit AUD-... --file genai-search.csv --surface search
```

Discover:

```powershell
rasai observe google-ai-import --audit AUD-... --file genai-discover.csv --surface discover
```

RASAi persiste apenas os campos presentes no export. Não inventa clicks, CTR, position, query ou citation count. Search/Discover possuem provenance separada.

### Google GenAI control

```powershell
rasai observe google-ai-control --audit AUD-... --state INCLUDE
rasai observe google-ai-control --audit AUD-... --state EXCLUDE
rasai observe google-ai-control --audit AUD-... --state INHERIT
```

Opções adicionais:

```text
--source-label TEXT
--observed-at ISO-8601
```

É evidência observacional/manual e non-scoring.

### Search Console - propriedades

```powershell
rasai observe gsc-sites --audit AUD-...
```

Lista/persiste propriedades acessíveis e permission level.

### Search Console - sitemaps

```powershell
rasai observe gsc-sitemaps `
  --audit AUD-... `
  --site-url "sc-domain:example.com"
```

Persiste path, lastSubmitted, lastDownloaded, pending, warnings/errors e submitted counts. O campo deprecated `contents[].indexed` não é usado.

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

`--max-rows` é teto real da coleta; page size da API é limitado separadamente.

Bearer token default: `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`. Override: `--token-env NAME`.

### Search Console Search Appearance

```powershell
rasai observe gsc-appearance `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31
```

Usa a dimensão documentada `searchAppearance` e mantém source provenance separada do Search Analytics convencional.

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

API key default: `RASAI_CRUX_API_KEY`. Override: `--key-env NAME`.

## RASAi Quality

Quality é derivado/read-only e não cria outro readiness score.

### Audit Health / Evidence Confidence / Coverage / Prioridade

```powershell
rasai quality report --audit AUD-... --audits-root audits
```

Gera `report/quality.html` com:

- Audit Health;
- Evidence Confidence por finding;
- Operational Priority `P0`-`P3`;
- Coverage Map;
- `nosnippet`, `max-snippet`, `data-nosnippet`, `X-Robots-Tag`;
- Recommendation Validation.

### Fix Verification

```powershell
rasai quality verify `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT `
  [--url https://example.com/page] `
  [--rule BR-GEO-011]
```

Saída: `audits/verification/VER-*/report.html` por default.

Estados principais:

```text
FIXED
PARTIALLY_FIXED
NOT_FIXED
NOT_VERIFIABLE
```

### Evidence Timeline

```powershell
rasai quality timeline `
  --audits-root audits `
  [--domain example.com] `
  [--url https://example.com/page]
```

Saída: `audits/quality/TIMELINE-*/report.html` por default.

## Credenciais observacionais

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_CRUX_API_KEY
```

Tokens/keys são inputs de runtime e não são persistidos em sidecar/report.

## Console

```powershell
rasai-console
```

`rasai-console.ini` armazena somente configuração não sensível. Monitoring, observability, quality e platform permanecem superfícies especializadas da CLI na implementação atual.

## Referências internas

- `MONITORING_OBSERVABILITY.md`
- `CONFIGURATION.md`
- `ENVIRONMENT_VARIABLES.md`
- `SCORE_GEO_004.md`
- `SCORING_GUIDE.md`
- `INTERACTIVE_CONSOLE.md`
- `PRODUCT_PLATFORM_ARCHITECTURE.md`
- `specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md`
- `specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
- `specification/26_OBSERVED_GENERATIVE_VISIBILITY.md`
- `specification/27_MONITORING_OBSERVABILITY.md`
- `specification/28_AUDIT_QUALITY_VERIFICATION.md`
