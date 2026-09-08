# Baseline semântico determinístico

## Contrato

A análise semântica possui um baseline local, evidence-bound e versionado:

```text
SEMANTIC-BASELINE-001
```

Seu objetivo é permitir que uma auditoria `NO_AI` produza `RuleExecution` avaliável para regras semânticas quando as evidências persistidas forem suficientes, sem transformar a ausência de IA em requisito indireto de consolidação do `SARI-001 / SCORE-GEO-004`.

O baseline **não calcula o score**. Ele produz avaliações de regras; o `ScoringEngine` continua sendo o único responsável pela aritmética de Score, Coverage, Confidence e Consolidation.

## Fontes permitidas

A avaliação usa somente dados já preservados pela auditoria, principalmente:

- title;
- headings;
- main content extraído;
- links;
- Structured Data / JSON-LD parseado;
- evidence IDs pertencentes ao mesmo snapshot;
- URL da página apenas quando necessária para um sinal estrutural explícito.

Não há chamada externa, RAG, corpus adicional, pesquisa na Web ou inferência de fatos ocultos.

## Política conservadora

O baseline segue estas regras:

- `PASS` somente quando há evidência positiva suficiente para o critério local;
- `NOT_APPLICABLE` somente quando a aplicabilidade pode ser resolvida de forma defensável a partir das evidências;
- ausência de evidência não vira `FAIL`;
- ausência de evidência não vira `PASS`;
- quando o critério não pode ser resolvido com segurança, a regra permanece `UNKNOWN` se nenhum provider válido a resolver;
- findings continuam sendo criados somente por `FAIL`/`WARNING` evidence-backed;
- fatos determinísticos fortes, como ausência de title ou Structured Data inválido, mantêm precedência.

O baseline não tenta reproduzir livremente o raciocínio de um LLM. Ele cobre somente sinais que podem ser reabertos e auditados.

## Relação com IA

A IA permanece opcional.

Quando não há provider configurado, o baseline é usado para as regras que consegue resolver. Quando um provider válido está habilitado, a avaliação semântica normalizada continua podendo aprofundar critérios que exigem interpretação mais rica. A provenance da execução permite distinguir os modos.

Falha operacional de um provider explicitamente configurado permanece visível como degradação; o runtime não mascara indisponibilidade externa como se a medição tivesse sido equivalente ao modo `NO_AI` solicitado pelo operador.

## Provenance

Avaliações produzidas pelo baseline são persistidas com:

```text
provider = DETERMINISTIC_BASELINE
configuration_version = SEMANTIC-BASELINE-001
rule_version = 2   # BR-GEO-028..049 após adoção do baseline
```

O audit registra a capability:

```text
semantic_baseline:SEMANTIC-BASELINE-001
```

Isso permite distinguir auditorias antigas das novas sem alterar a identidade pública `SARI-001` nem a versão matemática `SCORE-GEO-004`.

## Consolidação sem IA

`NO_AI` não significa automaticamente `CONSOLIDATED`.

Um Overall só pode ser consolidado quando os requisitos normais do `SCORE-GEO-004` forem satisfeitos. Portanto, mesmo com o baseline, uma página com evidência insuficiente, pré-requisitos bloqueados ou grupos de regras legitimamente não resolvidos pode permanecer `PARTIAL` ou `NOT_CONSOLIDATED`.

A diferença é que **a simples ausência de API key/provider deixa de ser, por si só, a causa mecânica para que dimensões semânticas permaneçam sem avaliação**.

## Limite metodológico

O baseline é uma metodologia proprietária do RASAi e contém heurísticas internas para sinais semânticos que não possuem um standard GEO/AEO universal. Ele deve ser interpretado junto com `report/references.html` e com a classificação `basis` de cada regra.

Nenhuma avaliação do baseline garante ranking, citação, resposta generativa, tráfego ou conversão.
