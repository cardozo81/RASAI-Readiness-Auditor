# SearchGEO Readiness Auditor

Auditor local de **Search/GEO Readiness** com evidência persistida, scoring reproduzível, análise semântica opcional por IA, remediação textual advisory, diagnóstico de crawling/discovery, Acessibilidade, Web Performance/Lighthouse/CrUX, Apdex sintético e outcomes observados de AI Search importáveis.

O produto avalia sinais técnicos e semânticos úteis para Search e sistemas generativos sem prometer ranking, tráfego, citação ou presença em respostas de IA.

## Estado funcional

Capacidades integradas:

- auditoria por URL única, conjunto explícito ou arquivo TXT;
- `mobile`, `desktop` ou `both`;
- persistência em SQLite + artifacts + log operacional;
- mini-site HTML com navegação canônica;
- **SearchGEO Readiness Index `SGRI-001`** com Score, Coverage, Confidence e Consolidation separados;
- dashboard executivo com síntese final dos indicadores, sem misturar metodologias;
- análise semântica opcional por IA;
- remediação textual evidence-bound e revisão/proposta JSON-LD;
- **M24 Crawling, Discovery & AI Access** com diagnóstico determinístico de `robots.txt`, crawlers, sitemaps, discovery, `llms.txt` experimental e remediação técnica opcional por IA;
- PageSpeed/Lighthouse e Core Web Vitals/CrUX como domínio separado;
- Acessibilidade automatizada projetada separadamente a partir do artifact Lighthouse;
- **M23 Synthetic Navigation Apdex** em Chromium, separado de Lighthouse/CrUX e do SGRI;
- **M25 Synthetic User Experience Apdex** calibrável, com população Mobile/Desktop/Tablet, separado do M23 e explicitamente não-RUM;
- relatórios históricos/consolidados offline sobre múltiplos `AUD-*`, com índice analítico reconstruível e snapshots HTML estáticos;
- console interativo com preflight, progresso, custo/quota, timeouts, persistência de configuração e abertura de artifacts.

Em implementação no M26, sem alterar scoring:

- **Observed Generative Visibility** import-first, com outcomes observados por fonte/período em `report/ai-visibility.html`;
- suporte inicial ao contrato `OGV-IMPORT-001` para Bing Webmaster Tools AI Performance normalizado e query-runs controlados;
- preservação do artifact por SHA-256, validação same-origin e Citation Presence Rate somente sobre runs válidos;
- nenhuma coleta automática por scraping e nenhum endpoint de AI Performance presumido quando não houver API pública documentada.

> O `SGRI-001` é um índice proprietário, evidence-based e reprodutível do SearchGEO. Enquanto a aritmética não mudar, o banco preserva `SCORE-GEO-002` como versão do motor de cálculo. Lighthouse, Core Web Vitals, Acessibilidade automatizada, M23/M25 Apdex, diagnósticos M24 e outcomes M26 possuem metodologias/domínios próprios e não são convertidos silenciosamente no SGRI.

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
searchgeo --version
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
| M26 Observed Visibility | import local; sem credencial externa nesta versão |

Detalhes do bootstrap e fallback manual: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Console interativo

Forma recomendada no Windows:

```cmd
iniciar.cmd
```

Quando o ambiente já estiver preparado/ativado, o entrypoint direto permanece:

```powershell
searchgeo-console
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
C. Histórico / relatórios consolidados [OFFLINE | sem APIs]
R. Executar
Q. Sair
```

A opção `C` é independente do pipeline de auditoria: lê `AUD-*/audit.db` em modo somente leitura, atualiza um índice analítico derivado/reconstruível e gera snapshots HTML estáticos sem acessar APIs. Veja [docs/CONSOLIDATED_REPORTING.md](docs/CONSOLIDATED_REPORTING.md).

