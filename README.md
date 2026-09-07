# RASAI — Search & AI Readiness Auditor

> **Identidade atual:** **RASAI — Search & AI Readiness Auditor**. O índice público é **SARI-001 — Search & AI Readiness Index**. `searchgeo`, `searchgeo-console`, `SEARCHGEO_*`, o namespace Python `searchgeo` e IDs `SCORE-GEO-*`/`BR-GEO-*` permanecem compatíveis. Veja [docs/BRANDING_AND_COMPATIBILITY.md](docs/BRANDING_AND_COMPATIBILITY.md).

Auditor local de **Search/GEO Readiness** com evidência persistida, scoring reproduzível, análise semântica opcional por IA, remediação textual advisory, diagnóstico de crawling/discovery, Acessibilidade, Web Performance/Lighthouse/CrUX, Apdex sintético e outcomes observados de AI Search importáveis.

O produto avalia sinais técnicos e semânticos úteis para Search e sistemas generativos sem prometer ranking, tráfego, citação ou presença em respostas de IA.

## Estado funcional

Capacidades integradas:

- auditoria por URL única, conjunto explícito ou arquivo TXT;
- `mobile`, `desktop` ou `both`;
- persistência em SQLite + artifacts + log operacional;
- mini-site HTML com navegação canônica;
- **Search & AI Readiness Index `SARI-001`** com `SCORE-GEO-003` como método padrão, Score, Coverage, Confidence e Consolidation separados;
- dashboard executivo com síntese final dos indicadores, sem misturar metodologias;
- análise semântica opcional por IA;
- remediação textual evidence-bound e revisão/proposta JSON-LD;
- **Rastreamento, descoberta e acesso de crawlers** com diagnóstico determinístico de `robots.txt`, crawlers, sitemaps, discovery, `llms.txt` experimental e remediação técnica opcional por IA;
- PageSpeed/Lighthouse e Core Web Vitals/CrUX como domínio separado;
- Acessibilidade automatizada projetada separadamente a partir do artifact Lighthouse;
- **Synthetic Navigation Apdex** em Chromium, separado de Lighthouse/CrUX e do SARI;
- **Synthetic User Experience Apdex** calibrável, com população Mobile/Desktop/Tablet, separado do Synthetic Navigation Apdex e explicitamente não-RUM;
- relatórios históricos/consolidados offline sobre múltiplos `AUD-*`, com índice analítico reconstruível e snapshots HTML estáticos;
- console interativo com preflight, progresso, custo/quota, timeouts, persistência de configuração e abertura de artifacts.

Observed Generative Visibility (domínio observacional separado):

- **Observed Generative Visibility** import-first, com outcomes observados por fonte/período em `report/ai-visibility.html`;
- suporte inicial ao contrato `OGV-IMPORT-001` para Bing Webmaster Tools AI Performance normalizado e query-runs controlados;
- preservação do artifact por SHA-256, validação same-origin e Citation Presence Rate somente sobre runs válidos;
- nenhuma coleta automática por scraping e nenhum endpoint de AI Performance presumido quando não houver API pública documentada;
- `CONTROLLED_QUERY_RUNS` elegíveis podem alimentar posteriormente a calibração offline do `SCORE-GEO-003`, sem recalcular o AUD fonte.

> O `SARI-001` é um índice proprietário e reprodutível. `SCORE-GEO-003` é o método padrão para novas auditorias: as dimensões permanecem determinísticas/evidence-based e o Overall exige modelo calibrado `VALIDATED`. Sem model artifact validado, o Overall fica `NOT_CONSOLIDATED`; nenhum coeficiente é inventado e não há fallback silencioso para `SCORE-GEO-002`. Auditorias `SCORE-GEO-002` permanecem históricas e não são recalculadas. Lighthouse, Core Web Vitals, Acessibilidade automatizada, Apdex e outcomes observados mantêm seus domínios próprios.

## Instalação rápida — Windows

