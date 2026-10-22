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
canônica permanecem distintos, sem recalcular SCORE-GEO-004.

## Limites de aceite

- Sem fonte externa da mesma AUD/scope, não inventar severidade de medicoes de desempenho externas,
  CrUX, SERP, Apdex nem efeitos reais em buscas/IA.
- O aviso não altera notas, gates, coortes, AUD, coletores ou resultados.
- Testes são offline; sem browser, rede, APIs pagas ou reprocessamento.
- A #600 segue sujeita aos requisitos integrais de #601/#602 e aceite
  visual previsto no seu escopo.

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
