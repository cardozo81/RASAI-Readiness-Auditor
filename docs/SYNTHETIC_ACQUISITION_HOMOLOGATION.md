# Homologação do Synthetic Acquisition Engine - #207

## Escopo

Este documento registra o gate automatizado de paridade e carga exigido antes da retirada do runtime de compatibilidade em #208.

A homologação compara o caminho isolado e o caminho canônico usando **os mesmos fatos brutos**. Isso isola o efeito da estratégia de aquisição: qualquer diferença de score/classificação nessa comparação seria introduzida pela infraestrutura, não pela variabilidade da rede.

Não é usado benchmark de latência de Internet como critério de aprovação. Latência externa é não determinística e não demonstra ausência de bias. A carga é medida por:

- aquisições físicas necessárias;
- redução de aquisições contra execução isolada;
- waves normalizadas sob concorrência 1 e 4;
- preservação integral da população lógica dos evaluators.

## Contrato físico homologado

```text
FULL_EXPERIENCE = N_EXPERIENCE
LOAD_ONLY = max(N_NAVIGATION - N_EXPERIENCE, 0)
TOTAL_PHYSICAL = max(N_NAVIGATION, N_EXPERIENCE)
```

Quando Navigation exige menos observações que Experience, os ordinais Navigation são distribuídos deterministicamente por toda a população FULL. A seleção usa ordinal de planejamento anterior ao start, portanto completion order concorrente não altera a amostra.

## Benchmark de carga

| NAV | EXP | Isolado: aquisições | Canônico: aquisições | Redução física | Waves isoladas (c=4) | Waves canônicas (c=4) | Redução de waves |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 1000 | 1050 | 1000 | 4,76% | 263 | 250 | 4,94% |
| 100 | 100 | 200 | 100 | 50,00% | 50 | 25 | 50,00% |
| 150 | 100 | 250 | 150 | 40,00% | 63 | 38 | 39,68% |
| 1000 | 50 | 1050 | 1000 | 4,76% | 263 | 250 | 4,94% |

CAT-06 somente mantém `TOTAL_PHYSICAL=N_NAVIGATION`; CAT-07 somente mantém `TOTAL_PHYSICAL=N_EXPERIENCE`. O planner não cria ganho artificial quando não existe população compatível para compartilhar.

## Paridade CAT-06

O harness entrega a mesma sequência de `load_duration_ms` ao classifier/summarizer canônico do CAT-06 nos caminhos baseline e canônico.

São comparados diretamente:

- valid/invalid;
- Satisfied/Tolerating/Frustrated;
- sucesso/timeout/navigation error;
- Apdex;
- mean/median;
- stddev;
- coefficient of variation;
- p95.

Para o cenário NAV=50/EXP=1000, também é verificado que:

- o primeiro ordinal é 0;
- o último ordinal é 999;
- existem 50 ordinais únicos;
- a média da amostra distribuída não desvia materialmente da população controlada.

## Paridade CAT-07

O harness reconstrói 100 ocorrências FULL com KPM e observáveis pós-load e passa baseline/replay pelo mesmo `classify_measurement` e `_summary`.

São comparados diretamente:

- valid/invalid;
- Satisfied/Tolerating/Frustrated;
- error-forced frustrated;
- Apdex;
- mean/median/p95;
- JavaScript error samples;
- request error samples;
- network unsettled samples;
- KPM por ocorrência;
- XHR/fetch-related facts;
- `network_settled`.

Fragmentos sem perfil aplicado continuam inválidos; o caminho canônico não os promove.

## Device e concorrência

O workload é validado para Mobile e Desktop. O planner é device-neutral, mas não cruza populações entre devices.

Concorrência 1 e 4 são exercitadas no workload normalizado. A seleção Navigation é ligada ao ordinal de planejamento, não à ordem de conclusão, então concorrência não muda a população lógica escolhida.

## Conclusão do gate

A aprovação de #207 exige o workflow dedicado integralmente verde junto com os gates existentes de Apdex, reprocessamento e SCORE-GEO.

Critério de aprovação:

1. paridade estatística exata quando baseline/canônico recebem os mesmos fatos;
2. nenhuma promoção de evidência inválida;
3. nenhuma redução de target lógico;
4. `TOTAL_PHYSICAL=max(N_NAVIGATION,N_EXPERIENCE)` nos cenários combinados;
5. execução individual de CAT-06/CAT-07 preservada;
6. nenhuma alteração em SARI/SCORE-GEO;
7. nenhuma alteração no motor/orquestração de IA.

Somente após esse gate #208 pode substituir/remover o runtime de compatibilidade.
