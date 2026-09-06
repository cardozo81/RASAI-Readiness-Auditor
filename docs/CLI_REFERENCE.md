# Referência da CLI

Referência operacional da linha de comando do SearchGEO Readiness Auditor.

## Entrada principal

```text
searchgeo [-h] [--version] [--config PATH] audit ...
```

Ajuda:

```text
`-h`, `--help`
```

Versão:

```text
`--version`
```

Configuração geral de aplicação/logging:

```text
`--config PATH`
```

## Comando `audit`

Forma geral:

```powershell
searchgeo audit target [target ...] [opções]
```

`target` pode ser domínio ou URL HTTP(S). Também é possível usar `--urls-file PATH`.

## Entrada e contexto

| Opção | Uso |
|---|---|
| `target` | um ou mais domínios/URLs da mesma origem normalizada |
| `--urls-file PATH` | TXT UTF-8 com uma URL/domínio por linha |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | contexto de idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas auditadas |
| `--audits-root PATH` | diretório raiz dos workspaces; default `audits` |
| `--device-context` | `mobile`, `desktop` ou `both` |

Default de dispositivo:

```text
mobile
```

Override por ambiente:

```text
`SEARCHGEO_DEVICE_CONTEXT`
```

## IA

Seleção:

```text
`--ai-provider`
```

Valores aceitos pela superfície pública:

```text
none
openai
deepseek
mimo
auto
xai
grok
qwen
gemini
anthropic
claude
```

AUTO permanece limitado a:

```text
OpenAI -> DeepSeek -> MiMo
```

Providers adicionais são seleção explícita.

Modelo explícito:

```text
`--ai-model MODEL_ID`
```

`--ai-model` não deve ser usado com `auto`; AUTO usa configuração por provider.

### Defaults públicos de modelo

Sem override explícito:

```text
OPENAI     gpt-5.6-luna
DEEPSEEK   deepseek-v4-flash
MIMO       mimo-v2.5
XAI        grok-4.6
QWEN       qwen3.8-flash
GEMINI     gemini-3.8-flash
ANTHROPIC  claude-sonnet-5
```

### Esforço/profundidade

O produto usa o menor esforço suportado quando o usuário não fornece override:

```text
OPENAI     NONE
DEEPSEEK   NONE
MIMO       NONE
XAI        LOW
QWEN       PROVIDER_DEFAULT
GEMINI     LOW
ANTHROPIC  LOW
```

Overrides de reasoning/thinking usam as variáveis específicas do provider expostas pelo registry/console quando suportadas.

### Timeout IA

```text
SEARCHGEO_AI_TIMEOUT_SECONDS
```

Default público: `180` segundos por tentativa.

## Remediação textual por IA

```text
--ai-content-remediation
--no-ai-content-remediation
```

Default: OFF.

A remediação exige provider de IA apto. É advisory/evidence-bound e não altera automaticamente o Score GEO.

## M24 — remediação técnica de crawling/discovery por IA

```text
--ai-technical-remediation
--no-ai-technical-remediation
```

Default: OFF.

Variável equivalente:

```text
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Valores de ambiente aceitos:

```text
true / false
1 / 0
yes / no
on / off
```

Precedência: argumento CLI explícito > variável de ambiente > OFF.

Essa opção **não habilita o M24 determinístico** — os diagnósticos técnicos de crawling/discovery já são executados no pipeline normal. Ela habilita somente uma camada opcional de explicação/remediação por IA sobre diagnósticos M24 já persistidos.

A IA técnica:

- exige provider compatível/configurado para produzir sugestão;
- não altera `RuleExecution`, Finding, Score, Coverage, Confidence ou Consolidation;
- não decide automaticamente políticas de treinamento/crawler;
- não transforma `llms.txt` em requisito;
- exige revisão humana.

O relatório correspondente é `report/crawling-discovery.html`; telemetria de IA M24 também pode aparecer em `report/ai-usage.html`.

## Web Performance / PageSpeed / Lighthouse / CrUX

Habilitação:

```text
--web-performance
--no-web-performance
```

Default: OFF.

Limite de páginas externas:

```text
--web-performance-max-pages N
```

`0` significa todas as páginas auditadas, respeitando o limite geral da auditoria.

Timeout por chamada externa:

```text
--web-performance-timeout-seconds SECONDS
```

Default público: `120` segundos.

Variável equivalente:

```text
SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS
```

Esse timeout controla a espera pela resposta externa PageSpeed/CrUX. A API PageSpeed executa Lighthouse remotamente; não há nessa superfície um argumento separado do SearchGEO para definir o timeout interno de carregamento usado pelo Lighthouse.

Field data:

```text
--web-performance-field-source auto|pagespeed|crux|none
```

Default: `auto`.

`crux` direto exige `SEARCHGEO_CRUX_API_KEY`.

Categorias Lighthouse:

```text
--lighthouse-categories performance,accessibility,best-practices,seo
```

Default: as quatro categorias acima.

Variáveis relacionadas:

```text
SEARCHGEO_WEB_PERFORMANCE
SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES
SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS
SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE
SEARCHGEO_LIGHTHOUSE_CATEGORIES
SEARCHGEO_PAGESPEED_API_KEY
SEARCHGEO_CRUX_API_KEY
```

## Synthetic Navigation Apdex

Habilitação:

```text
--synthetic-apdex
--no-synthetic-apdex
```

Default: OFF.

Threshold:

```text
--apdex-threshold-seconds SECONDS
```

`T` é obrigatório quando Synthetic Apdex está habilitado.

Amostras válidas por URL/device:

```text
--apdex-samples-per-context N
```

Default quando habilitado: `100`.

Máximo de tentativas:

```text
--apdex-max-attempts-per-context N
```

Default: `ceil(1.25 × alvo)`.

Máximo de páginas:

```text
--apdex-max-pages N
```

Default: `1`; `0` usa todas as páginas disponíveis dentro do limite geral.

Timeout por navegação:

```text
--apdex-timeout-seconds SECONDS
```

Deve ser `> 4T`. Default efetivo: `max(45, 4T + 5)`.

Delay:

```text
--apdex-delay-seconds SECONDS
```

Default: `1`.

Concorrência:

```text
--apdex-concurrency N
```

Valores: `1` ou `2`. Default: `1`.

Variáveis equivalentes:

```text
SEARCHGEO_SYNTHETIC_APDEX
SEARCHGEO_APDEX_THRESHOLD_SECONDS
SEARCHGEO_APDEX_SAMPLES_PER_CONTEXT
SEARCHGEO_APDEX_MAX_ATTEMPTS_PER_CONTEXT
SEARCHGEO_APDEX_MAX_PAGES
SEARCHGEO_APDEX_TIMEOUT_SECONDS
SEARCHGEO_APDEX_DELAY_SECONDS
SEARCHGEO_APDEX_CONCURRENCY
```

## Exemplos

### Sem IA

```powershell
searchgeo audit https://example.com `
  --ai-provider none `
  --device-context mobile
```

### OpenAI explícito

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-model gpt-5.6-luna
```

### Remediação técnica M24 por IA

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-technical-remediation
```

Sem `--ai-technical-remediation`, M24 continua executando apenas os diagnósticos determinísticos e não gera custo de IA por essa finalidade.

### Web Performance

```powershell
searchgeo audit https://example.com `
  --web-performance `
  --web-performance-timeout-seconds 120 `
  --web-performance-field-source auto
```

### Synthetic Apdex de smoke

```powershell
searchgeo audit https://example.com `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-concurrency 1
```

## Console interativo

```powershell
searchgeo-console
```

O console configura a mesma superfície principal de execução e adiciona persistência de parâmetros não sensíveis em `searchgeo-console.ini`, progresso, preflight e atalhos para artifacts. Secrets não são gravados no INI.

O parâmetro M24 `--ai-technical-remediation` é documentado como superfície CLI/ambiente nesta versão; não deve ser presumido como opção persistida no INI do console enquanto não houver integração explícita correspondente.

Consulte [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONFIGURATION.md](CONFIGURATION.md) e [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md).
