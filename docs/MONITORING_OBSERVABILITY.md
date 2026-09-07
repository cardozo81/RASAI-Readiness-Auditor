# RASAI Monitor, Observability & Quality

**Status:** IMPLEMENTED CANDIDATE — human smoke required before merge.

## Purpose

This capability turns isolated RASAI audits into a longitudinal, evidence-bound workflow without changing the audit source of truth or silently adding new signals to `SARI-001`.

It keeps five questions methodologically separate:

1. **Readiness:** what technical/semantic conditions were observed by the audit?
2. **Observed outcomes:** what did external Search/AI systems report?
3. **Change:** what materially changed between persisted audits?
4. **Association:** did an outcome move across a comparable period while a technical regression also existed?
5. **Decision quality:** is the audit evidence complete/reliable enough to support remediation decisions?

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

Observation rows are identified by:

```text
(dataset_id, record_id)
```

Independent collections may legitimately reuse local IDs. OBS-001 sidecars using global `record_id` are migrated automatically while preserving rows and historical dataset metadata. `audit.db` is not touched.

Dataset provenance persists source type, capture method, period, artifact path/SHA-256, collection time and source metadata. Secrets are never persisted.

## RASAI Monitor

### Compare

```powershell
rasai monitor compare --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Possible states include:

```text
REGRESSED
IMPROVED
CHANGED
NEW
RESOLVED
UNCHANGED
DATA_UNAVAILABLE
NOT_COMPARABLE
```

Different scoring versions are not silently converted. `SCORE-GEO-002` remains historical and is not treated as methodologically equivalent to `SCORE-GEO-003`.

### Release gate

```powershell
rasai monitor gate --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Exit codes:

- `0` — PASS;
- `1` — blocking deterioration or non-comparable pair;
- `2` — execution/configuration error.

The default gate is **deterministic and fail-closed**:

- deterministic BR-GEO rules;
- deterministic page-state changes;
- baseline/current domain set must be comparable;
- material `NEW` FAIL/WARNING states are eligible for blocking, not only `REGRESSED` events.

Explicit escape hatches:

```text
--allow-noncomparable
--allow-new-failures
```

These exist for deliberate release policies and are not defaults.

The following families are excluded until opt-in:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

This prevents semantic/AI findings, synthetic variance or aggregate counters from entering release decisions indirectly.

### Change Impact

```powershell
rasai monitor impact --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

RASAI selects one latest dataset per source/AUD rather than summing overlapping historical collections.

Observation windows:

```text
ALIGNED_WINDOW
PARTIAL_OVERLAP
NON_OVERLAPPING
UNKNOWN_PERIOD
DATA_UNAVAILABLE
```

`TEMPORAL_ASSOCIATION_ONLY` is emitted only for aligned/partially overlapping periods. Missing metrics stay missing; `NULL` is never converted into zero.

Google Generative AI Performance exports are deliberately **non-directional** in Change Impact. Their values can be shown and compared, but a lower/higher exported impression value is not automatically `REGRESSED`/`IMPROVED`, because unavailable/non-numeric report values may be downloaded as zero.

## Google Search Console

OAuth bearer token default:

```powershell
$env:GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN="..."
```

The token is runtime-only.

### Property discovery

```powershell
rasai observe gsc-sites --audit AUD-...
```

Read-only inventory of accessible Search Console properties/permission levels for preflight.

### Sitemaps

```powershell
rasai observe gsc-sitemaps --audit AUD-... --site-url "sc-domain:example.com"
```

Read-only. Deprecated `contents[].indexed` is not normalized as current evidence.

### Search Analytics

```powershell
rasai observe gsc-search `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31 `
  --max-rows 100000
```

The collector requires the `page` dimension internally so each row can be attached to the AUD. Rows outside the AUD's exact normalized origins are removed from both normalized storage and the preserved per-AUD response artifact. Metadata reports how many API rows were seen/excluded.

If the API returns data but none belongs to the audited origin, collection fails as a property/scope configuration error rather than creating a misleading dataset.

`--max-rows` is a hard local cap; API page size remains bounded to the documented maximum. Search Analytics may still return top rows rather than every available row.

### Search Appearance

```powershell
rasai observe gsc-appearance `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --start-date 2026-08-01 `
  --end-date 2026-08-31
```

Uses the documented `searchAppearance` dimension and stores a distinct source provenance so it does not replace standard Search Analytics data.

### URL Inspection

```powershell
rasai observe gsc-inspect `
  --audit AUD-... `
  --site-url "sc-domain:example.com" `
  --max-urls 25
```

Only URLs already persisted in the source AUD are eligible. The API describes the indexed version known to Google; it is not a live-test substitute.

Failure policy:

- URL-specific errors can be recorded as `ERROR` while the batch continues;
- HTTP 401/403/429, selected 5xx responses and network failure abort immediately so the same systemic failure is not repeated across all URLs;
- a systemic failure before persistence does not create a partial sidecar dataset.

## CrUX History

```powershell
$env:SEARCHGEO_CRUX_API_KEY="..."
rasai observe crux-history `
  --audit AUD-... `
  --target https://example.com/ `
  --scope origin `
  --form-factor PHONE `
  --periods 40
