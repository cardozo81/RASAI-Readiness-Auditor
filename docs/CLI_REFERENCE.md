# Referência da CLI

Referência operacional da linha de comando do SearchGEO Readiness Auditor.

## Entrada principal

A superfície pública possui dois fluxos:

```text
searchgeo [-h] [--version] [--config PATH] audit ...
searchgeo visibility import|report ...
```

O router superior intercepta somente `visibility`; os demais comandos continuam delegados ao pipeline de auditoria existente.

Tokens canônicos do contrato público: `-h`, `--help`, `--version`, `--config PATH`.

Ajuda: `-h`, `--help`.

Versão: `--version`.

Configuração geral de aplicação/logging: `--config PATH`.

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

Default de dispositivo: `mobile`.

Override por ambiente: `SEARCHGEO_DEVICE_CONTEXT`.

## IA

Seleção: `--ai-provider`.

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

Modelo explícito: `--ai-model MODEL_ID`.

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

`SEARCHGEO_AI_TIMEOUT_SECONDS`. Default público: `180` segundos por tentativa.

## Remediação textual por IA

```text
--ai-content-remediation
--no-ai-content-remediation
```

Default: OFF. A remediação exige provider de IA apto. É advisory/evidence-bound e não altera automaticamente o Score GEO.

## Rastreamento, descoberta e acesso de crawlers — remediação técnica de crawling/discovery por IA

```text
--ai-technical-remediation
--no-ai-technical-remediation
```

Default: OFF.

Variável equivalente: `SEARCHGEO_AI_TECHNICAL_REMEDIATION`.

Valores de ambiente aceitos: `true/false`, `1/0`, `yes/no`, `on/off`.

Precedência: argumento CLI explícito > variável de ambiente > OFF.

Essa opção **não habilita o Rastreamento, descoberta e acesso de crawlers determinístico** — os diagnósticos técnicos de crawling/discovery já são executados no pipeline normal. Ela habilita somente uma camada opcional de explicação/remediação por IA sobre diagnósticos Rastreamento, descoberta e acesso de crawlers já persistidos.

A IA técnica:

- exige provider compatível/configurado para produzir sugestão;
- não altera `RuleExecution`, Finding, Score, Coverage, Confidence ou Consolidation;
- não decide automaticamente políticas de treinamento/crawler;
- não transforma `llms.txt` em requisito;
- exige revisão humana.

O relatório correspondente é `report/crawling-discovery.html`; telemetria de IA Rastreamento, descoberta e acesso de crawlers também pode aparecer em `report/ai-usage.html`.

## Web Performance / PageSpeed / Lighthouse / CrUX

Habilitação:

```text
--web-performance
--no-web-performance
```

Default: OFF.

Limite de páginas externas: `--web-performance-max-pages N`. `0` significa todas as páginas auditadas, respeitando o limite geral da auditoria.

Timeout por chamada externa: `--web-performance-timeout-seconds SECONDS`. Default público: `120` segundos.

Variável equivalente: `SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS`.

Esse timeout controla a espera pela resposta externa PageSpeed/CrUX. A API PageSpeed executa Lighthouse remotamente; não há nessa superfície um argumento separado do SearchGEO para definir o timeout interno de carregamento usado pelo Lighthouse.

Field data: `--web-performance-field-source auto|pagespeed|crux|none`. Default: `auto`. `crux` direto exige `SEARCHGEO_CRUX_API_KEY`.

Categorias Lighthouse: `--lighthouse-categories performance,accessibility,best-practices,seo`.

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

## Synthetic Navigation Apdex — Synthetic Navigation Apdex

Habilitação:

```text
--synthetic-apdex
--no-synthetic-apdex
```

Default: OFF.

Parâmetros:

- `--apdex-threshold-seconds SECONDS`: `T`, obrigatório quando habilitado;
- `--apdex-samples-per-context N`: amostras válidas por URL/device, default `100`;
- `--apdex-max-attempts-per-context N`: default `ceil(1.25 × alvo)`;
- `--apdex-max-pages N`: default `1`; `0` usa todas as páginas disponíveis dentro do limite geral;
- `--apdex-timeout-seconds SECONDS`: deve ser `> 4T`; default efetivo `max(45, 4T + 5)`;
- `--apdex-delay-seconds SECONDS`: default `1`;
- `--apdex-concurrency N`: valores `1` ou `2`, default `1`.

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

