# Aplicabilidade de Dimensões e Premissas Mínimas - SARI-001 / SCORE-GEO-004

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Current scoring runtime:** `SCORE-GEO-004`  
**Aggregation contract:** `HIERARCHICAL_WEIGHTED_READINESS_V1`

## 1. Principle

`NOT_APPLICABLE` is not failure, missing evidence or score zero.

A dimension is:

- `APPLICABLE` when at least one applicable RuleExecution exists;
- `NOT_APPLICABLE` when executions exist and the dimension's observed universe is legitimately outside applicability;
- `NOT_CONSOLIDATED` when the dimension has no usable measurement, applicability is blocked or its Coverage/Confidence is insufficient;
- `PARTIAL` when useful measurement exists but the dimension does not meet its complete consolidation gate.

Complete absence of RuleExecutions for a dimension never becomes benign `NOT_APPLICABLE`.

The Overall may still have a numeric value when a **non-critical** applicable dimension is not sufficiently measured. In that case the missing dimension contributes zero Coverage, its numeric weight is not imputed as either 0 or 100, and the Overall can only be `CONSOLIDATED` if the remaining weighted Coverage/Confidence satisfy the published gate.

## 2. Missing execution versus explicit unresolved execution

The scoring pipeline must preserve the difference between:

```text
not applicable
unresolved/unknown
execution error
no execution materialized
```

For an applicable rule/group, acquisition or prerequisite failure should materialize an explicit RuleExecution state such as `UNKNOWN`, `ERROR` or a prerequisite-blocked `NOT_APPLICABLE` as defined by that rule family. A required applicable group must not disappear silently merely to reduce the Coverage denominator.

At dimension level, complete absence of executions yields:

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_CONSOLIDATED
limitation = NO_RULE_EXECUTIONS
```

This dimension remains in the Overall applicable universe unless applicability was positively established as `NOT_APPLICABLE`.

## 3. Blocked prerequisite

`PREREQUISITE_BLOCKED` is not benign non-applicability.

Reason codes such as:

```text
SEMANTIC_PREREQUISITE_BLOCKED
CONTENT_EXTRACTION_PREREQUISITE_BLOCKED
```

keep the affected measurement unresolved. They cannot be promoted to `NOT_APPLICABLE` solely to elevate score, Coverage or Consolidation.

For critical dimensions, insufficient measurement also blocks Overall consolidation through the critical measurement gate.

## 4. Dimensions and Overall

For each audited device:

1. materialize the eleven SARI dimensions;
2. separate legitimate `NOT_APPLICABLE` dimensions;
3. preserve explicit unresolved/error states;
4. calculate dimension Value, Coverage, Confidence and Consolidation independently;
5. calculate the weighted Overall only over measured/applicable numeric dimension values;
6. calculate Overall Coverage over the complete applicable weighted universe;
7. apply Confidence and critical measurement gates;
8. persist limitations, excluded dimensions and Critical Readiness Gate states.

Overall contract:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Dimension weights:

| Dimension | Weight |
|---|---:|
| `DISCOVERY_ACCESS` | 15% |
| `INDEXABILITY` | 15% |
| `CONTENT_EXTRACTABILITY` | 15% |
| `SEMANTIC_STRUCTURE` | 7% |
| `ENTITY_CLARITY` | 8% |
| `STRUCTURED_DATA` | 5% |
| `ANSWERABILITY` | 7% |
| `CITATION_READINESS` | 7% |
| `EVIDENCE_TRUST` | 8% |
| `INTENT_COVERAGE` | 5% |
| `CONTENT_VALUE` | 8% |

A legitimate `NOT_APPLICABLE` dimension leaves the denominator and receives neither 0 nor 100.

A non-critical applicable dimension without value does **not** receive a fabricated numeric score. It lowers Overall Coverage and Confidence according to its published weight. Overall consolidation is permitted only if the weighted measurement still satisfies the 80% Coverage gate and HIGH/MEDIUM Confidence.

Critical dimensions are stricter: `DISCOVERY_ACCESS`, `INDEXABILITY` and `CONTENT_EXTRACTABILITY` cannot remain insufficiently measured in a consolidated Overall.

## 5. Score, Coverage and Consolidation are separate

The contract deliberately separates:

```text
Score         quality of the evaluated universe
Coverage      weighted completeness of the applicable measurement
Confidence    strength of the measurement
Consolidation sufficiency for analytical publication
Critical Gate operational readiness state
```

Therefore:

- `UNKNOWN`/`ERROR` do not become quality zero;
- missing non-critical measurement does not become quality zero or 100;
- a high numeric Score with incomplete measurement must expose reduced Coverage/Confidence;
- a low numeric Score can be `CONSOLIDATED` when the poor quality was measured strongly;
- a numerically high SARI may coexist with operational `BLOCKED` if a critical observed condition failed.

## 6. Critical measurement and readiness gates

Critical dimensions:

```text
DISCOVERY_ACCESS
INDEXABILITY
CONTENT_EXTRACTABILITY
```

A critical dimension that is applicable but lacks sufficient measurement blocks Overall `CONSOLIDATED` regardless of aggregate Coverage.

Separately, Critical Readiness Gates summarize observed operational conditions:

- Discovery Gate: `PAGE_ACCESS`, `ROBOTS`, `REDIRECT`;
- Indexability Gate: `INDEX_DIRECTIVES`, `CANONICAL`, `SOFT_ERROR`;
- Extraction Gate: `RENDER_ACCESS`, `JS_CONTENT`, `CONTENT_EXTRACTION`.

Gate states:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

Readiness status:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

These states do not rewrite the numeric SARI.

## 7. Structured Data / JSON-LD

JSON-LD is optional/contextual in the general baseline. Absence alone is not a universal readiness failure.

If BR-GEO-034..037 are legitimately `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- absence alone creates no automatic penalty;
- the dimension is not imputed as zero;
- its 5% weight leaves the applicable Overall denominator.