A forma recomendada é executar, por duplo clique ou pelo terminal, o launcher da raiz:

```cmd
iniciar.cmd
```

O launcher valida/prepara CPython 3.13, `.venv`, dependências do `pyproject.toml` e Chromium do Playwright apenas quando necessário; ao concluir, abre diretamente a primeira tela do console interativo. Se Python 3.13 estiver ausente, ele tenta instalá-lo via `winget`.

Fluxo manual de fallback:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
rasai --version
```

Compatibilidade principal:

| Item | Estado |
|---|---|
| Windows + PowerShell/CMD | alvo operacional principal |
| CPython 3.13.x | obrigatório; `>=3.13,<3.14` |
| Playwright | obrigatório |
| Chromium | obrigatório para rendering e Apdex sintético |
| SQLite | local/embarcado |
| IA externa | opcional |
| PageSpeed/CrUX | opcional |
| Observed Generative Visibility | import local; sem credencial externa nesta versão |
| SCORE-GEO-003 calibration | offline sobre AUDs persistidos; sem chamada externa durante fitting/inference |

Detalhes do bootstrap e fallback manual: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Console interativo

Forma recomendada no Windows:

```cmd
iniciar.cmd
```

Quando o ambiente já estiver preparado/ativado, o entrypoint direto permanece:

```powershell
rasai-console
```

O console executa a mesma superfície funcional principal da auditoria e adiciona configuração guiada.

Menu principal:

```text
1. Entrada
2. Projeto
3. Dispositivo
4. IA
5. Remediação textual IA
6. Web Performance
7. max-pages
8. WebPerf max-pages
9. Idioma / mercado
10. Raiz auditorias
11. Synthetic Apdex

H. Ajuda / custos
E. Variáveis de ambiente / credenciais
S. Salvar configuração INI [SEM CHAVES]
C. Histórico / relatórios consolidados [OFFLINE — sem APIs]
R. Executar
Q. Sair
```

A opção `C` é independente do pipeline de auditoria: lê `AUD-*/audit.db` em modo somente leitura, atualiza um índice analítico derivado/reconstruível e gera snapshots HTML estáticos sem acessar APIs. Veja [docs/CONSOLIDATED_REPORTING.md](docs/CONSOLIDATED_REPORTING.md).

A opção `E` agrupa as variáveis por domínios funcionais. Cada variável mostra finalidade, domínio aceito, default efetivo, dependências, custo/impacto e referência; `D` abre diretamente a documentação detalhada. Veja [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

Observed Generative Visibility e calibração `SCORE-GEO-003` permanecem superfícies CLI separadas nesta versão; não executam coleta/treinamento automático no menu da auditoria.

### Configuração persistente

O console usa:

```text
rasai-console.ini
```

Se não existir, é criado com defaults. Parâmetros não sensíveis podem ser salvos e carregados automaticamente na próxima execução.

**API keys, tokens, senhas e outras credenciais não são gravados no INI.** No menu `E. Variáveis de ambiente / credenciais`, o usuário pode alterar uma credencial apenas para a sessão atual ou, mediante confirmação explícita, persistir/remover a credencial no ambiente **User** do Windows. A persistência no Windows não exige privilégio de administrador e não grava o segredo em arquivos do RASAI.

Para cada secret, o console indica a origem do valor efetivamente usado, por exemplo `SO:USER`, `SO:MACHINE`, `SESSÃO` ou `SESSÃO | SO:USER existente`. Se um valor é alterado dentro do console, o valor da **sessão atual prevalece** durante aquela execução; a variável persistida no Windows funciona como valor herdado por novos processos.

O console nunca exibe o valor da chave em claro. Variáveis de ambiente do Windows não são um cofre de segredos: processos executados sob o mesmo usuário e ferramentas com acesso ao perfil podem lê-las.

Quando uma variável opcional possui default seguro, o menu mostra `<default efetivo: ...>` sem criar um override redundante no sistema operacional. Dessa forma, uma instalação nova continua utilizável sem preencher dezenas de variáveis.

O console marca alterações não salvas e alerta antes de sair.

### Progresso

Durante a auditoria, a mesma tela é atualizada aproximadamente uma vez por segundo com:

```text
Status
URL
Dispositivo
Operação
Início / fim / duração
Etapa
Progresso
Detalhe
```

A atualização usa processo/SQLite/log local e não gera polling HTTP/API adicional.

Detalhes: [docs/INTERACTIVE_CONSOLE.md](docs/INTERACTIVE_CONSOLE.md).

## Operação sem IA

A IA é opcional. Com `--ai-provider none`, o RASAI continua executando as análises determinísticas de acesso técnico, redirects/TLS, indexabilidade, extração de conteúdo, crawling/discovery e comparação entre dispositivos. Synthetic Navigation Apdex e Synthetic User Experience Apdex também são independentes de LLM quando habilitados. Lighthouse e Core Web Vitals permanecem independentes de IA, mas dependem das respectivas fontes externas quando configuradas.

As dimensões predominantemente semânticas podem permanecer `UNKNOWN`/`NOT_CONSOLIDATED` sem IA. Isso reduz Coverage e pode impedir o Overall do SARI-001; não transforma ausência de IA em falha do website e não aplica score zero artificial.

Mesmo com todas as dimensões consolidadas, o `SCORE-GEO-003` exige um model artifact `VALIDATED` para materializar o Overall calibrado.

## IA

Providers concretos:

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

AUTO permanece:

```text
OpenAI -> DeepSeek -> MiMo
```

Providers adicionais permanecem explicit-only até promoção de qualificação.

### Defaults públicos

Sem override explícito, o RASAI privilegia o modelo mais simples disponível na integração e o menor esforço suportado:

| Provider | Modelo default | Esforço default |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.5` | `NONE` |
| xAI | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `PROVIDER_DEFAULT` |
| Gemini | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `LOW` |