## Synthetic User Experience Apdex — Synthetic User Experience Apdex

Habilitação:

```text
--apdex-experience
--no-apdex-experience
```

Default: OFF. O Synthetic User Experience Apdex é um segundo domínio Apdex, sintético e calibrável. Não substitui o Synthetic Navigation Apdex e não representa RUM.

Principais parâmetros:

```text
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

Quando habilitado, `device-mix` deve representar explicitamente a população sintética e somar 100.

### Calibração Dynatrace

```text
--apdex-dynatrace-import
--dynatrace-base-url URL
--dynatrace-application-id ID
--apdex-dynatrace-config-json PATH
```

O import de configuração é usado para alinhar KPM/thresholds/política quando suportado. O resultado produzido continua sintético; não se torna RUM apenas por usar parâmetros derivados do Dynatrace.

Variáveis Synthetic User Experience Apdex usam prefixos `SEARCHGEO_APDEX_EXPERIENCE_*` e `SEARCHGEO_APDEX_DYNATRACE_IMPORT`, além das variáveis Dynatrace documentadas em `ENVIRONMENT_VARIABLES.md`.

Página canônica: `report/apdex-experience.html`.

## Observed Generative Visibility — Observed Generative Visibility

O Observed Generative Visibility não é parte do comando `audit`; ele atua sobre um workspace `AUD-*` já existente e importa outcomes observados em domínio separado do readiness.

### Importar dataset

```powershell
searchgeo visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

O arquivo precisa obedecer ao contrato `OGV-IMPORT-001`.

Fontes iniciais suportadas:

```text
BING_WEBMASTER_TOOLS_AI_PERFORMANCE
CONTROLLED_QUERY_RUNS
```

`source.capture_method` é obrigatório e registra como a evidência foi obtida/normalizada. Valores aceitos:

```text
MANUAL_TRANSCRIPTION
NORMALIZED_EXPORT
CONTROLLED_PROTOCOL
EXTERNAL_AUTOMATION
```

Esse campo é proveniência declarada do dataset; não significa que o SearchGEO autenticou ou coletou diretamente a informação no sistema externo.

Regras relevantes:

- JSON UTF-8 válido;
- URLs devem pertencer ao `normalized_origin` da auditoria;
- artifact importado é preservado com SHA-256;
- reimport do mesmo conteúdo é idempotente;
- métricas Bing declaradas permanecem identificadas como métricas reportadas pela fonte;
- Citation Presence Rate só é calculado sobre query-runs `VALID`;
- runs `INVALID` ficam fora do denominador;
- rank observado exige `ranking_semantics` explícita;
- nenhum outcome Observed Generative Visibility altera `SGRI-001`/`SCORE-GEO-002`.

### Regenerar o report

```powershell
searchgeo visibility report `
  --audit-id AUD-... `
  --audits-root audits
```

Página canônica: `report/ai-visibility.html`.

O Observed Generative Visibility é **import-first**: não faz scraping de Bing Webmaster Tools e não presume endpoint de API de AI Performance sem documentação pública correspondente.

Contrato completo: [specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).

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

### Remediação técnica Rastreamento, descoberta e acesso de crawlers por IA

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-technical-remediation
```

### Web Performance

```powershell
searchgeo audit https://example.com `
  --web-performance `
  --web-performance-timeout-seconds 120 `
  --web-performance-field-source auto
```

### Synthetic Navigation Apdex de smoke

```powershell
searchgeo audit https://example.com `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-concurrency 1
```

### Importar visibilidade observada

```powershell
searchgeo visibility import `
  --audit-id AUD-EXEMPLO `
  --file .\observed-visibility.json
```

## Console interativo

```powershell
searchgeo-console
```

O console configura a superfície principal de auditoria e adiciona persistência de parâmetros não sensíveis em `searchgeo-console.ini`, progresso, preflight e atalhos para artifacts. Secrets não são gravados no INI.

O Observed Generative Visibility é inicialmente uma superfície CLI/import-first separada; não deve ser presumido como coleta automática ou item persistido do fluxo de auditoria no console enquanto essa integração não existir explicitamente.

O parâmetro Rastreamento, descoberta e acesso de crawlers `--ai-technical-remediation` também permanece documentado como superfície CLI/ambiente nesta versão quando não houver integração explícita correspondente no INI.

Consulte [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONFIGURATION.md](CONFIGURATION.md), [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md), [specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md](specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md) e [specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).
