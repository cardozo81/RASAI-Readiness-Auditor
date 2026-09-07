# TECHNICAL_ARCHITECTURE.md

**Status:** APPROVED — consolidated current architecture for RASAI/SARI-001, SCORE-GEO-003, external evidence, Apdex, AI visibility, monitoring and observability.

## 1. Architectural style

RASAI is a local, modular, CLI-first, single-machine application.

Baseline runtime does not require a web server, database server, Docker, background daemon, external AI, Google/Bing APIs, CrUX/PageSpeed, `llms.txt` or IndexNow for the primary readiness audit.

Primary audit evidence remains usable without optional external integrations.

## 2. Runtime

- CPython 3.13.x;
- Playwright + Chromium;
- embedded SQLite;
- local filesystem;
- HTTP/HTTPS to the audited target;
- HTTPS to optional AI/API providers only when explicitly configured/enabled.

## 3. Primary audit pipeline

```text
CLI / interactive console
→ configuration + device context
→ discovery/acquisition
→ rendering
→ extraction/evidence
→ deterministic rules
→ optional semantic provider
→ device comparison when applicable
→ findings
→ SARI dimension scoring
→ SCORE-GEO-003 projection/calibration state
→ prioritization/remediation
→ static report site
→ optional enrichments
```

The audit pipeline owns the authoritative `AUD-*/audit.db` and audit artifacts.

## 4. Scoring status

- public readiness index: `SARI-001`;
- current scoring runtime for new audits: `SCORE-GEO-003`;
- `SCORE-GEO-002`: historical only.

Dimension calculations remain evidence-bound and deterministic. The `SCORE-GEO-003` Overall follows the versioned calibrated-model contract and must not be replaced with an arbitrary simple average when the model is not validated/eligible.

No downstream enrichment is allowed to silently create a ScoreContribution or enter SARI/SCORE-GEO-003.

## 5. Device context

Public device scope is `mobile`, `desktop` or `both`. User-facing default is `mobile` unless a later explicit configuration contract changes it.

Only selected/materialized snapshots may trigger downstream analysis or external calls. A Mobile-only audit must not produce a Desktop AI/API call merely to make reports symmetrical. Desktop × Mobile comparison is applicable only when both contexts exist.

## 6. Persistence boundaries

### 6.1 Primary audit

```text
AUD-*/
├─ audit.db
├─ artifacts/
└─ report/
```

`audit.db` is the source of truth for evidence, RuleExecutions, findings, scoring and audit-time extension tables.

### 6.2 Consolidated history

```text
audits/.searchgeo/consolidated-index.db
```

This is a derived, rebuildable cache. Source `audit.db` files are opened read-only.

### 6.3 Search & AI Observability

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

The observability sidecar stores data collected/imported after the source audit without migrating or mutating `audit.db`. It is derived/rebuildable from preserved artifacts and direct collection results. Credentials, API keys and bearer tokens are not persisted in observability artifacts/database.

## 7. Optional AI

`SemanticAnalysisProvider` remains vendor-abstracted. `NONE` is a valid operating mode.

Invariants:

- provider failure is not a website finding by itself;
- a valid result terminates the provider chain for that context;
- unavailable providers do not overwrite a prior valid result;
- provider/model/usage/cost telemetry is operational data, not scoring;
- chain-of-thought and secrets are not persisted;
- content/technical remediation by AI is advisory and evidence-bound.

## 8. External Web Performance

PageSpeed/Lighthouse and CrUX are optional evidence domains and remain distinct: Lighthouse is lab/synthetic execution; CrUX is field/RUM aggregate evidence where available.

Unavailable PageSpeed/CrUX does not invalidate SARI-001 or SCORE-GEO-003. No Lighthouse category score, LCP, INP, CLS or CWV assessment automatically enters readiness scoring.

## 9. Synthetic Apdex

