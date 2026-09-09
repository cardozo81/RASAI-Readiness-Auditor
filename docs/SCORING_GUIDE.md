# SCORING_GUIDE.md

Guia operacional do **Search & AI Readiness Index `SARI-001`**.

## Método vigente

Todas as novas auditorias usam:

```text
scoring_version = SCORE-GEO-004
```

`SCORE-GEO-004` é determinístico, transparente e reproduzível por auditoria. Não depende de model artifact externo e não representa probabilidade de ranking ou citação.

Contrato completo: [`SCORE_GEO_004.md`](SCORE_GEO_004.md).

## Dimensões

1. `TECHNICAL_ACCESSIBILITY`
2. `INDEXABILITY`
3. `CONTENT_EXTRACTABILITY`
4. `SEMANTIC_STRUCTURE`
5. `ENTITY_CLARITY`
6. `STRUCTURED_DATA`
7. `ANSWERABILITY`
8. `CITATION_READINESS`
9. `EVIDENCE_TRUST`
10. `INTENT_COVERAGE`

Desktop e Mobile permanecem separados. Somente dispositivos efetivamente auditados são publicados como resultado válido.

## RuleResult

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

Somente `PASS`, `WARNING` e `FAIL` entram no denominador do score da dimensão.

`UNKNOWN` e `ERROR` reduzem Coverage e força da conclusão; não são `FAIL`.

`NOT_APPLICABLE` sai do universo aplicável quando legítimo.

## Fórmula das dimensões

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00

Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

Grupos correlacionados, pré-requisitos, evidência e aplicabilidade fazem parte do contrato versionado.

## Coverage

```text
Dimension Coverage = evaluated applicable weight / total applicable weight
Overall Coverage = média da Coverage das dimensões aplicáveis
```

Coverage mede completude da análise, não qualidade do site.

## Confidence

Dimensão:

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação abaixo dos critérios acima
UNAVAILABLE Coverage <= 0
```

Overall:

```text
menor Confidence das dimensões aplicáveis
```

Confidence descreve força da medição e não probabilidade de outcome externo.

## Consolidation

Dimensão:

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          estado avaliável com Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Overall `CONSOLIDATED` exige:

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Overall Coverage >= 80%
Overall Confidence = HIGH ou MEDIUM
```

Resultado calculável abaixo desse gate pode ser `PARTIAL` quando a Coverage é de pelo menos 50% e a Confidence está disponível. Estado insuficiente nunca vira zero.

### Soft-404 e Coverage de Indexability

`BR-GEO-016` é avaliada com evidência de estado renderizado quando disponível. Ela não pode permanecer `UNKNOWN` apenas por fronteira interna entre módulos. `BR-GEO-016` e `BR-GEO-023` pertencem ao grupo `INDEXABILITY / SOFT_ERROR`; o agrupamento impede peso duplicado quando ambas observam o mesmo contexto de soft-404.

## Overall

Contrato:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Fórmula:

```text
Overall = soma dos Dimension Scores aplicáveis / quantidade de dimensões aplicáveis
```

Cada dimensão aplicável possui o mesmo peso no Overall.

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero. Uma dimensão aplicável sem valor ou em `NOT_CONSOLIDATED` bloqueia a publicação de Overall consolidado.

## Structured Data

JSON-LD não é requisito universal para que a auditoria possua Overall.

Quando `STRUCTURED_DATA` é legitimamente `NOT_APPLICABLE`, a dimensão sai do denominador sem receber nota artificial.

Pré-requisito bloqueado não pode ser tratado como `NOT_APPLICABLE` benigno.

## IA e baseline determinístico

IA é opcional para o pipeline de scoring. Ela não calcula o score.

Sem provider, a rule version 2 das regras semânticas `BR-GEO-028..049` usa `SEMANTIC-BASELINE-001` para resolver somente critérios que possuam evidência local suficiente. O baseline não usa rede e não promove lacunas para resultado favorável.

Uma execução `NO_AI` pode alcançar `CONSOLIDATED` quando o baseline e as demais regras produzirem Coverage/Confidence suficientes. Se faltarem evidências para regras aplicáveis, `UNKNOWN` continua possível e os gates normais continuam valendo.

Provider semântico válido pode aprofundar avaliações. Auditorias com e sem provider não devem ser consideradas medições semanticamente idênticas sem observar `audit_mode`, rule version e provenance; o cálculo matemático do `SCORE-GEO-004`, porém, é o mesmo.

Detalhes: [`SEMANTIC_BASELINE.md`](SEMANTIC_BASELINE.md).

## Métricas externas fora do score

Não entram no SARI-001/SCORE-GEO-004:

- Lighthouse Performance;
- Core Web Vitals;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- tráfego e conversão;
- Observed Generative Visibility.

Indisponibilidade de PageSpeed/Lighthouse não reduz o Overall RASAi.

## Parametrização

Configurável:

- URLs/domínios;
- dispositivos;
- provider/modelo de IA e contexto editorial;
- Web Performance;
- Synthetic Apdex;
- limites de coleta e execução.

Fixo/versionado no SCORE-GEO-004:

- dimensões;
- catálogo de regras/pesos;
- fatores PASS/WARNING/FAIL;
- Overall de igual peso entre dimensões aplicáveis;
- thresholds de Coverage/Confidence/Consolidation.

A matemática oficial não é alterada por configuração de uma auditoria.

## CLI

Para inspecionar o contrato vigente:

```powershell
rasai scoring inspect
```

O comando não cria model artifact e não executa rede.

## Reprodutibilidade

`BR-GEO-054` verifica reconstrução a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- evidências persistidas;
- `SCORE-GEO-004` e seu contrato de agregação.

Avaliações `DETERMINISTIC_BASELINE` registram também `SEMANTIC-BASELINE-001` como configuration version/capability.

