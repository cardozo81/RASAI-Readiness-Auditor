# RASAI Monitor, Observability & Quality

**Status:** IMPLEMENTED — candidate for human smoke before merge.

## Purpose

This capability turns isolated RASAI audits into a longitudinal, evidence-bound workflow without changing the audit source of truth or silently adding new signals to `SARI-001`.

It keeps five questions methodologically separate:

1. **Readiness:** what technical/semantic conditions were observed by the audit?
2. **Observed outcomes:** what did external Search/AI systems report?
3. **Change:** what materially changed between persisted audits?
4. **Association:** did an observed outcome move across a comparable period while a technical regression also existed?
5. **Decision quality:** is the audit evidence sufficiently complete/reliable to support remediation decisions?

RASAI does not convert temporal coincidence into causality.

## Architecture

```text
AUD-BASELINE/audit.db -----\
                            > RASAI Monitor -> MON-*/report.html + manifest.json + impact.html
AUD-CURRENT/audit.db ------/

AUD-CURRENT/audit.db (read-only)
          |
          +--> observability.db          # RASAI-OBS-002
          +--> artifacts/observability/*
          +--> report/observability.html
          +--> report/quality.html

AUD-* collection
          |
          +--> Fix Verification -> verification/VER-*/report.html
          +--> Evidence Timeline -> quality/TIMELINE-*/report.html
```

`audit.db` is not migrated by Monitor, Observability or Quality. External observations are derived/rebuildable sidecar data.

## Observability sidecar — RASAI-OBS-002

`RASAI-OBS-002` changes observation row identity from a global `record_id` to the composite identity:

```text
(dataset_id, record_id)
```

This is required because independent collections legitimately reuse local IDs such as `GSC-SA-00000001`. Existing OBS-001 sidecars are migrated automatically while preserving their rows. `audit.db` is not touched by this migration.

Dataset provenance persists:

- source type;
- capture method;
- observation period when available;
- artifact path;
- artifact SHA-256;
- collection time;
- source-specific metadata.

Secrets are never persisted.

## RASAI Monitor

### Compare

```powershell
rasai monitor compare --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Signals are classified, as applicable, as:

- `REGRESSED`
- `IMPROVED`
- `CHANGED`
- `NEW`
- `RESOLVED`
- `UNCHANGED`
- `DATA_UNAVAILABLE`
- `NOT_COMPARABLE`

Different scoring versions are not silently converted. `SCORE-GEO-002` is historical and is not treated as methodologically equivalent to `SCORE-GEO-003`.

### Release gate

```powershell
rasai monitor gate --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Exit codes:

- `0` — PASS;
- `1` — blocking regression;
- `2` — execution/configuration error.

The **default gate** contains only:

- deterministic BR-GEO rules allowed by the gate contract;
- deterministic page-state regressions.

The following families are excluded unless explicitly opted in:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

This prevents semantic/AI findings, synthetic variance or aggregate counters from entering a release decision indirectly.

### Change Impact

```powershell
rasai monitor impact --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

For each source, RASAI selects one latest dataset per AUD instead of summing overlapping historical collections. Observation windows are classified as:

- `ALIGNED_WINDOW`
- `PARTIAL_OVERLAP`
- `NON_OVERLAPPING`
- `UNKNOWN_PERIOD`
- `DATA_UNAVAILABLE`

`TEMPORAL_ASSOCIATION_ONLY` can be emitted only for aligned/partially overlapping windows. Non-overlapping or unknown periods do not receive an association claim.

Missing metrics stay missing. A `NULL` click/CTR/position field is never converted into an observed zero.

## Google Search Console

Authentication uses an OAuth bearer token supplied at runtime through `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` by default.

### Property discovery

```powershell
rasai observe gsc-sites --audit AUD-...
```

Persists accessible Search Console properties and permission level. This helps preflight the exact `siteUrl` required by later calls.

### Search Analytics

```powershell
rasai observe gsc-search `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31 `
  --max-rows 100000
```

`--max-rows` is a real hard cap. API page size is bounded independently at the documented maximum.

Search Analytics may return the top rows rather than every row available for the property; the sidecar records this coverage limitation.

### Search Appearance

```powershell
rasai observe gsc-appearance `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31
```

This uses the documented `searchAppearance` dimension. Search Appearance is persisted under a distinct source provenance and does not overwrite standard Search Analytics observations.

### URL Inspection

