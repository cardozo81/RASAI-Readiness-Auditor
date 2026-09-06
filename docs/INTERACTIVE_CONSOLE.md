# Console interativo de execução

O SearchGEO mantém `searchgeo audit` como interface estável e oferece o console textual opcional:

```powershell
searchgeo-console
```

O console é uma camada de configuração, preflight, observabilidade e execução sobre o mesmo pipeline da CLI. Ele não implementa um segundo motor de auditoria. O submenu de relatórios consolidados é um subsistema offline adicional e também não altera o pipeline de auditoria.

## Princípios

- uma tela lógica por vez;
- configuração explícita antes da execução;
- defaults seguros visíveis sem obrigar o usuário a materializar variáveis redundantes;
- variáveis avançadas agrupadas por fronteira funcional;
- progresso/etapa durante a execução sem polling externo adicional;
- secrets nunca exibidos em claro nem gravados no INI;
- persistência opcional de credenciais no Windows exige confirmação explícita e usa apenas `User`;
- integração externa indisponível é explicada e não vira finding do website;
- custo prévio é estimativa de exposição, não invoice;
- consumo real após a execução vem da telemetria persistida;
- Synthetic Apdex é carga sintética, não custo financeiro de API;
- consolidação histórica é somente leitura sobre `AUD-*/audit.db`, sem chamadas de API e sem recalcular o motor GEO.

## Arquivo de configuração do usuário

O console usa por padrão:

```text
searchgeo-console.ini
```

Ao iniciar:

1. se o arquivo não existir, ele é criado com defaults não sensíveis;
2. os parâmetros persistíveis são carregados;
3. configurações de ambiente válidas continuam disponíveis para a sessão;
4. API keys, tokens, senhas e outros secrets não são gravados pelo INI.

O menu mostra `SALVO` ou `ALTERAÇÕES NÃO SALVAS`. Para persistir parâmetros não sensíveis:

```text
S. Salvar configuração INI [SEM CHAVES]
```

A gravação é atômica. Ao sair com alterações pendentes, o console pede decisão explícita. Credenciais que diferem da persistência do Windows continuam sendo tratadas como alterações voláteis da sessão.

## Credenciais

Principais variáveis:

| Serviço | Variável |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| MiMo | `MIMO_API_KEY` |
| xAI | `XAI_API_KEY` |
| Qwen | `DASHSCOPE_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| PageSpeed | `SEARCHGEO_PAGESPEED_API_KEY` |
| CrUX | `SEARCHGEO_CRUX_API_KEY` |

A referência completa, incluindo **como obter cada chave**, está em [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). Para as chaves Google de PageSpeed/CrUX, veja também [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md).

### Sessão × persistência no Windows

O valor efetivamente usado pela auditoria é o valor presente no processo atual. Se uma key herdada do Windows é alterada dentro do console, **o valor da sessão aberta prevalece imediatamente**.

A origem é representada sem exibir o segredo:

```text
[SET] [SO:USER]
[SET] [SO:MACHINE]
[SET] [SESSÃO]
[SET] [SESSÃO | SO:USER existente]
```

Para uma variável de secret:

```text
S = setar/alterar somente a sessão atual
R = remover somente da sessão atual
P = persistir/remover credencial no Windows/User
D = abrir documentação detalhada
V = voltar
```

A opção `P` exige valor válido na sessão e confirmação explícita `SIM`. A persistência usa o ambiente **User** do Windows, não `Machine`, não exige Administrador e nunca grava o segredo em arquivos SearchGEO. Remover a persistência `User` não apaga o valor já carregado na sessão atual.

Variáveis de ambiente não são um secret manager: processos e ferramentas com acesso ao mesmo perfil podem lê-las.

MiMo exige credencial PAYG `sk-...` no adapter atual. Token Plan `tp-...` usa produto/endpoint diferente.

## Menu de variáveis de ambiente — organizado por domínio

A antiga lista plana foi substituída por um nível de navegação por fronteira funcional:

```text
CONFIGURAÇÃO AVANÇADA — VARIÁVEIS DE AMBIENTE

1. Aplicação e execução
2. IA — credenciais
3. IA — modelos e reasoning
4. IA — endpoints avançados
5. Web Performance / Google APIs
6. Synthetic Apdex
7. Browser / Playwright

