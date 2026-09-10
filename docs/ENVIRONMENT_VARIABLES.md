# Variáveis de ambiente - referência completa

Referência operacional da superfície de variáveis reconhecida pelo RASAi - Search & AI Readiness Auditor.

Verificação documental: **2026-09-10**.

## Regra de uso

Variáveis de ambiente são uma camada de override avançado. Quando existe default seguro, o runtime o aplica sem exigir que a variável seja materializada no sistema operacional.

Não grave secrets em `rasai-console.ini`, arquivos de URL, artifacts, HTML, `audit.db`, `observability.db` ou logs. O console deve mostrar secrets apenas como `[SET]` e pode indicar a origem do valor sem revelar seu conteúdo.

Categorias do menu de ambiente:

```text
1. Aplicação e execução
2. IA - credenciais
3. IA - modelos e reasoning
4. IA - endpoints avançados
5. IA - contexto editorial / YMYL
6. Web Performance / Google APIs
7. Synthetic Apdex
8. Search Intelligence / Observability
9. Control plane / SaaS
10. Web API / Identity
11. Remote control plane
12. Browser / Playwright
```

## 1. Aplicação e execução

| Variável | Tipo / valores | Default efetivo | Finalidade |
|---|---|---|---|
| `RASAI_CONFIG` | caminho de arquivo existente | nenhum override obrigatório | aponta para TOML geral quando necessário |
| `RASAI_CONSOLE_MODE` | `local`, `remote` | `local` | seleciona console local ou cliente do control plane remoto |
| `RASAI_LOG_LEVEL` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG` | `INFO` | verbosidade do log |
| `RASAI_DEVICE_CONTEXT` | `mobile`, `desktop`, `both` | `mobile` | contexto de dispositivo |
| `RASAI_AI_TIMEOUT_SECONDS` | número finito `>0` | `180` | timeout por tentativa de IA |
| `RASAI_AI_CONTENT_REMEDIATION` | booleano | `false` | habilita remediação textual por IA |
| `RASAI_AI_TECHNICAL_REMEDIATION` | booleano | `false` | habilita remediação técnica evidence-bound de crawling/discovery |

`RASAI_CONSOLE_MODE=remote` não cria outro audit engine. O console remoto atua como cliente HTTP do control plane.

## 2. IA - credenciais

Nenhuma credencial possui default.

| Variável | Provider / finalidade |
|---|---|
| `OPENAI_API_KEY` | OpenAI |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `MIMO_API_KEY` | Xiaomi MiMo; o adapter usa chave PAYG compatível |
| `XAI_API_KEY` | xAI / Grok |
| `DASHSCOPE_API_KEY` | Alibaba Qwen |
| `GEMINI_API_KEY` | Google Gemini |
| `ANTHROPIC_API_KEY` | Anthropic Claude |
| `DYNATRACE_API_TOKEN` | importação live de configuração Dynatrace para Synthetic User Experience Apdex |
| `RASAI_PAGESPEED_API_KEY` | PageSpeed Insights API |
| `RASAI_CRUX_API_KEY` | Chrome UX Report API |
| `RASAI_SERPAPI_API_KEY` | SerpApi para Search Intelligence live |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | bearer OAuth do Google Search Console |
| `RASAI_PLATFORM_DATABASE_URL` | DSN PostgreSQL do control plane; pode conter credenciais e é tratado como secret |
| `RASAI_OIDC_SESSION_SECRET` | segredo HMAC da sessão Web/OIDC |

Referências de obtenção/configuração:

- OpenAI: <https://platform.openai.com/api-keys>
- DeepSeek: <https://api-docs.deepseek.com/>
- Xiaomi MiMo: <https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration>
- xAI: <https://docs.x.ai/developers/quickstart>
- Alibaba Qwen: <https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen>
- Gemini: <https://ai.google.dev/gemini-api/docs/api-key>
- Anthropic: <https://console.anthropic.com/>
- PageSpeed/CrUX: [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md)
- Search Console OAuth: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing>

## 3. IA - modelos e reasoning

| Variável | Valores aceitos / papel | Default efetivo |
|---|---|---|
| `RASAI_OPENAI_MODEL` | modelo OpenAI suportado pelo registry | `gpt-5.6-luna` |
| `RASAI_OPENAI_REASONING_EFFORT` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` |
| `RASAI_DEEPSEEK_MODEL` | modelo DeepSeek suportado pelo registry | `deepseek-v4-flash` |
| `RASAI_DEEPSEEK_REASONING_EFFORT` | esforço suportado pelo runtime | `NONE` |
| `RASAI_MIMO_MODEL` | modelo MiMo suportado pelo registry | `mimo-v2.5` |
| `RASAI_MIMO_REASONING_EFFORT` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` |
| `RASAI_XAI_MODEL` | modelo xAI suportado pelo registry | `grok-4.6` |
| `RASAI_XAI_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` |
| `RASAI_QWEN_MODEL` | modelo Qwen suportado pelo registry | `qwen3.8-flash` |
| `RASAI_GEMINI_MODEL` | modelo Gemini suportado pelo registry | `gemini-3.8-flash` |
| `RASAI_GEMINI_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH` | `LOW` |
| `RASAI_ANTHROPIC_MODEL` | modelo Anthropic suportado pelo registry | `claude-sonnet-5` |
| `RASAI_ANTHROPIC_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` |

Qwen não expõe `RASAI_QWEN_REASONING_EFFORT`; não crie variável que não exista no contrato do runtime.

## 4. IA - endpoints avançados

No uso normal, mantenha os endpoints default.

| Variável | Default |
|---|---|
| `RASAI_XAI_ENDPOINT` | `https://api.x.ai/v1/responses` |
| `RASAI_QWEN_ENDPOINT` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions` |
| `RASAI_GEMINI_ENDPOINT` | `https://generativelanguage.googleapis.com/v1beta/interactions` |
| `RASAI_ANTHROPIC_ENDPOINT` | `https://api.anthropic.com/v1/messages` |

