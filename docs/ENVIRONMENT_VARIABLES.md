# Variáveis de ambiente - referência completa

Referência operacional da superfície de variáveis reconhecida pelo RASAi - Search & AI Readiness Auditor.

**Verificação contra o runtime:** 10/09/2026.

Variáveis de ambiente são *overrides* avançados. Quando existe um default seguro, o runtime aplica esse valor mesmo que a variável não esteja materializada no sistema operacional. Segredos não devem ser gravados em `rasai-console.ini`, arquivos de URL, relatórios, bancos ou logs.

## Como interpretar as tabelas

- **Default efetivo:** valor usado pelo runtime na ausência de override.
- **Valores permitidos:** domínio validado pelo código. Quando a célula descreve um tipo/faixa, qualquer valor que satisfaça aquela validação pode ser aceito.
- **Recomendado:** configuração operacional indicada para o uso normal. Quando consta “default”, a recomendação é não criar a variável apenas para repetir o valor já aplicado internamente.
- **Sem default:** a aplicação não inventa um valor. A variável só deve ser definida quando a integração ou o modo correspondente realmente exigir.
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
| `RASAI_AI_AUTO_EXCLUDE` | vazio | CSV ou lista separada por `;` de providers válidos e elegíveis ao pool AUTO | vazio; exclua apenas provider que deva permanecer configurado, mas fora do AUTO | remove providers apenas do pool `AI=auto` |
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | booleano | `false`; habilite quando houver provider apto e a remediação por IA for desejada | habilita remediação de conteúdo por IA |
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | booleano | `false`; habilite apenas quando a remediação técnica advisory for necessária | habilita remediação técnica por IA |
| `RASAI_AI_EXCHANGE_LOG_MAX_BYTES` | `524288` | inteiro de `4096` a `4194304` bytes | `524288` | limite por request/response sanitizado no log de intercâmbio de IA |

No console local, a preferência normal de timezone deve ser configurada pelo item **Timezone apresentação** e persistida em `[presentation] timezone = ...` no `rasai-console.ini`. `RASAI_PRESENTATION_TIMEZONE` é um override avançado para automação/processos e não reinterpreta nem regrava timestamps canônicos UTC. O offset corrente, como `UTC-03:00`, é apenas apresentação; o valor persistido de configuração é o identificador IANA. Consulte [TIMEZONE_CONTRACT.md](TIMEZONE_CONTRACT.md).

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

A presença de uma credencial não prova crédito, quota, plano nem acesso ao modelo. Em `AI=auto`, entram no pool apenas providers registrados como elegíveis, com credencial/configuração válidas e não excluídos pelo usuário.

## 3. IA - modelos

Os defaults abaixo são os **defaults públicos efetivamente aplicados** por `provider_runtime_policy`; eles prevalecem sobre defaults internos antigos de classes/qualificação que não representam a superfície pública atual.

| Variável | Default efetivo | Valores permitidos pelo runtime | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_MODEL` | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `gpt-5.6-luna` para custo/volume; `gpt-5.6-sol` quando a prioridade for máxima qualidade |
| `RASAI_DEEPSEEK_MODEL` | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `deepseek-v4-flash` no uso normal; `deepseek-v4-pro` quando a qualidade justificar maior custo/latência |
| `RASAI_MIMO_MODEL` | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `mimo-v2.5` no uso normal |
| `RASAI_XAI_MODEL` | `grok-4.6` | `grok-4.6` | default |
| `RASAI_QWEN_MODEL` | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `qwen3.8-flash` como default público; use `qwen3.8-max` somente quando deliberadamente necessário |
| `RASAI_GEMINI_MODEL` | `gemini-3.8-flash` | `gemini-3.8-flash` | default |
| `RASAI_ANTHROPIC_MODEL` | `claude-sonnet-5` | `claude-sonnet-5` | default |

## 4. IA - reasoning

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_OPENAI_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` para custo/latência mínimos; elevar deliberadamente quando a tarefa exigir |
| `RASAI_DEEPSEEK_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` no uso normal |
| `RASAI_MIMO_REASONING_EFFORT` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` no uso normal |
| `RASAI_XAI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` no uso normal |
| `RASAI_QWEN_REASONING_EFFORT` | não existe na superfície atual | Qwen usa `PROVIDER_DEFAULT` internamente | não criar variável inexistente |
| `RASAI_GEMINI_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH` | `LOW` no uso normal |
| `RASAI_ANTHROPIC_REASONING_EFFORT` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` no uso normal |