A opção 4 do console permite escolher provider, modelo, esforço/profundidade quando suportados e timeout por tentativa.

Default de timeout IA:

```text
180 s por tentativa
```

### Remediação técnica de rastreamento e descoberta por IA

Os diagnósticos determinísticos de rastreamento e descoberta executam independentemente de IA. Para habilitar apenas a camada técnica advisory:

```powershell
rasai audit https://example.com `
  --ai-provider openai `
  --ai-technical-remediation
```

Equivalente por ambiente:

```text
SEARCHGEO_AI_TECHNICAL_REMEDIATION=true
```

Default: OFF. Essa finalidade não altera Score, Coverage, Confidence, Consolidation ou `SARI-001`; sugestões exigem revisão humana.

## Credenciais

Principais variáveis:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
SEARCHGEO_PAGESPEED_API_KEY
SEARCHGEO_CRUX_API_KEY
```

Credencial configurada não garante saldo, quota, plano ou acesso ao modelo. O passo a passo para obtenção de cada chave está em [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md); PageSpeed e CrUX possuem orientação adicional em [docs/GOOGLE_API_KEYS.md](docs/GOOGLE_API_KEYS.md).

MiMo PAYG usa credencial `sk-...` no adapter atual. Token Plan `tp-...` pertence a produto/endpoint diferente.

Observed Generative Visibility e calibração `SCORE-GEO-003` não exigem credencial externa na implementação import/offline atual.

## Rastreamento e descoberta

O diagnóstico de rastreamento e descoberta aprofunda a análise técnica de descoberta sem criar novo score. Ele cobre, conforme evidência disponível:

- `robots.txt` e acesso por crawler;
- Googlebot, OAI-SearchBot, GPTBot e Google-Extended com papéis separados;
- sitemaps XML, sitemap index, gzip, RSS 2.0, Atom 1.0 e texto plano;
- limites/sintaxe e cruzamentos com HTTP, `noindex`, canonical e robots na amostra auditada;
- feeds RSS/Atom observados;
- `/llms.txt` como proposta comunitária experimental; sua presença ou ausência **não altera o Search & AI Readiness Index**;
- IndexNow como não determinável quando não existir evidência explícita de submissão;
- remediação técnica opcional por IA, default OFF.

Declarações `Sitemap:` cross-origin são preservadas como evidência, mas não são seguidas automaticamente pelo auditor; isso é uma fronteira de segurança/escopo, não um finding do site.

Página canônica:

```text
report/crawling-discovery.html
```

Detalhes: [docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md).

## Web Performance, Lighthouse e Acessibilidade

Habilitação pela CLI:

```powershell
rasai audit https://example.com `
  --ai-provider none `
  --web-performance
```

