# Variáveis de ambiente - referência completa

Referência operacional da superfície de variáveis reconhecida pelo RASAi - Search & AI Readiness Auditor.

**Verificação contra o runtime:** 11/09/2026.

O RASAi está em fase pré-publicação. Esta referência descreve somente o contrato atual do produto. Coexistência de controles ou aliases técnicos não representa compatibilidade com uma versão pública anterior.

Variáveis de ambiente são *overrides* avançados. Quando existe um default seguro, o runtime aplica esse valor mesmo que a variável não esteja materializada no sistema operacional. Segredos não devem ser gravados em `rasai-console.ini`, arquivos de URL, relatórios, bancos ou logs.

## Como interpretar as tabelas

- **Default efetivo:** valor usado pelo runtime na ausência de override.
- **Valores permitidos:** domínio validado pelo código.
- **Recomendado:** configuração operacional indicada para o uso normal.
- **Sem default:** a aplicação não inventa um valor.
- Em serviços dirigidos por credencial, **auto por requisitos** significa: sem override do toggle, o serviço só fica elegível quando credencial e demais configurações obrigatórias existem.
- Valores booleanos aceitam, conforme a superfície de validação, formas equivalentes como `true`/`false`, `1`/`0`, `yes`/`no` e `on`/`off`. Para documentação e automação, prefira `true` ou `false`.