```

Direct CrUX is validated **before the network request**:

- target must be HTTP(S);
- target origin must exactly match an origin from the AUD;
- `--scope origin` rejects path/query/fragment;
- collection periods are bounded to 40;
- API key is not persisted.

Historical LCP/INP/CLS remains field data and is not merged with Lighthouse lab metrics or Apdex.

## Generic Observability import

```powershell
rasai observe import --audit AUD-... --file observations.json
```

Contract: `RASAI-OBS-IMPORT-001`.

Search/Index URLs and CrUX targets are constrained to audited origins. CrUX `ORIGIN` targets cannot contain path/query/fragment, periods cannot be inverted, and metadata fields must be JSON objects when supplied.

## Bing Search/Chat outcomes

```powershell
rasai observe bing-import --audit AUD-... --file bing-search-performance.csv
rasai observe bing-import --audit AUD-... --file bing-search-performance.csv --surface Chat
```

Bing remains import-first where a direct documented contract is not implemented. Explicit `--surface` participates in dataset/source identity, so the same raw CSV can coexist as separate explicit surfaces without overwriting another import. Artifact SHA-256 still describes the original bytes.

## Google Generative AI Performance — import-first

RASAI does not presume an undocumented API endpoint for these reports.

```powershell
rasai observe google-ai-import --audit AUD-... --file genai-search.csv --surface search
rasai observe google-ai-import --audit AUD-... --file genai-discover.csv --surface discover
```

Search and Discover are distinct source types. RASAI persists only fields actually present and does not invent clicks, CTR, position, query or citation count.

Suppression/rounding/unavailable tokens are retained with explicit metadata. An exported zero is not independently asserted as proof of zero visibility.

### Google GenAI control

```powershell
rasai observe google-ai-control --audit AUD-... --state INCLUDE
rasai observe google-ai-control --audit AUD-... --state EXCLUDE
rasai observe google-ai-control --audit AUD-... --state INHERIT
```

Observed/manual configuration fact only; `scoring_impact=NONE`.

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
- retrieval/chunkability;
- template/component clusters;
- CrUX History;
- dataset provenance.

Freshness is anchored to persisted AUD/snapshot time. Regenerating the same report later must not change a verdict merely because wall-clock time advanced.

## Search & AI content controls

Quality reports publisher controls as evidence, not penalties:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

Artifact reads are confined to the AUD workspace; path traversal references are not followed.

## RASAI Quality

### Per-audit report

```powershell
rasai quality report --audit AUD-...
```

`report/quality.html` contains:

- Audit Health / Data Quality;
- Evidence Confidence per finding;
- actionable Operational Priority P0–P3;
- Coverage Map;
- Search/AI content controls;
- Recommendation Validation.

Executive Top Priorities excludes `RESOLVED`, `CLOSED` and `DISMISSED`. These states remain visible in the complete Evidence Confidence history.

Quality is decision support, not another readiness score.

### Fix Verification

```powershell
rasai quality verify `
  --baseline AUD-BASELINE `
  --current AUD-CURRENT `
  [--url https://example.com/page] `
  [--rule-id BR-GEO-011]
```

Evidence-bound statuses include `FIXED`, `PARTIALLY_FIXED`, `NOT_FIXED` and `NOT_VERIFIABLE`. This proves only the persisted rule transition, not downstream Search/AI impact.

### Evidence Timeline

```powershell
rasai quality timeline --audits-root audits [--domain example.com] [--url https://example.com/page]
```

Builds a longitudinal report from immutable AUD workspaces without rewriting history.

## SCORE-GEO-003 calibration

```powershell
rasai scoring dataset --audits-root audits --dataset-version GEO-CAL-001
```

`READY_FOR_MODEL_FIT != VALIDATED`. Calibration source AUDs are opened read-only, and target/feature granularity remains aligned when the controlled outcome is not device-specific.

## HTML surfaces

Canonical per-AUD navigation is conditional on file existence:

```text
index.html
readiness.html
score-geo-003.html
mobile.html
desktop.html
remediation.html
content-suggestions.html
crawling-discovery.html
accessibility.html
web-performance.html
apdex.html
apdex-experience.html
ai-visibility.html
observability.html
quality.html
ai-usage.html
references.html
```

## Human smoke minimum

Before merge:

1. use two real comparable `AUD-*` workspaces;
2. run `monitor compare`, `monitor gate` and `monitor impact`;
3. exercise a deliberately regressed/new-failure pair if available;
4. generate/open `quality.html`;
5. run one Fix Verification and Evidence Timeline;
6. test `observability.html` empty state;
7. with valid OAuth, test GSC property discovery, sitemaps, Search Analytics, Search Appearance and URL Inspection;
8. with a valid key/eligible origin, test CrUX History;
9. import Bing and Google GenAI exports when available;
10. verify canonical navigation/order/current active state;
11. verify `SCORE-GEO-003` current and `SCORE-GEO-002` historical only;
12. verify source `audit.db` SHA-256 unchanged by Monitor/Observability/Quality;
13. verify bearer tokens/API keys do not appear in sidecar/artifacts/HTML.