Não é necessário reexecutar website, IA ou APIs externas.

## Relatórios e versionamento do path

```text
readiness.html  página canônica do SARI-001
scoring.html    fórmula, versão vigente, gates e rastreabilidade do método
```

O arquivo `scoring.html` é deliberadamente **version-neutral**. A versão efetiva pertence ao campo persistido `scoring_version` e ao conteúdo da página. Assim, uma futura revisão metodológica não quebra bookmarks, links internos, automações ou rotas do produto apenas por mudar de `SCORE-GEO-004` para outra versão.

Relatórios consolidados preservam `scoring_version` como parte da comparabilidade. Auditorias de versões diferentes não devem ser normalizadas silenciosamente como se fossem equivalentes.

## Limite de validade

SCORE-GEO-004 é uma métrica proprietária, transparente e reproduzível. O baseline semântico é igualmente proprietário e não deve ser apresentado como standard GEO/AEO universal. Nenhum deles é certificação oficial de Google, Microsoft, OpenAI, Anthropic ou outro mantenedor e não garante ranking, tráfego, conversão ou citação futura.

<!-- rasai-confidence-ai-robots-20260908 -->
## Confidence, IA, robots.txt e sitemap

A `Confidence` do SARI-001 **não depende da presença de IA**. O runtime deriva Confidence de Coverage, completude das evidências avaliadas e erros de execução. Uma auditoria `NO_AI` pode atingir `MEDIUM` ou `HIGH` e consolidar normalmente quando as regras aplicáveis possuem evidência suficiente.

A IA pode, em regras explicitamente semânticas, ajudar a transformar uma avaliação que ficaria `UNKNOWN` em uma execução evidence-bound válida. Nesse caso a Confidence pode aumentar como consequência da Coverage/evidência adicional, nunca porque o provider declarou uma confiança subjetiva.

`robots.txt` e sitemap já participam do `SCORE-GEO-004` por regras determinísticas:

- `BR-GEO-003`: aquisição/interpretação de sitemap quando disponível;
- `BR-GEO-017`: interpretabilidade de `robots.txt` quando presente;
- `BR-GEO-018`: resolução independente de acesso por crawler.

A ausência isolada de `robots.txt` ou sitemap não recebe `FAIL` automático. Recurso existente porém inválido, não interpretável, inacessível ou com controle de crawler materialmente problemático pode produzir `WARNING`, `UNKNOWN` ou outra conclusão prevista na regra. Os diagnósticos aprofundados de crawling/discovery permanecem advisory e não alteram diretamente Score/Coverage/Confidence.

### Transparência de robots.txt e sitemap no SARI

A página canônica **Search & AI Readiness** expõe uma seção `SARI - inputs técnicos de descoberta` com BR-GEO-003, BR-GEO-017 e BR-GEO-018, seus resultados persistidos e o papel efetivo no score. BR-GEO-017 e BR-GEO-018 compartilham o grupo `ROBOTS`, portanto o SCORE-GEO-004 usa a regra representativa mais restritiva do grupo por dispositivo para evitar peso duplicado. Os diagnósticos aprofundados de crawling/discovery continuam advisory/non-scoring; isso não remove a participação das regras determinísticas básicas no SARI.

## Refinamento pré-publicação: discovery, JSON-LD e fatores estáticos

- `robots.txt` e sitemap ausentes não recebem o mesmo fator de um recurso encontrado e utilizável; a ausência é uma lacuna pequena, não uma falha dura de crawling.
- Sitemap publicado porém inválido é desfavorável; falha de rede que impede avaliação continua `UNKNOWN` e reduz Coverage.
- `script[type="application/ld+json"]` é extraído do HTML. Ausência de JSON-LD é uma lacuna leve mensurável; JSON-LD inválido é desfavorável; consistência com conteúdo/entidades pode usar IA evidence-bound quando habilitada.
- A IA técnica não escolhe pesos. Ela só pode emitir classes contratadas e referenciadas por evidência; o runtime converte essas classes em `PASS/WARNING/FAIL` com fatores estáticos/versionados no mesmo `scoring_group`, sem bônus duplicado.
- Lighthouse, Core Web Vitals, Accessibility e Apdex continuam independentes da aritmética do SARI. Indisponibilidade de uma API externa não é tratada como falha do website.
- Faixas de interpretação e pesos do método são estáticos por versão. Não existe parâmetro por auditoria para alterar o conceito de excelência, preservando comparabilidade temporal.

## Explicabilidade operacional

`scoring.html` materializa, por dimensão, regra representativa, critério, `scoring_group`, peso, resultado, fator e contribuição efetiva. Regras do mesmo grupo não recebem pesos cumulativos. A leitura operacional deve separar itens que reduzem score de itens que apenas reduzem Coverage/Confidence. O Overall usa peso igual entre dimensões aplicáveis; os pesos exibidos atuam apenas dentro de cada dimensão.

<!-- rasai-readiness-canonical-fix-20260908 -->
## Projeção canônica do readiness

`readiness.html` é a superfície que centraliza SARI, pontuação por dimensão, Cobertura, Confiança e Consolidação. `mobile.html` e `desktop.html` preservam evidências/findings por dispositivo e não devem duplicar a função de página canônica do índice.

A projeção deve consultar o schema efetivamente persistido de cada capacidade. Para Crawling & Discovery, a execução persistida possui uma linha por `audit_id` e usa `updated_at`; a geração do SARI não depende de uma coluna `completed_at` inexistente. O nome físico da tabela é detalhe interno e não integra o contrato documental. Uma falha de projeção não pode ser confundida com falha de scoring: o score já persistido continua sendo a fonte de verdade, mas a auditoria deve sinalizar a falha operacional até que o HTML seja materializado corretamente.