Aumentar reasoning pode elevar latência, tokens e custo. `AI=auto` não é cadeia fixa: o runtime consulta o provider registry, monta o conjunto elegível da execução e aplica roteamento/circuit breaker conforme o contrato vigente. Consulte [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## 5. IA - endpoints avançados

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_XAI_ENDPOINT` | `https://api.x.ai/v1/responses` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_QWEN_ENDPOINT` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_GEMINI_ENDPOINT` | `https://generativelanguage.googleapis.com/v1beta/interactions` | URL absoluta HTTP(S) | default HTTPS |
| `RASAI_ANTHROPIC_ENDPOINT` | `https://api.anthropic.com/v1/messages` | URL absoluta HTTP(S) | default HTTPS |

Não altere endpoints no uso normal. Um override incorreto pode causar falha, cobrança inesperada ou envio de dados ao destino errado. Em produção, não use HTTP para providers externos.

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

## 7. Web Performance / Google APIs

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` | booleano | `false` por segurança/custo; habilitar quando a coleta for requerida | coleta externa PageSpeed/Lighthouse/CrUX |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | inteiro `>= 0`; `0=todas` | `10` ou limite menor para smoke/teste | teto de páginas externas |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | número `> 0` | `120` | timeout por request |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` | `auto` | política de dados de campo |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | combinação CSV sem duplicatas de `performance`, `accessibility`, `best-practices`, `seo`, `agentic-browsing` | default de cinco categorias | categorias pedidas ao PageSpeed |
| `RASAI_PAGESPEED_API_KEY` | sem default | API key válida | secret/env | PageSpeed Insights |
| `RASAI_CRUX_API_KEY` | sem default | API key válida | secret/env; necessária para `field_source=crux` | CrUX direto |

`agentic-browsing` permanece experimental no Lighthouse. Se a resposta não trouxer a categoria, o RASAi mantém o campo como `NULL`; não converte ausência em zero e não invalida as demais categorias recebidas.

## 8. Synthetic Navigation Apdex (`apdex.html`)

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | `false` | booleano | `false`; habilitar quando houver objetivo de medição sintética |
| `RASAI_APDEX_THRESHOLD_SECONDS` | sem default | número `> 0` | usar o SLO/KPM definido para o sistema; não inventar `T` |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | `100` | inteiro `>= 1` | `100` para execução representativa; reduzir apenas em smoke controlado |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | `ceil(1.25 × samples)` | inteiro `>= samples` | default derivado |
| `RASAI_APDEX_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline seguro; ampliar conscientemente |
| `RASAI_APDEX_TIMEOUT_SECONDS` | `max(45, 4T + 5)` | número `> 0` e `> 4T` | default derivado |
| `RASAI_APDEX_DELAY_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme sensibilidade do alvo |
| `RASAI_APDEX_CONCURRENCY` | `1` | `1`, `2` | `1`; `2` somente quando a carga paralela for aceitável |

O threshold `T` é obrigatório quando Synthetic Navigation Apdex está habilitado porque não existe objetivo de desempenho universal defensável para todos os sites. Consulte [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md).

## 9. Synthetic User Experience Apdex (`apdex-experience.html`)

O recurso permanece default OFF. Quando habilitado sem override manual ou importação Dynatrace, o runtime aplica somente os defaults de referência que podem ser mapeados de forma tecnicamente defensável ao sintético do RASAi.

| Variável | Default efetivo | Valores permitidos | Recomendado | Origem/observação |
|---|---|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | booleano | `false`; habilitar deliberadamente | exige Synthetic Navigation Apdex ativo |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | inteiro `>= 1` | `100`; ampliar quando for necessário reduzir incerteza | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 × samples)` | inteiro `>= samples` | default derivado | orçamento de tentativas por página |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline seguro | RASAi sintético |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | CSV com `mobile`, `desktop` e/ou `tablet`, percentuais finitos `>=0`, soma exata `100` | usar população real conhecida quando o objetivo for comparar com RUM | peso populacional das amostras, não número de subrequests |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | `cold`, `warm` | `cold` para baseline reprodutível | não há equivalência 1:1 com RUM |
| `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | `USER_ACTION_DURATION`, `DOM_INTERACTIVE`, `LOAD_EVENT_START`, `LOAD_EVENT_END`, `RESPONSE_START`, `RESPONSE_END`, `LARGEST_CONTENTFUL_PAINT` | `USER_ACTION_DURATION` no perfil compatível atual | fallback executável; `VISUALLY_COMPLETE` não é executável com semântica equivalente ao fornecedor |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3` | número `> 0` | `3` no perfil compatível | referência/fallback Dynatrace Load |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12` | número `> 0` e maior que o limiar Satisfied | `12` no perfil compatível | independente de `4T` |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | booleano | `true` | erros qualificáveis podem forçar Frustrated |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | `navigation`, `first-party`, `all` | `first-party` | escolha conservadora do RASAi |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5` | número `> 0` | `5` | janela pós-load para recursos tardios |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme sensibilidade do alvo | intervalo mínimo entre ações |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | `1` | `1`, `2` | `1` | workers simultâneos |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | booleano | `false`; habilitar somente com configuração Dynatrace deliberada | importa calibração |
| `RASAI_DYNATRACE_BASE_URL` | sem default | URL HTTPS absoluta | definir apenas na importação live | ambiente Dynatrace |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | texto não vazio | definir apenas na importação live | ID da aplicação web Dynatrace |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | caminho para arquivo JSON existente | **preferido à importação live quando o objetivo for reprodutibilidade** | configuração exportada/offline |
| `DYNATRACE_API_TOKEN` | sem default | token válido | secret/env; nunca persistir | necessário somente na importação live |

### Referência Dynatrace e limite de equivalência

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

O perfil interno `DYNATRACE_WEB_LOAD_REFERENCE_2026` usa referências públicas de Load Action para mapear KPM/thresholds sem afirmar equivalência de fornecedor. Os trechos originais e respectivas traduções pt-BR que sustentam o fallback e os valores de referência são mantidos em [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md), evitando reprodução redundante aqui.

O RASAi não calcula `VISUALLY_COMPLETE` com semântica equivalente à do fornecedor; o default sintético defensável é `USER_ACTION_DURATION` com 3 s / 12 s. XHR e Custom Actions autônomas exigiriam jornadas/clickpaths compatíveis e não são inventadas a partir da navegação do crawler.

## 10. Search Intelligence / Observability

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SERP_MODE` | `disabled` | `disabled`, `live`, `fixture` | `disabled` no baseline; `fixture` para teste; `live` somente com BYOK e intenção de consumo |
| `RASAI_SERP_PROVIDER` | `serpapi` | `serpapi`, `serpapi-bing` | `serpapi`, salvo objetivo explícito de Bing |
| `RASAI_SERPAPI_API_KEY` | sem default | credencial SerpApi válida | secret/env |
| `RASAI_SERP_FIXTURE_PATH` | sem default | caminho para arquivo existente | usar somente em `fixture` |
| `RASAI_SERP_MAX_QUERIES` | `10` | inteiro `> 0` | `10` ou menor para smoke/custo controlado |
| `RASAI_SERP_MAX_REQUESTS` | `10` | inteiro `> 0` | `10` |
| `RASAI_SERP_MAX_DEPTH` | `20` | inteiro `> 0` | `20` |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | inteiro `>= 0` | `10` |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | número `> 0` | `20` |
| `RASAI_SERP_RETRIES` | `1` | inteiro `>= 0` | `1` |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | número `>= 0` | `1` ou maior se o provider/alvo exigir |
| `RASAI_SEARCH_AI_PROVIDER` | `none` | `none`, `fixture`, `openai` | `none` no baseline; `fixture` para teste; `openai` quando análise competitiva por IA for desejada |
| `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | sem default | OAuth bearer token válido | secret/env, temporário |

Search Intelligence permanece separado de `SARI-001`/`SCORE-GEO-004`. Consulte [SERP_OBSERVATION.md](SERP_OBSERVATION.md), [SEARCH_INTELLIGENCE_HISTORY.md](SEARCH_INTELLIGENCE_HISTORY.md) e [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md).

## 11. Control plane / SaaS

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; aliases internos aceitos `postgres`, `pg` | `sqlite` para operação local; `postgresql` como valor canônico para control plane centralizado/hosted |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | DSN com esquema `postgres://` ou `postgresql://` e host válido | definir somente com backend PostgreSQL; tratar como segredo |

