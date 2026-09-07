# Aplicabilidade de Dimensões e Premissas Mínimas — SARI-001 / SCORE-GEO-003

**Status:** APPROVED — current applicability contract.
**Current scoring runtime:** `SCORE-GEO-003`.

## 1. Motivação

O modelo separa uma dimensão **não aplicável** de uma dimensão que **não conseguiu consolidar**. No `SCORE-GEO-003`, o Overall depende do contrato calibrado e não de média simples das dimensões.

## 2. Princípio normativo

`NOT_APPLICABLE` não é falha, ausência de evidência nem score zero.

Uma dimensão é:

- `APPLICABLE` quando existe pelo menos uma RuleExecution aplicável;
- `NOT_APPLICABLE` quando RuleExecutions existem e todas estão legitimamente fora do universo aplicável;
- `NOT_CONSOLIDATED` quando faltam execuções necessárias, a aplicabilidade ficou bloqueada ou Coverage/Confidence são insuficientes.

Ausência completa de RuleExecutions nunca vira `NOT_APPLICABLE`.

## 3. Pré-requisito bloqueado

`PREREQUISITE_BLOCKED` não é não aplicabilidade benigna.

Reason codes como:

```text
SEMANTIC_PREREQUISITE_BLOCKED
CONTENT_EXTRACTION_PREREQUISITE_BLOCKED
```

mantêm a dimensão `NOT_CONSOLIDATED`.

## 4. Dimensões e Overall no SCORE-GEO-003

Para cada dispositivo efetivamente auditado:

1. materializar as dimensões definidas pelo SARI-001;
2. separar `NOT_APPLICABLE` legítimas;
3. exigir Value/Coverage/Confidence suficientes das dimensões aplicáveis;
4. persistir explicitamente limitações e dimensões excluídas;
5. produzir Overall **somente** conforme o contrato/model artifact versionado do `SCORE-GEO-003`.

Uma dimensão `NOT_APPLICABLE` não recebe 0/100, não reduz artificialmente Coverage e não deve ser imputada como falha.

O Overall do `SCORE-GEO-003` depende de model artifact `VALIDATED`; não existe fallback para média aritmética simples das dimensões.

Quando o model artifact não atende os gates de validação/promoção, o runtime deve expor estado/limitação em vez de fabricar um Overall aparentemente validado.

## 5. Fonte externa sobre GEO/AEO

O RASAi não assume a existência de um standard universal GEO/AEO.

Fonte primária do Google:

**Optimizing your website for generative AI features on Google Search**
<https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>

Consequências normativas para o RASAi:

- não apresentar SARI/SCORE-GEO como score oficial de mecanismo;
- não exigir markup especial GEO/AEO;
- não exigir `llms.txt` para Google Search;
- não exigir chunking artificial;
- não orientar reescrita apenas “para IA” sem finding/evidência;
- não tratar Structured Data como requisito universal de recursos generativos;
- manter foco em acesso técnico, conteúdo útil/confiável, organização clara e sinais web/SEO documentados.

## 6. Structured Data / JSON-LD

### 6.1 Obrigatoriedade

JSON-LD é **OPCIONAL / REFORÇO** no baseline geral. Structured Data continua útil para casos normais de Search/rich results e para explicitar entidades/propriedades quando aplicável.

### 6.2 Ausente