Overrides devem ser URLs absolutas compatíveis com o adapter correspondente. Endpoint incorreto pode causar falha, envio de dados ao destino errado ou cobrança inesperada.

## 5. IA - contexto editorial / YMYL

Todos os defaults são `auto`.

| Variável | Valores principais |
|---|---|
| `RASAI_CONTENT_RISK_PROFILE` | `auto`, `standard`, `ymyl` |
| `RASAI_YMYL_CATEGORY` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` |
| `RASAI_PAGE_PURPOSE` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` |
| `RASAI_INTENDED_AUDIENCE` | `auto`, `general`, `professional`, `mixed` |
| `RASAI_EXPERIENCE_REQUIREMENT` | `auto`, `required`, `beneficial`, `not-expected` |
| `RASAI_FRESHNESS_SENSITIVITY` | `auto`, `low`, `medium`, `high` |
| `RASAI_CONTENT_ORIGIN` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` |

Essas variáveis não fazem chamada externa sozinhas. Elas condicionam a análise quando uma etapa de IA está habilitada. Consulte [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md).

## 6. Web Performance / Google APIs

| Variável | Tipo / valores | Default | Finalidade |
|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | booleano | `false` | habilita PageSpeed/Lighthouse/CrUX |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | inteiro `>=0`; `0=todas` | `10` | teto de páginas enviadas |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | número `>0` | `120` | timeout por request externo |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto`, `pagespeed`, `crux`, `none` | `auto` | política de field data |
| `RASAI_LIGHTHOUSE_CATEGORIES` | CSV de `performance`, `accessibility`, `best-practices`, `seo`, `agentic-browsing` | `performance,accessibility,best-practices,seo,agentic-browsing` | categorias Lighthouse solicitadas |
| `RASAI_PAGESPEED_API_KEY` | secret | nenhum | chave PageSpeed |
| `RASAI_CRUX_API_KEY` | secret | nenhum | chave CrUX direta |

As cinco categorias Lighthouse são solicitadas na mesma chamada PageSpeed por contexto. `agentic-browsing` é experimental; ausência isolada desse score não invalida as quatro categorias estáveis obtidas. Nenhuma categoria Lighthouse entra automaticamente no `SARI-001`/`SCORE-GEO-004`.

Consulte [LIGHTHOUSE_CATEGORIES.md](LIGHTHOUSE_CATEGORIES.md), [LIGHTHOUSE_WEB_QUALITY.md](LIGHTHOUSE_WEB_QUALITY.md) e [EXTERNAL_METRICS_INTEGRITY.md](EXTERNAL_METRICS_INTEGRITY.md).