O domínio externo usa PageSpeed/Lighthouse e CrUX conforme configuração.

Default operacional de timeout externo:

```text
120 s por chamada PageSpeed/CrUX
```

Configurável por:

```text
--web-performance-timeout-seconds
SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS
opção 6 do console
```

Esse timeout controla quanto o cliente aguarda a resposta da API externa. PageSpeed executa o Lighthouse remotamente; o endpoint não oferece ao RASAI um parâmetro separado para configurar o timeout interno de carregamento da página usado pelo Lighthouse.

Quando PageSpeed falha, o relatório preserva a causa real (`timeout`, HTTP, quota, etc.). CrUX direto pode ainda produzir dados de campo. Acessibilidade automatizada depende do artifact Lighthouse e fica explicitamente **não obtida** quando esse artifact não foi produzido.

O report nunca converte ausência de dado em resultado fictício do website.

Web Performance e Acessibilidade permanecem indicadores próprios e não são introduzidos diretamente como features adicionais no Overall `SCORE-GEO-003`.

## Synthetic Navigation Apdex

Exemplo de smoke controlado:

```powershell
rasai audit https://example.com `
  --ai-provider none `
  --no-web-performance `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-delay-seconds 1 `
  --apdex-concurrency 1
```

Fórmula:

```text
Apdex = (Satisfied + 0.5 × Tolerating) / Total de amostras válidas
Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T
```

Defaults quando habilitado:

```text
T                      = obrigatório
amostras válidas       = 100
max attempts           = ceil(1.25 × alvo)
max pages              = 1
timeout por navegação  = max(45 s, 4T + 5 s)
delay                   = 1 s
concorrência            = 1; máximo 2
```

Grupos com menos de 100 amostras válidas são diagnóstico small-group e recebem `*`.

Synthetic Apdex não usa LLM nem chama PageSpeed/CrUX, mas gera navegações reais e tráfego HTTP contra o alvo.

## Synthetic User Experience Apdex

Synthetic User Experience Apdex adiciona um domínio Apdex calibrável para user-action telemetry sintética. Pode usar população explícita Mobile/Desktop/Tablet, session mode, KPM temporal, thresholds e política de erros configurados ou importados.

Exemplo manual:

```powershell
rasai audit https://example.com `
  --apdex-experience `
  --apdex-experience-device-mix mobile=60,desktop=35,tablet=5 `
  --apdex-experience-satisfied-seconds 1.5 `
  --apdex-experience-frustrated-seconds 6
```

Também pode alinhar parâmetros com configuração Dynatrace quando explicitamente configurado. Mesmo calibrado, o resultado continua **sintético e não-RUM**.

Página canônica:

```text
report/apdex-experience.html
```

