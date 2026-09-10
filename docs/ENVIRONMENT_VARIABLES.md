# Variáveis de ambiente - referência completa

Referência operacional da superfície de variáveis reconhecida pelo RASAi - Search & AI Readiness Auditor.

Verificação documental: **2026-09-10**.

Variáveis de ambiente são overrides avançados. Quando existe default seguro, o runtime aplica o valor sem exigir materialização no sistema operacional. Secrets não devem ser gravados em `rasai-console.ini`, arquivos de URL, reports, bancos ou logs.

## 1. Aplicação e execução

| Variável | Default / domínio | Finalidade |
|---|---|---|
| `RASAI_CONSOLE_INI` | `rasai-console.ini` | caminho do arquivo INI persistente do console |
| `RASAI_CONFIG` | opcional | TOML geral |
| `RASAI_CONSOLE_MODE` | `local` | console local ou cliente remoto |
| `RASAI_LOG_LEVEL` | `INFO` | verbosidade |
| `RASAI_DEVICE_CONTEXT` | `mobile` | `mobile`, `desktop`, `both` |
| `RASAI_AI_TIMEOUT_SECONDS` | `180` | timeout por tentativa de IA |
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | remediação de conteúdo por IA |
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | remediação técnica por IA |
| `RASAI_AI_EXCHANGE_LOG_MAX_BYTES` | `524288` | limite por request/response sanitizado; faixa 4096..4194304 |

## 2. IA - credenciais

Cada provider usa sua própria credencial: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `MIMO_API_KEY`, `XAI_API_KEY`, `DASHSCOPE_API_KEY`, `GEMINI_API_KEY` ou `ANTHROPIC_API_KEY`.

A presença da credencial não prova crédito, quota, plano ou acesso ao modelo. Em `AI=auto`, somente providers registrados como elegíveis e com configuração válida entram no pool daquela execução.

## 3. IA - modelos e reasoning

| Variável | Default efetivo |
|---|---|
| `RASAI_OPENAI_MODEL` | `gpt-5.6-luna` |
| `RASAI_OPENAI_REASONING_EFFORT` | `NONE` |
| `RASAI_DEEPSEEK_MODEL` | `deepseek-v4-flash` |
| `RASAI_DEEPSEEK_REASONING_EFFORT` | `NONE` |
| `RASAI_MIMO_MODEL` | `mimo-v2.5` |
| `RASAI_MIMO_REASONING_EFFORT` | `NONE` |
| `RASAI_XAI_MODEL` | `grok-4.6` |
| `RASAI_XAI_REASONING_EFFORT` | `LOW` |
| `RASAI_QWEN_MODEL` | `qwen3.8-flash` |
| `RASAI_GEMINI_MODEL` | `gemini-3.8-flash` |
| `RASAI_GEMINI_REASONING_EFFORT` | `LOW` |
| `RASAI_ANTHROPIC_MODEL` | `claude-sonnet-5` |
| `RASAI_ANTHROPIC_REASONING_EFFORT` | `LOW` |

Qwen usa `PROVIDER_DEFAULT` para reasoning no adapter vigente.

### Política AUTO

`AI=auto` não é uma cadeia fixa. O runtime consulta o provider registry e usa todos os providers `auto_eligible` aptos. A seleção usa round-robin entre necessidades de IA, uma tentativa por provider por necessidade e circuit breaker por execução. Falhas terminais retiram o provider imediatamente; falhas temporárias abrem o breaker ao atingir três falhas entre as últimas cinco observações.

