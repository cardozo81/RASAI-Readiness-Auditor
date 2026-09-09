# WORKFLOWS.md

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Scoring:** `SCORE-GEO-004`

## 1. Primary audit workflow

```text
Initialize
→ Resolve Device Context
→ Discover
→ Acquire/Render selected contexts
→ Technical analysis
→ Extract evidence/content
→ Semantic analysis or fallback
→ Compare Desktop × Mobile when applicable
→ Findings
→ Dimension scores
→ SCORE-GEO-004 Overall
→ Priority / remediation
→ Static report site
→ Complete
```

Core principles are Evidence First, failure isolation, explicit device scope, optional AI and separation between readiness, observed outcomes, Web Performance, accessibility and Apdex.

## 2. Device context

Public scope is `mobile`, `desktop` or `both`. Only selected/materialized contexts may trigger downstream rendering, analysis or external calls.

Desktop × Mobile comparison is applicable only when both contexts exist. A single-context audit does not treat the missing comparison context as a rendering failure.

## 3. Discovery, acquisition and evidence

Discovery normalizes/deduplicates input and discovered URLs, applies origin/scope policy and `max_pages`, and persists enough provenance to explain the audited universe.

Each selected page/device context preserves the evidence required by the pipeline, including HTTP state, RAW/rendered content and extracted technical/semantic facts as applicable.

Failure of an extractor, browser, provider or optional service is distinguished from a website failure.

## 4. Semantic analysis

AI is optional. When available, semantic output is accepted only after local contract/schema/evidence validation. When unavailable or insufficient, semantic-only rules may remain `UNKNOWN` rather than becoming `FAIL`.

Provider failure is operational state, not a website finding. Business Rules remain provider-neutral.

## 5. Findings and scoring

The scoring workflow:

- validates evidence/finding integrity;
- computes deterministic dimension contributions;
- computes dimension Score and Coverage;
- derives Confidence and Consolidation;
- computes Overall under `SCORE-GEO-004`;
- validates BR-GEO-054 reproducibility.

Overall contract:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Rules:

- applicable dimensions have equal Overall weight;
- legitimate `NOT_APPLICABLE` dimensions leave the denominator;
- an applicable dimension without value or `NOT_CONSOLIDATED` prevents consolidated Overall;
- Overall Coverage is the mean Coverage of applicable dimensions;
- Overall Confidence is the minimum Confidence of applicable dimensions;
- consolidated Overall requires Coverage >= 80% and Confidence HIGH/MEDIUM;
- a calculable result may be PARTIAL when Coverage >= 50% and Confidence is available;
- insufficient evidence never becomes zero.

## 6. Recommendations and remediation

Recommendations are derived from persisted findings/evidence and approved remediation recipes. Proposed examples are not observed evidence. Remediation does not alter the score by itself.

## 7. Static report site

Canonical entry:

```text
report/index.html
```

Canonical method pages:

```text
report/readiness.html
report/scoring.html
```

Other domain pages are materialized conditionally, including Mobile/Desktop, remediation, content suggestions, crawling/discovery, accessibility, Web Performance, both Apdex domains, AI visibility, Observability, Quality, AI usage and references.

Opening static HTML does not trigger crawling, AI or external API collection. `audit.db` + artifacts remain source evidence.

## 8. Completion and derived workflows

A completed audit can subsequently feed read-only/derived workflows:

- Monitoring (`compare`, `gate`, `impact`);
- Observability/imports;
- Quality/Fix Verification/Timeline;
- Product Platform indexing and deployment comparisons.

These workflows preserve the source `audit.db` and do not silently recalculate historical scoring.