RASAI maintains separate Synthetic Navigation Apdex and Synthetic User Experience Apdex methods. They have their own profiles, thresholds, samples and reliability limits. They are not RUM and are not merged with Lighthouse/CrUX or SARI.

## 10. Crawling, Discovery & AI Access enrichment

The crawling/discovery enrichment can add deterministic diagnostics for robots, sitemaps, crawler policies, feeds and experimental `llms.txt` handling.

Invariants:

- `scoring_impact=NONE` for this enrichment;
- absence of `llms.txt` is not a readiness failure;
- cross-origin sitemap expansion is not performed automatically without an explicit safety contract;
- AI technical remediation is optional/advisory;
- the enrichment does not alter SARI-001/SCORE-GEO-003.

## 11. Observed Generative Visibility

`ai-visibility.html` is an import-first observed-outcome surface. It may preserve supported external exports and controlled query runs under the documented contract.

Observed visibility does not enter SARI/SCORE-GEO-003 automatically and is not converted into a universal GEO score.

## 12. Search & AI Observability

`rasai observe` / `rasai observability` uses documented external contracts where implemented:

- Google Search Console Search Analytics;
- Google URL Inspection;
- CrUX History;
- supported import-first search/AI outcome datasets.

Output:

```text
AUD-*/observability.db
AUD-*/artifacts/observability/*
AUD-*/report/observability.html
```

The report may derive evidence-bound diagnostics such as Indexability Reality Matrix, Query × Intent Alignment, Potential Search Cannibalization candidates, structured-data documentation completeness, entity consistency, freshness/date conflicts, hreflang checks, retrieval/chunkability observations and template/root-cause clusters.

These are advisory/observational domains and do not silently become new SARI dimensions.

## 13. RASAI Monitor

Monitoring reads two persisted audit workspaces without modifying them:

```text
AUD-BASELINE/audit.db --\
                         > compare/gate/impact -> MON-*/
AUD-CURRENT/audit.db ---/
```

`compare` classifies material change while respecting device, URL universe and scoring-version compatibility.

`gate` uses deterministic signals only by default. Semantic/LLM-derived rules participate only when explicitly enabled.

`impact` may relate technical changes to observed Search/Index/CrUX movements. Language is association-only; temporal coincidence does not establish causality.

## 14. Calibration dataset manager

`rasai scoring dataset` inspects pre-fit sufficiency for SCORE-GEO-003 and writes a deterministic manifest/fingerprint.

Pre-fit readiness is not equivalent to model validation. AUC/Brier and other post-fit promotion gates remain authoritative for validated model status.

## 15. Reporting architecture

The public result remains a static HTML report site. Pages are projections over persisted evidence/data; reopening HTML must not trigger crawling, provider calls or API collection.

Canonical optional-page registry includes, when files exist:

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
ai-usage.html
references.html
```

A normalization pass must never remove another already-materialized optional page from navigation merely because it was generated by a different module.

## 16. Failure isolation

Optional layers are fail-open relative to the primary audit: external AI, PageSpeed/CrUX, Apdex enrichment, crawling/discovery enrichment, observability APIs, consolidated reporting and monitoring/report projection.

A failed optional collector may produce a limitation/error state, but cannot retroactively turn a completed audit into a website failure.

## 17. Security boundaries

- same-origin/scope restrictions remain enforced by audit/collectors;
- no implicit cross-origin expansion;
- no secrets in reports/artifacts;
- external responses are treated as untrusted input and normalized before use;
- monitoring opens source audit databases read-only;
- observability data is separated from source audit evidence;
- imported outcomes preserve provenance and artifact hashes.

## 18. Methodological invariant

RASAI keeps the following domains separate unless a future explicit, versioned and validated methodology changes the contract:

```text
Readiness (SARI-001 / SCORE-GEO-003)
Observed Search/AI outcomes
Web Performance / field experience
Synthetic Apdex
Accessibility
Monitoring/change analysis
```

The dashboard may summarize them together visually, but it must not manufacture a cross-domain score that implies a validated relationship not supported by the method.
