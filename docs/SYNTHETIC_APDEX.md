# Synthetic Navigation Apdex

Guia operacional do Synthetic Navigation Apdex do RASAi.

> A funcionalidade é **desabilitada por padrão**. Ela não altera `SARI-001`, findings GEO, Coverage ou Confidence. O índice mede uma Task sintética de navegação e não deve ser confundido com RUM/APM de usuários reais.

## Fórmula

```text
Apdex = (Satisfied + 0.5 × Tolerating) / Total de amostras válidas

Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T
```

`T` é configurado explicitamente pelo usuário e não possui default universal.

## Task medida

Cada amostra executa uma navegação real em Chromium até o evento `load` previsto pela implementação, usando perfil sintético controlado, BrowserContext novo e cache desabilitado.

Uma amostra pode ser:

- `SATISFIED`;
- `TOLERATING`;
- `FRUSTRATED`;
- inválida/excluída quando a ferramenta/profile não conseguiu produzir uma medição válida.

Timeout ou erro de navegação/aplicação conta como `FRUSTRATED` quando o profile foi efetivamente aplicado e a amostra é observável como execução válida.

## Grupos

O alvo normal é `100` amostras válidas por URL/device. Grupos entre 1 e 99 amostras válidas são diagnósticos de grupo pequeno e recebem marcador específico. O objetivo é impedir que um smoke curto pareça uma baseline final.

Quando o alvo configurado é menor que 100 e é integralmente atingido sem amostras inválidas, o run permanece `PARTIAL` por `SMALL_GROUP_BELOW_NORMAL_MINIMUM`. Esse estado é diferente de coleta incompleta ou amostra inválida.

## Configuração

CLI:

```text
--synthetic-apdex
--apdex-threshold-seconds
--apdex-samples-per-context
--apdex-max-attempts-per-context
--apdex-max-pages
--apdex-timeout-seconds
--apdex-delay-seconds
--apdex-concurrency
```

Variáveis:

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

| Parâmetro | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| habilitação | `false` | booleano | `false`; habilitar deliberadamente |
| `T` | sem default | número finito `> 0` | usar SLO/KPM definido para a Task |
| amostras válidas | `100` | inteiro `>= 1` | `100`; reduzir apenas em smoke controlado |
| máximo de tentativas | `ceil(1.25 × alvo)` | inteiro compatível com a validação do runtime | default derivado |
| máximo de páginas | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline seguro |
| timeout por navegação | `max(45 s, 4T + 5 s)` | número finito positivo e maior que `4T` | default derivado |
| delay | `1 s` | número `>= 0` | `1 s` ou maior conforme sensibilidade do alvo |
| concorrência | `1` | `1`, `2` | `1` |

## Console interativo

O console expõe Synthetic Apdex junto das demais configurações de auditoria, explica a finalidade de cada valor e mostra a carga máxima projetada em quantidade de navegações iniciadas.

O timeout de Apdex é independente do timeout de IA e do timeout PageSpeed/Lighthouse.

## Carga operacional

Synthetic Apdex não possui API paga própria e não chama LLM/PageSpeed/CrUX, mas gera CPU/tempo local, Chromium, tráfego HTTP real contra o alvo e múltiplos requests de subrecursos por navegação.

Não interprete `100 amostras` como `100 requests HTTP`. Para smoke, prefira 1 URL, 1 device, 3-5 amostras, concorrência 1 e alvo controlado. Não execute volume relevante contra produção sem autorização.

## Persistência

Os dados são persistidos em tabelas dedicadas e o relatório é materializado em:

```text
report/apdex.html
```

Identificadores internos históricos de tabela/evento podem permanecer por compatibilidade de schema; a UI e a documentação operacional usam nomenclatura funcional.

## Relação com Lighthouse e CrUX

Apdex não é inferido de LCP, INP, CLS, FCP, TBT, Speed Index ou duração da chamada PageSpeed. Lighthouse/CrUX e Synthetic Apdex medem fenômenos distintos e permanecem em páginas separadas do report.

Quando um artifact Lighthouse existe, o RASAi pode extrair metadados de perfil para rastreabilidade. Ausência do artifact não invalida as navegações Synthetic Apdex; apenas impede essa comparação documental.

## Segurança metodológica

- falha de ferramenta fica fora do denominador quando não há amostra válida;
- erro observável da aplicação/navegação não é mascarado como falha da ferramenta;
- grupo pequeno é marcado explicitamente;
- nenhum resultado é adicionado matematicamente ao Score GEO;
- não há promessa de experiência real de usuários finais.

## Diagnóstico de erros e sensibilidade ao `T`

`apdex.html` separa problemas da própria execução Synthetic Navigation Apdex de sinais relacionados de Web Performance. São mostrados application errors, timeouts, navigation errors, amostras inválidas/excluídas, fração Tolerating/Frustrated, variabilidade e cauda. Core Web Vitals/Lighthouse aparecem como correlação separada e não entram na fórmula Apdex.

O relatório apresenta análise de sensibilidade em torno do `T` configurado (`T ±10%/20%`) usando as mesmas amostras. Essa tabela é apenas diagnóstico metodológico: não deve ser usada para escolher threshold que produza a nota desejada. `T` deve representar SLO/KPM ou configuração comparável do APM.

## Diagnósticos de console/browser por amostra

Synthetic Navigation Apdex persiste, de forma limitada e sem response bodies, `console.error`, `pageerror` e `requestfailed` observados durante cada navegação. O HTML lista e agrupa esses eventos. A associação é temporal e diagnóstica: um console error não é automaticamente a causa da duração e não reduz Apdex por si só.

## Coeficiente de variação e estabilidade

```text
CV (%) = desvio padrão das durações / média das durações × 100
```

O CV mede dispersão relativa das navegações sintéticas. Valor menor indica maior consistência no mesmo perfil/origem/alvo; valor maior indica maior oscilação. O CV não identifica sozinho a causa e um CV baixo não significa página rápida.

A UI pode marcar CV elevado como **sinal de atenção do RASAi**. Esse destaque é heurística interna de apresentação, não threshold universal do Apdex nem norma estatística externa. O CV não entra na fórmula do Apdex.

Uma futura execução distribuída por regiões deve separar estabilidade intrarregional de dispersão entre regiões.

## Referências e direitos autorais

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

A fórmula e a nomenclatura Apdex são baseadas na especificação pública do Apdex. Este arquivo não reproduz integralmente a especificação externa.

- Apdex Technical Specification v1.1: <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>
- Chrome DevTools Protocol - Emulation: <https://chromedevtools.github.io/devtools-protocol/tot/Emulation/>
- Chrome DevTools Protocol - Network: <https://chromedevtools.github.io/devtools-protocol/tot/Network/>