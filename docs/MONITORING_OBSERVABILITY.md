# RASAi Monitor, Observability & Quality

**Estado no baseline de desenvolvimento:** IMPLEMENTED / INTEGRATED IN `main`

## Purpose

This capability turns isolated RASAi audits into a longitudinal, evidence-bound workflow without changing the audit source of truth or silently adding new signals to `SARI-001/SCORE-GEO-004`.

It keeps these questions separate:

1. **Readiness:** what technical/semantic conditions were observed by the audit?
2. **Observed outcomes:** what did external Search/AI systems report?
3. **Change:** what materially changed between persisted audits?
4. **Association:** did an outcome move across a comparable period while a technical regression also existed?
5. **Decision quality:** is the audit evidence complete/reliable enough to support remediation decisions?

Temporal coincidence is not causal inference.

## Architecture

```text
AUD-BASELINE/audit.db -----\
                            > RASAi Monitor -> MON-*/report.html + manifest.json + impact.html
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

## Methodological boundary

```text
SARI-001      public readiness index
SCORE-GEO-004 current runtime scoring contract
SCORE-GEO-003 historical scoring contract
```

Monitoring, Observability and Quality do not create another readiness score. External outcomes, Lighthouse/CrUX and synthetic metrics are not added to the Overall implicitly.

## Observability sidecar

Current contract:

```text
RASAI-OBS-002
identity = (dataset_id, record_id)
```

Dataset provenance persists source type, capture method, period, artifact path/SHA-256, collection time and metadata. Secrets are runtime-only.

## RASAi Monitor

### Compare

```powershell
rasai monitor compare --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Possible states include `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `UNCHANGED`, `DATA_UNAVAILABLE` and `NOT_COMPARABLE`.

Different `scoring_version` values are not silently converted or treated as equivalent.

### Release gate

```powershell
rasai monitor gate --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Default gate is deterministic and fail-closed. Optional families require explicit opt-in:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

Operational overrides are explicit:

```text
--allow-noncomparable
--allow-new-failures
```

### Change Impact

```powershell
rasai monitor impact --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

One latest dataset is selected per source/AUD. Overlapping histories are not summed. Missing values remain missing. Temporal associations are reported without causal language.

## Search & AI Observability

Main command:

```text
rasai observe ...
```

Alias:

```text
rasai observability ...
```

Supported operational surfaces include generic import, Bing import-first, Google AI import/control, Search Console property/sitemap/Search Analytics/Search Appearance/URL Inspection, CrUX History and report/status commands.

Rules common to external collection:

- target/source scope is validated against the AUD;
- OAuth tokens/API keys are not persisted;
- auth/quota/network errors are operational failures, not website findings;
- data absent from a source is not invented;
- `NULL` is never normalized to zero unless the source actually reports a numeric zero with that semantics;
- source/surface/provenance remain explicit.

## Observability diagnostics

`report/observability.html` can include:

- Indexability Reality Matrix;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- structured-data/entity/freshness/hreflang/retrieval diagnostics;
- template/root-cause clusters;
- CrUX History;
- dataset provenance.

These are derived diagnostics and do not automatically alter `SARI-001/SCORE-GEO-004`.

## RASAi Quality

```powershell
rasai quality report --audit AUD-...
rasai quality verify --baseline AUD-A --current AUD-B
rasai quality timeline --audits-root audits
```

Quality includes Audit Health, Evidence Confidence, Operational Priority, Coverage Map, publisher content-use controls, Recommendation Validation, Fix Verification and Evidence Timeline.

Quality is decision support, not another readiness score.

## Scoring command surface

Current runtime:

```powershell
rasai scoring inspect
```

The command inspects `SCORE-GEO-004`. Historical `SCORE-GEO-003` dataset/calibration/model-artifact flows are not current commands of the 004 entrypoint.

## HTML surfaces

Canonical per-AUD navigation is conditional on file existence:

```text
index.html
readiness.html
scoring.html
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


## Validation expectations

Automated validation should cover read-only behavior, comparability, gate policy, OBS-002 identity/migration, external-data scoping, secret exclusion, NULL preservation, Quality/Verification/Timeline semantics and canonical navigation.

Human smoke remains appropriate when validating real credentials, external provider behavior or visual/operational behavior. It is not a pending-merge status for capabilities already integrated in `main`.
