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

Não armazena secrets como chaves de IA, tokens OAuth, passwords ou credentials.

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

`AUTO` usa a cadeia core OpenAI → DeepSeek → MiMo. Providers de extensão permanecem explicit-only.

Credenciais são lidas das variáveis documentadas em [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). A existência da variável não garante saldo, quota, plano ou acesso ao modelo.

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

Esses defaults pertencem à política pública de runtime (`provider_runtime_policy`); seleção explícita válida prevalece.

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
- o contexto não cria score próprio de E-E-A-T/YMYL e **não altera diretamente `SARI-001` nem a fórmula vigente de `SCORE-GEO-004`**;
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

Essa finalidade é advisory, não altera scoring e não decide automaticamente política de crawler.

Página canônica:

```text
report/crawling-discovery.html
```

## Web Performance, Lighthouse e CrUX

Principais variáveis:

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

`crux` direto exige a credencial documentada para CrUX.

## Search Console / Observability

Os comandos observacionais do Search Console usam OAuth bearer token em runtime. Esse valor é temporário, não é API key e não deve ser gravado no INI, artifact, SQLite ou HTML.

Consulte [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md) e [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

## Synthetic Apdex

Principais variáveis:

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

Quando habilitado, `T` deve ser definido pelo perfil desejado; o RASAi não inventa threshold universal.

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
- integrações derivadas não alteram silenciosamente `SARI-001/SCORE-GEO-004`.

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

## Persistência do console e precedência de configuração

O console usa `rasai-console.ini` (ou o caminho indicado por `RASAI_CONSOLE_INI`) como contrato persistente de parâmetros não sensíveis. Ao salvar, o RASAi grava o estado operacional e uma seção `[environment]` com variáveis reconhecidas não secretas. Chaves, tokens, passwords e credenciais continuam fora do INI.

Na inicialização, a ordem é: valor já presente no processo/Windows > valor persistido em `[environment]` > valor persistido nas seções funcionais do INI > default. O INI é lido antes da execução e seus valores não secretos são projetados novamente para o ambiente dos adapters. Assim, `RASAI_AI_CONTENT_REMEDIATION`, `RASAI_AI_TECHNICAL_REMEDIATION`, Web Performance, timeouts, modelo/reasoning selecionados e Synthetic Navigation Apdex sobrevivem a Save -> fechar -> reabrir.

`RASAI_AI_CONTENT_REMEDIATION` controla conteúdo. `RASAI_AI_TECHNICAL_REMEDIATION` controla somente a remediação técnica advisory de crawling/discovery. Nenhuma das duas eleva SARI/Confidence por opinião da IA.

