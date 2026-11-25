# Referência da CLI

Referência operacional do **RASAi - Search & AI Readiness Auditor**.

## Entradas públicas

```text
rasai audit ...
rasai search ...
rasai search-history ...
rasai search-monitor ...
rasai visibility import|report ...
rasai scoring inspect
rasai monitor compare|impact|gate ...
rasai observe ...
rasai observability ...
rasai quality report|verify|timeline ...
rasai platform ...
rasai-console
```

## Opções globais

- `-h`, `--help` - ajuda da superfície/comando.
- `--version` - identificador técnico do pacote.
- `--config PATH` - arquivo TOML quando suportado pela superfície.

## `audit`

Forma geral:

```powershell
rasai audit target [opções]
```

### Entrada e contexto

| Opção | Uso |
|---|---|
| `target` | exatamente um domínio/URL HTTP(S) para a nova AUD |
| `--project TEXT` | nome humano do projeto |
| `--language CODE` | idioma; default `pt-BR` |
| `--market CODE` | mercado; default `BR` |
| `--max-pages N` | máximo determinístico de páginas |
| `--audits-root PATH` | raiz dos workspaces; default `audits` |
| `--device-context` | `mobile` ou `desktop`; uma AUD usa um único device |
| `--ai-provider` | `none`, provider explícito/alias do registry ou `auto` |
| `--ai-model MODEL_ID` | override de modelo para provider explícito |

Default de dispositivo: `mobile`. Override: `RASAI_DEVICE_CONTEXT`.

Novas auditorias públicas aceitam **exatamente uma URL/domínio de entrada**. O crawler ainda pode descobrir e auditar páginas adicionais dentro do mesmo escopo conforme `--max-pages`. O suporte interno a `URL_SET` permanece somente para leitura/compatibilidade de auditorias históricas e não reabre entrada multi-target na CLI.

O contrato de novas AUDs single-URL persiste a capability técnica `declared_single_url_scope`. Links internos observados no HTML renderizado continuam como evidência de navegação e para BR-GEO-022, mas não geram `RENDERED_DISCOVERY_GAP` apenas por estarem fora das URLs efetivamente auditadas. AUDs históricas sem esse marcador não são reinterpretadas, e limitações já persistidas continuam legíveis.

## Índice e Método de Pontuação de Prontidão

**Search & AI Readiness Index - Índice de Prontidão Search & IA**, versão pública **001**, é o índice apresentado ao usuário; `SARI-001` é o identificador metodológico técnico. O **Método de Pontuação de Prontidão**, versão pública **001**, é a metodologia vigente; `SCORE-GEO-005` é o contrato técnico atual para novas auditorias, enquanto `SCORE-GEO-004` permanece preservado para observações históricas.

Inspeção local do contrato:

```powershell
rasai scoring inspect
```