## 1. Aplicação, execução e apresentação temporal

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_CONSOLE_INI` | `rasai-console.ini` | caminho válido para o INI do console | default | seleciona o arquivo INI persistente do console |
| `RASAI_CONFIG` | sem arquivo obrigatório; `rasai.toml` pode ser descoberto pelo fluxo normal | caminho para arquivo TOML existente | não definir, salvo necessidade de apontar outro TOML | força um TOML geral |
| `RASAI_CONSOLE_MODE` | `local` | `local`, `remote` | `local`; use `remote` apenas com control plane remoto configurado | escolhe console local ou cliente remoto |
| `RASAI_LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG` | `INFO`; `DEBUG` somente para diagnóstico | verbosidade operacional |
| `RASAI_DEVICE_CONTEXT` | `mobile` | `mobile`, `desktop`, `both` | `mobile` para execução mínima; `both` quando a auditoria precisar dos dois contextos | device padrão quando CLI/menu não sobrescrevem |
| `RASAI_PRESENTATION_TIMEZONE` | `America/Sao_Paulo` | identificador IANA válido; offsets fixos como `-03:00` não são aceitos | `America/Sao_Paulo` no produto Brasil; alterar apenas quando a apresentação exigir outro fuso | timezone de apresentação; não altera timestamps canônicos UTC |
| `RASAI_AI_TIMEOUT_SECONDS` | `180` | número `> 0`, em segundos | `180` | timeout máximo por tentativa de IA |
| `RASAI_AI_AUTO_EXCLUDE` | vazio | CSV ou lista separada por `;` de providers válidos e elegíveis ao pool AUTO | vazio | remove providers apenas do pool `AI=auto` |
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | booleano | `false`; habilite quando houver provider apto e a remediação por IA for desejada | habilita remediação de conteúdo por IA |
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | booleano | `false`; habilite apenas quando a remediação técnica advisory for necessária | habilita remediação técnica por IA |
| `RASAI_AI_EXCHANGE_LOG_MAX_BYTES` | `524288` | inteiro de `4096` a `4194304` bytes | `524288` | limite por request/response sanitizado no log de intercâmbio de IA |

No console local, a preferência normal de timezone deve ser configurada pelo item **Timezone apresentação** e persistida em `[presentation] timezone = ...` no `rasai-console.ini`. `RASAI_PRESENTATION_TIMEZONE` é um override avançado para automação/processos e não reinterpreta nem regrava timestamps canônicos UTC. Consulte [TIMEZONE_CONTRACT.md](TIMEZONE_CONTRACT.md).

`RASAI_AI_AUTO_EXCLUDE` não apaga credenciais nem impede seleção explícita. Exemplo: `RASAI_AI_AUTO_EXCLUDE=gemini` mantém Gemini disponível para seleção direta, mas impede chamadas Gemini durante `AI=auto`.

## 2. IA - credenciais

| Variável | Default efetivo | Valores permitidos | Recomendado | Observação |
|---|---|---|---|---|
| `OPENAI_API_KEY` | sem default | credencial não vazia válida para OpenAI | usar somente por secret/env | necessária ao selecionar OpenAI |
| `DEEPSEEK_API_KEY` | sem default | credencial não vazia válida para DeepSeek | usar somente por secret/env | necessária ao selecionar DeepSeek |
| `MIMO_API_KEY` | sem default | chave PAYG iniciada por `sk-`; `tp-...` não é aceita pelo adapter atual | `sk-...` PAYG | necessária ao selecionar MiMo |
| `XAI_API_KEY` | sem default | credencial não vazia válida para xAI | usar somente por secret/env | necessária ao selecionar xAI/Grok |
| `DASHSCOPE_API_KEY` | sem default | credencial não vazia válida para Alibaba Model Studio | usar somente por secret/env | necessária ao selecionar Qwen |
| `GEMINI_API_KEY` | sem default | credencial não vazia válida para Gemini | usar somente por secret/env | necessária ao selecionar Gemini |
| `ANTHROPIC_API_KEY` | sem default | credencial não vazia válida para Anthropic | usar somente por secret/env | necessária ao selecionar Anthropic/Claude |
| `COPILOT_GITHUB_TOKEN` | sem default | token de usuário compatível com Copilot SDK (`github_pat_`, `gho_` ou `ghu_`); classic PAT `ghp_` não é aceito | fine-grained PAT com `Copilot Requests`, somente por secret/env | necessária ao selecionar `copilot`; usa assinatura Copilot elegível e não participa de `AI=auto` |

A presença de uma credencial não prova crédito, quota, plano nem acesso ao modelo. Em `AI=auto`, entram no pool apenas providers registrados como elegíveis, com credencial/configuração válidas e não excluídos pelo usuário. GitHub Copilot é `explicit-only`: mesmo com `COPILOT_GITHUB_TOKEN` configurado, ele só é consumido quando selecionado de forma explícita.

As URLs oficiais para criar/gerenciar cada credencial são exibidas pelo console e consolidadas em [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## 3. IA - modelos

Os valores abaixo são os **defaults públicos efetivamente aplicados** pelo contrato atual de `provider_runtime_policy`.

| Variável | Default efetivo | Valores permitidos pelo runtime | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_MODEL` | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `gpt-5.6-luna` para custo/volume; `gpt-5.6-sol` quando a prioridade for máxima qualidade |
| `RASAI_DEEPSEEK_MODEL` | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `deepseek-v4-flash` no uso normal; `deepseek-v4-pro` quando a qualidade justificar maior custo/latência |
| `RASAI_MIMO_MODEL` | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `mimo-v2.5` no uso normal |
| `RASAI_XAI_MODEL` | `grok-4.6` | `grok-4.6` | default |
| `RASAI_QWEN_MODEL` | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `qwen3.8-flash` como default público; use `qwen3.8-max` somente quando deliberadamente necessário |
| `RASAI_GEMINI_MODEL` | `gemini-3.8-flash` | `gemini-3.8-flash` | default |
| `RASAI_ANTHROPIC_MODEL` | `claude-sonnet-5` | `claude-sonnet-5` | default |
| `RASAI_COPILOT_MODEL` | `auto` | `auto` | `auto`; deixa o SDK/assinatura resolver o modelo disponível para o usuário |

