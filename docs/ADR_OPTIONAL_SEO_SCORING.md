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

O módulo `rasai.optional_seo_interpretation` compara somente os registros físicos `rule_executions` e `score_contributions` da mesma AUD e expõe, na visão executiva, descontos **já persistidos** para ausência isolada comprovada; nunca estima um novo score, reescreve dados, lê configuração do operador ou efetua rede.

Esse passo corrige o risco de **interpretação** enquanto a mudança de política de pontuação permanece aberta para decisão versionada.


## Progresso de implementação - classificação de evidência (14/10/2026)

O módulo `rasai.optional_seo_policy.classify_seo_evidence` materializa os quatro estados **exclusivamente interpretativos** `OPTIONAL_ABSENCE`, `OBSERVED_CONFLICT`, `AVAILABLE`, `UNKNOWN` para os `observed_value` físicos de BR-GEO-003, BR-GEO-013 e BR-GEO-017. JSON com chaves repetidas, literais não padrão, erro de rede, tipo desconhecido ou prova parcial gera `UNKNOWN` - não sinal de ausência comprovada. Sitemap inválido e canonical conflitante são distinguíveis de ausência convencional. Um `robots.txt` presente não comprova permissão de bots, que segue regra independente BR-GEO-018.

A projeção de descontos opcionais reutiliza esse classificador, evitando aceitar JSON ambíguo como prova. **Nenhuma regra do M5 ou peso SCORE-GEO-004 foi alterado.** O classificador não decide se uma oportunidade opcional deve sair da fórmula de scoring; essa decisão exige versão nova, backtest por dimensões, coverage, confidence e gates. A conclusão de #602 continua condicionada a esses critérios.


## Laboratório determinístico de sensibilidade (sem publicação de score)

`rasai.optional_seo_score_scenarios.preview_optional_seo_policy_sensitivity` recebe RuleExecutions em memória da mesma AUD e compara três cálculos pelo motor atual, com os mesmos agrupamentos e pesos:

- `CANONICAL_SCORE_GEO_004`: interpretação canônica **sem alteração**;
- `SENSITIVITY_OPTIONAL_ABSENCE_PASS`: cenário extremo que trata somente ausência opcional estritamente comprovada como PASS;
- `SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE`: cenário extremo que trata somente essas ausências como NOT_APPLICABLE e deixa o motor efetuar sua normalização de denominador/cobertura.

O laboratório expõe por dimensão e overall os campos `value`, `coverage`, `confidence`, `consolidation_status` e marcadores de readiness/gates. Os dois últimos cenários **não** são recomendação de implementação nem uma versão novo contrato de pontuação aprovada: PASS pode dar prêmio imerecido e NOT_APPLICABLE pode reduzir cobertura e aumentar incerteza. Comparar as três projeções expõe efeitos colaterais sem substituir metodologia.

O laboratório é offline, restrito a uma única AUD/dispositivo, recusa ID físico duplicado, não persiste scores nem altera RuleExecutions. A decisão final da issue #602 continua aberta até decisão normativa e, se houver alteração numérica, novo contrato versionado e paridade de compatibilidade. O golden físico da AUD de 14/10 já foi comprovado no Windows em 15/10/2026, sem aprovação de nova política.


## Replay físico sem mutação (CLI, gate histórico)

Para a cópia já extraída de uma AUD de teste, a inspeção é apenas de leitura:

```bash
python -m rasai.optional_seo_audit_replay /caminho/para/AUD-ID --device MOBILE
```

O replay exige uma única AUD válida, `audit.db` regular, sem arquivos SQLite journal/WAL/SHM, escopo de uma AUD e até 4.000 regras físicas. Confere `quick_check` e integridade referencial, calcula SHA-256 do arquivo antes/depois e **aborta** caso o score canônico recalcado pelo SCORE-GEO-004 não coincida com os campos persistidos de cada dimensão e overall (valor, cobertura, confiança, consolidação e versão). Só depois expõe cenários de sensibilidade não oficiais. Nunca grava dados e não autoriza mudanças de pontuação.

### Resultado efetivo do golden físico - 15/10/2026

O operador executou a CLI em **cópia estável e isolada** da AUD `AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF` no Windows, no baseline `main@beb5cc8c5e287ecee6e869779881702efb74eb07`. Foram verificadas **59 rule executions**, paridade `VERIFIED_SCORE_GEO_004`, **zero requests, zero escritas em AUD** e `published_score_mutated=false`. O SHA-256 de `audit.db` antes e depois foi `036ec79119c937540a29dad0571607d0f24f5b404c31d11adee4ff44760274c3`.

O score canônico foi **86,484962 (ATTENTION)**, com cobertura **0,974737**. Cenários exploratórios: `OPTIONAL_ABSENCE_NOT_APPLICABLE = 89,800752 (READY)` e `OPTIONAL_ABSENCE_PASS = 89,958647 (READY)`. O resultado é **sensibilidade, não aprovação metodológica**. Testes pontuais do replay/scoring: **19 passed**. Logs estão no diretório de evidência local do operador e não foram incorporados neste documento.

O **gate de replay físico da amostra de 14/10 está cumprido** para o código e a cópia acima. Antes de mudar SCORE-GEO-004 são obrigatórios parecer normativo, contrato/versão nova quando aplicável, regressões e teste de compatibilidade histórica. Não usar a AUD operacional com sidecars/journals ativos nem mutar os scores existentes.


## Regra conservadora de consistência física

A classificação read-only agora exige que a evidência de `ABSENT` em `robots.txt`/`sitemap` não contenha falha simultânea de aquisição. Ausência canônica com `canonicals=[]` tampouco pode coexistir com `invalid`, `normalized` ou `declared` não vazios e ser promovida a ausência opcional confirmada. Registros contraditórios ficam `UNKNOWN` para avaliação posterior; não são interpretados como prova de indisponibilidade global nem como defeito confirmado. O comportamento preserva o contrato SCORE-GEO-004 e impede que o laboratório de simulação inclua fatos ambíguos na coorte de ausência opcional.