A. Todas as variáveis
D. Abrir documentação detalhada
V. Voltar
```

Dentro de cada grupo, somente as variáveis daquele domínio são exibidas. Ao selecionar uma variável, a tela informa:

```text
Grupo
Para que serve
Tipo
Valores aceitos
Default efetivo
Quando é obrigatória
Se é sensível
Custo/impacto
Valor/origem atual
Exemplo
Como obter/referência
Observações
```

### Defaults na tela

Quando a variável está ausente, mas existe um default seguro do produto, o console exibe por exemplo:

```text
SEARCHGEO_DEVICE_CONTEXT              <default efetivo: mobile>
SEARCHGEO_AI_TIMEOUT_SECONDS           <default efetivo: 180>
SEARCHGEO_WEB_PERFORMANCE              <default efetivo: false>
SEARCHGEO_OPENAI_MODEL                 <default efetivo: gpt-5.6-luna>
```

Isso **não cria a variável no sistema operacional**. O objetivo é mostrar o valor efetivamente usado e evitar configuração redundante. Secrets não possuem default. O threshold T do Synthetic Apdex também não recebe valor inventado porque precisa refletir o objetivo de desempenho definido pelo usuário.

### Variáveis com domínio fechado

Enums e booleanos são configurados por lista guiada. Exemplos:

```text
SEARCHGEO_DEVICE_CONTEXT
  mobile | desktop | both

SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE
  auto | pagespeed | crux | none

SEARCHGEO_APDEX_CONCURRENCY
  1 | 2
```

Modelos e níveis de reasoning são derivados do provider registry, reduzindo risco de a UI divergir da validação do código.

### Validações adicionais

O editor recusa antes da execução, entre outros casos:

- `SEARCHGEO_CONFIG` apontando para arquivo inexistente;
- `SEARCHGEO_LOG_LEVEL` fora do domínio aceito;
- categoria Lighthouse desconhecida ou duplicada;
- endpoint avançado que não seja URL HTTP(S) absoluta;
- modelo/reasoning fora do domínio do provider;
- `field_source=crux` sem credencial CrUX ativa;
- limites inválidos de Synthetic Apdex.

## Provider registry e AUTO

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

A cadeia `AUTO` permanece:

```text
OpenAI -> DeepSeek -> MiMo
```

xAI, Qwen, Gemini e Anthropic permanecem explicit-only enquanto sua qualificação não for promovida.

## Defaults públicos de IA

| Provider | Modelo default | Esforço default |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.5` | `NONE` |
| xAI | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `PROVIDER_DEFAULT` |
| Gemini | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `LOW` |

Overrides explícitos continuam prevalecendo quando o adapter aceita o valor.

## Menu principal

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
R. Executar [APTO|INDISPONÍVEL]
Q. Sair
```

Após uma auditoria:

```text
P. Abrir pasta da auditoria
I. Abrir relatório HTML
M. Voltar ao menu
Q. Sair
```

## Opção 4 — IA

A configuração reúne provider, modelo, esforço/profundidade quando suportado e timeout por tentativa. Exemplo:

```text
4. IA : openai [APTO] | modelo=gpt-5.6-luna | esforço=NONE | timeout=180s
```

`SEARCHGEO_AI_TIMEOUT_SECONDS` continua disponível como override avançado. Em `AUTO`, OpenAI, DeepSeek e MiMo mantêm suas próprias configurações; fallback não herda parâmetro incompatível do provider anterior.

## Opção 5 — Remediação textual por IA

Só pode ser habilitada quando a opção 4 possui provider apto. Com IA=`none` ou provider indisponível:

```text
INDISPONÍVEL [REQUER IA CONFIGURADA E ATIVA NO ITEM 4]
```

A remediação é advisory/evidence-bound, pode gerar chamadas adicionais e não altera automaticamente Score, Coverage, Confidence, RuleExecution ou Finding.

## Opção 6 — Web Performance

Configura PageSpeed/Lighthouse e dados de campo CrUX. O console permite definir habilitação, field source e timeout por URL.

Default operacional:

```text
120 segundos
```

Esse timeout controla quanto o cliente espera a resposta PageSpeed/CrUX. A API PageSpeed executa Lighthouse remotamente e não expõe ao SearchGEO parâmetro separado para o timeout interno de carregamento do Lighthouse.

`field_source=crux` exige `SEARCHGEO_CRUX_API_KEY`.

Falha PageSpeed pode deixar Lighthouse/Acessibilidade indisponíveis enquanto CrUX direto ainda pode funcionar. O relatório preserva a causa real; não converte ausência de dado em problema do website.

## Opção 11 — Synthetic Apdex

Ao habilitar, o console explica e solicita T, amostras válidas, máximo de tentativas, máximo de páginas, timeout, delay e concorrência.

Defaults:

```text
T                    = obrigatório
amostras válidas     = 100
max attempts         = ceil(1.25 × alvo)
max pages            = 1
timeout                = max(45 s, 4T + 5 s)
delay                  = 1 s
concorrência           = 1; máximo 2
```

Grupos com 1–99 amostras válidas são small-group e recebem `*`. Synthetic Apdex não usa LLM nem PageSpeed/CrUX, mas gera tráfego HTTP real; volume relevante em produção exige autorização.

## Opção C — Histórico / relatórios consolidados

A opção `C` é um fluxo independente e offline. Ela não usa provider de IA, PageSpeed, CrUX ou Synthetic Apdex em modo de execução. Apenas lê os resultados que já foram persistidos em auditorias anteriores.

Fluxo:

```text
AUD-*/audit.db
  -> leitura SQLite mode=ro / query_only
  -> .searchgeo/consolidated-index.db
  -> filtros de domínio, período, device e URL
  -> validação de comparabilidade
  -> consolidated/CONS-*/report.html + manifest.json
