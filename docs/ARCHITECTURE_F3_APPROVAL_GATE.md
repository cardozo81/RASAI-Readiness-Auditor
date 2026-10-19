# RASAi - Gate de aprovação metodológica F3 (proposta, não aprovada)

**Estado: PROPOSED / BLOCKED-HUMAN.** Issue #646, branch `feat/acceptance-and-architecture-governance`.

## Contratos existentes que NÃO exigem ADR de alteração de método
A leitura M6/F1 é consultiva e a resolução F2 pode produzir recomendações
descritivas nos consumidores explicitamente elegíveis
(`descriptive_report` e `m6_read_only_diagnostic`). Identidade URL,
device, página e snapshot devem coincidir. Em caso de dúvida, abster-se.
O modo DECLARED não pode se apresentar como observação física.

## Mudanças F3 que exigem decisão expressa
Nenhuma descoberta automática ou declaração pode recalibrar silenciosamente
SARI, SCORE-GEO, Apdex, M23/M25, coortes, métricas, thresholds ou coleta
de uma AUD já iniciada. Qualquer consumidor proposto para essas superfícies
requer **uma ADR própria** contendo:

- ID do consumidor, owner, risco de regressão e aplicabilidade por fase.
- Proveniência independente de evidência e regra de resolução para LEGACY/UNKNOWN.
- Fórmulas e parâmetro antes/depois, golden/parity e versionamento de método.
- Migração não destrutiva de auditorias antigas e estratégia de rollback.
- Aprovação explícita do responsável metodológico antes de ligar a feature gate.

## Decisão necessária
Escolher consumidores específicos a autorizar, designar responsável e
aprovar uma ADR individual após apresentação das provas. Até isso ocorrer:
**F3 permanece inativa**. Nenhum estado `PASS` de CI concede autorização
metodológica. Tampouco hashes embutidos no mesmo SQLite constituem atestação
externa independente. Esta proposta não altera scores ou AUDs seladas.

## Fechamento da #646
Os gates F1/F2 e compatibilidade devem estar verdes no HEAD final.
Atestação criptográfica independente exige uma âncora de confiança separada,
controle e rotação de chaves/versionamento; não inserir credenciais no INI,
HTML, repositório ou evidência. A questão de qual agente/autoridade assina
a evidência requer aprovação de governança antes de ser tratada como prova.
