# SCORE-GEO-004

`SCORE-GEO-004` é o método de scoring padrão para novas auditorias RASAi.

O índice público continua sendo `SARI-001 - Search & AI Readiness Index`.

## Objetivo da versão 004

O `SCORE-GEO-003` introduziu um Overall calibrado empiricamente contra outcomes observados de citação. Esse contrato é metodologicamente defensável para pesquisa, mas exige um dataset multi-domínio `VALIDATED` antes de qualquer auditoria individual poder publicar Overall.

Isso criava uma dependência operacional inadequada para o produto: uma auditoria tecnicamente completa podia permanecer com `Overall = null` apenas porque o corpus global de calibração ainda não existia.

O `SCORE-GEO-004` separa os dois problemas:

- **scoring operacional** - determinístico, reproduzível e disponível por auditoria;
- **validação empírica** - opcional, multi-domínio e independente do score publicado.

Nenhuma probabilidade de ranking ou citação é inferida pelo `004`.

## Dimensões

As dez dimensões permanecem:

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

A fórmula de cada dimensão permanece evidence-bound:

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00

Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos silenciosamente em `FAIL`.

## Overall

O Overall usa o contrato versionado:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Fórmula:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Regras:

- dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero;
- dimensão aplicável sem valor ou `NOT_CONSOLIDATED` bloqueia a publicação de Overall;
- cada dimensão aplicável possui o mesmo peso no Overall;
- o cálculo não depende de IA, Lighthouse, Core Web Vitals, Accessibility ou Synthetic Apdex;
- nenhuma calibração estatística é usada como input do score.

## Coverage, Confidence e Consolidation

A Coverage do Overall é a média da Coverage das dimensões aplicáveis.

A Confidence do Overall é a menor Confidence entre as dimensões aplicáveis.

O Overall recebe `CONSOLIDATED` quando:

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Coverage média >= 80%
Confidence mínima = HIGH ou MEDIUM
```

Se o Overall é calculável, mas o gate acima não é satisfeito, ele pode ser `PARTIAL` quando existe cobertura suficiente para uma leitura limitada.

Estados insuficientes nunca são convertidos em zero.

## Relação com SCORE-GEO-003

`SCORE-GEO-003` permanece preservado como contrato histórico e pipeline de calibração empírica.

Ele não é recalculado nem reclassificado como `004` em auditorias antigas.

A infraestrutura existente de calibração `003` pode continuar sendo usada para:

- pesquisa;
- validação empírica das dimensões;
- benchmarking;
- avaliação de associação com outcomes observados;
- insumo para uma futura versão metodológica, se houver evidência suficiente.

Um artifact `VALIDATED` do `003` não altera automaticamente resultados `004`.

## Independência de métricas externas

Os seguintes domínios continuam fora do SARI/SCORE-GEO:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex;
- métricas de tráfego/conversão;
- outcomes observados de AI visibility.

Eles possuem páginas e metodologias próprias. Indisponibilidade PageSpeed/Lighthouse, por exemplo, não reduz o SCORE-GEO-004.

## Reprodutibilidade

`BR-GEO-054` deve reconstruir o resultado a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- fórmula e thresholds versionados do `SCORE-GEO-004`;
- evidências persistidas no `audit.db`.

Não é necessário reexecutar website, IA ou calibração.

## Relatório

Novas auditorias materializam:

```text
report/readiness.html
report/score-geo-004.html
```

`readiness.html` é a página canônica do SARI-001.

`score-geo-004.html` expõe fórmula, gates de consolidação, Coverage, Confidence, estado do Overall e separação explícita em relação ao método calibrado `003`.

## Limite de validade

O `SCORE-GEO-004` é proprietário, transparente e reproduzível, mas não é um standard oficial de Google, OpenAI, Microsoft, Anthropic ou qualquer outro mantenedor.

O número representa readiness segundo o contrato RASAi. Ele não é probabilidade de ranking, tráfego, conversão, resposta ou citação futura.
