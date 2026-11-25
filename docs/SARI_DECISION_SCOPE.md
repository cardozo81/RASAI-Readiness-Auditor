# Limites decisórios do SARI

## Escopo do contrato

O número 0 - 100, a cobertura (percentual com fração canônica), a confiança
contratual e os critical readiness gates descrevem o universo de regras
avaliado. Não são garantia de experiência real, cobertura de uma população
estatística, ranking orgânico ou citação generativa.

## Convergência não garantida  -  #600

O aviso `data-sari-nonconvergence` é exibido nas superfícies SARI
(executiva, visão de dispositivo e painel operacional). Mesmo quando o
SARI possui uma nota elevada e confiança HIGH, Lighthouse de laboratório,
CrUX de campo (ORIGIN/URL), Apdex sintético, cobertura SERP e serviços
generativos mantêm contratos e evidências próprios. A mensagem não
pressupõe que essas medições foram executadas ou tiveram resultado ruim.

Exemplo motivador: Overall 86,484962; coverage=0,974737; confidence=HIGH
coexiste com CONTENT_VALUE coverage=0,7/LOW/PARTIAL. Percentuais e fração
canônica permanecem distintos, sem recalcular a nota original. Este é um exemplo histórico; o método vigente de novas AUDs é `SCORE-GEO-005`, com `SCORE-GEO-004` preservado para replay.

O detalhamento técnico do índice e de seus limites está em `report-catalog/sari.html` e `methodology.html`; a síntese executiva está em `report-presentation/indices.html` e `index.html`. Não se presume réplica do aviso nem de cada campo. Consulte [guia de relatórios](REPORT_GUIDE.md).

## Limites de aceite

- Sem fonte externa da mesma AUD/scope, não inventar severidade de medicoes de desempenho externas,
  CrUX, SERP, Apdex nem efeitos reais em buscas/IA.
- O aviso não altera notas, gates, coortes, AUD, coletores ou resultados.
- Testes são offline; sem browser, rede, APIs pagas ou reprocessamento.
- As issues [#600](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/600), [#601](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/601) e [#602](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/602) foram encerradas como concluídas. O encerramento não prova convergência entre métricas externas nem certifica toda AUD futura.

## Origem da população nos resumos web (#600)

A tabela reduzida de métricas de Web Performance discrimina os percentis
CrUX de campo da execução Lighthouse de laboratório. Quando o registro
persistido informa `field_scope=ORIGIN`, exibe explicitamente que os
percentis e o resultado CWV se referem à **origem agregada**, não à URL
específica. Para `field_scope=URL`, identifica a URL observada pela
fonte. Sem escopo verificável, usa **escopo não verificado** e não
atribui indicadores à URL por inferência. A mesma tabela rotula scores e
marcos lab como execução pontual. Não altera dados brutos, scores SARI,
origens de amostragem, classificação CrUX nem coleta módulo de observabilidade.