```

O índice é cache derivado e reconstruível. Os `audit.db` permanecem fonte de verdade e não são modificados.

O relatório reúne os indicadores persistidos relevantes — Score/Coverage/Confidence, dimensões GEO, Web Performance, CWV, Synthetic Apdex e estatística de findings — apenas quando as observações são comparáveis. Mudanças de `scoring_version`, universo de URLs, profile/threshold Apdex ou ausência de dado são tratadas explicitamente; nenhum valor ausente vira zero.

Mobile e Desktop permanecem separados. Em filtro explícito por URL, score audit-level só entra se o universo completo da auditoria estiver contido no conjunto selecionado; o sistema não recalcula score parcial.

Relatórios idênticos são reutilizados somente quando filtros, versão do formato e fingerprints dos AUDs elegíveis permanecem iguais. Um novo AUD elegível gera novo snapshot.

Detalhes de arquitetura, metodologia, dedupe e rollback: [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [CONSOLIDATED_REPORTING_VALIDATION.md](CONSOLIDATED_REPORTING_VALIDATION.md).

## Progresso durante a execução

A mesma tela é atualizada aproximadamente uma vez por segundo com:

```text
Status
URL
Dispositivo
Operação
Início
Fim
Duração
Etapa
Progresso
Detalhe
```

Não há polling HTTP adicional: a atualização usa estado do subprocesso, SQLite local em leitura e tail limitado do log.

## Configuração × resultado obtido

Após a execução, console e relatório diferenciam o que foi configurado do que foi materializado. São mostrados separadamente tentativas/sucessos de IA, tokens/custo estimado, chamadas PageSpeed/CrUX, cobertura de Acessibilidade e tentativas/amostras Synthetic Apdex.

Fonte configurada que falhou por timeout, quota, HTTP, ausência de artifact ou falta de dado não é apresentada como sucesso nem como problema do website.

## Segurança e persistência

- INI não armazena secrets;
- reports/logs não devem conter chaves em claro;
- key configurada não é prova de saldo/quota;
- sessão atual prevalece sobre valores herdados durante o processo aberto;
- persistência Windows usa somente `User` e confirmação explícita;
- remoção da persistência `User` não apaga automaticamente a sessão atual;
- origem `SO:USER`, `SO:MACHINE` ou `SESSÃO` é mostrada sem revelar o secret;
- variáveis de ambiente não equivalem a secret manager;
- parâmetros não sensíveis podem ser salvos no INI;
- alterações não salvas são avisadas antes da saída;
- consolidação não escreve em `AUD-*/audit.db` e não depende de credenciais externas.

## Leituras relacionadas

- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI_REFERENCE.md](CLI_REFERENCE.md)
- [CONSOLE_COST_AND_USAGE.md](CONSOLE_COST_AND_USAGE.md)
- [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md)
- [CONSOLIDATED_REPORTING_VALIDATION.md](CONSOLIDATED_REPORTING_VALIDATION.md)
- [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [AI_GUIDE.md](AI_GUIDE.md)
