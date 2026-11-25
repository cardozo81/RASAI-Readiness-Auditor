# Procedimento de revisão editorial por família de evidências

> **Estado:** referência de qualidade para futuras entregas. A [decisão formal de 25/11/2026](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/722#issuecomment-7159540850) encerrou administrativamente a demanda histórica #722 por descontinuação do escopo residual, sem certificar completude integral. Não reabrir a investigação antiga apenas porque permanecem fontes sem evidência específica. Avaliar defeitos materiais novos com evidências próprias.

## Finalidade e escopo

Este procedimento transforma o inventário **já existente** de `report-presentation/anexos/dados-de-apoio/editorial-review.json` em uma avaliação editorial **rastreável**, sem promover automaticamente uma classificação de código a uma aprovação humana. A fonte de verdade continua sendo `audit.db` e seus artefatos; `report-presentation` e `report-catalog` mantêm representações independentes. Não executar IA, Search, coleta, scoring, reprocessamento ou escrita na AUD para preencher lacunas visuais.

O exemplo de homologação AUD-594E99EA879F4DDDB15EEA93F9A0E918 registrou **102 famílias** (95 com linhas) e **61 tópicos técnicos**, segundo o histórico da issue. Esses números são históricos, **não são constantes de aceitação de uma nova AUD**. Inventariar 100% das famílias efetivamente presentes em cada AUD, inclusive as vazias, e todas as entradas de `technical_only_topics`.

## Preparação: reconciliar antes de decidir

Para cada família de `families` no recibo, verificar na **cópia isolada** da AUD: `family`, `row_count`, `status_field_observations`, `rows_without_recorded_status`, `page`, `href`, `annex`, `materialization`, `analytical_direct_fields`, `existing_contextual_renderer`, `classification`, `decision_relevance` e `rationale`. Confrontar quantidades e campos com SQLite/sidecars correspondentes, as onze páginas de HTML e os anexos endereçados por conteúdo. Preservar hashes e identificadores. Usar `absent_or_unexecuted_topics` e `sidecar_projections` separadamente: ausência de tabela, fonte vazia, etapa não executada e indisponibilidade de sidecar não são equivalentes.

`PRESENT_SUMMARIZED`, `PRESENT_FIELD_PROJECTION`, `PRESENT_CONTEXTUAL` e `PRESENT_TECHNICAL_ONLY` descrevem **representações**, não decisões aceitas. `POLICY_REVIEW_REQUIRED` exige análise explícita, não descarte. Não contar uma tabela técnica, um link ou uma síntese genérica como prova de suficiência executiva. `open_decision_gaps` é fila inicial, **não universo exaustivo**: também revisar famílias com projeção já presente.

## Decisão obrigatória por família (A/B/C/D)

| Decisão | Critério demonstrável | Destino da revisão |
| --- | --- | --- |
| **A - Técnica deliberada** | Informação existe, tem finalidade de proveniência, diagnóstico ou rastreabilidade, e a decisão do usuário já é atendida por síntese específica quando necessária | Manter no anexo/detalhe técnico, justificando por que uma nova visualização **não** acrescenta decisão relevante; verificar link acessível |
| **B - Ausente/não executada** | A fonte e o contrato de execução comprovam ausência, não solicitação ou não execução; `row_count=0` isoladamente **não** comprova esse estado | Comunicar N/D ou estado real com limitação; não fabricar taxa, zero, falha ou gráfico |
| **C - Projeção analítica necessária** | Há campos/valores persistidos pertinentes à decisão, mas a apresentação não permite comparar, segmentar ou entender denominador, moeda, tempo ou escopo | Especificar campos exatos, tabela/sidecar e uma visualização analítica mínima usando componentes existentes |
| **D - Síntese executiva necessária** | Uma pergunta decisória material permanece sem resposta contextualizada, apesar de evidência suficiente ou de limitação relevante registrada | Especificar pergunta, resposta suportada, ressalvas, proveniência e posição entre as onze páginas; não converter observação em recomendação aprovada |

Se a evidência não permitir escolher A/B/C/D, marcar **PENDENTE - evidência insuficiente**, registrar exatamente o que falta e **não** contabilizar a família como aceita. A decisão é editorial, não produz alteração de `classification` no recibo original nem modifica `human_editorial_acceptance=PENDING` ou `certifies_editorial_completeness=false`.

## Registro privado e aprovação

Para cada família, manter na pasta **privada** de homologação um registro com: identificador da AUD/cópia e SHA do banco; família e contagem; estado de execução; página e âncora atuais; evidência concreta (tabela/campo/registro/sidecar e versão do gerador); decisão A/B/C/D ou PENDENTE; pergunta do usuário; ganho informacional e risco de apresentação; solução mínima para C/D; resultado dos testes de paridade; resultado da inspeção humana; e situação `PENDING`/`ACCEPTED`/`REJECTED`. Anotar cada ocorrência `PRESENT_TECHNICAL_ONLY` por página e família, mesmo quando uma família aparece em mais de uma superfície.

A triagem deve priorizar Painel, IA/custos, Busca e visibilidade em IA, Plano de Ação, Segurança e reprocessamentos, mas **sem excluir as demais**. Separar custo previsto, estimativa por tentativa, telemetria observada e cobrança efetiva; separar decisões de governança aceitas/rejeitadas; preservar cobertura, confiança e status de execução sem extrapolar.

Antes de propor código, exigir lacuna C/D **com materialidade e fonte demonstradas**. Implementar em branch própria somente a projeção derivada necessária; conferir contagens e campos, estados N/D, URLs/âncoras/anexos, autonomia dos relatórios e ausência de nova coleta. Testar somente o código alterado; o classificador de risco de CI pode acionar suíte integral automaticamente caso a mudança esteja fora da allowlist leve. Não disparar workflows manuais apenas por rotina.

## Gate de encerramento da #722

**Registro histórico do critério original, não pendência atual.** O critério de certificação integral exigia: (1) cada família da AUD homologada tem decisão explícita ou justificativa verificável; (2) cada tópico técnico recebeu revisão, inclusive duplicações legítimas em páginas diferentes; (3) nenhuma lacuna C/D material permanece sem solução ou ressalva aprovada; (4) reconciliação física e paridade dos onze HTMLs, links, anexos e hashes passam; (5) inspeção offline em 390/1440/2560 px e aceite humano/visual estão registrados; (6) CI no SHA final está verde. Não confundir cobertura das fontes com completude decisória. O critério original não foi integralmente cumprido; a issue foi encerrada por decisão formal de governança, não por aprovação integral. As 100/102 famílias aceitas, 61/61 ocorrências técnicas e 11/11 páginas homologadas visualmente permanecem como resultados históricos. As duas famílias sem comprovação específica mantêm PENDENTE e N/D com limitação, assim como os indicadores históricos `human_editorial_acceptance=PENDING` e `certifies_editorial_completeness=false`. Para futuras revisões, use os critérios como referência de qualidade proporcional ao escopo e não como obrigação de repetir o aceite histórico.

Os documentos e testes já existentes são a referência técnica: [contrato da apresentação](../src/rasai/parallel_report/README.md), [guia de aceitação de apresentação](PRESENTATION_EDITORIAL_ACCEPTANCE.md), [teste da triagem](../tests/report_presentation/test_editorial_review.py) e [aceite físico isolado](../scripts/presentation_acceptance.py).

Dados privados, URLs auditadas, arquivos SQLite, logs, evidências e capturas devem permanecer fora de issues/PRs públicas. Apenas decisões metodológicas, códigos e resultados agregados sanitizados podem ser registrados no GitHub.
