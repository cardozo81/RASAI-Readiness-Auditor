# Configuração operacional

O RASAi pode ser configurado por CLI, console interativo, arquivo INI do console e variáveis de ambiente. Credenciais permanecem fora do arquivo INI.

## Precedência prática

Para `rasai audit`, argumentos CLI explícitos prevalecem sobre variáveis de ambiente quando a opção possui equivalente CLI.

Para `rasai-console`:

1. `rasai-console.ini` fornece parâmetros persistidos não sensíveis;
2. variáveis já presentes no processo/ambiente têm precedência sobre valores persistidos equivalentes;
3. alterações de sessão valem imediatamente para o processo atual;
4. salvar o INI persiste somente estado não sensível;
5. no Windows, secrets podem opcionalmente ser persistidos no ambiente User somente por ação explícita do operador.

O console nunca grava API keys, OAuth tokens, senhas ou outras credenciais no INI.

## Referência canônica de variáveis

Consulte [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) para finalidade, tipo, domínio aceito, **default efetivo**, **valores permitidos**, **recomendação**, dependências e impacto operacional de cada variável.

Quando este guia resumido e `ENVIRONMENT_VARIABLES.md` divergirem, a referência detalhada deve ser reconciliada com o runtime; não se deve preservar um valor documental antigo apenas por compatibilidade textual.

## Menu de ambiente/credenciais

O console organiza a configuração por fronteira funcional:

```text
1. Aplicação e execução
2. IA - credenciais
3. IA - modelos e reasoning
4. IA - endpoints avançados
5. IA - contexto editorial / YMYL
6. Web Performance / Google APIs
7. Synthetic Apdex
8. Browser / Playwright
A. Todas as variáveis
D. Abrir documentação detalhada
V. Voltar
```

## Arquivo INI do console

Arquivo padrão:

```text
rasai-console.ini
```

Pode armazenar entrada, projeto, idioma/mercado, `max-pages`, `audits-root`, device, configuração não sensível de IA, Web Performance e Synthetic Apdex.

Não armazena secrets como chaves de IA, tokens OAuth, passwords ou credenciais de integração.

## Valores padrão gerais

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| dispositivo | `mobile` | `mobile`, `desktop`, `both` | `mobile` para execução mínima; `both` quando for necessário comparar dispositivos |
| provider de IA | `none` | `none`, `openai`, `deepseek`, `mimo`, `xai`, `grok`, `qwen`, `gemini`, `anthropic`, `claude`, `auto` | `none` sem necessidade semântica; `auto` quando houver múltiplos providers aptos e política de fallback desejada |
| remediação de conteúdo por IA | `false` | booleano | `false`; habilitar deliberadamente |
| remediação técnica por IA | `false` | booleano | `false`; habilitar deliberadamente |
| contexto editorial | `auto` | domínios definidos em `ENVIRONMENT_VARIABLES.md` | `auto`, salvo quando houver classificação humana conhecida |
| Web Performance | `false` | booleano | `false` por segurança de quota/custo; habilitar quando necessário |
| `max-pages` da auditoria | `100` | inteiro positivo conforme CLI | ajustar conscientemente ao escopo |
| Web Performance `max-pages` | `10` | inteiro `>= 0`; `0=todas` | `10` ou menor em smoke |
| timeout de Web Performance | `120 s` | número `> 0` | `120 s` |
| idioma | `pt-BR` | valor textual aceito pela configuração | `pt-BR` para o produto no Brasil |
| mercado | `BR` | valor textual aceito pela configuração | `BR` quando o mercado auditado for Brasil |
| `audits-root` | `audits` | caminho válido | default |
| Synthetic Navigation Apdex | `false` | booleano | `false`; habilitar apenas com `T` e autorização de carga adequados |
| Synthetic User Experience Apdex | `false` | booleano | `false`; habilitar somente quando a medição calibrada for desejada |

## IA

### Providers e aliases