## 4. IA - reasoning

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` para custo/latência mínimos |
| `RASAI_DEEPSEEK_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` no uso normal |
| `RASAI_MIMO_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` no uso normal |
| `RASAI_XAI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` no uso normal |
| `RASAI_QWEN_REASONING_EFFORT` | não existe na superfície atual | Qwen usa `PROVIDER_DEFAULT` internamente | não criar variável inexistente |
| `RASAI_GEMINI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH` | `LOW` no uso normal |
| `RASAI_ANTHROPIC_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` no uso normal |
| `RASAI_COPILOT_REASONING_EFFORT` | não existe na superfície atual | Copilot usa `PROVIDER_DEFAULT` via SDK | não criar variável inexistente |

Aumentar reasoning pode elevar latência, tokens e custo. `AI=auto` consulta o provider registry, monta o conjunto elegível da execução e aplica roteamento/circuit breaker conforme o contrato vigente. Consulte [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## 5. IA - endpoints avançados

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_XAI_ENDPOINT` | `https://api.x.ai/v1/responses` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_QWEN_ENDPOINT` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_GEMINI_ENDPOINT` | `https://generativelanguage.googleapis.com/v1beta/interactions` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_ANTHROPIC_ENDPOINT` | `https://api.anthropic.com/v1/messages` | URL absoluta HTTP(S) | default HTTPS |

Não altere endpoints no uso normal. Um override incorreto pode causar falha, cobrança inesperada ou envio de dados ao destino errado. Em produção, não use HTTP para providers externos.

GitHub Copilot não expõe endpoint override nesta integração: o transporte é o SDK oficial autenticado pelo token de usuário configurado.

## 6. IA - contexto editorial / YMYL

Todos os campos têm default `auto`.

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_CONTENT_RISK_PROFILE` | `auto` | `auto`, `standard`, `ymyl` | `auto`, salvo classificação humana conhecida |
| `RASAI_YMYL_CATEGORY` | `auto` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` | `auto`; configure manualmente apenas com base editorial explícita |
| `RASAI_PAGE_PURPOSE` | `auto` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` | `auto` |
| `RASAI_INTENDED_AUDIENCE` | `auto` | `auto`, `general`, `professional`, `mixed` | `auto` |
| `RASAI_EXPERIENCE_REQUIREMENT` | `auto` | `auto`, `required`, `beneficial`, `not-expected` | `auto` |
| `RASAI_FRESHNESS_SENSITIVITY` | `auto` | `auto`, `low`, `medium`, `high` | `auto` |
| `RASAI_CONTENT_ORIGIN` | `auto` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` | `auto` |

Um campo configurado como `auto` permanece `AUTO` no estado persistido. Com IA ligada, o HTML pode exibir separadamente interpretação transitória baseada no conteúdo/evidências enviados. Essa leitura não sobrescreve o banco, não vira evidência determinística e não altera diretamente `SARI-001`/`SCORE-GEO-004`.

Detalhes: [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md) e [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md).

## 7. Métricas, padrões e Web Performance

A referência detalhada desta família está em [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md).

### 7.1 Controles gerais e métricas sem credencial

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | booleano | `true` | métricas derivadas de crawlability, indexability, canonical, sitemap, structured data e disponibilidade |
| `RASAI_RETRIEVAL_METRICS` | `true` | booleano | `true` | MRR e métricas de Information Retrieval quando houver dados suficientes |
| `RASAI_OPEN_WEB_METRICS` | `true` | booleano | `true` | W3C Performance APIs no browser já aberto, sem nova navegação |
| `RASAI_W3C_VALIDATOR` | `true` | booleano | `true`, bounded; desligar em ambiente que não permita validação externa | W3C Nu HTML Checker |
| `RASAI_MDN_OBSERVATORY` | `true` | booleano | `true`, salvo restrição de privacidade/egress | scan HTTP Observatory por origem |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | booleano | `true`; resultado só materializa com dataset/detector suficientes | habilita capacidade WebDX/Baseline |
| `RASAI_WEB_FEATURES_DATASET` | sem default | caminho para arquivo existente | dataset versionado `web-features` quando a análise for usada | fonte local WebDX/Baseline |
| `RASAI_STANDARDS_MAX_URLS` | `10` | inteiro `>= 0`; `0=todas` | `10` | teto de URLs submetidas a serviços externos desta família |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | número `> 0` e `< 3600` | `20` | timeout por request de standards |

Todos possuem desligamento explícito. `RASAI_WEB_PLATFORM_BASELINE=true` sem dataset suficiente resulta em `NOT_CONFIGURED`/`NO_DATA`, nunca em nota inventada.

