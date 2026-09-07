# Guia das Business Rules — BR-GEO-001..054

A definição normativa prevalente está em [`docs/specification/03_BUSINESS_RULES.md`](specification/03_BUSINESS_RULES.md). Este guia explica a finalidade operacional das regras sem duplicar pesos/fórmulas de scoring.

## Contrato comum

Resultados possíveis:

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

Finding exige RuleExecution + Evidence rastreável. Falha de pré-requisito deve bloquear conclusões derivadas em vez de produzir cascading failures.

## Basis

Quando `RuleDefinition` materializa `basis`, os valores são `OFFICIAL`, `STANDARD` ou `HEURISTIC`. Regras executoras/integridade podem não possuir `basis` separado; ausência desse campo não autoriza inventar uma fonte externa.

## Scoring

O guia de regras **não define a versão vigente de cálculo por coluna local**. A referência atual é:

- índice público: `SARI-001`;
- scoring vigente para novas auditorias: `SCORE-GEO-003`;
- histórico: `SCORE-GEO-002`.

Pesos, dimensões, applicability, Coverage, Confidence, model artifact e Overall devem ser lidos em [`SCORING_GUIDE.md`](SCORING_GUIDE.md), [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) e [`SCORE_GEO_003.md`](SCORE_GEO_003.md). Auditorias históricas preservam sua `scoring_version`; o report não deve reinterpretá-las silenciosamente como `003`.

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
| BR-GEO-034 | MEDIUM | verificar Structured Data sintaticamente interpretável |
| BR-GEO-035 | LOW | identificar tipos/propriedades presentes em Structured Data |
| BR-GEO-036 | MEDIUM | verificar consistência Structured Data × conteúdo visível |
| BR-GEO-037 | MEDIUM | verificar consistência entre entidades estruturadas/observadas |
| BR-GEO-038 | HIGH | identificar intenção primária |
| BR-GEO-039 | MEDIUM | verificar resposta explícita a perguntas primárias relevantes |
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
| BR-GEO-053 | CRITICAL | verificar rastreabilidade/reabertura de Finding, RuleExecution e Evidence |
| BR-GEO-054 | CRITICAL de integridade | verificar reprodutibilidade/integridade do scoring persistido para a `scoring_version` da auditoria |

## Regras semânticas e IA

Uma regra pode ser semanticamente avaliada com provider de IA quando o contrato permitir, mas o provider não é a Business Rule. Resultado aceito continua sujeito a schema, evidence IDs, applicability e validações locais.

Falha/ausência de IA não é evidência de baixa qualidade do website. Quando não existe base suficiente, o resultado deve permanecer `UNKNOWN`/limitado conforme a regra.

## Structured Data

BR-GEO-034..037 avaliam **o que foi observado**. Ausência legítima de Structured Data pode ser `NOT_APPLICABLE`; não deve receber zero apenas por estar ausente. Quando presente, sintaxe, tipos/propriedades e consistência podem ser avaliados.

Os diagnósticos adicionais de `report/observability.html` sobre Product/Breadcrumb/Organization são checks documentais/advisory e não criam novas BR-GEO nem um “Rich Results score”.

## International Search / hreflang

Checks de hreflang adicionados em Observability são diagnósticos complementares. Eles não foram inseridos retroativamente em BR-GEO-001..054 nem no SARI sem novo contrato de versionamento.

## BR-GEO-054 e versionamento

BR-GEO-054 deve reconstruir/validar o scoring conforme a **versão persistida**:

- nova auditoria: `SCORE-GEO-003`;
- auditoria histórica: pode conter `SCORE-GEO-002`.

A regra não deve converter um histórico `002` em `003`, nem recalcular Overall de `003` usando a antiga média simples do `002`.

## Evidência e remediation

O report deve distinguir sempre:

- valor observado/evidência;
- conclusão da regra;
- finding materializado;
- exemplo/receita de correção.

Exemplo de correção não é evidência observada. Selectors só devem ser exibidos como causa/local quando houver correspondência confiável; relações document-level/set-level não devem receber selector arbitrário apenas para preencher a UI.
