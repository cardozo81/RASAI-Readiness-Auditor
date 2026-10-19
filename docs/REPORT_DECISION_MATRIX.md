# Matriz decisória de evidências da AUD

**Contrato consultivo:** RASAI-DECISION-EVIDENCE-604-001.
**Issues:** #604, #600, #319, #304, #601, #602, #603.

## Superfícies e indicadores

A visão geral index.html recebe a seção Matriz decisória de evidências; sari.html recebe a seção Universo medido e limites de comparação, com link para a visão geral. O leitor não recalcula o índice e não agrega métricas de universos diferentes.

| Indicador | Fonte | Limitação |
| --- | --- | --- |
| SARI por dispositivo | scores.OVERALL_READINESS | Nota do método, cobertura e readiness; não certifica ranking ou experiência. |
| Cobertura por dimensão | scores.coverage | Confiança agregada não apaga cobertura não integral. |
| Lighthouse Performance | web_performance_observations.performance_score | Laboratório em escala 0-100; não CrUX. |
| CrUX LCP/INP/CLS | web_performance_observations | ORIGIN agrega uma origem; URL significa página específica. |
| CAT-06/CAT-07 | Status do catálogo persistido | Conclusão operacional não comprova representatividade das amostras Apdex. |
| SERP | Uma observação identificável da AUD | Retorno versus requested_depth não é participação de mercado. |
| Sinais SEO opcionais | score_contributions + rule_executions | Descontos do SCORE-GEO-004 já persistidos; não são aplicados novamente. |
| Alegações comerciais | Fronteira do CAT-03 | Esta matriz não autentica condições gerais ou registro regulatório. |
| Presença generativa | Limitação de escopo | SERP e Search API não comprovam citação gerativa ou share. |

## CLI somente leitura para o smoke consolidado

```bash
python -m rasai.report_decision_matrix_cli /caminho/AUD-ID
```

A CLI emite apenas JSON no stdout: saída 0 quando a matriz é montada e 2 quando a origem não é verificável. Exige pasta AUD-*, audit.db físico regular, sem symlink ou WAL/SHM/journal pendente. SQLite é aberto em mode=ro&immutable=1 e query_only=ON, sem escrita. Os sensores físicos de SERP e SEO são projetados pelos leitores existentes de relatório, preservando abstenção individual quando não há identidade completa.

Nenhum browser, IA, Search API, PageSpeed, reprocessamento, custo adicional ou escrita no histórico é acionado. A matriz não constitui nova pontuação, não substitui inspeção visual dos HTMLs nem autentica recibos jurídicos de fonte externa.

## Aceite contextual

Na AUD de referência do dia 14/10/2026, conferir o score SARI e sua cobertura, Lighthouse separado de CrUX ORIGIN, estado de catálogos parciais, profundidade SERP realmente observada, descontos SEO opcionais e limitações explícitas de prova documental/generativa.

Essa verificação não fecha automaticamente #601 (clique físico same-sample), #602 (decisão normativa sobre scoring), #603 (fonte primária vigente), nem o épico #604.