Providers canônicos:

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
```

Aliases CLI:

```text
grok   -> xai
claude -> anthropic
```

### `AUTO`

`AI=auto` **não é uma cadeia fixa OpenAI → DeepSeek → MiMo** no runtime vigente.

O coordenador:

1. consulta o `provider_registry`;
2. considera todos os providers com `auto_eligible=true`;
3. exige credencial e configuração válidas;
4. aplica exclusões de `RASAI_AI_AUTO_EXCLUDE`;
5. usa round-robin entre necessidades de IA;
6. tenta cada provider elegível no máximo uma vez por necessidade;
7. aplica circuit breaker/saúde por execução;
8. encerra a necessidade no primeiro resultado válido.

Excluir um provider de `AUTO` não remove sua credencial nem impede seleção explícita posterior.

### Modelos e reasoning

| Provider | Default público de modelo | Modelos permitidos | Default de reasoning | Recomendado |
|---|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `NONE` | default público; elevar capacidade deliberadamente |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `NONE` | default público |
| MiMo | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `NONE` | default público |
| xAI | `grok-4.6` | `grok-4.6` | `LOW` | default público |
| Qwen | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `PROVIDER_DEFAULT` | default público |
| Gemini | `gemini-3.8-flash` | `gemini-3.8-flash` | `LOW` | default público |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | `LOW` | default público |

Os valores permitidos de reasoning são publicados em `ENVIRONMENT_VARIABLES.md` e `PROVIDER_REGISTRY.md`.

### Timeout de IA

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---:|---|---|
| `RASAI_AI_TIMEOUT_SECONDS` | `180` | número finito `> 0`, em segundos | `180`; reduzir/aumentar somente por necessidade operacional |

O timeout vale por tentativa de provider, não para a auditoria inteira.

## Contexto editorial da IA — YMYL e E-E-A-T

Variáveis:

```text
RASAI_CONTENT_RISK_PROFILE
RASAI_YMYL_CATEGORY
RASAI_PAGE_PURPOSE
RASAI_INTENDED_AUDIENCE
RASAI_EXPERIENCE_REQUIREMENT
RASAI_FRESHNESS_SENSITIVITY
RASAI_CONTENT_ORIGIN
```

Todas usam `auto` quando ausentes. Os domínios completos de valores permitidos estão em [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md).

Regras:

- valor explícito representa contexto fornecido pelo operador;
- `auto` permite somente hipótese provisória baseada nas evidências disponíveis;
- configuração explícita é preferível quando a classificação YMYL já é conhecida;
- campos `auto` não podem virar fatos sobre autoria, expertise, experiência, compliance, reputação ou processo editorial oculto;
- o contexto não cria score E-E-A-T/YMYL e não altera diretamente `SARI-001`/`SCORE-GEO-004`;
- essas variáveis não criam custo externo por si só: apenas condicionam chamadas de IA que já estejam habilitadas.

Base conceitual: [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md).

## Remediação de conteúdo por IA

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | booleano | `false`; habilitar quando houver provider apto e objetivo explícito de gerar sugestões |

Quando executada, `content-suggestions.html` e `ai-usage.html` expõem provider, modelo, reasoning, tentativas/status, duração, tokens e custo estimado quando existe base confiável.

## Rastreamento, descoberta e acesso de crawlers

A camada determinística faz parte do pipeline. A IA técnica opcional usa:

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | booleano | `false`; habilitar somente quando orientação advisory por IA for desejada |

Precedência:

```text
CLI explícito > RASAI_AI_TECHNICAL_REMEDIATION > false
```

Essa finalidade é advisory, não altera scoring e não decide automaticamente política de crawler.

Página canônica:

```text
report/crawling-discovery.html
```

## Web Performance, Lighthouse e CrUX

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` | booleano | `false`; habilitar quando a coleta externa for necessária |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | inteiro `>= 0`; `0=todas` | `10` ou menos em smoke |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | número `> 0` | `120` |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` | `auto` |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | combinação CSV sem duplicatas dessas cinco categorias | default das cinco categorias |
| `RASAI_PAGESPEED_API_KEY` | sem default | API key válida | secret/env |
| `RASAI_CRUX_API_KEY` | sem default | API key válida | secret/env; obrigatória para `field_source=crux` |

`agentic-browsing` permanece experimental. Se a resposta não materializar a categoria, o valor correspondente permanece indisponível/`NULL`; a ausência não vira zero e não invalida as demais categorias.

## Search Console e Observability

Comandos observacionais do Search Console usam OAuth bearer token em runtime. Esse valor é temporário, não é API key e não deve ser gravado no INI, artifact, SQLite ou HTML.

Consulte [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md) e [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md).

## Synthetic Navigation Apdex

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | `false` | booleano | `false` |
| `RASAI_APDEX_THRESHOLD_SECONDS` | sem default | número finito `> 0` | usar SLO/KPM definido para o sistema; não inventar `T` |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | `100` | inteiro `>= 1` | `100`; reduzir apenas em smoke controlado |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | `ceil(1.25 × samples)` | inteiro positivo e validado pelo runtime | default derivado |
| `RASAI_APDEX_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline de carga |
| `RASAI_APDEX_TIMEOUT_SECONDS` | `max(45, 4T + 5)` | número `> 4T` | default derivado |
| `RASAI_APDEX_DELAY_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme sensibilidade do alvo |
| `RASAI_APDEX_CONCURRENCY` | `1` | `1`, `2` | `1` |

Synthetic Navigation Apdex só pode ser habilitado com `T` explícito. Consulte [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md).

## Synthetic User Experience Apdex

Os defaults, valores permitidos e recomendados dessa camada estão consolidados em [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md) e [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md). Ela permanece desabilitada por padrão e pode usar configuração Dynatrace importada quando explicitamente solicitada.

## Dispositivo

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_DEVICE_CONTEXT` | `mobile` | `mobile`, `desktop`, `both` | `mobile` para execução mínima; `both` quando a comparação Desktop × Mobile for necessária |

## Persistência do console

O console usa `rasai-console.ini` ou o caminho indicado por `RASAI_CONSOLE_INI` como persistência de parâmetros não sensíveis. Na inicialização, a precedência é:

```text
valor já presente no processo/Windows
> valor persistido em [environment]
> valor persistido nas seções funcionais do INI
> default do runtime
```

Valores não secretos do INI são projetados novamente para o ambiente dos adapters antes da execução. Assim, remediação de IA, Web Performance, timeouts, modelo/reasoning selecionados e Synthetic Apdex podem sobreviver a salvar → fechar → reabrir.

## Segurança

- use variáveis de ambiente ou secret manager apropriado;
- secrets não entram no INI;
- persistência Windows/User exige ação explícita;
- logs e relatórios não devem registrar secrets;
- credencial configurada não implica crédito/quota;
- variáveis persistidas não equivalem a secret manager;
- integrações derivadas não alteram silenciosamente `SARI-001/SCORE-GEO-004`.

## Documentos relacionados

- [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md)
- [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md)
- [`INTERACTIVE_CONSOLE.md`](INTERACTIVE_CONSOLE.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_GUIDE.md`](AI_GUIDE.md)
- [`PROVIDER_REGISTRY.md`](PROVIDER_REGISTRY.md)
- [`GOOGLE_API_KEYS.md`](GOOGLE_API_KEYS.md)
- [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md)
- [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
- [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md)
- [`specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md`](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)