Detalhes: [docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md](docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## SCORE-GEO-003 — calibração

O `SCORE-GEO-003` mantém as dez dimensões atuais como features e calibra somente o Overall contra outcome binário `CITED/NOT_CITED`.

Promotion gate mínimo:

```text
40 domínios
12 domínios no holdout
2 engines
10 queries por domínio
3 repetições por query/engine
3 dias distintos de observação por domínio
2400 observações válidas
AUC holdout >= 0,60
Brier < baseline por prevalência de treino
```

O split é feito por domínio, evitando que queries do mesmo site apareçam em treino e validação. A cobertura temporal é agregada por domínio entre AUDs elegíveis e exige pelo menos três datas distintas.

Calibrar:

```powershell
rasai scoring calibrate --dataset-version GEO-CAL-001
```

Inspecionar:

```powershell
rasai scoring inspect
```

Artifact padrão:

```text
.searchgeo/scoring/score-geo-003-model.json
```

Override de path:

```text
SEARCHGEO_SCORE_GEO_003_MODEL
```

Artifact abaixo dos gates recebe `EXPERIMENTAL` e não consolida Overall. Detalhes: [docs/SCORE_GEO_003.md](docs/SCORE_GEO_003.md).

## Observed Generative Visibility

Observed Generative Visibility mede **outcomes observados/importados**, não readiness. Ele atua depois que já existe um `AUD-*` e não chama mecanismos de busca por conta própria.

Importação:

```powershell
rasai visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Regeneração do report:

```powershell
rasai visibility report `
  --audit-id AUD-... `
  --audits-root audits
```

O contrato inicial é `OGV-IMPORT-001`. O arquivo é preservado em `artifacts/m26/` com SHA-256 e as URLs devem pertencer ao origin da auditoria.

Para query-runs controlados:

```text
Citation Presence Rate
= runs VALID com citação / total de runs VALID
```

O relatório mostra tamanho amostral e Wilson 95%. A taxa não é previsão de citação futura. A operação de importação não recalcula o SARI; query-runs elegíveis podem posteriormente compor um dataset versionado de calibração do `SCORE-GEO-003`.

Página canônica:

```text
report/ai-visibility.html
```

Detalhes: [docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).

## Execução rápida

### Mobile, sem IA e sem integrações externas

```powershell
rasai audit https://example.com --project "Exemplo"
```

### Desktop

```powershell
rasai audit https://example.com --device-context desktop
```

### Mobile + desktop

```powershell
rasai audit https://example.com --device-context both
```

### Várias URLs

```powershell
rasai audit `
  https://example.com/ `
  https://example.com/produto `
  https://example.com/faq `
  --project "Exemplo" `
  --max-pages 3
```

## Estrutura de saída

```text
audits/<AUD-ID>/
├─ audit.db
├─ artifacts/
│  └─ m26/                    # quando houver import Observed Generative Visibility
├─ logs/
│  └─ audit.log
└─ report/
   ├─ index.html               # dashboard executivo
   ├─ readiness.html           # SARI-001 e indicadores RASAI
   ├─ score-geo-003.html       # método, calibração, dataset e gates
   ├─ mobile.html              # evidências/findings; condicional
   ├─ desktop.html             # evidências/findings; condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html  # Rastreamento, descoberta e acesso de crawlers
   ├─ accessibility.html       # quando materializado
   ├─ web-performance.html
   ├─ apdex.html               # Synthetic Navigation Apdex, quando habilitado/materializado
   ├─ apdex-experience.html    # Synthetic User Experience Apdex, quando habilitado/materializado
   ├─ ai-visibility.html       # Observed Generative Visibility, após import/report
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

Model artifact global/local do projeto:

```text
.searchgeo/
└─ scoring/
   └─ score-geo-003-model.json
```

`audit.db` e `artifacts/` são fontes persistidas; o report é projeção humana.

`index.html` não cria um “score geral de tudo”. Ele resume o resultado final de cada família e aponta para a página canônica correspondente. Quando existem vários contextos Lighthouse, o dashboard prefere faixa por dispositivo/quantidade de contextos válidos a inventar uma média única do site.

`readiness.html` é a página exclusiva dos indicadores agregados RASAI. Mobile/Desktop não repetem Overall, dimensões, Coverage, Confidence ou Consolidation.

`score-geo-003.html` explica o método vigente, status do model artifact, dataset, AUC/Brier e promotion gate.

`crawling-discovery.html` é a página exclusiva do domínio Rastreamento, descoberta e acesso de crawlers e não recalcula o SARI.

`apdex-experience.html` é o domínio Synthetic User Experience Apdex e permanece separado do Synthetic Navigation Apdex Standard.

`ai-visibility.html` é o domínio observacional Observed Generative Visibility. **Readiness e visibilidade observada não são fundidos em uma métrica observacional única**; outcomes controlados entram apenas no processo explícito/versionado de calibração.

Os relatórios históricos usam uma área separada e não escrevem nos workspaces `AUD-*`:

```text
audits/.searchgeo/
└─ consolidated-index.db       # cache analítico reconstruível

audits/consolidated/
└─ CONS-<timestamp>/
   ├─ report.html              # snapshot estático
   └─ manifest.json            # filtros, fontes e rastreabilidade
```

Um `CONS-*` já existente é reutilizado quando filtros, versão do formato e fingerprints das fontes elegíveis são idênticos. Um novo `AUD-*` elegível invalida essa reutilização e produz novo snapshot.

Relatórios consolidados devem segmentar séries por `scoring_version`; `SCORE-GEO-002` e `SCORE-GEO-003` não são a mesma série metodológica.

A página inicial inclui **Configuração × resultado obtido** quando essa projeção está disponível, permitindo distinguir o que foi solicitado do que foi realmente materializado e a causa de limitações operacionais.

## Segurança

- secrets não são persistidos no INI;
- a persistência opcional de secrets no Windows usa apenas o escopo `User` e exige confirmação explícita por chave;
- a sessão atual prevalece sobre o valor herdado do SO para a execução em andamento;
- o console mascara credenciais como `[SET]` e informa sua origem sem revelar o valor;
- variáveis de ambiente não substituem um secret manager quando esse nível de proteção for necessário;
- secrets não devem aparecer em reports/logs;
- não trate key configurada como prova de saldo/quota;
- Rastreamento, descoberta e acesso de crawlers não segue automaticamente sitemap cross-origin declarado sem política segura de aquisição/autorização;
- remediação técnica Rastreamento, descoberta e acesso de crawlers não deve automatizar policy de crawler/treinamento sem decisão humana;
- não execute Synthetic Navigation Apdex e Synthetic User Experience Apdex em volume relevante contra produção sem autorização;
- Observed Generative Visibility rejeita URLs cross-origin e não faz scraping de portal de webmaster;
- calibração `SCORE-GEO-003` não deve ser promovida a `VALIDATED` sem satisfazer integralmente o promotion gate versionado.

## Identificadores internos históricos

Nomes internos de módulos, tabelas, eventos e documentos normativos podem manter identificadores históricos por compatibilidade e rastreabilidade. A UI, os relatórios e a documentação operacional usam nomenclatura funcional.

## Documentação

- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)
- [docs/INTERACTIVE_CONSOLE.md](docs/INTERACTIVE_CONSOLE.md)
- [docs/CONSOLIDATED_REPORTING.md](docs/CONSOLIDATED_REPORTING.md)
- [docs/CONSOLIDATED_REPORTING_VALIDATION.md](docs/CONSOLIDATED_REPORTING_VALIDATION.md)
- [docs/AI_GUIDE.md](docs/AI_GUIDE.md)
- [docs/GOOGLE_API_KEYS.md](docs/GOOGLE_API_KEYS.md)
- [docs/REPORT_GUIDE.md](docs/REPORT_GUIDE.md)
- [docs/OUTPUTS_AND_ARTIFACTS.md](docs/OUTPUTS_AND_ARTIFACTS.md)
- [docs/SEARCHGEO_READINESS_INDEX.md](docs/SEARCHGEO_READINESS_INDEX.md)
- [docs/SCORE_GEO_003.md](docs/SCORE_GEO_003.md)
- [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md)
- [docs/SCORING_VALIDATION.md](docs/SCORING_VALIDATION.md)
- [docs/INDICATOR_PROVENANCE.md](docs/INDICATOR_PROVENANCE.md)
- [docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)
- [docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md](docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md)
- [docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md)