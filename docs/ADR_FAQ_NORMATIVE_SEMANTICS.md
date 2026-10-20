# ADR-FAQ-001 - fronteira observacional e escolha normativa BR-GEO-039/049

**Estado:** PROPOSTA CONSERVADORA - DECISÃO HUMANA DE MÉTODO PENDENTE.
**Origem:** issue #651 (sucessora normativa de #601).
**Escopo:** preservar a distinção entre observação de DOM e avaliação
determinística sem promover comportamento de crawler ou reescrever AUD.
**Importante:** este documento **não** aprova mudança de pontuação nem
substitui a deliberação específica do operador solicitada na issue.

## Estados observacionais distintos de decisão de regra

| Observação material | Evidência permitida | Inferência proibida |
| --- | --- | --- |
| FAQ e resposta visíveis no DOM inicial | Texto e controle acessíveis sem interação | Indexação ou conformidade universal |
| Controle recolhido com texto ainda no DOM | Disponibilidade do texto no DOM renderizado | Prova de descobribilidade crawler |
| Controle recolhido, painel não montado | Resposta não observada na captura inicial | Inexistência editorial ou falha automática |
| Controle expandido sem texto recuperável | Resposta não demonstrada naquela captura | Ausência definitiva da resposta publicada |
| Controle ambíguo, ID duplicado, snapshot incompleto | UNKNOWN observacional e abstenção | Ausência editorial, sucesso ou FAIL |
| Conteúdo surge após gesto físico autorizado | Disponibilidade humana após clique naquela amostra | Evidência de que crawler clica/obtém resposta |
| Inexistência editorial alegada sem prova independente | NOT_VERIFIED no parecer consultivo | FAIL regulatório/editorial por ausência no DOM |
| Fonte editorial independente e exaustiva que prova ausência | Elegível a parecer separado com proveniência | Reclassificação retroativa automática de scoring |

### Opções normativas abertas à aprovação humana

**A - Preservar status/fator/weight atuais (recomendação conservadora).**
Manter sem alteração a interpretação de resultados determinísticos
`BR-GEO-039` e `BR-GEO-049` no contrato vigente SCORE-GEO-005.
Observações sem prova suficiente continuam consultivas como
`UNKNOWN`/`NOT_VERIFIED` na **camada de evidência**, sem serem
automaticamente transformadas em novos resultados de regra.
`WARNING` persistido continua com o fator canônico da regra.
Não recalcular, migrar, reabrir ou reclassificar AUD anterior.
Não há nova versão numérica de score por decisão sem alteração.

**B - Nova abstenção normativa em vez de WARNING.**
Exigiria nova versão de método e regra por condição, com
normalização de peso, Coverage/Confidence, readiness gates e SARI,
migração não destrutiva, golden/parity para múltiplas AUDs.
Uma classe de observação UNKNOWN não pode ser equiparada
automaticamente a `RuleResult.UNKNOWN` de novo motor.

**C - Alterar fatores/pesos, condições ou FAIL/PASS.**
Exigiria calibração, fonte da definição de resposta editorial,
análise antes/depois de score por dimensão e Overall,
regressões, versão nova, regra de histórico e aceite humano expresso.

### Recomendação e critério de saída

A alternativa **A** evita transformar ausência em uma constatação
editorial sem prova e preserva compatibilidade do score. Ela apenas
confirma a fronteira observacional em vigor nas funções
`faq_observation`, `faq_transition_policy` e
`faq_aud_receipt_binding`. Um HMAC de recibo ou DOM posterior
não prova que a pessoa interagiu na mesma amostra original;
a homologação física dessa condição permanece na #652.

**Para aprovar esta ADR:** o responsável deve decidir especificamente
qual alternativa A/B/C prevalece e, se B/C, indicar política exata de
status/fator/peso/versão e gates de compatibilidade. Aprovação genérica
para implementar backlog não escolhe resultados metodológicos.
A issue #651 **permanece aberta** até tal deliberação e evidência
suficiente. A #601 observacional já encerrada não é reaberta.

**Limite:** nenhum teste ou novo classificador normativo foi executado
por esta proposta; o arquivo é apenas a preparação da decisão.