If JSON-LD is present, syntax, types/properties and factual coherence become evaluable.

Structured Data can normalize observed facts but must not invent price, rating/review, authorship, dates, product/service facts, claims or entities.

The current parser is oriented to JSON-LD in `script[type="application/ld+json"]`; Microdata/RDFa must not be described as fully covered without equivalent implementation/tests.

## 8. Content Value

`CONTENT_VALUE` is an 8% `RASAI_HEURISTIC` dimension.

Its baseline rules measure only evidence that can be defended from preserved content:

- useful/specific non-trivial content;
- explicit first-party differentiation/experience/analysis/data when evidenced;
- proportional depth/context.

Absence of proof of differentiation or originality remains `UNKNOWN`, not `FAIL`. That unresolved weight reduces Coverage instead of punishing quality without evidence.

## 9. Minimum/contextual premises

| Topic | Class | RASAi effect |
|---|---|---|
| Technically retrievable URL | MINIMUM | Material failure compromises technical readiness. |
| Analyzable document/content | MINIMUM | Dependent dimensions cannot consolidate without a usable basis. |
| Essential content after rendering | MINIMUM when JS applies | Main information must remain retrievable. |
| Identifiable main content | MINIMUM | Basis for semantic/answerability/content-value analysis. |
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

## 10. Confidence

Confidence represents strength of the auditor conclusion, not text quality.

Dimension baseline:

```text
HIGH        Coverage >= 90%, evidence complete, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         measurable but below HIGH/MEDIUM requirements
UNAVAILABLE no evaluated applicable weight
```

Overall Confidence combines weighted confidence with strict treatment of critical dimensions. A critical LOW/UNAVAILABLE dimension keeps Overall Confidence LOW.

`LOW` alone does not authorize a content finding/recommendation. Action requires a specific RuleExecution/finding and evidence.

## 11. Consolidation thresholds

Dimension:

```text
CONSOLIDATED     Coverage >= 80% and Confidence HIGH/MEDIUM
PARTIAL          measurable with Coverage >= 50% below complete gate
NOT_CONSOLIDATED Coverage < 50% or Confidence UNAVAILABLE
NOT_APPLICABLE   legitimately outside applicable universe
```

Overall:

```text
CONSOLIDATED
  numeric value exists
  Overall Coverage >= 80%
  Overall Confidence HIGH/MEDIUM
  no applicable critical dimension lacks sufficient measurement

PARTIAL
  numeric value exists
  Coverage >= 50%
  Confidence available
  complete gate not satisfied

NOT_CONSOLIDATED
  no numeric measurement
  critical measurement blocker
  or measurement below minimum gate
```

## 12. Reporting

`report/readiness.html` and `report/scoring.html` distinguish:

- Score;
- Coverage;
- Confidence;
- Consolidation;
- `NOT_APPLICABLE`;
- `NOT_CONSOLIDATED`;
- scoring/aggregation contract;
- Critical Readiness Gates;
- limitations and excluded dimensions.

A report must not present a numeric value computed from the measured universe as if Coverage were 100% when it is not.

## 13. Reproducibility and comparability

BR-GEO-054 validates integrity/reproducibility for the persisted scoring contract. Current audits use `SCORE-GEO-004` with `HIERARCHICAL_WEIGHTED_READINESS_V1`.

Given the same RuleExecutions, contributions, evidence and versioned formula/gates, dimensions and Overall state must be reconstructible without reopening the website or calling AI.

Historical 003 audits remain reproducible under their own persisted contract and must not be silently recalculated as 004.

Because RASAi remains pre-production, development audits created under the previous experimental 004 aggregation are non-comparable with the weighted contract and should be regenerated when reused. The aggregation/version metadata must prevent silent comparison.

## 14. Minimum tests

Validate that:

1. complete absence of a dimension's RuleExecutions produces `NOT_CONSOLIDATED`, never benign `NOT_APPLICABLE`;
2. a missing non-critical dimension lowers weighted Overall Coverage and is explicitly limited rather than imputed as 0 or 100;
3. a missing/insufficient critical dimension blocks Overall consolidation;
4. legitimate `NOT_APPLICABLE` receives no artificial zero or maximum score;
5. blocked prerequisites remain unresolved/blocking rather than benignly non-applicable;
6. present Structured Data makes relevant rules applicable;
7. `PASS`/`WARNING`/`FAIL` participate in the value per dimension/group contract;
8. `UNKNOWN`/`ERROR` reduce Coverage/Confidence without becoming `FAIL`;
9. page count does not multiply scoring-group importance;
10. deterministic evidence takes precedence over AI corroboration in the same scope/group;
11. absent legitimate Structured Data receives no artificial score;
12. Overall limitations/excluded dimensions and Critical Gate states are persisted;
13. BR-GEO-054 is reproducible for the persisted contract;
14. reports do not equate Confidence LOW with poor content;
15. internal heuristics are distinguished from external sources;
16. incompatible scoring/aggregation contracts are not merged silently.
