# Synthetic Navigation Apdex

Guia operacional do Synthetic Navigation Apdex do RASAi.

> A funcionalidade é **default OFF**. Ela não altera `SARI-001`, findings GEO, Coverage ou Confidence. O índice mede uma Task sintética de navegação e não deve ser confundido com RUM/APM de usuários reais.

## Fórmula

```text
Apdex = (Satisfied + 0.5 × Tolerating) / Total de amostras válidas

Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T
```

`T` é configurado explicitamente pelo usuário.

## Task medida

Cada amostra executa uma navegação real em Chromium até o evento de load previsto pela implementação, usando perfil sintético controlado, BrowserContext novo e cache desabilitado.

Uma amostra pode ser:

- `SATISFIED`;
- `TOLERATING`;
- `FRUSTRATED`;
- inválida/excluída quando a ferramenta/profile não conseguiu produzir uma medição válida.

Timeout ou erro de navegação/aplicação conta como Frustrated quando o profile foi efetivamente aplicado e a amostra é observável como execução válida.

## Grupos

Default normal:

```text
100 amostras válidas por URL/device
```

Grupos entre 1 e 99 amostras válidas são diagnóstico small-group e recebem marcador `*`. O objetivo é impedir que um smoke curto pareça uma baseline final.


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

## Console interativo

Item:

```text
11. Synthetic Apdex
```

O console explica a finalidade de cada valor antes da entrada e mostra a carga máxima projetada em quantidade de navegações iniciadas.

O timeout de Apdex é independente do timeout de IA e do timeout PageSpeed/Lighthouse.

## Carga operacional

Synthetic Apdex não possui API paga própria e não chama LLM/PageSpeed/CrUX, mas gera:

- CPU/tempo local;
- Chromium;
- tráfego HTTP real contra a URL alvo;
- múltiplos requests de subrecursos por navegação.

Não interprete `100 amostras` como `100 requests HTTP`. Cada navegação pode carregar muitos recursos.

Para smoke, prefira 1 URL, 1 device, 3-5 amostras, concorrência 1 e alvo controlado. Não execute volume relevante contra produção sem autorização.

## Persistência

Dados são persistidos em tabelas dedicadas e o relatório é materializado em:

```text
report/apdex.html
```

Os identificadores internos históricos de tabela/evento podem permanecer por compatibilidade de schema; a UI e a documentação operacional usam nomenclatura funcional.

## Relação com Lighthouse e CrUX

Apdex não é inferido de:

```text
LCP
INP
CLS
FCP
TBT
Speed Index
duração da chamada PageSpeed
```

Lighthouse/CrUX e Synthetic Apdex medem fenômenos distintos e permanecem em páginas separadas do report.

## Rastreamento de Lighthouse

Quando um artifact Lighthouse existe, o RASAi pode extrair metadados de perfil para rastreabilidade. Ausência do artifact não invalida as navegações Synthetic Apdex; apenas impede essa comparação documental.

## Segurança metodológica

- falha de ferramenta fica fora do denominador quando não há amostra válida;
- erro observável da aplicação/navegação não é mascarado como falha da ferramenta;
- grupo pequeno é marcado explicitamente;
- nenhum resultado é adicionado matematicamente ao Score GEO;
- não há promessa de experiência real de usuários finais.

<!-- rasai-apdex-diagnostics-sensitivity-20260908 -->
## Diagnóstico de erros e sensibilidade ao T

`apdex.html` separa problemas da própria execução Synthetic Navigation Apdex de sinais relacionados de Web Performance. São mostrados application errors, timeouts, navigation errors, amostras inválidas/excluídas, fração Tolerating/Frustrated, variabilidade e cauda. Core Web Vitals/Lighthouse aparecem como correlação separada e não são duplicados nem entram na fórmula Apdex.

O relatório também apresenta uma análise de sensibilidade em torno do `T` configurado (`T ±10%/20%`) usando as mesmas amostras. Essa tabela é somente diagnóstico metodológico: não deve ser usada para escolher um threshold que produza a nota desejada. O `T` deve representar SLO/KPM ou a configuração comparável do APM/Dynatrace.

## Console/browser diagnostics por amostra

Synthetic Navigation Apdex persiste, de forma limitada e sem response bodies, `console.error`, `pageerror` e `requestfailed` observados durante cada navegação. O HTML lista esses eventos por amostra e também os agrupa para o teste completo por tipo/mensagem/recurso e quantidade de amostras afetadas. Essa associação é temporal e diagnóstica: um console error não é tratado automaticamente como causa da duração e não reduz o Apdex por si só. Somente application error, timeout e navigation error continuam alterando a classificação Apdex.

<!-- rasai-apdex-cv-20260908 -->
## Coeficiente de variação e estabilidade das amostras

O relatório apresenta o **coeficiente de variação (CV)** das durações válidas:

```text
CV (%) = desvio padrão das durações / média das durações × 100
```

O CV mede a dispersão relativa das navegações sintéticas. Em um mesmo perfil, origem e alvo, valor menor indica tempos mais consistentes; valor maior indica maior oscilação. Ele pode refletir, em conjunto, máquina executora, rede local, rota, DNS/TCP/TLS, CDN, servidor, terceiros e comportamento da própria aplicação. O CV **não identifica sozinho a causa** e um CV baixo não significa página rápida: uma página pode ser lenta e estável.

A UI pode marcar CV elevado como **sinal de atenção do RASAi**. Esse destaque é heurística de apresentação, não limiar universal do Apdex nem norma estatística externa. O CV não entra na fórmula do Apdex. Para diagnóstico, deve ser lido junto com média/mediana, percentis/cauda, erros, perfil, `T` e quantidade de amostras.

Uma futura execução distribuída por regiões não deve misturar indiscriminadamente todas as origens em um único CV: estabilidade **intrarregional** e dispersão **entre regiões** respondem perguntas diferentes e devem permanecer separadas.
