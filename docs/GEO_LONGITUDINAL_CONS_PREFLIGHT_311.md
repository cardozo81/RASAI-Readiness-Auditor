# #311 - CONS-3 integration preflight for GEO longitudinal

## Evidence inspected (main 30af79d1, 2026-10-09)

- `src/rasai/consolidation/reporting.py` declares `REPORT_FORMAT_VERSION = "CONS-3"`.
- `_request_fingerprint` hashes report format version, canonical filters, and
  `ConsolidatedData.source_fingerprint`. `_find_existing` reuses an existing
  `CONS-*/report.html` when its manifest has the same fingerprint.
- `write_report` writes `report.html` and `manifest.json` under
  `audits_root/consolidated/CONS-*`. The manifest lists sources and current
  policies for score/performance/Apdex comparability; it does not declare a
  GEO longitudinal measurement.
- `_render_html` is the canonical CONS presentation. Its sections describe
  existing SARI, scores, performance, Apdex, findings, reliability and sources.
- `src/rasai/geo_longitudinal_311.py` and
  `src/rasai/geo_longitudinal_html_311.py` already provide standalone
  read-only advisory JSON/HTML, not a CONS-3 fragment or a calibrated trend.

This inventory is based on inspected source contracts, not on an executed
consolidation or on a valid longitudinal sample. No AUD, CONS or provider was
accessed or changed while preparing this note.

## Required independent gates before a native CONS-* integration

1. **Methodology approval.** Define whether GEO is merely an advisory
   observation inventory or an accepted trend indicator. Without comparable
   snapshots, keep `trend_conclusion=N/D`; do not reweight SARI, Apdex or
   other canonical aggregates.
2. **Cohort provenance.** Select only complete logical AUDs with a verified
   persisted GEO observation and matching query, target URL, observation
   schema/methodology, SERP scope and external-search chronology. A URL
   match alone does not demonstrate equivalent intent or exposure.
3. **Source selection and security.** Read each source database in read-only
   mode, prove AUD identity, reject invalid snapshots/foreign references,
   cap input and output size, preserve original databases and manifests,
   and render all provider text as untrusted HTML data.
4. **Fingerprint correctness.** If GEO material is embedded or linked from
   the canonical report, the request/source fingerprint and version
   contract must cover all GEO inputs. Reusing an old CONS-3 fingerprint
   after adding new GEO sources would return a stale report.
5. **Report and manifest contract.** Define a versioned optional GEO
   section/companion and explicit absence/limitation states. Preserve
   independent provenance, no external provider calls during rendering,
   and no silent alteration of existing summary/aggregation semantics.
6. **Regression gates.** Positive multi-AUD eligible fixtures, mismatched
   methodology/scope, partial completion, stale Search API, duplicate
   sources, old CONS compatibility, offline idempotence, HTML escaping and
   source-db SHA-256 immutability must pass on Linux and Windows.

## Current decision

Do **not** connect the standalone GEO report to `write_report` yet.
The historical 21-AUD inspection in #311 produced zero eligible cohorts.
Current CONS-3 fingerprint and aggregated methodology do not authorize a
new GEO trend claim. The integration remains pending a versioned contract
and explicit methodology/acceptance; this document does not mark that
feature as implemented.

The existing `python -m rasai geo-longitudinal` standalone advisory is the
safe offline review surface. No lifecycle edits, synthetic historical
cohorts outside fixtures, or commercial Search API requests are justified.