### 7.2 Controle agregado de Web Performance

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` no controle agregado isolado; serviços individuais podem ativar a família quando seus requisitos existem e não há hard-off explícito | booleano | não materializar apenas para repetir default; use `false` quando quiser hard-off explícito da família externa | controle agregado vigente de PageSpeed/Lighthouse/CrUX |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | inteiro `>= 0`; `0=todas` | `10` | teto de páginas externas |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | número `> 0` | `120` | timeout por request |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` | `auto` | política de dados de campo |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | combinação CSV sem duplicatas das categorias suportadas | default | categorias pedidas ao PageSpeed |

`RASAI_WEB_PERFORMANCE=false` explícito impede a execução externa dessa família para a auditoria. Na ausência desse hard-off, PageSpeed e CrUX podem ser ativados pelos controles individuais abaixo.

### 7.3 PageSpeed e CrUX

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_PAGESPEED_ENABLED` | auto por requisitos; sem override | booleano | omitir para auto; `false` para desligamento explícito | liga/desliga PageSpeed individualmente |
| `RASAI_PAGESPEED_API_KEY` | sem default | API key válida | secret/env | credencial PageSpeed Insights |
| `RASAI_CRUX_ENABLED` | auto por requisitos; sem override | booleano | omitir para auto; `false` para desligamento explícito | liga/desliga CrUX dedicado individualmente |
| `RASAI_CRUX_API_KEY` | sem default | API key válida | secret/env | credencial CrUX API |

PageSpeed somente fica elegível quando `RASAI_PAGESPEED_API_KEY` existe. CrUX dedicado somente fica elegível quando `RASAI_CRUX_API_KEY` existe. As chaves nunca entram no INI.

`agentic-browsing` permanece experimental no Lighthouse. Se a resposta não trouxer a categoria, o RASAi mantém o campo como `NULL`; ausência não é convertida em zero.

### 7.4 Google Search Console

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_GSC_ENABLED` | auto por requisitos; sem override | booleano | omitir para auto; `false` para desligar | habilita coleta observacional Search Console |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | sem default | OAuth bearer token válido | secret/env temporário; SaaS deve usar secret store | credencial Search Console |
| `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` | sem default | `sc-domain:<domínio>` ou URL-prefix HTTP(S) absoluta | property exata que pertence ao audit/job | contexto mínimo não secreto da propriedade |
| `RASAI_GSC_SEARCH_ANALYTICS_DAYS` | `1` | inteiro `0..31` | `1`; `0` desliga apenas Search Analytics automático | período finalizado consultado por auditoria |
| `RASAI_GSC_SEARCH_MAX_ROWS` | `10000` | inteiro `1..50000` | `10000` ou menor se volume/quota exigirem | teto de linhas normalizadas |
| `RASAI_GSC_FINAL_DATA_LAG_DAYS` | `3` | inteiro `0..30` | `3` | defasagem usada para preferir dados `final` |

Search Console só fica `READY` com token + property. A automação bounded coleta Sitemaps, URL Inspection até `RASAI_STANDARDS_MAX_URLS` e Search Analytics finalizado conforme os limites acima. Resultados vão para `observability.db` e não alteram SARI automaticamente.

A property e os limites GSC podem ser persistidos no INI. O access token nunca pode ser persistido nele.

Orientação oficial para OAuth e criação de credenciais: https://developers.google.com/webmaster-tools/v1/how-tos/authorizing e https://console.cloud.google.com/apis/credentials.

