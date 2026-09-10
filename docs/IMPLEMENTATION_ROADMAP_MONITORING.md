# RASAi Monitoring, Observability & Quality - Current Capability Status

**Estado:** IMPLEMENTED / INTEGRATED

This document summarizes the capabilities present in the current RASAi contract. It is not a branch/PR delivery log.

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
- persisted source artifacts + SHA-256;
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
- Google Generative AI Performance exports remain non-directional in Change Impact when source values do not support a directional conclusion;
- latest compatible dataset selection avoids double-summing overlapping collections;
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
- actionable Operational Priority P0-P3, excluding `RESOLVED`/`CLOSED`/`DISMISSED` from the executive work queue while retaining evidence needed for timeline/comparison;
- Fix Verification;
- Evidence Timeline;
- artifact reads confined to the AUD workspace;
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

## Safety gates

Dedicated automated coverage includes:

- composite observation identity `(dataset_id, record_id)`;
- Search Analytics hard caps and origin scoping;
- CrUX direct/imported origin scoping;
- URL Inspection systemic failure isolation;
- Bing surface identity;
- Google GenAI missing/ambiguous metrics;
- release gate comparability and `NEW` failure policy;
- Quality actionable priorities;
- Quality filesystem confinement;
- crawling/discovery, Synthetic User Experience Apdex, Observed Generative Visibility, source-quality and consolidated-reporting regression suites.

## Methodological boundary

- `SARI-001` is the public readiness index;
- observed outcomes do not automatically enter SARI/scoring;
- Quality is decision-support, not another readiness score;
- Monitoring detects change/association and does not infer causality.

## Operational validation

Automated regression is mandatory for changes in these domains. Human smoke on representative persisted AUDs and real external integrations is used when credentials/network access are available and the change requires environmental validation.

Operational commands and smoke procedure: [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md).
Normative contracts: [`specification/27_MONITORING_OBSERVABILITY.md`](specification/27_MONITORING_OBSERVABILITY.md) and [`specification/28_AUDIT_QUALITY_VERIFICATION.md`](specification/28_AUDIT_QUALITY_VERIFICATION.md).