## 7. Synthetic Apdex

### 7.1 Synthetic Navigation Apdex

| Variável | Tipo / valores | Default quando aplicável |
|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | booleano | `false` |
| `RASAI_APDEX_THRESHOLD_SECONDS` | número `>0` | sem default metodológico; obrigatório quando habilitado |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | inteiro `>=1` | `100` |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | inteiro `>= samples` | `ceil(1.25 × samples)` |
| `RASAI_APDEX_MAX_PAGES` | inteiro `>=0`; `0=todas` | `1` |
| `RASAI_APDEX_TIMEOUT_SECONDS` | número `>0` e efetivamente `>4T` | `max(45, 4T+5)` |
| `RASAI_APDEX_DELAY_SECONDS` | número `>=0` | `1` |
| `RASAI_APDEX_CONCURRENCY` | `1`, `2` | `1` |

### 7.2 Synthetic User Experience Apdex

| Variável | Tipo / valores | Default quando aplicável |
|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | booleano | `false` |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | inteiro `>=1` | `100` |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | inteiro `>= samples` | `ceil(1.25 × samples)` |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | inteiro `>=0`; `0=todas` | `1` |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | percentuais CSV somando 100% | `mobile=60,desktop=35,tablet=5` |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold`, `warm` | `cold` |
| `RASAI_APDEX_EXPERIENCE_KPM` | KPM suportada | `USER_ACTION_DURATION` |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | número `>0` | calibração explícita quando não importada |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | número `>0` | calibração explícita quando não importada |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | booleano | `true` quando Experience está ativo |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `navigation`, `first-party`, `all` | `first-party` |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | número `>0` | `5` |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | número `>=0` | `1` |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | `1`, `2` | `1` |
| `RASAI_APDEX_DYNATRACE_IMPORT` | booleano | `false` |
| `RASAI_DYNATRACE_BASE_URL` | URL HTTPS | nenhum |
| `RASAI_DYNATRACE_APPLICATION_ID` | texto | nenhum |
| `RASAI_DYNATRACE_CONFIG_JSON` | caminho de arquivo | nenhum |
| `DYNATRACE_API_TOKEN` | secret | nenhum |

Synthetic User Experience Apdex exige Synthetic Navigation Apdex habilitado. Consulte [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md) e [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## 8. Search Intelligence / Observability

| Variável | Tipo / valores | Default |
|---|---|---|
| `RASAI_SERP_MODE` | `disabled`, `live`, `fixture` | `disabled` |
| `RASAI_SERP_PROVIDER` | `serpapi`, `serpapi-bing` | `serpapi` |
| `RASAI_SERPAPI_API_KEY` | secret | nenhum |
| `RASAI_SERP_FIXTURE_PATH` | caminho de arquivo | nenhum |
| `RASAI_SERP_MAX_QUERIES` | inteiro `>0` | `10` |
| `RASAI_SERP_MAX_REQUESTS` | inteiro `>0` | `10` |
| `RASAI_SERP_MAX_DEPTH` | inteiro `>0` | `20` |
| `RASAI_SERP_MAX_COMPETITORS` | inteiro `>=0` | `10` |
| `RASAI_SERP_TIMEOUT_SECONDS` | número `>0` | `20` |
| `RASAI_SERP_RETRIES` | inteiro `>=0` | `1` |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | número `>=0` | `1` |
| `RASAI_SEARCH_AI_PROVIDER` | `none`, `fixture`, `openai` | `none` |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | secret/token OAuth | nenhum |

Search Intelligence/Observability permanece separado de `SARI-001`/`SCORE-GEO-004`. Consulte [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md) e [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md).

## 9. Control plane / SaaS

| Variável | Tipo / valores | Default | Regra |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite`, `postgresql` | `sqlite` | seleciona backend do control plane |
| `RASAI_PLATFORM_DATABASE_URL` | secret/DSN PostgreSQL | nenhum | obrigatória quando backend=`postgresql`; nunca deve ser gravada no INI |

SQLite permanece disponível para operação local. PostgreSQL é o backend centralizado do control plane quando explicitamente configurado. Consulte [POSTGRESQL_MIGRATION_STRATEGY.md](POSTGRESQL_MIGRATION_STRATEGY.md) e [PRODUCT_PLATFORM_ARCHITECTURE.md](PRODUCT_PLATFORM_ARCHITECTURE.md).

