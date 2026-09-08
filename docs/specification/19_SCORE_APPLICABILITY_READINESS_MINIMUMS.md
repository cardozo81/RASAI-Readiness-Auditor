# Aplicabilidade de Dimensões e Premissas Mínimas - SARI-001 / SCORE-GEO-004

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Current scoring runtime:** `SCORE-GEO-004`

## 1. Principle

`NOT_APPLICABLE` is not failure, missing evidence or score zero.

A dimension is:

- `APPLICABLE` when at least one applicable RuleExecution exists;
- `NOT_APPLICABLE` when executions exist and all are legitimately outside the applicable universe;
- `NOT_CONSOLIDATED` when required executions are missing, applicability is blocked or Coverage/Confidence is insufficient.

Complete absence of RuleExecutions never becomes benign `NOT_APPLICABLE`.

## 2. Blocked prerequisite

`PREREQUISITE_BLOCKED` is not non-applicability.

Reason codes such as:

```text
SEMANTIC_PREREQUISITE_BLOCKED
CONTENT_EXTRACTION_PREREQUISITE_BLOCKED
```

keep the affected dimension non-consolidated until sufficient evidence exists.

## 3. Dimensions and Overall

For each audited device:

1. materialize the SARI dimensions;
2. separate legitimate `NOT_APPLICABLE` dimensions;
3. require sufficient values/Coverage/Confidence for applicable dimensions;
4. persist limitations and excluded dimensions;
5. compute Overall under `SCORE-GEO-004` only.

Overall contract:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

A legitimate `NOT_APPLICABLE` dimension leaves the denominator and receives neither 0 nor 100.

An applicable dimension without value or in `NOT_CONSOLIDATED` prevents publication of a consolidated Overall. No external model artifact is required by 004.

`SCORE-GEO-003` remains historical and used a different calibrated-model contract.

## 4. Structured Data / JSON-LD

JSON-LD is optional/contextual in the general baseline. Absence alone is not a universal readiness failure.

If BR-GEO-034..037 are legitimately `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- absence alone creates no automatic penalty;
- the dimension is not imputed as zero.

If JSON-LD is present, syntax, types/properties and factual coherence become evaluable.

Structured Data can normalize observed facts but must not invent price, rating/review, authorship, dates, product/service facts, claims or entities.

The current parser is oriented to JSON-LD in `script[type="application/ld+json"]`; Microdata/RDFa must not be described as fully covered without equivalent implementation/tests.

## 5. Minimum/contextual premises

| Topic | Class | RASAi effect |
|---|---|---|
| Technically retrievable URL | MINIMUM | Material failure compromises technical readiness. |
| Analyzable document/content | MINIMUM | Dependent dimensions cannot consolidate without a usable basis. |
| Essential content after rendering | MINIMUM when JS applies | Main information must remain retrievable. |
| Identifiable main content | MINIMUM | Basis for semantic/answerability analysis. |
| Important information in retrievable text | MINIMUM | Visual-only/hidden information limits extraction. |
| Indexability coherent with public intent | CONTEXTUAL/MINIMUM for public Search | Intentional blocks can make a URL ineligible for public search. |
| Identifiable topic/intent | SEMANTIC MINIMUM | Required to evaluate what the URL answers. |
| Coherent claims/values | FACTUAL MINIMUM | Contradictions reduce evidence/citation readiness. |
| JSON-LD | OPTIONAL / REINFORCEMENT | When present, it must be valid/coherent. |
| Sitemap | OPTIONAL / DISCOVERY | Useful; absence alone is not FAIL. |
| Canonical | CONTEXTUAL | Important for duplicates/preference; not universal blocker alone. |
| robots.txt | OPTIONAL AS FILE | Absence does not mean blocked; present rules are interpreted. |
| Author/publisher | CONTEXTUAL | Depends on page/claim type. |
| Publication/update date | CONTEXTUAL | Relevant to temporal/editorial content. |
| `llms.txt` | NOT REQUIRED | Not a universal Search & AI requirement. |
| GPTBot allowed | NOT REQUIRED for Search readiness | GPTBot and Search crawlers have distinct purposes. |
| special GEO/AEO markup | NOT REQUIRED | No universal official requirement is assumed. |
| artificial AI chunking | NOT REQUIRED | Not introduced as an artificial scoring rule. |

## 6. Confidence

Confidence represents strength of the auditor conclusion, not text quality.

`LOW` alone does not authorize a content finding/recommendation. Action requires a specific RuleExecution/finding and evidence.

## 7. Reporting

`report/readiness.html` and `report/scoring.html` distinguish Score, Coverage, Confidence, `NOT_APPLICABLE`, `NOT_CONSOLIDATED`, version and limitations.

`report/score-geo-004.html` is only a compatibility alias for `scoring.html`.

## 8. Reproducibility

BR-GEO-054 validates integrity/reproducibility for the persisted `scoring_version`. For current audits, that version is `SCORE-GEO-004`.

Given the same RuleExecutions, contributions, evidence and versioned formula/gates, dimensions and Overall state must be reconstructible without reopening the website or calling AI.

Historical 003 audits remain reproducible under their own persisted contract and must not be silently recalculated as 004.

## 9. Minimum tests

Validate that:

1. missing RuleExecutions do not create artificial consolidation;
2. legitimate `NOT_APPLICABLE` does not receive zero;
3. blocked prerequisites remain blocking;
4. present Structured Data makes relevant rules applicable;
5. PASS/WARNING/FAIL participate per dimension contract;
6. absent legitimate Structured Data receives no artificial score;
7. Overall limitations/excluded dimensions are persisted;
8. BR-GEO-054 is reproducible for persisted version;
9. reports do not equate Confidence LOW with poor content;
10. internal heuristics are distinguished from external sources;
11. different `scoring_version` values are not merged silently.
