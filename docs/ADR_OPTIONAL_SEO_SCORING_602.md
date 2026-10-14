# ADR - sinais SEO opcionais, evidências e efeito no SCORE-GEO (#602)

Status: **avaliação metodológica aberta; nenhum novo contrato de pontuação aprovado neste documento**.

## Evidência física de 14/10/2026

AUD `AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF` (uma URL, móvel). O SCORE-GEO-004 atribui as contribuições seguintes em sua respectiva dimensão:

| Regra | Resultado fonte | Weight × fator | Desconto isolado na dimensão |
| --- | --- | --- | ---: |
| BR-GEO-003 | Consulta de sitemap convencional ausente | 0,0485 × 0,8 | 0,97 ponto |
| BR-GEO-017 | robots.txt ausente | 0,1455 × 0,6 | 5,82 pontos |
| BR-GEO-013 | canonical não declarada | 0,30 × 0,5 | 15,00 pontos |

**O desconto isolado não é um novo SARI.** Se uma regra tornar-se N/A, o contrato poderá alterar denominadores, coverage/confidence e normalização; somar diretamente os descontos não equivale a recalcular o índice.

## Limite de padrões públicos

- robots.txt é opcional: https://developers.google.com/search/docs/crawling-indexing/robots/intro
- Google pode selecionar canonical mesmo sem declaração explícita: https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
- sitemap opcional em determinadas condições e pode existir fora de /sitemap.xml: https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview

Essas referências **não proíbem** atribuir mérito a práticas opcionais em um índice privado. Elas, porém, não autorizam classificar ausência isolada como bloqueio ou problema comprovado de indexação. A política deve separar maturidade opcional de falha observada.

## Contrato proposto para avaliação antes de implementar

- `OPTIONAL_ABSENCE`: sem defeito causal/obrigação demonstrada. Apresentar oportunidade contextual sem diagnóstico taxativo de falha. Investigar tratamento da cobertura/normalização e presença de outros sinais.
- `OBSERVED_CONFLICT`: canonical conflitante/duplicação material, robots que efetivamente bloqueia crawler solicitado, sitemap publicado inválido ou outra falha com prova. Manter penalização proporcionada à evidência.
- `NOT_OBSERVED` / `UNKNOWN`: recusar inferir ausência quando consulta falhou ou escopo da busca é incompleto. Não converter falha do provedor em falha do website.
- `NOT_APPLICABLE`: critérios comprovadamente inaplicáveis podem sair do universo medido **conforme contrato versionado**, não por ocultação na UI.

Para uma nova versão SCORE-GEO, antes de alterar pesos/avaliação:

1. Delimitar o indicador (maturidade de configuração ou risco de indexabilidade) e escolher o tratamento normativo com referência e fundamentação.
2. Provar em fixtures: robots ausente/válido/bloqueante, sitemap alternativo/invalidado, canonical ausente/duplicada/conflitante, datasource sem prova, RPR/paridade e auditorias históricas.
3. Calcular o impacto em valor por dimensão, peso normalizado, cobertura, confiança, readiness gates e SARI global, sem declarar nova versão equivalente à anterior.
4. Versionar regras e critérios, atualizar documentação, manter resultados de AUDs existentes sob SCORE-GEO-004.
5. Submeter a CI focal Linux/Windows e somente os gates externos necessários.

## Entrega executável parcial

O módulo `rasai.optional_seo_interpretation_602` compara somente os registros físicos `rule_executions` e `score_contributions` da mesma AUD e expõe, na visão executiva, descontos **já persistidos** para ausência isolada comprovada; nunca estima um novo score, reescreve dados, lê configuração do operador ou efetua rede.

Esse passo corrige o risco de **interpretação** enquanto a mudança de política de pontuação permanece aberta para decisão versionada.