Se BR-GEO-034..037 são legitimamente `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- ausência isolada não cria finding/penalidade;
- a dimensão não deve ser imputada como zero.

### 6.3 Presente

JSON-LD observado torna o domínio aplicável. Sintaxe, tipos/propriedades e coerência factual passam a ser avaliáveis.

Adicionar JSON-LD apenas para “destravar score” é inválido.

### 6.4 Coerência factual

Structured Data pode normalizar informação observada, nunca inventar preço, rating/review, autoria, data, produto/serviço, claim ou entidade.

## 7. Formatos cobertos

O parser operacional atual é orientado a JSON-LD em `script[type="application/ld+json"]`.

Microdata/RDFa não devem ser declarados como plenamente cobertos até haver implementação/testes equivalentes.

## 8. Premissas mínimas/contextuais

| Tópico | Classe | Efeito RASAi |
|---|---|---|
| URL tecnicamente recuperável | MÍNIMO | Falha material compromete readiness técnico. |
| Documento/conteúdo analisável | MÍNIMO | Sem base utilizável, dimensões dependentes não consolidam. |
| Conteúdo essencial após rendering | MÍNIMO quando há JS | Informação principal deve permanecer recuperável. |
| Conteúdo principal identificável | MÍNIMO | Base para análise semântica/answerability. |
| Informação importante em texto recuperável | MÍNIMO | Informação somente visual/oculta limita extração. |
| Indexabilidade coerente com intenção pública | CONTEXTUAL/MÍNIMO para Search público | Bloqueios intencionais podem tornar URL inelegível à busca pública. |
| Intenção/tópico identificável | MÍNIMO semântico | Necessário para avaliar o que a URL responde. |
| Claims/valores coerentes | MÍNIMO de confiança factual | Contradições comprometem evidence/citation readiness. |
| JSON-LD | OPCIONAL / REFORÇO | Quando presente, deve ser válido e coerente. |
| Sitemap | OPCIONAL / DESCOBERTA | Útil à descoberta; ausência isolada não é FAIL. |
| Canonical | CONTEXTUALMENTE RECOMENDADO | Importante em duplicidade/preferência; não blocker universal isolado. |
| robots.txt | OPCIONAL COMO ARQUIVO | Ausência não significa bloqueio; regras presentes devem ser interpretadas. |
| Autor/publisher | CONTEXTUAL | Depende do tipo de página/claims. |
| Data publicação/atualização | CONTEXTUAL | Relevante a conteúdo temporal/editorial. |
| `llms.txt` | NÃO OBRIGATÓRIO | Não é requisito universal de Search/GEO. |
| GPTBot liberado | NÃO OBRIGATÓRIO para Search readiness | GPTBot e OAI-SearchBot têm finalidades distintas. |
| markup GEO/AEO especial | NÃO OBRIGATÓRIO | Não existe requisito universal oficial correspondente. |
| chunking artificial para IA | NÃO OBRIGATÓRIO | Não deve ser introduzido como regra artificial. |

## 9. Confidence

Confidence representa a força da conclusão do auditor, não uma nota da qualidade do texto.

`LOW` isoladamente não autoriza finding/recommendation de conteúdo. Qualquer ação precisa de RuleExecution/finding e evidência específica.

## 10. Linguagem de requisitos

Evitar “obrigatório para GEO” quando o item for apenas recomendação de mecanismo, reforço opcional, aplicável a tipo específico de página ou heurística RASAi.

Classes preferenciais:

```text
MÍNIMO
CONTEXTUAL
OPCIONAL / REFORÇO
NÃO OBRIGATÓRIO
```

## 11. Report site

`report/references.html` deve apresentar fontes e natureza das regras. `report/readiness.html`/`score-geo-003.html` devem distinguir:

- score/dimensão persistida;
- Coverage;
- Confidence;
- `NOT_APPLICABLE`;
- `NOT_CONSOLIDATED`;
- estado/modelo/dataset do SCORE-GEO-003 quando aplicável.

Faixas visuais internas devem ser rotuladas como internas.

## 12. Reprodutibilidade

BR-GEO-054 valida a integridade e a reprodutibilidade do scoring persistido. A referência metodológica é `SCORE-GEO-003`.

Dadas as mesmas RuleExecutions, metadados e model artifact aplicável, dimensões, Coverage, Confidence, estado do Overall e limitations devem ser reconstruíveis sem reabrir website nem chamar IA.

## 13. Testes mínimos

Validar:

1. sem RuleExecutions não há consolidação artificial;
2. dimensão legitimamente `NOT_APPLICABLE` não recebe zero;
3. `PREREQUISITE_BLOCKED` continua bloqueando;
4. Structured Data presente torna o domínio aplicável;
5. PASS/WARNING/FAIL participam conforme o contrato da dimensão;
6. Structured Data ausente legítimo não recebe 0/100;
7. estado do Overall registra limitações/dimensões excluídas;
8. BR-GEO-054 é reproduzível para a versão persistida;
9. report não apresenta Confidence LOW como baixa qualidade textual;
10. report distingue heurística interna de fonte oficial;
11. resultados com `scoring_version` distinto não são misturados silenciosamente.
