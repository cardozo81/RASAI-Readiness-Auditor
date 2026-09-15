# Variáveis de ambiente - referência completa

Referência operacional das variáveis reconhecidas pelo RASAi - Search & AI Readiness Auditor.

O produto está em desenvolvimento e validação pré-publicação. Esta referência descreve somente o contrato vigente do runtime.

Variáveis de ambiente são overrides avançados. Quando existe um default seguro, o runtime aplica esse valor mesmo que a variável não esteja materializada no sistema operacional. Segredos não devem ser gravados em `rasai-console.ini`, arquivos de URL, relatórios, bancos ou logs.

Para saber **para que serve uma credencial, onde ela é usada e como criá-la no fornecedor**, consulte [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md). Para catálogo de providers de IA e SERP, consulte [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Como interpretar as tabelas

- **Default efetivo:** valor usado pelo runtime na ausência de override.
- **Valores permitidos:** domínio validado pelo código.
- **Recomendado:** configuração indicada para o uso normal.
- **Dependência:** condição que torna a variável necessária ou efetiva.
- **Sem default:** a aplicação não inventa um valor.
- Em serviços dirigidos por credencial, **auto por requisitos** significa que, sem override do toggle, o serviço só fica elegível quando credencial e demais configurações obrigatórias existem.
- Valores booleanos aceitam, conforme a superfície, `true`/`false`, `1`/`0`, `yes`/`no` e `on`/`off`. Para documentação e automação, prefira `true` ou `false`.

## 1. Aplicação, execução e apresentação temporal

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade / dependência |
|---|---|---|---|---|
| `RASAI_CONSOLE_INI` | `rasai-console.ini` | caminho válido | default | seleciona o INI persistente do console |
| `RASAI_CONFIG` | sem arquivo obrigatório | caminho para TOML existente | omitir salvo necessidade de outro TOML | força arquivo geral de configuração |
| `RASAI_CONSOLE_MODE` | `local` | `local`, `remote` | `local` | `remote` exige control plane remoto configurado |
| `RASAI_LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG` | `INFO` | verbosidade operacional |
| `RASAI_DEVICE_CONTEXT` | `mobile` | `mobile`, `desktop`, `both` | `mobile` para execução mínima | device padrão quando CLI/menu não sobrescrevem |
| `RASAI_PRESENTATION_TIMEZONE` | `America/Sao_Paulo` | timezone IANA válido | `America/Sao_Paulo` | somente apresentação; persistência continua UTC |
| `RASAI_AI_TIMEOUT_SECONDS` | `180` | número `> 0` | `180` | timeout máximo por tentativa de IA |
| `RASAI_AI_AUTO_EXCLUDE` | vazio | CSV ou `;` de providers AUTO válidos | vazio | exclui provider apenas do pool `AI=auto` |
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | booleano | `false` | habilita remediação de conteúdo por IA |
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | booleano | `false` | habilita remediação técnica advisory por IA |
| `RASAI_AI_EXCHANGE_LOG_MAX_BYTES` | `524288` | inteiro `4096..4194304` | `524288` | teto por request/response sanitizado no log de intercâmbio de IA |

No console local, configure o timezone pelo item **Timezone apresentação**, persistido em `[presentation] timezone`. `RASAI_PRESENTATION_TIMEZONE` é override de processo e não reinterpreta timestamps persistidos. Consulte [TIMEZONE_CONTRACT.md](TIMEZONE_CONTRACT.md).

`RASAI_AI_AUTO_EXCLUDE` não apaga credenciais nem impede seleção explícita.

## 2. IA - credenciais

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência funcional |
|---|---|---|---|---|
| `OPENAI_API_KEY` | sem default | credencial OpenAI não vazia | secret/env | necessária ao selecionar OpenAI |
| `DEEPSEEK_API_KEY` | sem default | credencial DeepSeek não vazia | secret/env | necessária ao selecionar DeepSeek |
| `MIMO_API_KEY` | sem default | chave PAYG `sk-...`; `tp-...` não é aceita pelo adapter | `sk-...` em secret/env | necessária ao selecionar MiMo |
| `XAI_API_KEY` | sem default | credencial xAI não vazia | secret/env | necessária ao selecionar xAI/Grok |
| `DASHSCOPE_API_KEY` | sem default | credencial Alibaba Model Studio não vazia | secret/env | necessária ao selecionar Qwen |
| `GEMINI_API_KEY` | sem default | credencial Gemini não vazia | secret/env | necessária ao selecionar Gemini |
| `ANTHROPIC_API_KEY` | sem default | credencial Anthropic não vazia | secret/env | necessária ao selecionar Anthropic/Claude |
| `COPILOT_GITHUB_TOKEN` | sem default | token de usuário `github_pat_`, `gho_` ou `ghu_`; `ghp_` não é aceito | fine-grained PAT com `Copilot Requests` | necessária ao selecionar `copilot`; provider explicit-only |

A presença de uma credencial não comprova validade, saldo, quota, plano ou acesso ao modelo. Instruções de criação e links oficiais: [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

## 3. IA - modelos

| Variável | Default efetivo | Valores permitidos pelo runtime | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_MODEL` | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `gpt-5.6-luna`; usar Sol quando qualidade justificar maior custo/latência |
| `RASAI_DEEPSEEK_MODEL` | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `deepseek-v4-flash` |
| `RASAI_MIMO_MODEL` | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `mimo-v2.5` |
| `RASAI_XAI_MODEL` | `grok-4.6` | `grok-4.6` | default |
| `RASAI_QWEN_MODEL` | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `qwen3.8-flash` |
| `RASAI_GEMINI_MODEL` | `gemini-3.8-flash` | `gemini-3.8-flash` | default |
| `RASAI_ANTHROPIC_MODEL` | `claude-sonnet-5` | `claude-sonnet-5` | default |
| `RASAI_COPILOT_MODEL` | `auto` | `auto` | `auto` |

## 4. IA - reasoning

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` |
| `RASAI_DEEPSEEK_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` |
| `RASAI_MIMO_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` |
| `RASAI_XAI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` |
| `RASAI_QWEN_REASONING_EFFORT` | variável inexistente | Qwen usa `PROVIDER_DEFAULT` internamente | não criar variável inexistente |
| `RASAI_GEMINI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH` | `LOW` |
| `RASAI_ANTHROPIC_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` |
| `RASAI_COPILOT_REASONING_EFFORT` | variável inexistente | Copilot usa `PROVIDER_DEFAULT` via SDK | não criar variável inexistente |

Aumentar reasoning pode elevar latência, tokens e custo. `AI=auto` consulta o registry, considera somente providers elegíveis/configurados e aplica a política de roteamento vigente. Consulte [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## 5. IA - endpoints avançados

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_XAI_ENDPOINT` | `https://api.x.ai/v1/responses` | URL absoluta HTTP(S) | manter HTTPS default | endpoint do adapter xAI |
| `RASAI_QWEN_ENDPOINT` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions` | URL absoluta HTTP(S) | manter HTTPS default e região coerente com a key | endpoint do adapter Qwen |
| `RASAI_GEMINI_ENDPOINT` | `https://generativelanguage.googleapis.com/v1beta/interactions` | URL absoluta HTTP(S) | manter HTTPS default | endpoint do adapter Gemini |
| `RASAI_ANTHROPIC_ENDPOINT` | `https://api.anthropic.com/v1/messages` | URL absoluta HTTP(S) | manter HTTPS default | endpoint do adapter Anthropic |

Não altere endpoints no uso normal. Override incorreto pode causar falha, cobrança inesperada ou envio de dados a destino errado. Não use HTTP para providers externos. GitHub Copilot usa o SDK oficial e não possui endpoint override no contrato atual.

## 6. IA - contexto editorial / YMYL

Todos os campos abaixo usam `auto` por default.

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_CONTENT_RISK_PROFILE` | `auto` | `auto`, `standard`, `ymyl` | `auto` |
| `RASAI_YMYL_CATEGORY` | `auto` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` | `auto` |
| `RASAI_PAGE_PURPOSE` | `auto` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` | `auto` |
| `RASAI_INTENDED_AUDIENCE` | `auto` | `auto`, `general`, `professional`, `mixed` | `auto` |
| `RASAI_EXPERIENCE_REQUIREMENT` | `auto` | `auto`, `required`, `beneficial`, `not-expected` | `auto` |
| `RASAI_FRESHNESS_SENSITIVITY` | `auto` | `auto`, `low`, `medium`, `high` | `auto` |
| `RASAI_CONTENT_ORIGIN` | `auto` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` | `auto` |

Um valor `auto` permanece `AUTO` no estado persistido. Eventual interpretação transitória por IA não sobrescreve o banco, não vira evidência determinística e não altera diretamente `SARI-001`/`SCORE-GEO-004`.

### 6.1 IA - análise profunda e idioma

Improvement Intelligence usa a seleção principal de IA da execução. Não possui provider/modelo/reasoning próprios. Com `AI=auto`, reutiliza a mesma ordenação por custo, elegibilidade, quarentena, circuit breaker e fallback do runtime canônico. A execução é limitada a uma URL explícita e permanece advisory/non-scoring.

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_AI_ANALYSIS_LANGUAGE` | `auto` | `auto` ou tag BCP-47 | `auto` | idioma preferencial das explicações e sugestões |
| `RASAI_IMPROVEMENT_INTELLIGENCE` | `false` | booleano | `false`; habilitar somente para URL única e IA principal ativa | ativa análise profunda evidence-bound |
| `RASAI_IMPROVEMENT_DOMAINS` | todos os domínios suportados | CSV de `TECHNICAL_HTML`, `SEMANTICS_STRUCTURE`, `CONTENT`, `SEARCH_RANKING`, `FILES_DISCOVERY`, `PERFORMANCE`, `ACCESSIBILITY`, `BEST_PRACTICES`, `SECURITY`, `AI_ACCESS` | restringir aos domínios necessários | controla evidências enviadas ao estudo |
| `RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS` | `30` | inteiro `1..100` | `30` | limita backlog/output |
| `RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS` | `240` | número `> 0` | `240` | timeout da necessidade estruturada; não redefine política de roteamento |

No console interativo, a capacidade **Análise profunda e melhorias** configura apenas ativação/domínios/limites próprios e referencia as dependências canônicas relacionadas. Provider, modelo e reasoning vêm da **IA principal** da execução, acessível em `INÍCIO > Inteligência Artificial`. Consulte [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md).

## 7. Métricas, padrões e Web Performance

Referência funcional: [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md).

### 7.1 Controles gerais e métricas sem credencial

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | booleano | `true` | métricas derivadas de evidência persistida |
| `RASAI_RETRIEVAL_METRICS` | `true` | booleano | `true` | MRR e métricas de Information Retrieval quando houver dados suficientes |
| `RASAI_OPEN_WEB_METRICS` | `true` | booleano | `true` | W3C Performance APIs no browser já aberto |
| `RASAI_W3C_VALIDATOR` | `true` | booleano | `true`, bounded | W3C Nu HTML Checker |
| `RASAI_W3C_CSS_VALIDATOR` | `true` | booleano | `true`, bounded/throttled | W3C CSS Validation Service |
| `RASAI_MDN_OBSERVATORY` | `true` | booleano | `true` salvo restrição de privacidade/egress | scan HTTP Observatory por origem |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | booleano | `true` | solicita análise WebDX/Baseline |
| `RASAI_WEB_FEATURES_DATASET` | `auto` | `auto` ou caminho para arquivo existente | `auto` | fonte canônica global WebDX; caminho local é override para pin/versionamento |
| `RASAI_STANDARDS_MAX_URLS` | `10` | inteiro `>= 0`; `0=todas` | `10` | teto de URLs em serviços externos desta família |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | número `> 0` e `< 3600` | `20` | timeout por request |

`RASAI_WEB_FEATURES_DATASET=auto` atende a configuração normal da fonte global `web-platform-dx/web-features`; o dataset-base não depende do domínio auditado. No contrato `WEB-PLATFORM-BASELINE-001`, o runtime resolve e congela a versão usada por `AUD-*` (versão/SHA-256), detecta features diretamente observáveis no HTML persistido e em CSS/JavaScript inline e cruza essas evidências com `compat_features`. CSS/JS externos do alvo não são refeitos apenas para ampliar WebDX; `NO_DATA` significa ausência de evidência diretamente mapeável ou de artifact elegível, não ausência do detector. Consulte [WEB_PLATFORM_BASELINE.md](WEB_PLATFORM_BASELINE.md).

### 7.2 Controle agregado de Web Performance

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` no controle agregado isolado | booleano | omitir quando quiser resolução por serviços; `false` para hard-off | controle agregado PageSpeed/Lighthouse/CrUX |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | inteiro `>= 0`; `0=todas` | `10` | teto de páginas externas |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | número `> 0` | `120` | timeout por request |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` | `auto` | política de dados de campo |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | CSV sem duplicatas das categorias suportadas | default | categorias pedidas ao PageSpeed |

`RASAI_WEB_PERFORMANCE=false` explícito impede a execução externa dessa família. Sem hard-off, serviços individuais podem ficar elegíveis por seus requisitos.

### 7.3 PageSpeed, CrUX e CrUX History

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_PAGESPEED_ENABLED` | auto por requisitos | booleano | omitir para auto; `false` para desligar | exige `RASAI_PAGESPEED_API_KEY` para ficar `READY` |
| `RASAI_PAGESPEED_API_KEY` | sem default | API key válida | secret/env | autenticação/quota PageSpeed Insights |
| `RASAI_CRUX_ENABLED` | auto por requisitos | booleano | omitir para auto; `false` para desligar | exige `RASAI_CRUX_API_KEY` |
| `RASAI_CRUX_HISTORY_ENABLED` | auto por requisitos | booleano | omitir para auto; `false` para desligar | usa `RASAI_CRUX_API_KEY`; coleta série histórica semanal por origem/form factor |
| `RASAI_CRUX_API_KEY` | sem default | API key válida | secret/env | credencial compartilhável entre CrUX current e History |

A existência da key não garante amostra CrUX elegível. Ausência de dados não vira `FAIL`. Instruções de criação: [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

### 7.4 Google Search Console

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_GSC_ENABLED` | auto por requisitos | booleano | omitir para auto; `false` para desligar | requer property + uma forma OAuth completa |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | sem default | OAuth 2.0 bearer token válido | apenas para teste pontual/manual | alternativa temporária ao fluxo com Refresh Token |
| `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID` | sem default | OAuth Client ID não vazio | persistir como configuração não secreta | obrigatório no fluxo durável com Refresh Token |
| `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET` | sem default | OAuth Client Secret não vazio | secret/env | obrigatório no fluxo durável; nunca entra no INI |
| `RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN` | sem default | OAuth Refresh Token válido | secret/env | obrigatório no fluxo durável; gera access token temporário em memória |
| `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` | sem default | `sc-domain:<domínio>` ou URL-prefix HTTP(S) | property exata autorizada no Search Console | contexto obrigatório da propriedade |
| `RASAI_GSC_SEARCH_ANALYTICS_DAYS` | `1` | inteiro `0..31` | `1` | `0` desliga apenas Search Analytics automático |
| `RASAI_GSC_SEARCH_MAX_ROWS` | `10000` | inteiro `1..50000` | `10000` | teto de linhas normalizadas |
| `RASAI_GSC_FINAL_DATA_LAG_DAYS` | `3` | inteiro `0..30` | `3` | defasagem para preferir dados finalizados |

Search Console fica configurado quando existe a property e **uma** destas formas de autenticação: um `ACCESS_TOKEN` manual, ou o trio `CLIENT_ID` + `CLIENT_SECRET` + `REFRESH_TOKEN`. No modo durável, o RASAi obtém o access token imediatamente antes da chamada ao Google e o mantém apenas em memória. Uma Google API Key, normalmente iniciada por `AIza`, não substitui OAuth para dados privados do Search Console. Consulte [GSC_OAUTH.md](GSC_OAUTH.md) e [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

### 7.5 Microsoft Clarity Data Export

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_CLARITY_ENABLED` | `false` | booleano | `false`; opt-in explícito | ativa Data Export; token sozinho não habilita |
| `RASAI_CLARITY_API_TOKEN` | sem default | bearer token válido do projeto Clarity | secret/env | obrigatório quando Clarity estiver habilitado |
| `RASAI_CLARITY_DAYS` | `1` | `1`, `2`, `3` | `1` | janela de dados solicitada à API |
| `RASAI_CLARITY_DIMENSIONS` | `URL,Device` | até 3 entre `Browser`, `Device`, `Country/Region`, `OS`, `Source`, `Medium`, `Campaign`, `Channel`, `URL`; `URL` obrigatória | `URL,Device` | preserva vínculo com URL auditada e, quando possível, dispositivo |

A integração é opt-in por causa da quota restrita da API. O token nunca entra no INI. Instruções de geração: [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

### 7.6 Common Crawl

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_COMMON_CRAWL_ENABLED` | `true` | booleano | `true`, salvo restrição de egress/política | habilita consulta bounded ao índice público Common Crawl |
| `RASAI_COMMON_CRAWL_MAX_URLS` | `3` | inteiro `0..25` | `3`; `0` desliga a subcoleta | teto de URLs exatas consultadas |
| `RASAI_COMMON_CRAWL_INDEX_COUNT` | `2` | inteiro `1..6` | `2` | número de índices mensais recentes consultados |

Common Crawl não exige credencial. Quando uma observação positiva qualifica, `BR-GEO-060` pode participar do SARI conforme [SARI_EXTERNAL_CRAWL_CORROBORATION.md](SARI_EXTERNAL_CRAWL_CORROBORATION.md). Ausência ou erro não cria penalidade.

### 7.7 Reprocessamento de coletas live

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_REPROCESS_LIVE_VALIDITY_MINUTES` | `1440` | inteiro `1..10080` | `1440` | janela em que uma recolha live pode ser refeita no mesmo `AUD-*` sem misturar estados temporalmente distantes |

Depois da janela, uma nova observação live deve ocorrer em nova auditoria quando o contrato de reprocessamento exigir coerência temporal. Consulte [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md).

## 8. Synthetic Navigation Apdex (`apdex.html`)

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | `false` | booleano | `false`; habilitar deliberadamente |
| `RASAI_APDEX_THRESHOLD_SECONDS` | sem default | número `> 0` | usar o SLO/KPM definido para o sistema; não inventar `T` |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | `100` | inteiro `>= 1` | `100` |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | `ceil(1.25 x samples)` | inteiro `>= samples` | default derivado |
| `RASAI_APDEX_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` |
| `RASAI_APDEX_TIMEOUT_SECONDS` | `max(45, 4T + 5)` | número `> 0` e `> 4T` | default derivado |
| `RASAI_APDEX_DELAY_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme sensibilidade do alvo |
| `RASAI_APDEX_CONCURRENCY` | `1` | `1`, `2` | `1` |
| `RASAI_APDEX_MOBILE_CLIENT_PROFILE` | `mobile-balanced-chromium` | `mobile-compact-chromium`, `mobile-balanced-chromium`, `mobile-large-chromium` | default |
| `RASAI_APDEX_MOBILE_HARDWARE_PROFILE` | `mobile-balanced` | `mobile-entry`, `mobile-balanced`, `mobile-premium` | `mobile-balanced` |
| `RASAI_APDEX_MOBILE_NETWORK_PROFILE` | `mobile-4g-balanced` | `mobile-3g-constrained`, `mobile-4g-balanced`, `mobile-4g-fast`, `mobile-5g` | `mobile-4g-balanced` |
| `RASAI_APDEX_DESKTOP_CLIENT_PROFILE` | `desktop-balanced-chromium` | `desktop-1366-chromium`, `desktop-balanced-chromium`, `desktop-wide-chromium` | default |
| `RASAI_APDEX_DESKTOP_HARDWARE_PROFILE` | `desktop-balanced` | `desktop-constrained`, `desktop-balanced` | `desktop-balanced` |
| `RASAI_APDEX_DESKTOP_NETWORK_PROFILE` | `desktop-balanced` | `desktop-constrained`, `desktop-balanced`, `desktop-fiber` | `desktop-balanced` |
| `RASAI_APDEX_TABLET_CLIENT_PROFILE` | `tablet-balanced-chromium` | `tablet-compact-chromium`, `tablet-balanced-chromium` | default |
| `RASAI_APDEX_TABLET_HARDWARE_PROFILE` | `tablet-balanced` | `tablet-entry`, `tablet-balanced`, `tablet-premium` | `tablet-balanced` |
| `RASAI_APDEX_TABLET_NETWORK_PROFILE` | `tablet-4g-balanced` | `tablet-4g-balanced`, `tablet-wifi` | `tablet-4g-balanced` |

Os presets controlam cliente/viewport, slowdown relativo de CPU e envelope de rede. Não mudam a fórmula Apdex nem afirmam equivalência com hardware físico.

## 9. Synthetic User Experience Apdex (`apdex-experience.html`)

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | booleano | `false` | exige Synthetic Navigation Apdex ativo |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | inteiro `>= 1` | `100` | população sintética |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 x samples)` | inteiro `>= samples` | default derivado | orçamento de tentativas |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` | teto de páginas |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | percentuais não negativos somando 100 | população real quando conhecida | peso populacional |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | `cold`, `warm` | `cold` | política de sessão sintética |
| `RASAI_APDEX_ACQUISITION_MODE` | `auto` | `auto`, `isolated` | `auto` | compartilhamento físico somente quando compatível |
| `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | `USER_ACTION_DURATION`, `DOM_INTERACTIVE`, `LOAD_EVENT_START`, `LOAD_EVENT_END`, `RESPONSE_START`, `RESPONSE_END`, `LARGEST_CONTENTFUL_PAINT` | `USER_ACTION_DURATION` | KPM sintético |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3` | número `> 0` | `3` | threshold satisfeito |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12` | número `> satisfied` | `12` | threshold frustrado |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | booleano | `true` | erros qualificáveis podem forçar Frustrated |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | `navigation`, `first-party`, `all` | `first-party` | escopo dos erros |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5` | número `> 0` | `5` | janela pós-load |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | `1` | número `>= 0` | `1` | intervalo entre ações |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | `1` | `1`, `2` | `1` | workers simultâneos |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | booleano | `false` | habilita importação live Dynatrace |
| `RASAI_DYNATRACE_BASE_URL` | sem default | URL HTTPS absoluta | configurar somente para importação live | URL do ambiente Dynatrace |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | texto não vazio | somente importação live | aplicação web consultada |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | caminho para JSON existente | preferível à importação live quando possível | configuração offline/reproduzível |
| `DYNATRACE_API_TOKEN` | sem default | token API válido com permissões mínimas necessárias | secret/env | obrigatório na importação live |

O valor `mobile=60,desktop=35,tablet=5` acima é o default técnico do runtime/variável. Na preparação pelo console, quando o mix está **HERDADO**, a interface projeta a próxima execução a partir de `Device`: `mobile` -> `100/0/0`, `desktop` -> `0/100/0` e `both` -> `60/40/0`. Essa projeção não altera o default da variável; Tablet permanece disponível por override avançado do mix.

Criação e segurança do token Dynatrace: [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md). Consulte também [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## 10. Search Intelligence / Observability

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_SERP_MODE` | `disabled` | `disabled`, `live`, `fixture` | `disabled`; `fixture` para teste; `live` com intenção explícita | escolhe modo SERP |
| `RASAI_SERP_PROVIDER` | `serpapi` | `serpapi`, `serpapi-bing`, `zenserp`, `scrapingdog` | conforme engine/quota | em `live`, determina a credencial exigida |
| `RASAI_SERPAPI_API_KEY` | sem default | credencial SerpApi válida | secret/env | exigida por `serpapi` e `serpapi-bing` |
| `RASAI_ZENSERP_API_KEY` | sem default | credencial Zenserp válida | secret/env | exigida por `zenserp` |
| `RASAI_SCRAPINGDOG_API_KEY` | sem default | credencial ScrapingDog válida | secret/env | exigida por `scrapingdog` |
| `RASAI_SERP_FIXTURE_PATH` | sem default | arquivo existente | apenas em `fixture` | fonte de teste offline |
| `RASAI_SERP_MAX_QUERIES` | `10` | inteiro `> 0` | `10` | teto de termos |
| `RASAI_SERP_MAX_REQUESTS` | `10` | inteiro `> 0` | `10` | teto de tentativas HTTP do RASAi, não créditos comerciais |
| `RASAI_SERP_MAX_DEPTH` | `20` | inteiro `> 0` | `20` | profundidade máxima solicitada |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | inteiro `>= 0` | `10` | teto de candidatos competitivos |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | número `> 0` | `20` | timeout por tentativa |
| `RASAI_SERP_RETRIES` | `1` | inteiro `>= 0` | `1` | retries permitidos |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | número `>= 0` | `1` ou maior se provider exigir | throttling local |

Search Intelligence permanece separado do SARI. Competitive AI não possui variável de provider própria: `--ai-provider` usa o registry canônico e `auto` reutiliza a orquestração central. Links de cadastro e orientação de keys: [PROVIDER_SETUP.md](PROVIDER_SETUP.md), [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md) e [COMPETITIVE_AI_INTELLIGENCE.md](COMPETITIVE_AI_INTELLIGENCE.md).

## 11. Control plane / SaaS

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; parser também aceita `postgres`, `pg` | `sqlite` local; `postgresql` centralizado | seleciona backend do control plane |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | DSN `postgres://` ou `postgresql://` com host válido | secret/env | obrigatória quando backend é PostgreSQL |

Selecionar PostgreSQL explicitamente sem URL válida ou sem conexão não provoca fallback silencioso para SQLite.

## 12. Web API / Identity

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_API_DOCS_ENABLED` | `false` | booleano | `false` fora de desenvolvimento controlado | expõe `/docs` e `/openapi.json` quando true |
| `RASAI_API_AUDITS_ROOT` | `audits` | caminho | default | raiz de AUDs usada pela API/store |
| `RASAI_API_AUTH_MODE` | `deny` | `deny`, `trusted-header`, `oidc` | `oidc` em ambiente hospedado | `deny` é fail-closed |
| `RASAI_API_TRUSTED_USER_HEADER` | `x-rasai-user-id` | nome de header não vazio e sem espaços | default | usado somente em `trusted-header` |
| `RASAI_OIDC_ISSUER` | sem default | URL HTTPS absoluta, sem credenciais/query/fragmento | issuer exato do IdP | obrigatório em `oidc` |
| `RASAI_OIDC_CLIENT_ID` | sem default | texto não vazio | client registrado | obrigatório em `oidc` |
| `RASAI_OIDC_AUDIENCE` | client ID | texto | manter client ID salvo requisito distinto do IdP | audience esperada para bearer JWT |
| `RASAI_OIDC_REDIRECT_URI` | sem default | URL absoluta; HTTPS, com HTTP somente em loopback | HTTPS | callback Web OIDC |
| `RASAI_OIDC_SESSION_SECRET` | sem default | segredo com pelo menos 32 bytes UTF-8 | secret store | protege transação PKCE e sessão Web |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | sem default | nome de variável de ambiente válida | referência para secret store | contém o nome da variável do client secret, não o segredo |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | CSV de algoritmos assimétricos suportados | default salvo contrato do IdP | allowlist de assinatura JWT; `none` e simétricos não aceitos |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | CSV contendo `openid` | reduzir ao necessário | scopes do login OIDC |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | inteiro `300..86400` | `28800` | TTL da sessão Web |

Detalhes de registro do client, fluxo Authorization Code + PKCE, JWT, cookies e vínculo `(issuer, subject) -> USR-*`: [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md) e [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

## 13. Remote control plane

| Variável | Default efetivo | Valores permitidos | Recomendado | Dependência / finalidade |
|---|---|---|---|---|
| `RASAI_REMOTE_BASE_URL` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS | endereço do control plane remoto |
| `RASAI_REMOTE_TOKEN_ENV` | sem default | nome de variável de ambiente válida | referência para bearer token | contém o nome da variável que guarda o token, não o token |
| `RASAI_REMOTE_USER_ID` | sem default | texto | somente `trusted-header` local/controlado | identidade técnica usada pelo cliente remoto nesse modo |
| `RASAI_REMOTE_TIMEOUT_SECONDS` | `30` | número `> 0` e `<= 300` | `30` | timeout do cliente remoto |

## 14. Browser / Playwright

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE` | sem override | caminho para executável existente | omitir | override avançado do Chromium |
| `RASAI_BROWSER_LOCALE` | `pt-BR` | locale BCP-47 | `pt-BR` salvo objetivo explícito distinto | locale do browser controlado |

## 15. Precedência e persistência

Quando a mesma capacidade puder ser definida por CLI/menu, variável e default, a superfície explícita da execução prevalece conforme o contrato do módulo.

Segredos podem existir apenas no processo/secret boundary apropriado. No Windows, persistência de segredo no escopo User só ocorre quando a superfície correspondente permitir e houver confirmação explícita. O INI do console não recebe segredos.

Variáveis terminadas em `_ENV` que são referências de segredo guardam **o nome de outra variável**, não o segredo em si.

Não entram no INI, entre outras:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
COPILOT_GITHUB_TOKEN
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN
RASAI_CLARITY_API_TOKEN
DYNATRACE_API_TOKEN
```

`RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID`, `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`, limites, toggles e fonte/pin de dataset WebDX são não secretos e podem ser persistidos quando a superfície de configuração suportar essa persistência.

## 16. Telemetria e segurança de IA

`ai_exchange_log` pode conter conteúdo/evidências da página efetivamente enviados ao provider. O workspace deve ser tratado como artefato potencialmente sensível. O recorder remove credenciais, headers de autenticação, parâmetros de segredo e campos reconhecidos como raciocínio privado antes da persistência.

Interpretação transitória de campos `auto` não deve ser promovida a evidência persistida nem a fato sobre credenciais, reputação, experiência pessoal, revisão profissional ou conformidade.

## 17. Regra para documentação de valores

Sempre que um `*.md` publicar configuração, deve distinguir quando aplicável:

1. default efetivo do runtime;
2. domínio, valores permitidos ou faixa validada pelo código;
3. valor recomendado para o cenário;
4. dependências e condições de obrigatoriedade;
5. impacto de custo, carga, segurança, quota, latência ou reprodutibilidade quando material.

Quando não existir default tecnicamente seguro, documentar **sem default** em vez de inventar um valor.