## 10. Web API / Identity

| Variável | Tipo / valores | Default |
|---|---|---|
| `RASAI_API_DOCS_ENABLED` | booleano | `false` |
| `RASAI_API_AUDITS_ROOT` | caminho | `audits` |
| `RASAI_API_AUTH_MODE` | `deny`, `trusted-header`, `oidc` | `deny` |
| `RASAI_API_TRUSTED_USER_HEADER` | nome de header HTTP | `x-rasai-user-id` |
| `RASAI_OIDC_ISSUER` | URL HTTPS | nenhum; requerida no modo `oidc` |
| `RASAI_OIDC_CLIENT_ID` | texto | nenhum; requerido no modo `oidc` |
| `RASAI_OIDC_AUDIENCE` | texto | client ID configurado |
| `RASAI_OIDC_REDIRECT_URI` | URL HTTPS; HTTP somente loopback | nenhum; requerida no fluxo OIDC web |
| `RASAI_OIDC_SESSION_SECRET` | secret | nenhum; requerido no modo OIDC web |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | nome da variável que contém o client secret | nenhum |
| `RASAI_OIDC_ALGORITHMS` | CSV | `RS256,ES256` |
| `RASAI_OIDC_SCOPES` | CSV | `openid,profile,email` |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | inteiro `300..86400` | `28800` |

`RASAI_OIDC_CLIENT_SECRET_ENV` persiste apenas o **nome** da variável que contém o segredo; o client secret real permanece fora do INI. Consulte [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md) e [WEB_API_FOUNDATION.md](WEB_API_FOUNDATION.md).

## 11. Remote control plane

| Variável | Tipo / valores | Default / regra |
|---|---|---|
| `RASAI_REMOTE_BASE_URL` | URL HTTPS; HTTP somente loopback | requerida no modo remoto |
| `RASAI_REMOTE_TOKEN_ENV` | nome da variável que contém o bearer token | nenhuma; o token real não é persistido |
| `RASAI_REMOTE_USER_ID` | texto | somente trusted-header em desenvolvimento loopback; proibido para host remoto |
| `RASAI_REMOTE_TIMEOUT_SECONDS` | número `>0` e `<=300` | `30` |

Para usar o cliente remoto, configure `RASAI_CONSOLE_MODE=remote`. A superfície remota chama a Web API e não reimplementa o core de auditoria.

## 12. Browser / Playwright

| Variável | Tipo | Default |
|---|---|---|
| `RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE` | caminho de arquivo existente | descoberta/instalação padrão do Playwright |
| `RASAI_BROWSER_LOCALE` | locale BCP 47 | `pt-BR` |

O locale pode alterar conteúdo entregue por sites que negociam idioma/região no browser.

## Defaults operacionais principais

Uma configuração local sem IA e sem integrações externas pode iniciar apenas com o target. Defaults relevantes:

```text
console mode                   = local
device                         = mobile
ai provider                    = none
ai timeout                     = 180 s
ai content remediation         = false
ai technical remediation       = false
web performance                = false
web performance max pages      = 10
web performance timeout        = 120 s
field source                   = auto
lighthouse categories          = performance,accessibility,best-practices,seo,agentic-browsing
synthetic navigation apdex     = false
synthetic experience apdex     = false
SERP mode                      = disabled
platform DB backend            = sqlite
API docs                       = false
API auth mode                  = deny
remote timeout                 = 30 s
browser locale                 = pt-BR
language                       = pt-BR
market                         = BR
max-pages                      = 100
audits-root                    = audits
```

Credenciais, thresholds metodológicos sem default e URLs/identificadores exigidos somente em modos específicos permanecem ausentes até configuração explícita.

## Segurança

- variável de ambiente não é um cofre de segredos;
- secrets não devem ser materializados em arquivos versionados;
- DSN PostgreSQL pode conter credenciais e deve ser tratado como secret;
- variáveis terminadas em `_ENV` que referenciam outro secret armazenam somente o nome da variável, não o valor do segredo;
- bearer tokens e API keys nunca devem aparecer em HTML, logs, SQLite ou artifacts;
- credencial configurada não prova quota, saldo, plano, permissão ou escopo válido.