Para investigar o índice e o método, abra `report-catalog/sari.html` e `report-catalog/methodology.html`; para leitura executiva, `report-presentation/indices.html` e o painel `report-presentation/index.html`. Consulte o [guia de leitura e correspondência temática dos relatórios](REPORT_GUIDE.md#correspondência-temática-entre-os-relatórios).

## IA no audit

Providers do registry:

```text
none
openai
deepseek
mimo
xai / grok
qwen
gemini
anthropic / claude
mistral
cohere
kimi / moonshot
copilot / github-copilot
auto
```

`AI=auto` considera todos os providers registrados como `auto_eligible=true` que estejam aptos na execução. Aptidão exige credencial e configuração válidas. Antes de cada necessidade, o runtime remove candidatos em quarentena e estima o custo da requisição para os providers restantes usando modelo, reasoning, input/output esperado, cache observado e a tarifa vigente naquele instante. Providers precificados são tentados do menor para o maior custo estimado; providers sem preço conhecido ficam depois dos precificados e preservam entre si a ordem rotativa determinística do coordenador. Cada provider é tentado no máximo uma vez por necessidade. Condições terminais continuam removidas imediatamente e falhas temporárias continuam sujeitas ao mesmo circuit breaker.

A presença de uma credencial não obriga o provider a participar do AUTO. `RASAI_AI_AUTO_EXCLUDE` aceita uma lista CSV de providers elegíveis a manter fora do pool AUTO daquela configuração, preservando suas chaves/modelos para seleção explícita posterior. Exemplo: `RASAI_AI_AUTO_EXCLUDE=gemini` mantém Gemini apto para uso explícito, mas fora do pool AUTO.

A ordem econômica é recalculada por necessidade e pode mudar por horário, janela peak/off-peak, faixa de contexto, modelo, reasoning ou comportamento de tokens observado durante a execução. O AUTO não troca silenciosamente para Batch, Flex ou outro service tier assíncrono apenas para obter desconto. Preços e janelas considerados estão em [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md).

Mistral é `auto_eligible=true`: com `MISTRAL_API_KEY` configurada e modelo vigente, entra em `AI=auto`. O uso explícito continua aceitando `--ai-provider mistral --ai-model mistral-small-2603` e fixa o endpoint global no tier Standard.

Cohere é `auto_eligible=true`: `--ai-provider cohere --ai-model command-a-03-2025` usa Chat V2 no endpoint fixo, Structured Outputs com validação local e não habilita tools, documents, RAG ou Rerank. `RASAI_COHERE_COMMERCIAL_MODE=UNKNOWN|TRIAL|PRODUCTION` condiciona pricing; `UNKNOWN` mantém o candidato UNPRICED, sem removê-lo do AUTO.

Kimi/Moonshot é `auto_eligible=true`: com `MOONSHOT_API_KEY` configurada pode participar de `AI=auto`; `--ai-provider kimi --ai-model kimi-k3` ou alias `moonshot` mantém a seleção explícita. `RASAI_KIMI_REASONING_EFFORT=LOW|HIGH|MAX` usa `LOW` por default. Structured Output é `json_schema` estrito e continua sujeito à validação local; tools, web search, Formula, documents, endpoint China e cache TTL 1h não são habilitados nesta entrega.

GitHub Copilot é `auto_eligible=true`: com `COPILOT_GITHUB_TOKEN` configurado pode entrar em `AI=auto`. O adapter usa o SDK oficial, modelo público `auto`, `use_logged_in_user=False` e sessão sem tools. Use `RASAI_AI_AUTO_EXCLUDE=copilot` para impedir consumo automático sem remover o token. No fluxo manual, instale o transporte com:

```powershell
python -m pip install -e ".[copilot]"
```

O timeout principal é `RASAI_AI_TIMEOUT_SECONDS`, default 180 segundos por tentativa.

### Remediação textual

```text
--ai-content-remediation
--no-ai-content-remediation
RASAI_AI_CONTENT_REMEDIATION
```

Default OFF. A camada gera sugestões evidence-bound e não recalcula score.

### Remediação técnica

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

Default OFF. A IA técnica explica/remedia diagnósticos já determinados pelo runtime e permanece advisory.

### Contexto editorial / YMYL / E-E-A-T

Os campos `RASAI_CONTENT_*`, `RASAI_YMYL_CATEGORY`, `RASAI_PAGE_PURPOSE`, `RASAI_INTENDED_AUDIENCE`, `RASAI_EXPERIENCE_REQUIREMENT` e `RASAI_FRESHNESS_SENSITIVITY` aceitam configuração editorial contextual.

Quando um campo está em `auto` e IA está ligada, a configuração persistida continua `AUTO`. A IA pode produzir interpretação transitória para o relatório, baseada apenas no conteúdo/evidências fornecidos. Essa leitura não sobrescreve banco, não vira evidência determinística e não altera diretamente o Índice de Prontidão Search & IA nem o Método de Pontuação de Prontidão.

### Telemetria de IA

Para investigar as tentativas registradas, use `report-catalog/ai-integrations.html`; a apresentação executiva de uso, custos e proveniência está em `report-presentation/ia-custos.html`. O runtime registra request/response sanitizados, provider/modelo, finalidade, duração, status, hashes e truncamento. Campos reconhecidos como credenciais e raciocínio privado do fornecedor são redigidos pelo registrador. Isso não garante ausência de todo conteúdo sensível ou opaco; preserve o banco e os artefatos sob acesso restrito. Veja [segurança e retenção da telemetria](AI_RUNTIME_SECURITY.md).

Quando a integração reporta uma unidade comercial nativa, o console/relatório a apresenta separadamente dos tokens. A telemetria pode mostrar, por exemplo, requisições de busca Perplexity ou créditos Manus; essas unidades nunca são reaproveitadas como `input_tokens`/`output_tokens`. Créditos Manus permanecem não precificados enquanto não houver conversão monetária oficial reproduzível. Esta entrega não cria novos valores para `--ai-provider`.

O report usa provider/modelo efetivamente persistidos; não existe allowlist HTML específica que precise ser atualizada para Copilot ou para futuros providers registrados.

Controle de tamanho:

```text
RASAI_AI_EXCHANGE_LOG_MAX_BYTES
```

Default: 524288 bytes por lado da comunicação; faixa aceita pelo runtime: 4096 a 4194304.

Documentos:

- [AI_GUIDE.md](AI_GUIDE.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md)
- [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md)

## Web Performance

```text
--web-performance
--no-web-performance
--web-performance-max-pages N
--web-performance-timeout-seconds SECONDS
--web-performance-field-source auto|pagespeed|crux|none
--lighthouse-categories performance,accessibility,best-practices,seo,agentic-browsing
```

O adapter PageSpeed vigente aceita e solicita por default no RASAi as categorias:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

A API PageSpeed Insights v5 expõe `AGENTIC_BROWSING` entre os valores aceitos para `category`. No RASAi, Agentic Browsing permanece uma categoria Lighthouse experimental e externa: sua ausência na resposta não é score zero, não invalida as demais categorias coletadas e seu valor não entra automaticamente no Índice de Prontidão Search & IA nem no Método de Pontuação de Prontidão.

Variáveis principais:

```text
RASAI_WEB_PERFORMANCE
RASAI_WEB_PERFORMANCE_MAX_PAGES
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS
RASAI_WEB_PERFORMANCE_FIELD_SOURCE
RASAI_LIGHTHOUSE_CATEGORIES
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
```

Lab e field data permanecem separados e não entram automaticamente no Índice de Prontidão Search & IA nem no Método de Pontuação de Prontidão.

## Synthetic Navigation Apdex

```text
--synthetic-apdex
--no-synthetic-apdex
--apdex-threshold-seconds SECONDS
--apdex-samples-per-context N
--apdex-max-attempts-per-context N
--apdex-max-pages N
--apdex-timeout-seconds SECONDS
--apdex-delay-seconds SECONDS
--apdex-concurrency 1|2|3|4

--apdex-mobile-client-profile PRESET
--apdex-mobile-hardware-profile PRESET
--apdex-mobile-network-profile PRESET
--apdex-desktop-client-profile PRESET
--apdex-desktop-hardware-profile PRESET
--apdex-desktop-network-profile PRESET
```

Desabilitado por padrão no runtime genérico. O limite de tempo de satisfação `T` deve estar explicitamente configurado quando habilitado. Concorrência de 3 ou 4 exige intervalo mínimo de 1 segundo entre amostras.

Os seis argumentos públicos de perfil usam a mesma precedência da configuração sintética: **CLI > variável de ambiente > default controlado**. Eles selecionam apenas o envelope de execução - cliente/viewport, slowdown relativo de CPU e rede - e não alteram a fórmula Apdex nem o Índice de Prontidão Search & IA ou o Método de Pontuação de Prontidão. Os equivalentes públicos em ambiente são `RASAI_APDEX_MOBILE_*_PROFILE` e `RASAI_APDEX_DESKTOP_*_PROFILE`; valores e defaults canônicos estão em [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md).

Os presets não emulam RAM, GPU, estado térmico ou scheduler físico. O engine executado continua Chromium; identidade/viewport não deve ser interpretada como emulação de Safari/Firefox reais.

A estratégia física canônica de Navigation e Experience Apdex é controlada por:

```text
RASAI_APDEX_ACQUISITION_MODE=auto|isolated
```

Default `auto`. O reuso físico só ocorre quando URL, device, perfil, sessão e requisitos de coleta são compatíveis. Cada Apdex preserva targets, thresholds, classificação e população próprios; ambos herdam o mesmo device único da AUD. `isolated` mantém as navegações físicas separadas.

## Synthetic User Experience Apdex

```text
--apdex-experience
--no-apdex-experience
--apdex-experience-samples N
--apdex-experience-max-attempts N
--apdex-experience-max-pages N
--apdex-experience-session-mode cold|warm
--apdex-experience-kpm KPM
--apdex-experience-satisfied-seconds SECONDS
--apdex-experience-frustrated-seconds SECONDS
--apdex-experience-errors
--no-apdex-experience-errors
--apdex-experience-error-scope navigation|first-party|all
--apdex-experience-settle-seconds SECONDS
--apdex-experience-delay-seconds SECONDS
--apdex-experience-concurrency 1|2|3
--apdex-population-profile-json JSON
```

A avaliação continua sintética, inclusive quando calibrada contra configuração Dynatrace. Concorrência de 3 exige intervalo mínimo de 1 segundo entre amostras.

O Synthetic User Experience Apdex herda o device da AUD: `mobile` produz 100% MOBILE e `desktop` produz 100% DESKTOP. Não existe mix público independente nem Tablet para novas AUDs. O target default do Experience é 100 amostras válidas por página; o Navigation mantém target separado de 150 amostras válidas por URL/device.

O campo técnico histórico de mix permanece apenas como compatibilidade interna para leitura/reprocessamento histórico; ele não é uma configuração pública para novas execuções.

`--apdex-population-profile-json` ativa uma camada **adicional** de Synthetic Population Apdex no CAT-07. O JSON define estratos, pesos e provenance; não troca o device da AUD, não substitui o Apdex Experience baseline e não altera CAT-06 ou SCORE-GEO. O contrato completo está em [SYNTHETIC_POPULATION_APDEX.md](SYNTHETIC_POPULATION_APDEX.md).

## Search Intelligence

### Observação pontual

```powershell
rasai search "termo" --domain cliente.example [opções]
```

Opções relevantes:

```text
--mode disabled|live|fixture
--provider PROVIDER
--depth N
--country CODE
--region TEXT
--language CODE
--device desktop|mobile
--competitive
--compare-content
--customer-url URL
--max-content-pages N
--ai-competitive
--ai-provider PROVIDER
--ymyl-mode AUTO|ON|OFF
--audit-workspace PATH
--dry-run
```

Providers SERP live atuais:

```text
serpapi       -> RASAI_SERPAPI_API_KEY
serpapi-bing  -> RASAI_SERPAPI_API_KEY
zenserp       -> RASAI_ZENSERP_API_KEY
scrapingdog   -> RASAI_SCRAPINGDOG_API_KEY
```

O console exibe a URL oficial de cadastro/login e a variável de credencial correspondente. Nenhum provider SERP externo atual é classificado pelo RASAi como gratuito e ilimitado; ofertas free tier conhecidas possuem limites próprios. `RASAI_SERP_MAX_REQUESTS` é teto de tentativas HTTP do RASAi, não garantia de equivalência 1:1 com créditos comerciais.

`NOT_FOUND_WITHIN_DEPTH` significa apenas que o domínio não foi observado na profundidade solicitada. Search Intelligence é non-scoring.

No `rasai-console`, quando termos SERP fazem parte da sessão, a etapa Search Intelligence integra o mesmo relógio de duração e o progresso global da auditoria. As consultas são acompanhadas por termo. Erros do provider permanecem fail-open para a auditoria principal: o diagnóstico original é persistido e categorizado como limitação técnica ou de conta/negócio quando identificável. O CAT-05 projeta a posição observada e o estado da capacidade a partir desses dados.

A comparação de conteúdo competitivo é opt-in porque baixa páginas públicas adicionais. Quando não habilitada, a classificação SERP pode existir sem listas de diferenças de conteúdo; o CAT-05 deve explicar essa ausência em vez de apresentar listas vazias como se fossem uma conclusão analítica. Recomendações competitivas por IA exigem comparação determinística consolidada e permanecem evidence-bound e não causais.

O CAT-05 projeta o campo `provider` persistido por observação; não mantém allowlist visual específica de SerpApi/Zenserp/ScrapingDog.

### Histórico

```powershell
rasai search-history --baseline-workspace audits/AUD-BASELINE --current-workspace audits/AUD-CURRENT
```

Também pode operar por milestone e modos `AUTO`, `GOLDEN` ou `EXPLICIT`. Comparações só produzem delta numérico quando o contexto observado é compatível.

### Monitoramento recorrente

```text
rasai search-monitor query add ...
rasai search-monitor query list
rasai search-monitor query enable --query-id ID
rasai search-monitor query disable --query-id ID
rasai search-monitor run --query-id ID
rasai search-monitor run-due
rasai search-monitor history --query-id ID
rasai search-monitor report
```

O scheduler usa a Product Platform. Credenciais BYOK não são gravadas em schedules.

Documentos:

- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [SEARCH_INTELLIGENCE_HISTORY.md](SEARCH_INTELLIGENCE_HISTORY.md)
- [SEARCH_INTELLIGENCE_MONITORING.md](SEARCH_INTELLIGENCE_MONITORING.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)

## Observed Generative Visibility

Import:

```powershell
rasai visibility import --audit-id AUD-... --audits-root audits --file observed-visibility.json
```


A importação preserva provenance/artifact e não recalcula scoring.

## RASAi Monitor

```text
rasai monitor compare ...
rasai monitor impact ...
rasai monitor gate ...
```

`compare` compara dois AUDs; `impact` descreve mudanças observadas em janelas compatíveis sem afirmar causalidade; `gate` aplica critérios de regressão configuráveis.

Exit codes do gate:

```text
0 PASS
1 regressão bloqueante
2 erro de execução/configuração
```

## Search & AI Observability

Comando principal:

```text
rasai observe ...
```

Alias:

```text
rasai observability ...
```

Subsuperfícies incluem `status`, `report`, `import`, `bing-import`, `google-ai-import`, `google-ai-control`, `gsc-sites`, `gsc-sitemaps`, `gsc-search`, `gsc-appearance`, `gsc-inspect` e `crux-history`.

Dados externos ficam em `artifacts/observability/observability.db` + artifacts observacionais; `audit.db` permanece a fonte de verdade da auditoria.

## Quality timeline / verification

```text
rasai quality report ...
rasai quality verify ...
rasai quality timeline ...
```

Use as superfícies de quality para projeções e verificações que não devem modificar evidência histórica.

## Product Platform / SaaS

```text
rasai platform ...
```

A Product Platform gerencia Organization, Workspace, Project, Property, Environment, memberships/RBAC, jobs, schedules, milestones e usage ledger conforme o backend configurado.

SQLite continua disponível para operação local; PostgreSQL é o backend centralizado do control plane quando configurado.

## Reprocessamento e consolidação reproduzíveis

Reprocessamento seletivo:

```text
rasai reprocess AUD-... --audits-root audits
rasai reprocess AUD-... --item COMPONENTE:ESCOPO --no-use-ai
rasai reprocess AUD-... --item COMPONENTE:ESCOPO --use-ai --ai-provider openai --ai-model MODELO
```

Opções adicionais:

```text
--item CHAVE
--use-ai | --no-use-ai
--ai-provider PROVIDER
--ai-model MODEL
--ai-reasoning PROFILE
```

`--item` pode ser repetido. Provider/model/reasoning explícitos exigem `--use-ai`. Sem `--item` e sem política explícita de IA, o comando preserva o comportamento normal de reprocessamento da CLI.

Relatório consolidado:

```text
rasai consolidate AUD-PRIMEIRO AUD-SEGUNDO --audits-root audits --selection-mode ALL
rasai consolidate AUD-PRIMEIRO AUD-SEGUNDO --selection-mode SUCCESS_ONLY
rasai consolidate AUD-PRIMEIRO AUD-SEGUNDO --selection-mode MANUAL --manual-audit-id AUD-INTERMEDIARIO
rasai consolidate AUD-PRIMEIRO AUD-SEGUNDO --specialist-ai --ai-provider openai
```

Opções:

```text
--selection-mode ALL|SUCCESS_ONLY|MANUAL
--manual-audit-id AUD-...
--specialist-ai | --no-specialist-ai
--ai-provider PROVIDER
--ai-model MODEL
--ai-reasoning PROFILE
--ai-timeout-seconds SECONDS
```

A CLI de consolidação é um adapter fino sobre os mesmos contratos de seleção e geração usados pelo console. Ela não implementa um segundo motor de CONS.

A geração, cópia e agendamento multiplataforma dos comandos está documentada em [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).

## Exemplos de execução no Windows

Os exemplos usam a raiz do projeto, a versão instalada e credenciais já configuradas no ambiente do sistema operacional. `example.com` é apenas um domínio ilustrativo: substitua pelo alvo autorizado. Nenhum comando abaixo contém chaves ou tokens. Antes de executar, confirme a carga permitida, as integrações habilitadas, a propriedade autorizada, as cotas e os custos. Mesmo uma auditoria sem IA pode fazer consultas externas.

### 1. Auditoria básica pelo CMD

```cmd
.venv\Scripts\python.exe -m rasai --version
.venv\Scripts\python.exe -m rasai audit --help
.venv\Scripts\python.exe -m rasai audit https://example.com --project "Avaliação inicial" --max-pages 1 --device-context mobile --ai-provider none --no-web-performance --no-synthetic-apdex --no-apdex-experience --no-ai-content-remediation --no-ai-technical-remediation
```

Esse exemplo limita o escopo, desliga IA, as duas avaliações Apdex e o agregado de desempenho Web. Não é um teste offline nem desliga todos os serviços de ambiente. Consulte a [configuração](CONFIGURATION.md) para controlar os demais serviços.

### 2. Auditorias separadas por dispositivo

PowerShell 5.1/7, com a mesma versão do programa:

```powershell
$Python = ".\.venv\Scripts\python.exe"
& $Python -m rasai audit https://example.com --project "Mobile" --device-context mobile --max-pages 1 --ai-provider none
if ($LASTEXITCODE -ne 0) { throw "Falha na auditoria móvel" }
& $Python -m rasai audit https://example.com --project "Desktop" --device-context desktop --max-pages 1 --ai-provider none
if ($LASTEXITCODE -ne 0) { throw "Falha na auditoria de computador" }
```

Cada execução tem sua própria identidade e evidências. Não use `both` como contexto de uma nova auditoria.

### 3. Apdex com amostras e tentativas explícitas

CMD, exemplo de carga limitada a uma página. Ajuste o volume à capacidade do alvo.

```cmd
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider none --synthetic-apdex --apdex-threshold-seconds 3 --apdex-samples-per-context 20 --apdex-max-attempts-per-context 25 --apdex-max-pages 1 --apdex-timeout-seconds 45 --apdex-delay-seconds 1 --apdex-concurrency 1 --apdex-experience --apdex-experience-samples 20 --apdex-experience-max-attempts 25 --apdex-experience-max-pages 1 --apdex-experience-session-mode cold --apdex-experience-satisfied-seconds 3 --apdex-experience-frustrated-seconds 12 --apdex-experience-delay-seconds 1 --apdex-experience-concurrency 1
```

Variações: para 100 amostras de experiência, use `--apdex-experience-samples 100 --apdex-experience-max-attempts 125`. Para 150 amostras de navegação, use `--apdex-samples-per-context 150 --apdex-max-attempts-per-context 188`. Esses pares são exemplos de metas e tetos de tentativas; 20 amostras servem apenas a diagnóstico de grupo pequeno. A especificação Apdex v1.1 define 100 como mínimo para apresentação normal do índice, sem que isso garanta representatividade da população real. O teto de tentativas precisa comportar a meta; não garante que todas as amostras sejam válidas. As duas avaliações têm populações e critérios próprios. [Metodologia de navegação](SYNTHETIC_APDEX.md) e [metodologia de experiência](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

### 4. Pesquisa SERP

Prévia de uma consulta avulsa (sem chamar o fornecedor):

```cmd
.venv\Scripts\python.exe -m rasai search "auditoria de sites" --domain example.com --mode live --provider serpapi --country BR --language pt-BR --device mobile --depth 10 --dry-run
```

Uma pesquisa vinculada à nova auditoria exige termos explícitos e modo de pesquisa ativo. Na versão 1.0.0, o comando planejado exibido pelo console pode omitir os termos SERP: confira a presença de cada `--search-query` antes de reutilizá-lo. CMD, usando a credencial `RASAI_SERPAPI_API_KEY` herdada:

```cmd
setlocal
set "RASAI_SERP_MODE=live"
set "RASAI_SERP_PROVIDER=serpapi"
set "RASAI_SERP_MAX_QUERIES=2"
set "RASAI_SERP_MAX_REQUESTS=10"
set "RASAI_SERP_MAX_DEPTH=10"
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider none --search-query "auditoria de sites" --search-query "qualidade de páginas web" --search-region Brasil --search-device mobile --search-depth 10 --search-competitive --no-search-compare-content --no-search-ai-competitive
endlocal
```

Use esse bloco em um arquivo `.cmd`; `setlocal` e `endlocal` limitam as alterações de ambiente ao script. Para mudar os termos, repita `--search-query` e respeite os tetos de consultas, requisições e profundidade. Comparação de conteúdo e interpretação por IA são opções adicionais: podem baixar páginas concorrentes ou gerar consumo de IA; não são necessárias para observar a SERP.

### 5. IA explícita ou seleção automática

CMD, exemplos independentes. O fornecedor escolhido precisa estar configurado, apto e autorizado.

```cmd
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider openai
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider deepseek
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider auto
```

Para um modelo e esforço explícitos, o exemplo abaixo (arquivo `.cmd`) usa valores presentes no catálogo distribuído com a versão 1.0.0; confira a configuração efetiva e a disponibilidade comercial atual antes de executar.

```cmd
setlocal
set "RASAI_DEEPSEEK_REASONING_EFFORT=HIGH"
.venv\Scripts\python.exe -m rasai audit https://example.com --max-pages 1 --device-context mobile --ai-provider deepseek --ai-model deepseek-flash --ai-content-remediation --ai-technical-remediation
endlocal
```

Para `auto`, configure os modelos de cada fornecedor pelas variáveis/catálogos correspondentes; não passe `--ai-model` com `--ai-provider auto`. Consulte [modelos e esforço](AI_MODEL_CONFIGURATION.md).

### 6. Auditoria com capacidades e integrações combinadas

O exemplo abaixo habilita desempenho Web, Apdex, pesquisa SERP, remediações por IA, análise profunda, segurança passiva e observabilidade externa. **Pode gerar custos e carga considerável.** Não é uma garantia de execução de todos os catálogos: as capacidades basais são resolvidas pelo programa e cada fonte externa exige seus próprios pré-requisitos.

PowerShell 5.1/7, execute em uma janela dedicada para não manter as variáveis não secretas em outros trabalhos:

```powershell
$Python = ".\.venv\Scripts\python.exe"
$env:RASAI_PRESENTATION_TIMEZONE = 'America/Sao_Paulo'
$env:RASAI_PAGESPEED_ENABLED = 'true'
$env:RASAI_CRUX_ENABLED = 'true'
$env:RASAI_CRUX_HISTORY_ENABLED = 'true'
$env:RASAI_COMMON_CRAWL_ENABLED = 'true'
$env:RASAI_SERP_MODE = 'live'
$env:RASAI_SERP_PROVIDER = 'serpapi'
$env:RASAI_SERP_MAX_QUERIES = '3'
$env:RASAI_SERP_MAX_REQUESTS = '10'
$env:RASAI_SERP_MAX_DEPTH = '20'
$env:RASAI_IMPROVEMENT_INTELLIGENCE = 'true'
$env:RASAI_PASSIVE_SECURITY = 'true'

# Ative apenas se a propriedade real estiver autorizada e configurada:
# $env:RASAI_GSC_ENABLED = 'true'
# $env:RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL = 'sc-domain:example.com'
# $env:RASAI_CLARITY_ENABLED = 'true'

$Argumentos = @(
    'audit', 'https://example.com',
    '--project', 'Auditoria integrada',
    '--device-context', 'mobile',
    '--language', 'pt-BR', '--market', 'BR', '--max-pages', '1',
    '--ai-provider', 'auto',
    '--ai-content-remediation', '--ai-technical-remediation',
    '--web-performance', '--web-performance-max-pages', '1',
    '--web-performance-field-source', 'auto',
    '--lighthouse-categories', 'performance,accessibility,best-practices,seo,agentic-browsing',
    '--synthetic-apdex', '--apdex-threshold-seconds', '3',
    '--apdex-samples-per-context', '20', '--apdex-max-attempts-per-context', '25',
    '--apdex-max-pages', '1', '--apdex-delay-seconds', '1', '--apdex-concurrency', '1',
    '--apdex-experience', '--apdex-experience-samples', '20',
    '--apdex-experience-max-attempts', '25', '--apdex-experience-max-pages', '1',
    '--apdex-experience-delay-seconds', '1', '--apdex-experience-concurrency', '1',
    '--search-query', 'auditoria de sites',
    '--search-query', 'qualidade de páginas web',
    '--search-query', 'prontidão para inteligência artificial',
    '--search-depth', '20', '--search-device', 'mobile',
    '--search-competitive', '--no-search-compare-content', '--no-search-ai-competitive'
)
& $Python -m rasai @Argumentos
if ($LASTEXITCODE -ne 0) { throw "Falha na execução. Consulte os logs da auditoria." }
```

**Credenciais e autorização:** PageSpeed usa `RASAI_PAGESPEED_API_KEY`, CrUX atual/histórico usa `RASAI_CRUX_API_KEY`, SerpApi usa `RASAI_SERPAPI_API_KEY`, GSC usa OAuth e propriedade autorizada, Clarity usa `RASAI_CLARITY_API_TOKEN` e o projeto correspondente. Common Crawl não exige chave. IA usa as credenciais dos fornecedores elegíveis. Não copie chaves para esse script. As linhas comentadas de GSC/Clarity não desligam configurações previamente herdadas: confira o ambiente ou defina explicitamente `false` se não quiser esses serviços.

A seleção de todos os catálogos e as autorizações interativas são feitas em **Preparar auditoria** no console. Não há equivalência demonstrada entre o comando acima e o plano interativo completo. Em particular, `RASAI_PERPLEXITY_ENABLED=true` só permite a integração, não informa consultas nem autoriza cobrança. Para pesquisas Perplexity com termos e modo WEB/FAST, use o fluxo explícito do console descrito em [Perplexity](PERPLEXITY_SEARCH_INTELLIGENCE.md). Não converta automaticamente termos SERP em pesquisas Perplexity.

### 7. Operações sobre auditorias já existentes

PowerShell 5.1/7, substitua os identificadores de exemplo pelos reais. Os comandos têm finalidades diferentes:

```powershell
$Python = ".\.venv\Scripts\python.exe"
& $Python -m rasai ai-reanalysis ".\audits\AUD-EXEMPLO"
& $Python -m rasai ai-reanalysis ".\audits\AUD-EXEMPLO" --write-local-replay
```

O primeiro inspeciona o plano local; o segundo materializa a reanálise consultiva local sem novas chamadas comerciais. A autorização de uma nova inferência paga é separada. Veja [reanálise consultiva](GEO_AI_MULTIQUERY_AND_REANALYSIS.md).

Para recriar a apresentação e o catálogo sem nova coleta, use o [script de rematerialização em cópia externa](REPORT_REMATERIALIZATION.md#regenerar-catálogo-e-apresentação-a-partir-de-uma-auditoria-existente). Para reprocessar ou consolidar, use a seção anterior e confirme o escopo: reprocessamento não é sinônimo de regeneração de HTML.

### Validar antes de executar

A ajuda do entrypoint oficial (`python -m rasai audit --help` e a ajuda do subcomando correspondente) é a referência local para os argumentos disponíveis. Os exemplos desta seção são baseados na versão 1.0.0 e na revisão estática dos registradores de argumentos e consumidores. A resolução de uma configuração, a aptidão de uma integração e a efetiva cobrança só podem ser confirmadas no ambiente de execução; não faça uma nova auditoria remunerada apenas para validar a sintaxe.

## Console interativo

```text
rasai-console
```

O console monta os mesmos argumentos públicos da CLI, apresenta capacidade dos providers, exposição pré-execução, configuração editorial, Web Performance e demais opções suportadas. Secrets não são gravados no INI. Em `AI=auto`, o usuário pode excluir providers aptos/elegíveis do pool sem apagar ou alterar suas credenciais. Todos os providers integrados podem participar do pool quando configurados e aptos; `RASAI_AI_AUTO_EXCLUDE` é o mecanismo para manter um provider configurado fora do AUTO.

## API / execução remota

A Web/API e o console remoto possuem documentação própria porque autenticação, OIDC, control plane, jobs e workers são contratos de deployment diferentes da CLI local:

- [WEB_API_CLI.md](WEB_API_CLI.md)
- [WEB_API_FOUNDATION.md](WEB_API_FOUNDATION.md)
- [PRODUCT_PLATFORM_ARCHITECTURE.md](PRODUCT_PLATFORM_ARCHITECTURE.md)
- [SAAS_PILOT_WEB.md](SAAS_PILOT_WEB.md)

O endpoint `GET /api/v1/audit-job-options` projeta o contrato canônico de opções não secretas. A UI Web deve derivar as opções de provider do `provider_registry`, evitando catálogo hardcoded divergente.

## Princípios de segurança da CLI

- não materializar API keys ou bearer tokens em argumentos/documentação/logs;
- não transformar falha de provider externo em finding do website;
- não recalcular evidência histórica para apresentar dado externo novo;
- não misturar métricas externas com o **Índice de Prontidão Search & IA** sem contrato metodológico versionado;
- manter retries/fallbacks limitados e observáveis;
- exigir revisão humana para remediações de conteúdo ou crawling sugeridas por IA.