## 8. Synthetic Navigation Apdex (`apdex.html`)

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | `false` | booleano | `false`; habilitar quando houver objetivo de medição sintética |
| `RASAI_APDEX_THRESHOLD_SECONDS` | sem default | número `> 0` | usar o SLO/KPM definido para o sistema; não inventar `T` |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | `100` | inteiro `>= 1` | `100` para execução representativa; reduzir apenas em smoke controlado |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | `ceil(1.25 x samples)` | inteiro `>= samples` | default derivado |
| `RASAI_APDEX_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline seguro; ampliar conscientemente |
| `RASAI_APDEX_TIMEOUT_SECONDS` | `max(45, 4T + 5)` | número `> 0` e `> 4T` | default derivado |
| `RASAI_APDEX_DELAY_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme sensibilidade do alvo |
| `RASAI_APDEX_CONCURRENCY` | `1` | `1`, `2` | `1`; `2` somente quando a carga paralela for aceitável |
| `RASAI_APDEX_MOBILE_CLIENT_PROFILE` | `mobile-balanced-chromium` | `mobile-compact-chromium`, `mobile-balanced-chromium`, `mobile-large-chromium` | default salvo objetivo explícito de viewport/cliente distinto |
| `RASAI_APDEX_MOBILE_HARDWARE_PROFILE` | `mobile-balanced` | `mobile-entry`, `mobile-balanced`, `mobile-premium` | `mobile-balanced`; CPU sintética, não RAM/hardware físico |
| `RASAI_APDEX_MOBILE_NETWORK_PROFILE` | `mobile-4g-balanced` | `mobile-3g-constrained`, `mobile-4g-balanced`, `mobile-4g-fast`, `mobile-5g` | `mobile-4g-balanced` como envelope controlado |
| `RASAI_APDEX_DESKTOP_CLIENT_PROFILE` | `desktop-balanced-chromium` | `desktop-1366-chromium`, `desktop-balanced-chromium`, `desktop-wide-chromium` | default salvo objetivo explícito de viewport/cliente distinto |
| `RASAI_APDEX_DESKTOP_HARDWARE_PROFILE` | `desktop-balanced` | `desktop-constrained`, `desktop-balanced` | `desktop-balanced`; CPU sintética, não RAM/hardware físico |
| `RASAI_APDEX_DESKTOP_NETWORK_PROFILE` | `desktop-balanced` | `desktop-constrained`, `desktop-balanced`, `desktop-fiber` | `desktop-balanced` como envelope controlado |
| `RASAI_APDEX_TABLET_CLIENT_PROFILE` | `tablet-balanced-chromium` | `tablet-compact-chromium`, `tablet-balanced-chromium` | default do perfil Tablet do Experience Apdex |
| `RASAI_APDEX_TABLET_HARDWARE_PROFILE` | `tablet-balanced` | `tablet-entry`, `tablet-balanced`, `tablet-premium` | `tablet-balanced`; CPU sintética, não RAM/hardware físico |
| `RASAI_APDEX_TABLET_NETWORK_PROFILE` | `tablet-4g-balanced` | `tablet-4g-balanced`, `tablet-wifi` | `tablet-4g-balanced` como envelope controlado |

Os nove presets acima controlam somente o ambiente sintético de execução: identidade/viewport do cliente, slowdown relativo de CPU e envelope de rede. Eles não mudam a fórmula Apdex, não alteram `SARI-001`/`SCORE-GEO-004` e não afirmam equivalência com RAM, GPU, térmica ou scheduler de um dispositivo físico.

O threshold `T` é obrigatório quando Synthetic Navigation Apdex está habilitado. Consulte [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md) e [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md).

## 9. Synthetic User Experience Apdex (`apdex-experience.html`)