A opção `E` agrupa as variáveis por domínios funcionais. Cada variável mostra finalidade, domínio aceito, default efetivo, dependências, custo/impacto e referência; `D` abre diretamente a documentação detalhada. Veja [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

M26 Observed Generative Visibility é inicialmente uma superfície CLI/import-first separada; não é uma coleta automática executada pelo menu de auditoria.

### Configuração persistente

O console usa:

```text
searchgeo-console.ini
```

Se não existir, é criado com defaults. Parâmetros não sensíveis podem ser salvos e carregados automaticamente na próxima execução.

**API keys, tokens, senhas e outras credenciais não são gravados no INI.** No menu `E. Variáveis de ambiente / credenciais`, o usuário pode alterar uma credencial apenas para a sessão atual ou, mediante confirmação explícita, persistir/remover a credencial no ambiente **User** do Windows. A persistência no Windows não exige privilégio de administrador e não grava o segredo em arquivos do SearchGEO.

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

Sem override explícito, o SearchGEO privilegia o modelo mais simples disponível na integração e o menor esforço suportado:

| Provider | Modelo default | Esforço default |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.5` | `NONE` |
| xAI | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `PROVIDER_DEFAULT` |
| Gemini | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `LOW` |

A opção 4 do console permite escolher provider, modelo, esforço/profundidade quando suportado e timeout por tentativa.

Default de timeout IA:

```text
180 s por tentativa
```

### Remediação técnica M24 por IA

Os diagnósticos determinísticos M24 executam independentemente de IA. Para habilitar apenas a camada técnica advisory:

```powershell
searchgeo audit https://example.com `
  --ai-provider openai `
  --ai-technical-remediation
```

Equivalente por ambiente:

```text
SEARCHGEO_AI_TECHNICAL_REMEDIATION=true
```

Default: OFF. Essa finalidade não altera Score, Coverage, Confidence, Consolidation ou `SGRI-001`; sugestões exigem revisão humana.

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

M26 não exige credencial externa na implementação import-first; ele lê um JSON local normalizado.

## Crawling, Discovery & AI Access — M24

M24 aprofunda o diagnóstico técnico de descoberta sem criar novo score. Ele cobre, conforme evidência disponível:

- `robots.txt` e acesso por crawler;
- Googlebot, OAI-SearchBot, GPTBot e Google-Extended com papéis separados;
- sitemaps XML, sitemap index, gzip, RSS 2.0, Atom 1.0 e texto plano;
- limites/sintaxe e cruzamentos com HTTP, `noindex`, canonical e robots na amostra auditada;
- feeds RSS/Atom observados;
- `/llms.txt` como proposta comunitária experimental e **non-scoring**;
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
searchgeo audit https://example.com `
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

Esse timeout controla quanto o cliente aguarda a resposta da API externa. PageSpeed executa o Lighthouse remotamente; o endpoint não oferece ao SearchGEO um parâmetro separado para configurar o timeout interno de carregamento da página usado pelo Lighthouse.

Quando PageSpeed falha, o relatório preserva a causa real (`timeout`, HTTP, quota, etc.). CrUX direto pode ainda produzir dados de campo. Acessibilidade automatizada depende do artifact Lighthouse e fica explicitamente **não obtida** quando esse artifact não foi produzido.

O report nunca converte ausência de dado em resultado fictício do website.

## Synthetic Navigation Apdex — M23

Exemplo de smoke controlado:

```powershell
searchgeo audit https://example.com `
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

## Synthetic User Experience Apdex — M25

M25 adiciona um domínio Apdex calibrável para user-action telemetry sintética. Pode usar população explícita Mobile/Desktop/Tablet, session mode, KPM temporal, thresholds e política de erros configurados ou importados.

Exemplo manual:

```powershell
searchgeo audit https://example.com `
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

## Observed Generative Visibility — M26

M26 mede **outcomes observados/importados**, não readiness. Ele atua depois que já existe um `AUD-*` e não chama mecanismos de busca por conta própria.

Importação:

```powershell
searchgeo visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Regeneração do report:

```powershell
searchgeo visibility report `
  --audit-id AUD-... `
  --audits-root audits
```

O contrato inicial é `OGV-IMPORT-001`. O arquivo é preservado em `artifacts/m26/` com SHA-256 e as URLs devem pertencer ao origin da auditoria.

Para query-runs controlados:

```text
Citation Presence Rate
= runs VALID com citação / total de runs VALID
```

O relatório mostra o tamanho amostral e intervalo Wilson 95% quando calculável. A taxa não é previsão de citação futura e não recalibra o SGRI.

Página canônica:

```text
report/ai-visibility.html
```

Detalhes: [docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md).

## Execução rápida

### Mobile, sem IA e sem integrações externas

```powershell
searchgeo audit https://example.com --project "Exemplo"
```

### Desktop

```powershell
searchgeo audit https://example.com --device-context desktop
```

### Mobile + desktop

```powershell
searchgeo audit https://example.com --device-context both
```

### Várias URLs

```powershell
searchgeo audit `
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
│  └─ m26/                    # quando houver import M26
├─ logs/
│  └─ audit.log
└─ report/
   ├─ index.html               # dashboard executivo
   ├─ searchgeo.html           # SGRI-001 e indicadores SearchGEO
   ├─ mobile.html              # evidências/findings; condicional
   ├─ desktop.html             # evidências/findings; condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html  # M24
   ├─ accessibility.html       # quando materializado
   ├─ web-performance.html
   ├─ apdex.html               # M23, quando habilitado/materializado
   ├─ apdex-experience.html    # M25, quando habilitado/materializado
   ├─ ai-visibility.html       # M26, após import/report
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

`audit.db` e `artifacts/` são fontes persistidas; o report é projeção humana.

`index.html` não cria um “score geral de tudo”. Ele resume o resultado final de cada família e aponta para a página canônica correspondente. Quando existem vários contextos Lighthouse, o dashboard prefere faixa por dispositivo/quantidade de contextos válidos a inventar uma média única do site.

`searchgeo.html` é a página exclusiva dos indicadores agregados SearchGEO. Mobile/Desktop não repetem Overall, dimensões, Coverage, Confidence ou Consolidation.

`crawling-discovery.html` é a página exclusiva do domínio M24 e não recalcula o SGRI.

`apdex-experience.html` é o domínio M25 e permanece separado do M23 Standard.

`ai-visibility.html` é o domínio observacional M26. **Readiness e visibilidade observada não são fundidos em um score comum.**

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

A página inicial inclui **Configuração × resultado obtido** quando essa projeção está disponível, permitindo distinguir o que foi solicitado do que foi realmente materializado e a causa de limitações operacionais.

## Segurança

- secrets não são persistidos no INI;
- a persistência opcional de secrets no Windows usa apenas o escopo `User` e exige confirmação explícita por chave;
- a sessão atual prevalece sobre o valor herdado do SO para a execução em andamento;
- o console mascara credenciais como `[SET]` e informa sua origem sem revelar o valor;
- variáveis de ambiente não substituem um secret manager quando esse nível de proteção for necessário;
- secrets não devem aparecer em reports/logs;
- não trate key configurada como prova de saldo/quota;
- M24 não segue automaticamente sitemap cross-origin declarado sem política segura de aquisição/autorização;
- remediação técnica M24 não deve automatizar policy de crawler/treinamento sem decisão humana;
- não execute M23/M25 Apdex em volume relevante contra produção sem autorização;
- M26 rejeita URLs cross-origin e não faz scraping de portal de webmaster.

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
- [docs/SCORING_GUIDE.md](docs/SCORING_GUIDE.md)
- [docs/SCORING_VALIDATION.md](docs/SCORING_VALIDATION.md)
- [docs/INDICATOR_PROVENANCE.md](docs/INDICATOR_PROVENANCE.md)
- [docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)
- [docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md](docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md)
- [docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md](docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md)