Detalhes: [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## 4. IA - endpoints avançados

Overrides de endpoint existem para providers que os expõem, incluindo `RASAI_XAI_ENDPOINT`, `RASAI_QWEN_ENDPOINT`, `RASAI_GEMINI_ENDPOINT` e `RASAI_ANTHROPIC_ENDPOINT`. Mantenha os endpoints default no uso normal; endpoint incorreto pode causar falha ou envio de dados ao destino errado.

## 5. IA - contexto editorial / YMYL

Defaults: `auto`.

| Variável | Valores principais |
|---|---|
| `RASAI_CONTENT_RISK_PROFILE` | `auto`, `standard`, `ymyl` |
| `RASAI_YMYL_CATEGORY` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` |
| `RASAI_PAGE_PURPOSE` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` |
| `RASAI_INTENDED_AUDIENCE` | `auto`, `general`, `professional`, `mixed` |
| `RASAI_EXPERIENCE_REQUIREMENT` | `auto`, `required`, `beneficial`, `not-expected` |
| `RASAI_FRESHNESS_SENSITIVITY` | `auto`, `low`, `medium`, `high` |
| `RASAI_CONTENT_ORIGIN` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` |

Um campo configurado como `auto` permanece `AUTO` no estado persistido. Com IA ligada, o HTML pode exibir separadamente uma interpretação transitória baseada no conteúdo/evidências enviados. Essa leitura não sobrescreve o banco, não vira evidência determinística e não altera diretamente SARI-001/SCORE-GEO-004.

Detalhes: [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md) e [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md).

## 6. Web Performance / Google APIs

| Variável | Default / domínio | Finalidade |
|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` | habilita coleta externa |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | teto de páginas; `0=todas` |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | timeout por request |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo` | categorias solicitadas ao PageSpeed |
| `RASAI_PAGESPEED_API_KEY` | sem default | PageSpeed Insights |
| `RASAI_CRUX_API_KEY` | sem default | CrUX direto |

O transporte PageSpeed vigente aceita somente `performance`, `accessibility`, `best-practices` e `seo`. `agentic-browsing` exige fonte Lighthouse direta separada e não deve ser enviado no request PageSpeed. O campo compatível pode permanecer `NULL` enquanto não existir fonte apropriada.

Detalhes: [LIGHTHOUSE_CATEGORIES.md](LIGHTHOUSE_CATEGORIES.md) e [LIGHTHOUSE_PAGESPEED_TRANSPORT.md](LIGHTHOUSE_PAGESPEED_TRANSPORT.md).

## 7. Synthetic Navigation Apdex

Variáveis principais:

```text
RASAI_SYNTHETIC_APDEX
RASAI_APDEX_THRESHOLD_SECONDS
RASAI_APDEX_SAMPLES_PER_CONTEXT
RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT
RASAI_APDEX_MAX_PAGES
RASAI_APDEX_TIMEOUT_SECONDS
RASAI_APDEX_DELAY_SECONDS
RASAI_APDEX_CONCURRENCY
```

Default OFF. O threshold `T` é obrigatório quando habilitado. Consulte [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md).

## 8. Synthetic User Experience Apdex

O recurso permanece default OFF. Quando habilitado sem override manual ou importação Dynatrace, o runtime aplica um baseline Dynatrace-compatible apenas onde existe mapeamento tecnicamente defensável.

| Variável | Default / regra | Origem |
|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | RASAi |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 × samples)` | RASAi derivado |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | `1` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | RASAi; sem default equivalente em RUM |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | RASAi; sem equivalente 1:1 em RUM |
| `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | fallback executável compatível; Dynatrace Load prefere `VISUALLY_COMPLETE` |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3.0` | referência/fallback Dynatrace Load |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12.0` | referência/fallback Dynatrace Load |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | alinhado à semântica Dynatrace de erros frustrantes |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | RASAi conservador; Dynatrace usa regras mais granulares |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | `1` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | `1` | RASAi sintético |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | RASAi |
| `RASAI_DYNATRACE_BASE_URL` | sem default | somente importação live |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | somente importação live |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | importação offline/reproduzível |
| `DYNATRACE_API_TOKEN` | secret; sem default | somente ambiente; nunca persistido |

O Dynatrace documenta `VISUALLY_COMPLETE` como KPM primária para Load Action, mas o RASAi não declara equivalência de fornecedor para essa métrica. O baseline executável usa `USER_ACTION_DURATION` com 3 s / 12 s, também utilizado como fallback quando a configuração Dynatrace importada fornece thresholds de fallback. XHR e Custom Actions autônomas exigiriam scripted journeys/clickpaths e não são inventadas a partir da navegação do crawler.

Consulte [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## 9. Search Intelligence / Observability

| Variável | Default / regra | Finalidade |
|---|---|---|
| `RASAI_SERP_MODE` | `disabled` | modo global de observação SERP |
| `RASAI_SERP_PROVIDER` | `serpapi` | adapter de Search live |
| `RASAI_SERPAPI_API_KEY` | secret; sem default | credencial BYOK SerpApi |
| `RASAI_SERP_FIXTURE_PATH` | sem default | fixture quando o modo é `fixture` |
| `RASAI_SERP_MAX_QUERIES` | `10` | teto de queries por execução |
| `RASAI_SERP_MAX_REQUESTS` | `10` | orçamento máximo de tentativas do provider |
| `RASAI_SERP_MAX_DEPTH` | `20` | profundidade máxima observada |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | teto de concorrentes derivados |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | timeout por request Search |
| `RASAI_SERP_RETRIES` | `1` | retries do Search provider |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | intervalo mínimo entre requests |
| `RASAI_SEARCH_AI_PROVIDER` | `none` | provider da análise competitiva por IA |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | secret; sem default | OAuth bearer temporário do Google Search Console |

Search Intelligence permanece separado de SARI-001/SCORE-GEO-004. Consulte [SERP_OBSERVATION.md](SERP_OBSERVATION.md), [SEARCH_INTELLIGENCE_HISTORY.md](SEARCH_INTELLIGENCE_HISTORY.md) e [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md).

## 10. Control plane / SaaS

| Variável | Regra |
|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | default `sqlite`; aceita `sqlite` ou `postgresql` |
| `RASAI_PLATFORM_DATABASE_URL` | requerida quando backend=`postgresql` |

SQLite permanece disponível para operação local. PostgreSQL é o backend centralizado do control plane quando configurado.

## 11. Web API / Identity

| Variável | Default / regra | Finalidade |
|---|---|---|
| `RASAI_API_DOCS_ENABLED` | `false` | habilita documentação interativa da API |
| `RASAI_API_AUDITS_ROOT` | `audits` | raiz de auditorias usada pela Web API |
| `RASAI_API_AUTH_MODE` | `deny` | `deny`, `trusted-header` ou `oidc` |
| `RASAI_API_TRUSTED_USER_HEADER` | `x-rasai-user-id` | header de identidade no modo trusted-header |
| `RASAI_OIDC_ISSUER` | requerido no modo OIDC | issuer HTTPS |
| `RASAI_OIDC_CLIENT_ID` | requerido no modo OIDC | client ID |
| `RASAI_OIDC_AUDIENCE` | client ID configurado | audience esperada do JWT |
| `RASAI_OIDC_REDIRECT_URI` | requerido no fluxo OIDC web | redirect URI |
| `RASAI_OIDC_SESSION_SECRET` | secret; requerido no OIDC web | HMAC da sessão |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | opcional | nome da variável que contém o client secret real |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | algoritmos JWT aceitos |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | scopes solicitados |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | TTL da sessão web |

Valores terminados em `_ENV` que representam referência de segredo persistem o nome da variável, não o segredo em si. Consulte [WEB_API_FOUNDATION.md](WEB_API_FOUNDATION.md) e [WEB_API_CLI.md](WEB_API_CLI.md).

## 12. Remote control plane

Variáveis principais:

```text
RASAI_REMOTE_BASE_URL
RASAI_REMOTE_TOKEN_ENV
RASAI_REMOTE_USER_ID
RASAI_REMOTE_TIMEOUT_SECONDS
```

O timeout default é 30 segundos. `RASAI_REMOTE_USER_ID` pertence apenas ao modo trusted-header de desenvolvimento em loopback.

## 13. Browser / Playwright

```text
RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE
RASAI_BROWSER_LOCALE
```

Locale default: `pt-BR`.

## Telemetria e segurança de IA

`ai_exchange_log` pode conter conteúdo/evidências da página efetivamente enviados ao provider, por isso o workspace deve ser tratado como artefato potencialmente sensível. O recorder remove credenciais, headers de autenticação, parâmetros de segredo e campos reconhecidos como raciocínio privado antes da persistência.

A interpretação editorial transitória de campos `auto` também é removida do exchange log persistido e materializada apenas na seção interpretativa do HTML final.

Detalhes: [AI_RUNTIME_SECURITY.md](AI_RUNTIME_RUNTIME_SECURITY.md) e [REPORTING_AI_USAGE.md](REPORTING_AI_USAGE.md).

## Defaults operacionais principais

```text
console mode                   = local
device                         = mobile
ai provider                    = none
ai timeout                     = 180 s
ai content remediation         = false
ai technical remediation       = false
ai exchange log max bytes      = 524288
web performance                = false
web performance max pages      = 10
web performance timeout        = 120 s
field source                   = auto
lighthouse categories          = performance,accessibility,best-practices,seo
synthetic navigation apdex     = false
synthetic experience apdex     = false
experience kpm                 = USER_ACTION_DURATION
experience satisfied           = 3.0 s
experience frustrated          = 12.0 s
experience errors affect       = true
experience error scope         = first-party
experience samples             = 100
experience device mix          = mobile=60,desktop=35,tablet=5
experience session             = cold
SERP mode                      = disabled
platform DB backend            = sqlite
API auth mode                  = deny
remote timeout                 = 30 s
browser locale                 = pt-BR
language                       = pt-BR
market                         = BR
max-pages                      = 100
audits-root                    = audits
```
