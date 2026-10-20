# ADR-FAQ-001 - fronteira observacional e escolha normativa BR-GEO-039/049

**Estado:** APROVADA - OPÇÃO A, preservação normativa (20/10/2026).
**Aceite formal:** operador aprovou expressamente `#651 seguir com a recomendação da opção A.`
**Versão da decisão:** `ADR-FAQ-001 v1`; método vigente `SCORE-GEO-005` não muda.
**Origem:** issue #651 (sucessora normativa de #601).
**Escopo:** preservar a distinção entre observação de DOM e avaliação
determinística sem promover comportamento de crawler ou reescrever AUD.
**Decisão vinculante:** não alterar pontuação, histórico, pesos, fatores, estados de regra ou consumidores. Não representa homologação física de clique.

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

### Alternativas deliberadas

**A - APROVADA: preservar status/fator/weight atuais.**
Manter sem alteração a interpretação de resultados determinísticos
`BR-GEO-039` e `BR-GEO-049` no contrato vigente SCORE-GEO-005.
Observações sem prova suficiente continuam consultivas como
`UNKNOWN`/`NOT_VERIFIED` na **camada de evidência**, sem serem
automaticamente transformadas em novos resultados de regra.
`WARNING` persistido continua com o fator canônico da regra.
Não recalcular, migrar, reabrir ou reclassificar AUD anterior.
Não há nova versão numérica de score por decisão sem alteração.

**B - NÃO ADOTADA: nova abstenção normativa em vez de WARNING.**
Exigiria nova versão de método e regra por condição, com
normalização de peso, Coverage/Confidence, readiness gates e SARI,
migração não destrutiva, golden/parity para múltiplas AUDs.
Uma classe de observação UNKNOWN não pode ser equiparada
automaticamente a `RuleResult.UNKNOWN` de novo motor.

**C - NÃO ADOTADA: alterar fatores/pesos, condições ou FAIL/PASS.**
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

### Efeito normativo e critérios de saída

A autorização formal escolheu **A**. Para BR-GEO-039/049 permanecem os
status já produzidos por regras determinísticas: `WARNING` recebe
`warning_factor=0.50`; `UNKNOWN` e `ERROR` de **RuleResult** seguem
não avaliados no denominador medido e afetam Coverage conforme contrato.
`UNKNOWN`/`NOT_VERIFIED` como evidência de FAQ são **observacionais**,
sem conversão automática em resultado de regra, PASS, FAIL ou WARNING.
DOM posterior a clique não prova indexação, e DOM sem resposta inicial
não prova ausência editorial.

Esta aprovação **não constitui alteração de método**: versão SCORE-GEO-005
mantida, sem recalibração de scores, migração ou replay; SCORE-GEO-004
histórico permanece reproduzível. Teste de paridade de regra WARNING,
Coverage e pontuação da mesma entrada sem opções SEO alteradas em
`tests/test_score_geo_v005_optional_seo.py` é gate focal; a CI do
commit correspondente precisa ser comprovada antes de encerrar #651.
Evidência real de clique no mesmo browser da AUD continua exigência
**independente da #652**.

Como nenhuma regra ou fator mudou, versão nova de scoring, golden de
pontuação alterada e migração de AUD são **não aplicáveis** por decisão
explícita; não afirmar que foram implementados. Qualquer mudança futura
exige ADR, versão de scorer, golden e consentimento próprios.