| Variável | Default efetivo | Valores permitidos | Recomendado | Origem/observação |
|---|---|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | booleano | `false`; habilitar deliberadamente | exige Synthetic Navigation Apdex ativo |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | inteiro `>= 1` | `100` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 x samples)` | inteiro `>= samples` | default derivado | orçamento de tentativas por página |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | CSV com percentuais não negativos e soma 100 | usar população real quando conhecida | peso populacional |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | `cold`, `warm` | `cold` | sessão sintética |
| `RASAI_APDEX_ACQUISITION_MODE` | `auto` | `auto`, `isolated` | `auto` | compartilhamento físico somente quando compatível; avaliação permanece independente |
| `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | `USER_ACTION_DURATION`, `DOM_INTERACTIVE`, `LOAD_EVENT_START`, `LOAD_EVENT_END`, `RESPONSE_START`, `RESPONSE_END`, `LARGEST_CONTENTFUL_PAINT` | `USER_ACTION_DURATION` | KPM sintético |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3` | número `> 0` | `3` | referência/fallback configurado |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12` | número `> satisfied` | `12` | referência/fallback configurado |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | booleano | `true` | erros qualificáveis podem forçar Frustrated |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | `navigation`, `first-party`, `all` | `first-party` | escopo de erro |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5` | número `> 0` | `5` | janela pós-load |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | `1` | número `>= 0` | `1` | intervalo entre ações |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | `1` | `1`, `2` | `1` | workers simultâneos |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | booleano | `false` | importa calibração quando deliberadamente habilitado |
| `RASAI_DYNATRACE_BASE_URL` | sem default | URL HTTPS absoluta | somente na importação live | ambiente Dynatrace |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | texto não vazio | somente na importação live | ID da aplicação web Dynatrace |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | caminho para JSON existente | preferido à importação live para reprodutibilidade | configuração exportada/offline |
| `DYNATRACE_API_TOKEN` | sem default | token válido | secret/env; nunca persistir | importação live |

`RASAI_APDEX_ACQUISITION_MODE=auto` implementa shared acquisition com avaliação independente. Consulte [SYNTHETIC_SHARED_ACQUISITION.md](SYNTHETIC_SHARED_ACQUISITION.md) e [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## 10. Search Intelligence / Observability

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SERP_MODE` | `disabled` | `disabled`, `live`, `fixture` | `disabled` no baseline; `fixture` para teste; `live` somente com BYOK e intenção de consumo |
| `RASAI_SERP_PROVIDER` | `serpapi` | `serpapi`, `serpapi-bing`, `zenserp`, `scrapingdog` | selecionar conforme engine/quota |
| `RASAI_SERPAPI_API_KEY` | sem default | credencial SerpApi válida | secret/env |
| `RASAI_ZENSERP_API_KEY` | sem default | credencial Zenserp válida | secret/env |
| `RASAI_SCRAPINGDOG_API_KEY` | sem default | credencial ScrapingDog válida | secret/env |
| `RASAI_SERP_FIXTURE_PATH` | sem default | caminho para arquivo existente | usar somente em `fixture` |
| `RASAI_SERP_MAX_QUERIES` | `10` | inteiro `> 0` | `10` ou menor para smoke/custo controlado |
| `RASAI_SERP_MAX_REQUESTS` | `10` | inteiro `> 0` | `10` |
| `RASAI_SERP_MAX_DEPTH` | `20` | inteiro `> 0` | `20` |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | inteiro `>= 0` | `10` |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | número `> 0` | `20` |
| `RASAI_SERP_RETRIES` | `1` | inteiro `>= 0` | `1` |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | número `>= 0` | `1` ou maior se o provider exigir |
| `RASAI_SEARCH_AI_PROVIDER` | `none` | `none`, `fixture`, `openai` | `none` no baseline |

As variáveis de Search Console estão centralizadas na seção 7.4 porque agora fazem parte do catálogo unificado de métricas e serviços, embora seus dados sejam persistidos no domínio Observability.

O provider selecionado em `RASAI_SERP_PROVIDER` determina qual variável de credencial é obrigatória. O console mostra provider, variável esperada e URL oficial de cadastro/login. Ofertas gratuitas verificadas são limitadas; nenhuma integração SERP externa atual é classificada pelo RASAi como gratuita e ilimitada.

`RASAI_SERP_MAX_REQUESTS` limita tentativas HTTP do RASAi e não representa créditos comerciais do fornecedor.

Search Intelligence permanece separado de `SARI-001`/`SCORE-GEO-004`. Consulte [SERP_OBSERVATION.md](SERP_OBSERVATION.md), [SEARCH_INTELLIGENCE_HISTORY.md](SEARCH_INTELLIGENCE_HISTORY.md) e [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md).

## 11. Control plane / SaaS

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; aliases de parser aceitos: `postgres`, `pg` | `sqlite` para operação local; `postgresql` para control plane centralizado/hosted |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | DSN com esquema `postgres://` ou `postgresql://` e host válido | definir somente com backend PostgreSQL; tratar como segredo |

SQLite permanece disponível para operação local. PostgreSQL é o backend centralizado do control plane quando configurado. Seleção explícita de PostgreSQL sem URL válida ou com falha de conexão não provoca fallback silencioso para SQLite.