SQLite permanece disponível para operação local. PostgreSQL é o backend centralizado do control plane quando configurado. Seleção explícita de PostgreSQL sem URL válida ou com falha de conexão não provoca fallback silencioso para SQLite.

## 12. Web API / Identity

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_API_DOCS_ENABLED` | `false` | booleano | `false` fora de desenvolvimento controlado |
| `RASAI_API_AUDITS_ROOT` | `audits` | caminho | default, salvo layout deliberadamente distinto |
| `RASAI_API_AUTH_MODE` | `deny` | `deny`, `trusted-header`, `oidc` | `deny` como fail-closed; `oidc` para ambiente hospedado; `trusted-header` somente em desenvolvimento/gateway confiável |
| `RASAI_API_TRUSTED_USER_HEADER` | `x-rasai-user-id` | nome de header HTTP sem espaços | default |
| `RASAI_OIDC_ISSUER` | sem default | URL HTTPS absoluta, sem credenciais, fragmento ou query | issuer exato do IdP, apenas em OIDC |
| `RASAI_OIDC_CLIENT_ID` | sem default | texto | client ID registrado no IdP |
| `RASAI_OIDC_AUDIENCE` | client ID configurado | texto | manter client ID salvo quando o IdP não exigir audience distinta |
| `RASAI_OIDC_REDIRECT_URI` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS em ambiente não local |
| `RASAI_OIDC_SESSION_SECRET` | sem default | segredo forte | secret/env; obrigatório no fluxo web OIDC |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | sem default | **nome** de uma variável de ambiente válida | persistir somente a referência; manter o segredo real na variável referenciada |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | CSV sem duplicatas de `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512` | default, salvo contrato explícito do IdP |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | CSV que contenha obrigatoriamente `openid` | default, reduzindo scopes se o IdP e o produto permitirem |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | inteiro `300..86400` | `28800`, salvo política de segurança mais restritiva |

Valores terminados em `_ENV` que representam referência de segredo persistem o **nome da variável**, não o segredo em si.

## 13. Remote control plane

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_REMOTE_BASE_URL` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS para host remoto |
| `RASAI_REMOTE_TOKEN_ENV` | sem default | nome de variável de ambiente válida | referenciar o bearer token; não persistir o token diretamente |
| `RASAI_REMOTE_USER_ID` | sem default | texto | usar somente no modo `trusted-header` de desenvolvimento em loopback; não usar em host remoto |
| `RASAI_REMOTE_TIMEOUT_SECONDS` | `30` | número `> 0` e `<= 300` | `30` |

## 14. Browser / Playwright

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE` | sem override | caminho para executável existente | não definir; usar descoberta/instalação normal do Playwright, salvo necessidade controlada |
| `RASAI_BROWSER_LOCALE` | `pt-BR` | locale BCP 47 | `pt-BR`, salvo objetivo explícito de outra localidade |

## 15. Precedência e persistência

Quando a mesma capacidade puder ser definida por CLI/menu, variável e default, a superfície explícita da execução prevalece conforme o contrato do respectivo módulo. O console resolve e exibe defaults mesmo quando as variáveis não existem no sistema operacional, permitindo distinguir **default efetivo** de **override configurado**.

Segredos podem existir apenas no processo atual e, no Windows, podem ser persistidos no escopo User somente após confirmação explícita. O INI do console não recebe segredos. Referências como `RASAI_OIDC_CLIENT_SECRET_ENV` e `RASAI_REMOTE_TOKEN_ENV` não são o segredo: guardam apenas o nome da variável que contém o segredo real.

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

Quando não existir default tecnicamente seguro, a documentação deve declarar **“sem default”** em vez de inventar um valor.