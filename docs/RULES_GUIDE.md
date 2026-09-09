# Guia das Business Rules - BR-GEO-001..059

A definição normativa prevalente está em [`docs/specification/03_BUSINESS_RULES.md`](specification/03_BUSINESS_RULES.md). Este guia explica a finalidade operacional das regras sem duplicar a fórmula completa do scoring.

## Contrato comum

```text
PASS
FAIL
WARNING
UNKNOWN
NOT_APPLICABLE
ERROR
```

Interpretação obrigatória:

```text
UNKNOWN != FAIL
ERROR != FAIL
NOT_APPLICABLE != FAIL
```

Finding exige RuleExecution + Evidence rastreável. Falha de pré-requisito bloqueia conclusões derivadas em vez de produzir cascading failures.

## Basis

Regras podem declarar `OFFICIAL`, `STANDARD` ou `HEURISTIC`. Regras de integridade podem representar contratos internos do auditor. Uma referência externa sustenta somente o fenômeno específico; não homologa o SARI composto.

## Scoring

- índice público: `SARI-001`;
- scoring vigente: `SCORE-GEO-004`;
- agregação: `HIERARCHICAL_WEIGHTED_READINESS_V1`.

O manifesto vigente mapeia explicitamente regra → dimensão → `scoring_group` → papel de evidência. O peso de um grupo é fixo e distribuído entre páginas/escopos aplicáveis; quantidade de páginas não multiplica o peso metodológico.

Detalhes: [`SCORING_GUIDE.md`](SCORING_GUIDE.md), [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) e [`SCORE_GEO_004.md`](SCORE_GEO_004.md).

## Catálogo

| Regra | Severidade operacional | Finalidade resumida |
|---|---|---|
| BR-GEO-001 | CRITICAL | validar e normalizar o target da auditoria |
| BR-GEO-002 | INFO | preservar rastreabilidade da origem de URLs descobertas |
| BR-GEO-003 | LOW | adquirir/interpretar sitemap quando disponível |
| BR-GEO-004 | INFO | preservar artifacts HTTP necessários à reprodutibilidade |
| BR-GEO-005 | HIGH | verificar recuperabilidade técnica da página |
| BR-GEO-006 | HIGH | verificar se a resposta HTTP final é utilizável |
| BR-GEO-007 | HIGH | validar cadeia de redirects sem loop/hop inválido |
| BR-GEO-008 | LOW | detectar efeito material introduzido por redirects |
| BR-GEO-009 | HIGH | verificar se HTML esperado é analisável |
| BR-GEO-010 | HIGH | detectar falha de rendering que oculta conteúdo essencial |
| BR-GEO-011 | HIGH | resolver diretivas de indexabilidade |
| BR-GEO-012 | MEDIUM | identificar `noindex` explícito corretamente |
| BR-GEO-013 | MEDIUM | verificar canonical interpretável e não conflitante |
| BR-GEO-014 | MEDIUM | validar plausibilidade técnica do canonical target |
| BR-GEO-015 | HIGH | detectar conflito canonical/indexabilidade introduzido por JS |
| BR-GEO-016 | MEDIUM | detectar página error-like apresentada como indexável |
| BR-GEO-017 | MEDIUM | interpretar robots.txt quando presente |
| BR-GEO-018 | HIGH | resolver acesso por crawler configurado |
| BR-GEO-019 | HIGH | comparar RAW × RENDERED por consistência semântica material |
| BR-GEO-020 | HIGH | verificar preservação de conteúdo essencial após JS |
| BR-GEO-021 | HIGH | verificar acesso direto a rotas client-side indexáveis |
| BR-GEO-022 | MEDIUM | verificar se navegação interna expõe destinos crawlable |
| BR-GEO-023 | HIGH | detectar soft-404 de client-side routing |
| BR-GEO-024 | MEDIUM | verificar lazy loading de conteúdo essencial |
| BR-GEO-025 | HIGH | identificar conteúdo principal |
| BR-GEO-026 | HIGH | verificar conteúdo significativo além de boilerplate |
| BR-GEO-027 | MEDIUM | verificar se informação essencial sobrevive à extração |
| BR-GEO-028 | HIGH | verificar presença/representatividade semântica do title |
| BR-GEO-029 | MEDIUM | avaliar hierarquia semântica |
| BR-GEO-030 | MEDIUM | avaliar identificabilidade de tópico/seções |
| BR-GEO-031 | MEDIUM | identificar entidade principal quando aplicável |
| BR-GEO-032 | MEDIUM | verificar contexto de tipos/relações de entidades |
| BR-GEO-033 | MEDIUM | detectar ambiguidade material de entidade |
| BR-GEO-034 | MEDIUM | verificar Structured Data sintaticamente interpretável quando presente |
| BR-GEO-035 | LOW | identificar tipos/propriedades presentes em Structured Data |
| BR-GEO-036 | MEDIUM | verificar consistência Structured Data × conteúdo visível |
| BR-GEO-037 | MEDIUM | verificar consistência entre entidades estruturadas/observadas |
| BR-GEO-038 | HIGH | identificar intenção primária |
| BR-GEO-039 | MEDIUM | verificar resposta explícita a perguntas relevantes |
| BR-GEO-040 | MEDIUM | verificar contexto suficiente das respostas |
| BR-GEO-041 | LOW | identificar claims factuais materiais |
| BR-GEO-042 | MEDIUM | verificar contexto dos claims |
| BR-GEO-043 | MEDIUM | verificar qualificadores numéricos/temporais |
| BR-GEO-044 | MEDIUM | detectar informação importante que exige inferência excessiva |
| BR-GEO-045 | MEDIUM | verificar atribuição/suporte de claims quando requerido |
| BR-GEO-046 | LOW | verificar publisher/author/responsável quando relevante |
| BR-GEO-047 | MEDIUM | verificar consistência de publicação/freshness |
| BR-GEO-048 | MEDIUM | avaliar cobertura de intenções primária/secundárias |
| BR-GEO-049 | MEDIUM | exigir evidência para gaps materiais de intenção |
| BR-GEO-050 | MEDIUM | verificar destinos tecnicamente utilizáveis em links internos |
| BR-GEO-051 | MEDIUM | identificar duplicatas/near-duplicates materiais |
| BR-GEO-052 | MEDIUM | detectar/classificar diferenças Desktop × Mobile |
| BR-GEO-053 | CRITICAL | verificar rastreabilidade de Finding, RuleExecution e Evidence |
| BR-GEO-054 | CRITICAL de integridade | verificar reprodutibilidade do scoring persistido |
| BR-GEO-055 | MEDIUM | avaliação IA evidence-bound corroborativa de sitemap |
| BR-GEO-056 | MEDIUM | avaliação IA evidence-bound corroborativa de robots.txt |
| BR-GEO-057 | MEDIUM | avaliar sinais de utilidade/especificidade não trivial do conteúdo |
| BR-GEO-058 | MEDIUM | avaliar diferenciação/experiência/análise/dado próprio explicitamente demonstrado |
| BR-GEO-059 | MEDIUM | avaliar profundidade/contexto proporcionais ao conteúdo e propósito observável |

