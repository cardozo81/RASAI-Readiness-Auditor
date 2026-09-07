# Configuração operacional

O RASAi pode ser configurado por CLI, console interativo, arquivo INI do console e variáveis de ambiente. Credenciais permanecem fora do arquivo INI.

## Prioridade prática

Para `rasai audit`, argumentos CLI explícitos prevalecem sobre defaults de ambiente quando o parâmetro possui equivalente CLI.

Para `rasai-console`:

1. `rasai-console.ini` fornece parâmetros persistidos não sensíveis;
2. variáveis de ambiente ficam disponíveis para credenciais e overrides avançados;
3. alterações de sessão valem imediatamente para o processo atual;
4. salvar INI persiste somente estado não sensível;
5. no Windows, secrets podem opcionalmente ser persistidos no ambiente User somente por ação explícita.

O console nunca grava API keys, OAuth tokens, senhas ou credentials no INI.

## Referência detalhada de variáveis

Consulte [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) para finalidade, tipo, domínio aceito, default efetivo, dependências, custo/impacto, exemplos e obtenção de credenciais.

O menu de ambiente/credenciais é organizado por fronteira funcional:

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

Pode armazenar entrada, projeto, idioma/mercado, `max-pages`, audits-root, device, configuração não sensível de IA, Web Performance e Synthetic Apdex.

Não armazena secrets como:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
qualquer TOKEN / SECRET / PASSWORD / CREDENTIAL
```

## Defaults gerais

```text
device                    = mobile
ai-provider               = none
ai-content-remediation    = off
ai-technical-remediation  = off
content-risk-profile      = auto
ymyl-category             = auto
page-purpose              = auto
intended-audience         = auto
experience-requirement    = auto
freshness-sensitivity     = auto
content-origin            = auto
Web Performance           = off
max-pages                 = 100
WebPerf max-pages         = 10
Web Performance timeout   = 120 s
language                  = pt-BR
market                    = BR
audits-root               = audits
Synthetic Apdex           = off
```

Para uma auditoria local sem IA nem integrações externas, basta informar o alvo.

## IA

Providers suportados:

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
```

Aliases:

```text
grok   -> xai
claude -> anthropic
```

AUTO:

```text
OpenAI -> DeepSeek -> MiMo
```

Credenciais:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
```

A existência da variável não garante saldo, quota, plano ou acesso ao modelo. Procedimentos completos estão em [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

### Defaults públicos de modelos

```text
OPENAI     gpt-5.6-luna
DEEPSEEK   deepseek-v4-flash
MIMO       mimo-v2.5
XAI        grok-4.6
QWEN       qwen3.8-flash
GEMINI     gemini-3.8-flash
ANTHROPIC  claude-sonnet-5
```

### Timeout de IA

```text
RASAI_AI_TIMEOUT_SECONDS=180
```

É timeout por tentativa, não da auditoria inteira.

## Contexto editorial da IA - YMYL e E-E-A-T

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

Todas usam `auto` quando ausentes.

Regras:

- valor explícito = contexto fornecido pelo operador;
- `auto` = hipótese provisória inferível apenas das evidências disponíveis;
- configuração explícita é preferível em YMYL claramente identificado;
- campos `auto` não podem virar fatos sobre autoria, expertise, experiência, compliance, reputação ou processo editorial;
- o contexto não cria score próprio de E-E-A-T/YMYL e **não altera diretamente `SARI-001` nem a fórmula vigente de `SCORE-GEO-003`**;
- essas variáveis não geram custo externo por si só; apenas condicionam chamadas de IA já habilitadas.

Base conceitual: [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md).

## Remediação textual por IA

```text
RASAI_AI_CONTENT_REMEDIATION
```

OFF por padrão. Quando habilitada e executada, `content-suggestions.html` e `ai-usage.html` expõem provider, modelo, reasoning, tentativas/status, duração, tokens e custo estimado quando existe base suportada.

## Rastreamento, descoberta e acesso de crawlers

A camada determinística faz parte do pipeline. A IA técnica opcional usa:

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

Default `false`; precedência:

```text
CLI explícito > RASAI_AI_TECHNICAL_REMEDIATION > false
```

Essa finalidade é advisory, não altera scoring e não decide automaticamente política de GPTBot/Google-Extended.

Página canônica:

```text
report/crawling-discovery.html
```

## Web Performance, Lighthouse e CrUX

```text
RASAI_WEB_PERFORMANCE
RASAI_WEB_PERFORMANCE_MAX_PAGES
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS
RASAI_WEB_PERFORMANCE_FIELD_SOURCE
RASAI_LIGHTHOUSE_CATEGORIES
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
```

Default de timeout externo:

```text
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS=120
```

Field source:

```text
auto
pagespeed
crux
none
```

`crux` direto exige `RASAI_CRUX_API_KEY`.

## Search Console / Observability

Os comandos `rasai observe gsc-sites`, `gsc-sitemaps`, `gsc-search`, `gsc-appearance` e `gsc-inspect` usam OAuth bearer token em runtime:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

Esse valor é **token OAuth temporário**, não API key. Não deve ser gravado no INI, artifact, SQLite ou HTML. O token precisa ter escopo Search Console compatível e acesso à propriedade informada. Consulte [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md) e [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

## Synthetic Apdex

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

Quando habilitado:

```text
T                      = obrigatório
amostras válidas       = 100
máximo de tentativas   = ceil(1.25 × alvo)
máximo de páginas      = 1
timeout por navegação  = max(45 s, 4T + 5 s)
delay                  = 1 s
concorrência           = 1; máximo 2
```

T não recebe valor arbitrário.

## Dispositivo

```text
RASAI_DEVICE_CONTEXT
```

Valores: `mobile`, `desktop`, `both`. Default: `mobile`.

## Segurança

- use variáveis de ambiente ou secret manager apropriado;
- secrets não entram no INI;
- persistência Windows/User exige ação explícita;
- logs e relatórios não devem registrar secrets;
- credencial configurada não implica crédito/quota;
- variáveis persistidas não equivalem a secret manager;
- integrações derivadas não alteram silenciosamente SARI/SCORE-GEO.

## Identificadores internos

Identificadores técnicos persistidos podem permanecer em tabelas e eventos por compatibilidade operacional. A interface pública usa a nomenclatura funcional do RASAi e do SARI.

## Documentos relacionados

- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [CLI_REFERENCE.md](CLI_REFERENCE.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md)
- [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md)
- [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md)
- [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)
