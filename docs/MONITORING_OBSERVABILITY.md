# RASAI Monitor & Search/AI Observability

**Status:** IMPLEMENTED — candidate for human smoke before merge.

## Purpose

This feature turns isolated RASAI audits into a longitudinal, evidence-bound workflow without changing the audit source of truth or silently adding new signals to SARI-001.

It answers four different questions with separate methods:

1. **Readiness:** what technical/semantic conditions were observed by the audit?
2. **Observed outcomes:** what did external search/AI systems report or what was observed under a controlled protocol?
3. **Change:** what materially changed between two persisted audits?
4. **Impact hypothesis:** did external outcomes move in the same period as a technical regression/improvement?

The fourth question is explicitly associative. RASAI does not claim causality from temporal coincidence.

## Architecture

```text
AUD-BASELINE/audit.db -----\
                            > RASAI Monitor -> MON-*/report.html + manifest.json
AUD-CURRENT/audit.db ------/

AUD-CURRENT/audit.db (read-only)
          |
          +--> observability.db
          +--> artifacts/observability/*
          +--> report/observability.html
```

`audit.db` is not migrated by monitoring or observability. External observations are stored in the sidecar `observability.db` and preserved artifacts.

## Commands

### Compare two audits

```powershell
rasai monitor compare --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

The comparison classifies signals as applicable into:

- `REGRESSED`
- `IMPROVED`
- `CHANGED`
- `NEW`
- `RESOLVED`
- `UNCHANGED`
- `DATA_UNAVAILABLE`
- `NOT_COMPARABLE`

Scoring versions, devices and URL universes are part of comparability. A `SCORE-GEO-002` historical observation is not silently compared as the same method as `SCORE-GEO-003`.

### Release gate

```powershell
rasai monitor gate --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Exit codes:

- `0`: PASS
- `1`: blocking regression
- `2`: execution/configuration error

Default gate is deterministic. Semantic/LLM-derived rules do not block a release unless explicitly included with `--include-semantic`.

### Change impact

```powershell
rasai monitor impact --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

The report may associate technical regressions with changes in Search Performance, observed indexing/canonical state and CrUX History. Output language must remain `TEMPORAL_ASSOCIATION_ONLY` or equivalent; it must not state that one signal caused another.

## Observed external data

### Google Search Console Search Analytics

Uses the official Search Analytics API. Supported dimensions are persisted as observed records, including query, page/URL, device, country, date and returned metrics such as clicks, impressions, CTR and position.

Credentials/tokens are runtime inputs and are not stored in `observability.db` or report artifacts.

### Google URL Inspection

Uses the official URL Inspection API. The report can compare local declarations with observed external state, including selected canonical and indexing/fetch fields returned by the API.

URL Inspection describes the indexed version known to Google; it is not presented as a live-test substitute.

### CrUX History

Uses the official Chrome UX Report History API. Historical LCP, INP and CLS data remains field data and is not merged with Lighthouse lab metrics or Apdex.

### Bing Search/Chat outcomes

Bing search performance/AI-related data is **import-first** where a documented direct API contract is not available in the implementation. RASAI does not invent an endpoint or scrape the Webmaster portal.

## Indexability Reality Matrix

`report/observability.html` can present, when available:

- audited URL/device;
- HTTP status;
- local meta robots;
- declared canonical;
- external source;
- external verdict/indexing state;
- externally selected canonical;
- canonical alignment.

A canonical difference is an observed divergence, not automatic proof of traffic loss.

## Query × Intent Alignment

Observed search queries can be compared conservatively with intents already persisted by RASAI rules (`BR-GEO-038` / `BR-GEO-048`). The current matching is lexical and explanatory. It is not a ranking factor, keyword score or causal model.

Statuses include:

- `ALIGNED`
- `PARTIAL`
- `UNMATCHED`
- `INTENT_NOT_AVAILABLE`

## Potential Cannibalization

A conservative candidate is surfaced when multiple URLs materially share the same observed query. The implementation requires at least two URLs with material impression share (current rule: each at least 20% of observed impressions for that source/query).

The label is **Potential Search Cannibalization**. It is a review candidate, not proof that the URLs are harming each other.

## Additional evidence-bound diagnostics

The observability report adds advisory diagnostics without adding a new SARI score:

- Product structured-data documentation completeness;
- Breadcrumb structured-data documentation completeness;
- Organization/entity completeness observations;
- cross-page entity consistency;
- date/freshness conflicts;
- hreflang absolute URL/syntax/self-reference/reciprocity checks;
- retrieval/chunkability observations;
- tables without explicit header relationships;
- repeated finding/template clusters and probable shared-component causes when a reliable selector exists.

Structured-data checks are documentation checks, not a fake Rich Results Test API and not a Google eligibility score.

## SCORE-GEO-003 calibration dataset manager

Before fitting a model, inspect dataset sufficiency:

```powershell
rasai scoring dataset --audits-root audits --dataset-version GEO-CAL-001
```

The dataset manifest records a deterministic fingerprint and pre-fit gates such as domain count, validation-domain capacity, engine diversity, query coverage, repetitions, temporal coverage and observation count.

`READY_FOR_MODEL_FIT` does **not** mean `VALIDATED`. Model validation/promotion still requires the post-fit gates defined by SCORE-GEO-003, including AUC and Brier criteria.

## HTML surfaces

Per-audit report pages remain methodologically separated. The canonical navigation registry includes a page only when its HTML file exists:

- `index.html`
- `readiness.html`
- `score-geo-003.html`
- `mobile.html`
- `desktop.html`
- `remediation.html`
- `content-suggestions.html`
- `crawling-discovery.html`
- `accessibility.html`
- `web-performance.html`
- `apdex.html`
- `apdex-experience.html`
- `ai-visibility.html`
- `observability.html`
- `ai-usage.html`
- `references.html`

This prevents a later optional-report normalization pass from removing links to optional pages already materialized.

## Method status

- Public readiness index: `SARI-001`.
- Current scoring runtime for new audits: `SCORE-GEO-003`.
- Historical scoring: `SCORE-GEO-002`.
- Observability outcomes: separate from SARI/scoring unless a future explicit versioned methodology says otherwise.
- Monitoring: derived/read-only comparison, not a new score.

## Human smoke requirements

Before merge, validate at minimum:

1. two real comparable `AUD-*` workspaces;
2. `monitor compare` HTML and manifest;
3. `monitor gate` exit behavior for a safe pair and a deliberately regressed fixture/pair if available;
4. `observability.html` with no external dataset (graceful empty state);
5. one Search Console/URL Inspection collection using valid credentials if available;
6. one CrUX History collection for an eligible URL/origin;
7. one import-first Bing dataset if available;
8. navigation consistency across all materialized HTML pages;
9. `SCORE-GEO-003` shown as current and `SCORE-GEO-002` only as historical;
10. source `audit.db` hashes unchanged by monitoring/observability operations.