```powershell
rasai observe gsc-inspect `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --max-urls 25
```

Only URLs persisted in the source AUD are eligible. URL Inspection describes the indexed version known to Google; it is not presented as a live-test substitute.

### Sitemaps

```powershell
rasai observe gsc-sitemaps --audit AUD-... --site-url "sc-domain:example.com"
```

Persists observed sitemap path, submission/download times, pending state, warnings/errors and submitted counts. Deprecated `contents[].indexed` is deliberately not used as evidence.

## Google Generative AI Performance — import-first

RASAI does **not** presume an undocumented API endpoint for the Search Console Generative AI Performance reports.

Search export:

```powershell
rasai observe google-ai-import --audit AUD-... --file genai-search.csv --surface search
```

Discover export:

```powershell
rasai observe google-ai-import --audit AUD-... --file genai-discover.csv --surface discover
```

Search and Discover are stored as distinct source types. Current normalized contract persists only fields actually present, notably impressions plus page/date/device/country when supplied.

RASAI does not invent:

- clicks;
- CTR;
- position;
- query;
- citation count.

Export suppression/rounding tokens such as `~` or `-` are recorded with explicit metadata. An exported zero is not independently asserted as proof of zero visibility.

### Google GenAI control state

```powershell
rasai observe google-ai-control --audit AUD-... --state INCLUDE
rasai observe google-ai-control --audit AUD-... --state EXCLUDE
rasai observe google-ai-control --audit AUD-... --state INHERIT
```

This is an observed/manual Search Console configuration fact. It does not change SARI.

## CrUX History

```powershell
rasai observe crux-history `
  --audit AUD-... `
  --target https://example.com/ `
  --scope url `
  --periods 40
```

Historical LCP/INP/CLS remains field data and is not merged with Lighthouse lab metrics or Apdex.

## Bing Search/Chat outcomes

```powershell
rasai observe bing-import --audit AUD-... --file bing-search-performance.csv
```

Bing remains import-first where a direct documented contract is not implemented. RASAI does not scrape the portal or invent endpoints.

## Observability diagnostics

`report/observability.html` can include:

- Indexability Reality Matrix;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- Product/Breadcrumb documentation checks;
- Organization/entity completeness;
- entity consistency;
- persisted-date freshness conflicts;
- hreflang checks;
- retrieval/chunkability observations;
- repeated template/component clusters;
- CrUX History;
- dataset provenance.

Freshness uses the persisted audit date (`completed_at`, then `started_at`, `created_at`, then captured snapshot time). Regenerating the same report in the future must not change a freshness verdict merely because the wall-clock date changed.

## Search & AI content controls

Quality reports publisher controls as evidence, not penalties:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

Only the relevant `X-Robots-Tag` response header is preserved in technical browser metadata; unrelated HTTP headers are not copied into this feature.

## RASAI Quality

### Per-audit quality report

```powershell
rasai quality report --audit AUD-...
```

Generates `report/quality.html` with:

- Audit Health / Data Quality;
- Evidence Confidence per finding;
- Operational Priority (`P0`–`P3`) separated from SARI;
- Coverage Map (URL × evidence domain);
- Search/AI content controls;
- Recommendation Validation;
- executive top priorities.

Audit Health validates the audit evidence itself. It is not another readiness score.

### Fix Verification

```powershell
rasai quality verify `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT `
  [--url https://example.com/page] `
  [--rule BR-GEO-011]
```

Statuses are evidence-bound transitions such as:

- `FIXED`
- `PARTIALLY_FIXED`
- `NOT_FIXED`
- `NOT_VERIFIABLE`

This proves only the persisted rule transition between selected AUDs; it does not prove downstream Search/AI impact.

### Evidence Timeline

```powershell
rasai quality timeline --audits-root audits [--domain example.com] [--url https://example.com/page]
```

Generates a longitudinal evidence report using persisted audit metadata, rule states and dimensions. It does not rewrite historical AUDs.

## SCORE-GEO-003 calibration

```powershell
rasai scoring dataset --audits-root audits --dataset-version GEO-CAL-001
```

The dataset manager remains pre-fit only. `READY_FOR_MODEL_FIT != VALIDATED`.

The real calibration collector now matches feature granularity to target granularity: when the controlled visibility outcome is not device-specific, one AUD-level feature vector is produced rather than duplicating the same target against separate mobile/desktop vectors.

Calibration reads source AUDs with SQLite `mode=ro` / `query_only`. Per-engine metrics are diagnostic robustness evidence; promotion still follows the explicitly versioned SCORE-GEO-003 protocol.

## HTML surfaces

Canonical per-AUD navigation includes an item only when the corresponding file exists:

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
- `quality.html`
- `ai-usage.html`
- `references.html`

## Human smoke minimum

Before merge, validate at minimum:

1. two comparable real `AUD-*` workspaces;
2. `monitor compare`, `monitor gate` and `monitor impact`;
3. a deliberately regressed pair for gate behavior;
4. `observability.html` empty state;
5. `quality.html` on a completed AUD;
6. one Fix Verification pair;
7. one Evidence Timeline over multiple AUDs;
8. Search Console property discovery, Search Analytics and URL Inspection with valid OAuth if available;
9. Search Appearance and Sitemaps with valid OAuth if available;
10. one CrUX History collection;
11. one Google GenAI export import if available;
12. navigation consistency across all materialized HTML pages;
13. `SCORE-GEO-003` shown as current and `SCORE-GEO-002` only as historical;
14. SHA-256 of source `audit.db` unchanged by Monitor/Observability/Quality operations.