## 12. Web API / Identity

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_API_DOCS_ENABLED` | `false` | booleano | `false` fora de desenvolvimento controlado |
| `RASAI_API_AUDITS_ROOT` | `audits` | caminho | default |
| `RASAI_API_AUTH_MODE` | `deny` | `deny`, `trusted-header`, `oidc` | `deny` como fail-closed; `oidc` para ambiente hospedado |
| `RASAI_API_TRUSTED_USER_HEADER` | `x-rasai-user-id` | nome de header HTTP sem espaços | default |
| `RASAI_OIDC_ISSUER` | sem default | URL HTTPS absoluta, sem credenciais, fragmento ou query | issuer exato do IdP |
| `RASAI_OIDC_CLIENT_ID` | sem default | texto | client ID registrado no IdP |
| `RASAI_OIDC_AUDIENCE` | client ID configurado | texto | manter client ID quando o IdP não exigir audience distinta |
| `RASAI_OIDC_REDIRECT_URI` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS em ambiente não local |
| `RASAI_OIDC_SESSION_SECRET` | sem default | segredo forte | secret/env |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | sem default | nome de variável de ambiente válida | persistir somente a referência |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | CSV de algoritmos suportados | default salvo contrato do IdP |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | CSV contendo obrigatoriamente `openid` | default, reduzindo scopes quando possível |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | inteiro `300..86400` | `28800` |

Valores terminados em `_ENV` que representam referência de segredo persistem o **nome da variável**, não o segredo em si.

## 13. Remote control plane

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_REMOTE_BASE_URL` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS para host remoto |
| `RASAI_REMOTE_TOKEN_ENV` | sem default | nome de variável de ambiente válida | referenciar o bearer token; não persistir o token diretamente |
| `RASAI_REMOTE_USER_ID` | sem default | texto | somente no modo `trusted-header` de desenvolvimento em loopback |
| `RASAI_REMOTE_TIMEOUT_SECONDS` | `30` | número `> 0` e `<= 300` | `30` |

## 14. Browser / Playwright

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE` | sem override | caminho para executável existente | não definir; usar descoberta/instalação normal do Playwright |
| `RASAI_BROWSER_LOCALE` | `pt-BR` | locale BCP 47 | `pt-BR`, salvo objetivo explícito de outra localidade |

## 15. Precedência e persistência

Quando a mesma capacidade puder ser definida por CLI/menu, variável e default, a superfície explícita da execução prevalece conforme o contrato do respectivo módulo. O console resolve e exibe defaults mesmo quando as variáveis não existem no sistema operacional, permitindo distinguir **default efetivo** de **override configurado**.

Segredos podem existir apenas no processo atual e, no Windows, podem ser persistidos no escopo User somente após confirmação explícita. O INI do console não recebe segredos. Referências como `RASAI_OIDC_CLIENT_SECRET_ENV` e `RASAI_REMOTE_TOKEN_ENV` não são o segredo: guardam apenas o nome da variável que contém o segredo real.

Na família de standards, `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`, limites GSC, toggles e caminhos de dataset são não secretos e podem ser persistidos. `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`, `RASAI_PAGESPEED_API_KEY` e `RASAI_CRUX_API_KEY` nunca são persistidos no INI.

## 16. Telemetria e segurança de IA

`ai_exchange_log` pode conter conteúdo/evidências da página efetivamente enviados ao provider; por isso, o workspace deve ser tratado como artefato potencialmente sensível. O recorder remove credenciais, headers de autenticação, parâmetros de segredo e campos reconhecidos como raciocínio privado antes da persistência.

A interpretação editorial transitória de campos `auto` também não deve ser promovida a evidência persistida nem a verdade factual sobre credenciais, reputação, experiência pessoal, revisão profissional ou conformidade.

## 17. Regra para documentação de valores

Sempre que um `*.md` publicar valores de configuração, deve distinguir, quando aplicável:

1. **default efetivo do runtime**;
2. **domínio/valores permitidos pelo código**;
3. **valor recomendado para o cenário descrito**;
4. dependências e condições que tornam a variável obrigatória;
5. impacto de custo, carga, segurança ou reprodutibilidade quando material.

Quando não existir default tecnicamente seguro, a documentação deve declarar **sem default** em vez de inventar um valor.
