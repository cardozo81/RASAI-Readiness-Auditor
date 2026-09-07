# RASAi Monitoring, Observability & Quality — Delivery Status

**Status:** IMPLEMENTED CANDIDATE — automated CI is mandatory on the current PR head; human smoke remains required before merge.
**Branch:** `feat/rasai-monitoring-observability`
**PR:** #82

## Delivered product areas

### Longitudinal Monitoring

- read-only comparison of persisted AUD workspaces;
- explicit `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `DATA_UNAVAILABLE` and `NOT_COMPARABLE` semantics;
- no silent conversion between scoring contracts;
- materiality thresholds per signal family;
- deterministic Release Gate;
- default fail-closed when the audit pair is not comparable;
- material `NEW` failures block by default;
- explicit overrides `--allow-noncomparable` and `--allow-new-failures`;
- opt-in only for semantic rules, performance, synthetic metrics, finding aggregates and SCORE dimensions;
- Change Impact with window comparability and `TEMPORAL_ASSOCIATION_ONLY`, never causal attribution.

### Search & AI Observability

- `RASAI-OBS-002` sidecar with composite `(dataset_id, record_id)` observation identity;
- automatic OBS-001 PK migration without modifying `audit.db` or rewriting historical dataset format provenance;
- preserved artifacts + SHA-256;
- Search Console property discovery;
- Search Console Sitemaps read-only;
- Search Analytics;
- Search Appearance as distinct provenance;
- URL Inspection restricted to URLs persisted in the AUD;
- systemic URL Inspection failures abort the batch instead of repeating authentication/quota/network failures per URL;
- CrUX History direct collection;
- direct/imported Search Analytics/CrUX scoped to the audited origin;
- out-of-scope Search Analytics rows are not persisted in normalized rows or artifacts;
- Bing Search Performance import-first with surface-aware dataset identity;
- Google Generative AI Performance import-first for Search/Discover;
- Google GenAI INCLUDE/EXCLUDE/INHERIT control observation;
- generic `RASAI-OBS-IMPORT-001` with URL/origin/period validation.

### Outcome interpretation hardening

- missing metrics remain missing; `NULL` is never synthesized as zero;
- Google Generative AI Performance exports remain non-directional in Change Impact because downloaded zero may represent report values that were unavailable/non-numeric;
- latest dataset selection avoids double-summing overlapping historical collections;
- temporal association requires aligned or partially overlapping periods.

### Diagnostics

- Indexability Reality Matrix;
- Query × Intent Alignment;
- conservative Potential Search Cannibalization candidates;
- structured-data documentation checks;
- hreflang/international-search checks;
- entity consistency;
- persisted-date freshness diagnostics;
- retrieval/chunkability diagnostics;
- template/root-cause clustering.

### Audit Quality & Verification

- `report/quality.html`;
- Audit Health / Data Quality;
- Evidence Confidence;
- Coverage Map;
- Recommendation Validation;
- publisher controls (`nosnippet`, `max-snippet`, `data-nosnippet`, `X-Robots-Tag`);
- actionable Operational Priority P0–P3, excluding `RESOLVED`/`CLOSED`/`DISMISSED` from the executive work queue while retaining their historical evidence;
- Fix Verification;
- Evidence Timeline;
- artifact reads confined to the AUD workspace.

### SCORE-GEO-003 calibration support

- calibration dataset manager;
- deterministic dataset fingerprint/manifest;
- pre-fit sufficiency gates;
- read-only source AUD access;
- feature/target granularity correction for outcomes without device specificity;
- `READY_FOR_MODEL_FIT != VALIDATED` maintained explicitly.

### Reporting / Navigation

- `report/observability.html`;
- `report/quality.html`;
- `MON-*/report.html`, `manifest.json`, optional `impact.html`;
- `VER-*/report.html`;
- `TIMELINE-*/report.html`;
- canonical optional-page navigation registry that preserves ordering and active-page state.

## Safety gates implemented

The dedicated CI covers, in addition to repository-wide regressions:

- OBS-001→OBS-002 migration;
- repeated local record IDs across datasets;
- Search Analytics hard caps and origin scoping;
- CrUX direct/imported origin scoping;
- URL Inspection systemic failure isolation;
- Bing surface identity;
- Google GenAI missing/ambiguous metrics;
- release gate comparability and `NEW` failure policy;
- Quality actionable priorities;
- Quality filesystem confinement;
- SCORE-GEO-003 pre-fit/calibration safety;
- crawling/discovery, Synthetic User Experience Apdex, Observed Generative Visibility, source-quality and consolidated-reporting regression suites.

## Methodological boundary

- `SARI-001` is the public readiness index;
- `SCORE-GEO-003` is the current scoring runtime for new audits;
- `SCORE-GEO-003` is the scoring method used by the current pipeline;
- observed outcomes do not automatically enter SARI/scoring;
- Quality is decision-support, not another readiness score;
- Monitoring detects change/association and does not infer causality.

## Remaining acceptance step

No implementation item in this roadmap is intentionally deferred to a new coding phase. The remaining pre-merge acceptance step is **human smoke on real persisted AUDs and, where credentials/data are available, real external integrations**.

Operational commands and smoke procedure: [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md).
Normative contracts: [`specification/27_MONITORING_OBSERVABILITY.md`](specification/27_MONITORING_OBSERVABILITY.md) and [`specification/28_AUDIT_QUALITY_VERIFICATION.md`](specification/28_AUDIT_QUALITY_VERIFICATION.md).
