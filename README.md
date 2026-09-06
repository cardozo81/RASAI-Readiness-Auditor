# SearchGEO Readiness Auditor

Auditor local de **Search/GEO Readiness** com evidência persistida, scoring reproduzível, análise semântica opcional por IA, remediação textual advisory, Acessibilidade, Web Performance/Lighthouse/CrUX e Synthetic Navigation Apdex.

O produto avalia sinais técnicos e semânticos úteis para Search e sistemas generativos sem prometer ranking, tráfego, citação ou presença em respostas de IA.

## Estado funcional

Capacidades integradas:

- auditoria por URL única, conjunto explícito ou arquivo TXT;
- `mobile`, `desktop` ou `both`;
- persistência em SQLite + artifacts + log operacional;
- mini-site HTML com navegação canônica;
- Score, Coverage e Confidence separados;
- análise semântica opcional por IA;
- remediação textual evidence-bound e revisão/proposta JSON-LD;
- PageSpeed/Lighthouse e Core Web Vitals/CrUX como domínio separado;
- Acessibilidade automatizada projetada separadamente a partir do artifact Lighthouse;
- Synthetic Navigation Apdex em Chromium, separado de Lighthouse/CrUX e do Score GEO;
- relatórios históricos/consolidados offline sobre múltiplos `AUD-*`, com índice analítico reconstruível e snapshots HTML estáticos;
- console interativo com preflight, progresso, custo/quota, timeouts, persistência de configuração e abertura de artifacts.

> O Score SearchGEO é um modelo interno de readiness. Lighthouse, Core Web Vitals, Acessibilidade automatizada e Apdex possuem metodologias próprias e são exibidos separadamente.

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
| Chromium | obrigatório para rendering e Synthetic Apdex |
| SQLite | local/embarcado |
| IA externa | opcional |
| PageSpeed/CrUX | opcional |

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

O console executa a mesma superfície funcional da CLI e adiciona configuração guiada.

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

A opção `E` não exibe mais uma lista plana. Ela agrupa as variáveis por **Aplicação**, **Credenciais IA**, **Modelos/reasoning**, **Endpoints avançados**, **Web Performance/Google**, **Synthetic Apdex** e **Browser/Playwright**. Cada variável mostra finalidade, domínio aceito, default efetivo, dependências, custo/impacto e referência; `D` abre diretamente a documentação detalhada. Veja [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

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

## Synthetic Navigation Apdex

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
├─ logs/
│  └─ audit.log
└─ report/
   ├─ index.html
   ├─ mobile.html              # condicional
   ├─ desktop.html             # condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ accessibility.html       # quando materializado
   ├─ web-performance.html
   ├─ apdex.html               # quando habilitado/materializado
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

`audit.db` e `artifacts/` são fontes persistidas; o report é projeção humana.

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

A página inicial inclui **Configuração × resultado obtido**, permitindo distinguir o que foi solicitado do que foi realmente materializado e a causa de limitações operacionais.

## Segurança

- secrets não são persistidos no INI;
- a persistência opcional de secrets no Windows usa apenas o escopo `User` e exige confirmação explícita por chave;
- a sessão atual prevalece sobre o valor herdado do SO para a execução em andamento;
- o console mascara credenciais como `[SET]` e informa sua origem sem revelar o valor;
- variáveis de ambiente não substituem um secret manager quando esse nível de proteção for necessário;
- secrets não devem aparecer em reports/logs;
- não trate key configurada como prova de saldo/quota;
- não execute Synthetic Apdex em volume relevante contra produção sem autorização.

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
