# SCORE-GEO-002 — Aplicabilidade de Dimensões e Premissas Mínimas GEO

**Status:** APPROVED
**Scoring baseline:** `SCORE-GEO-002`
**Supersede:** `SCORE-GEO-001` somente quanto à aplicabilidade/agregação de dimensões.

## 1. Motivação

`SCORE-GEO-001` confundia dimensão não aplicável com dimensão que não conseguiu consolidar. `SCORE-GEO-002` separa esses estados e impede penalidade artificial por tópico opcional ausente.

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

## 4. Overall Readiness

Para cada dispositivo efetivamente auditado:

1. materializar as dez dimensões do modelo;
2. separar `NOT_APPLICABLE` legítimas;
3. exigir Value e consolidação suficiente das restantes;
4. calcular média aritmética simples dos Values aplicáveis;
5. calcular Coverage pela média das dimensões aplicáveis;
6. calcular Confidence conforme o modelo vigente;
7. persistir `DIMENSION_NOT_APPLICABLE:<DIMENSION>`.

Uma dimensão `NOT_APPLICABLE` não recebe 0/100, não reduz Score/Coverage e não bloqueia Overall.

## 5. Fonte externa atual sobre GEO/AEO

O SearchGEO não assume a existência de um standard universal GEO/AEO.

Fonte primária do Google, verificada em 2026-09-03:

**Optimizing your website for generative AI features on Google Search**
<https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>

O Google explicita nesse guia que AEO/GEO são termos usados pela indústria e que, para os recursos generativos do Google Search, as práticas fundamentais continuam sendo SEO.

Consequências normativas para o SearchGEO:

- não apresentar o score SearchGEO como score oficial GEO;
- não exigir markup especial GEO/AEO;
- não exigir `llms.txt` para Google Search;
- não exigir chunking artificial;
- não orientar reescrita de conteúdo apenas “para IA”;
- não tratar Structured Data como requisito universal de recursos generativos;
- manter foco em acesso técnico, conteúdo útil/confiável, organização clara e sinais web/SEO efetivamente documentados.

## 6. Structured Data / JSON-LD

### 6.1 Obrigatoriedade

JSON-LD é **OPCIONAL / REFORÇO** no baseline geral.

O guia oficial do Google para recursos generativos não exige Structured Data especial para IA. Structured Data continua útil para seus casos normais de Search/rich results e para explicitar entidades/propriedades quando aplicável.

### 6.2 Ausente

Se BR-GEO-034..037 são legitimamente `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- não participa do Overall;
- ausência isolada não cria finding/penalidade.

### 6.3 Presente

JSON-LD observado torna a dimensão aplicável. Sintaxe, tipos/propriedades e coerência factual passam a ser avaliáveis.

Adicionar JSON-LD apenas para destravar score é inválido.

### 6.4 Coerência factual

Structured Data pode normalizar informação observada, nunca inventar:

- preço;
- rating/review;
- autoria;
- data;
- produto/serviço;
- claim;
- entidade.

## 7. Formatos cobertos

O parser operacional atual é orientado a JSON-LD em `script[type="application/ld+json"]`.

Microdata/RDFa não devem ser declarados como plenamente cobertos até haver implementação/testes equivalentes.

## 8. Premissas mínimas/contextuais

| Tópico | Classe | Efeito SearchGEO |
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
| Sitemap XML | OPCIONAL / DESCOBERTA | Útil à descoberta; ausência isolada não é FAIL. |
| Canonical | CONTEXTUALMENTE RECOMENDADO | Importante em duplicidade/preferência de URL; não blocker universal isolado. |
| robots.txt | OPCIONAL COMO ARQUIVO | Ausência não significa bloqueio; regras presentes devem ser interpretadas. |
| Autor/publisher | CONTEXTUAL | Depende do tipo de página/claims. |
| Data publicação/atualização | CONTEXTUAL | Relevante a conteúdo temporal/editorial. |
| `llms.txt` | NÃO OBRIGATÓRIO | Google declara que não é necessário para seus recursos generativos e não o usa como sinal de Search. |
| GPTBot liberado | NÃO OBRIGATÓRIO para Search readiness | GPTBot e OAI-SearchBot têm finalidades distintas. |
| markup GEO/AEO especial | NÃO OBRIGATÓRIO | Não existe requisito oficial correspondente no Google. |
| chunking artificial para IA | NÃO OBRIGATÓRIO | Não deve ser introduzido como regra artificial. |

## 9. Confidence

Confidence representa a força da conclusão do auditor, não uma nota da qualidade do texto.

`LOW` isoladamente não autoriza finding/recommendation de conteúdo. Qualquer ação de conteúdo precisa ser sustentada por RuleExecution/finding e evidência específica.

## 10. Linguagem de requisitos

Evitar “obrigatório para GEO” quando o item for apenas:

- recomendação de mecanismo;
- reforço opcional;
- aplicável a tipo específico de página;
- heurística SearchGEO.

Classes preferenciais:

```text
MÍNIMO
CONTEXTUAL
OPCIONAL / REFORÇO
NÃO OBRIGATÓRIO
```

## 11. Report site

`report/references.html` deve apresentar fontes e natureza das regras. `report/index.html` deve distinguir:

- score calculado;
- Coverage;
- Confidence;
- `NOT_APPLICABLE`;
- `NOT_CONSOLIDATED`.

Faixas visuais de Score são internas e devem ser rotuladas como tal.

## 12. Reprodutibilidade

BR-GEO-054 usa `SCORE-GEO-002`.

Dadas as mesmas RuleExecutions/metadados, aplicabilidade, Score, Overall, Coverage, Confidence e limitations devem ser reconstruíveis sem website/IA.

## 13. Testes mínimos

Validar:

1. sem RuleExecutions bloqueia Overall;
2. dimensão legitimamente `NOT_APPLICABLE` não bloqueia;
3. `PREREQUISITE_BLOCKED` continua bloqueando;
4. Structured Data presente torna dimensão aplicável;
5. PASS/WARNING/FAIL entram no cálculo;
6. Structured Data ausente legítimo não recebe 0/100;
7. Overall registra dimensões excluídas;
8. BR-GEO-054 é reproduzível;
9. report não apresenta Confidence LOW como baixa qualidade textual;
10. report distingue heurística interna de fonte oficial.