## Dimensão Discovery & Crawler Access

As regras antes associadas internamente a `TECHNICAL_ACCESSIBILITY` que realmente medem discovery/crawler access passam a usar:

```text
DISCOVERY_ACCESS
```

Isso evita conflito semântico com Accessibility/WCAG.

Principais grupos:

- `PAGE_ACCESS`;
- `ROBOTS`;
- `SITEMAP`;
- `REDIRECT`;
- `SPA_ROUTE`;
- `SPA_NAVIGATION`;
- `INTERNAL_LINKS`.

## Regras semânticas e IA

BR-GEO-028..049 podem receber avaliação de provider quando o contrato permitir, mas o provider não é a Business Rule. A saída permanece sujeita a schema, evidence IDs, applicability e validações locais.

Falha/ausência de IA não é evidência de baixa qualidade do website. Sem base suficiente, o estado permanece `UNKNOWN`.

## BR-GEO-055 / BR-GEO-056 - IA técnica corroborativa

Essas regras são opcionais e `AI_CORROBORATIVE`.

```text
BR-GEO-055 → SITEMAP
BR-GEO-056 → ROBOTS
```

O provider não escolhe pesos, thresholds ou Overall.

No mesmo escopo/grupo:

```text
DETERMINISTIC_PRIMARY > AI_CORROBORATIVE
```

Logo, uma conclusão determinística PASS/WARNING/FAIL não pode ser sobrescrita arbitrariamente por um verdict IA mais pessimista ou mais otimista.

## BR-GEO-057..059 - Content Value

Classificação: `RASAI_HEURISTIC`.

Baseline vigente:

```text
CONTENT-VALUE-BASELINE-001
```

### BR-GEO-057 - Content usefulness

Avalia sinais locais de conteúdo útil, específico e não trivial. A baseline utiliza apenas o conteúdo principal persistido. Conteúdo muito limitado pode produzir WARNING; input indisponível produz UNKNOWN.

### BR-GEO-058 - Content differentiation

Busca sinais **explícitos** de experiência, pesquisa, análise, metodologia, teste ou dados próprios.

Regra conservadora:

```text
sem evidência explícita de diferenciação → UNKNOWN
```

Nunca presumir falta de originalidade como FAIL apenas porque o auditor não consegue prová-la.

### BR-GEO-059 - Content depth

Avalia se a profundidade/contexto observáveis são suficientes para uma conclusão baseline. Quando a evidência local não permite julgar adequação ao propósito, o resultado permanece UNKNOWN.

## Structured Data

BR-GEO-034..037 avaliam markup quando aplicável.

Na aritmética vigente do SARI, ausência confirmada de Structured Data não é requisito universal e é tratada como `NOT_APPLICABLE` para o grupo de scoring. Markup existente inválido/contraditório continua avaliável.

Structured Data representa no máximo 5% do contrato SARI quando aplicável.

## Lighthouse

Category scores Lighthouse não são Business Rules SARI.

Um audit individual do Lighthouse pode futuramente ser mapeado como `CORROBORATIVE_EVIDENCE` de uma BR-GEO que avalie a mesma condição técnica. Esse mapeamento precisa ser explícito e não pode criar dupla pontuação.

## International Search / hreflang

Checks de hreflang em Observability continuam diagnósticos complementares. Não são promovidos ao SARI apenas por existirem; uma futura inclusão exige regra, applicability e peso explicitamente contratados.

## BR-GEO-054 e reprodutibilidade

BR-GEO-054 reconstrói o método vigente a partir de:

- RuleExecutions;
- evidências;
- manifesto de regras;
- pesos de dimensão/grupo;
- ScoreContributions;
- Coverage/Confidence/Consolidation;
- Critical Gates.

O contrato ativo permanece `SCORE-GEO-004`. Como o produto está em pré-produção, resultados experimentais anteriores ao contrato `HIERARCHICAL_WEIGHTED_READINESS_V1` devem ser regenerados em vez de mantidos como versão ativa.

## Evidência e remediation

O report deve distinguir:

- valor observado/evidência;
- conclusão da regra;
- finding;
- contribuição no score, quando existir;
- exemplo/receita de correção.

Exemplo de correção não é evidência observada. Selectors só devem ser exibidos quando houver correspondência confiável.