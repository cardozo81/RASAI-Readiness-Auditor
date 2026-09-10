# TECHNICAL_ARCHITECTURE.md

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Readiness:** `SARI-001`  
**Scoring runtime:** `SCORE-GEO-004`

## 1. Architectural style

RASAi is Windows-first for the current local runtime, modular and CLI/console driven. The primary audit does not require a web server, database server, Docker, external AI or external Search/Performance APIs.

The product also contains a separate local control plane for multi-user, multi-project, multi-property/multi-domain and deployment-oriented workflows. This prepares the domain model for SaaS without changing the immutable AUD evidence contract.

## 2. Runtime

Local baseline:

- CPython 3.13.x;
- Playwright + Chromium;
- embedded SQLite;
- local filesystem;
- HTTP/HTTPS to audited targets;
- optional HTTPS integrations only when explicitly enabled/configured.

Docker is not a local runtime requirement.

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
→ dimension scoring
→ SCORE-GEO-004 Overall
→ prioritization/remediation
→ static report site
→ optional enrichments
```

The authoritative audit evidence remains `AUD-*/audit.db` + artifacts.

## 4. Scoring

Current method:

```text
SCORE-GEO-004
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Dimension calculations remain deterministic and evidence-bound. The Overall is the weighted mean of measured applicable dimension scores using versioned dimension weights, with denominator renormalization over participating dimensions. Applicable dimensions without value are not imputed as zero; they reduce Coverage/Confidence and may constrain Consolidation. Critical readiness dimensions retain the stricter gates defined in `05_SCORING_MODEL.md`.

No downstream enrichment may silently create ScoreContribution or enter SARI/SCORE-GEO-004.

## 5. Device context

Public device scope is `mobile`, `desktop` or `both`. Only selected/materialized contexts may trigger downstream analysis or optional calls. Desktop × Mobile comparison is applicable only when both contexts exist.

Synthetic User Experience Apdex may model TABLET as a synthetic profile, but TABLET is not a canonical core `DeviceContext`; a mobile-only audit cannot silently execute desktop or tablet contexts.

## 6. Persistence boundaries

### Immutable audit evidence

```text
AUD-*/audit.db
AUD-*/artifacts/
AUD-*/report/
```

### Observability sidecar

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

This stores post-audit external observations without migrating or rewriting `audit.db`.

### Consolidated analytical cache

```text
audits/.rasai/consolidated-index.db
```

Derived and rebuildable; source AUD databases are read-only.

### Product control plane

```text
audits/.rasai/platform.db
```

Separate authority for organization/workspace/project/property/environment, users/memberships, milestones/deployments, baselines, schedules, integrations and usage metadata. It does not replace `audit.db` evidence.

## 7. Optional AI

`SemanticAnalysisProvider` is vendor-abstracted and `NONE` is valid.

Invariants:

- provider failure is not a website finding;
- accepted result terminates the chain for that context;
- unavailable providers do not overwrite valid evidence;
- provider/model/usage/cost is operational telemetry, not scoring;
- secrets and private reasoning are not persisted;
- AI remediation is advisory and evidence-bound;
- `AI=AUTO` separates capacidade configurada de participação no pool: excluir um provider do AUTO não remove sua credencial nem impede seleção explícita posterior.

## 8. External domains

The following remain independent of SARI unless a future explicit versioned method changes the contract:

- PageSpeed/Lighthouse lab metrics, including experimental Agentic Browsing when requested/supported;
- CrUX field metrics;
- Accessibility automation;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- crawling/discovery enrichments;
- Search Intelligence / Competitive Search;
- Observed Generative Visibility;
- Search & AI Observability;
- Monitoring/Change Impact;
- Quality/Verification.

Unavailable optional integrations produce limitations/operational state, not artificial website failures.

## 9. Reporting architecture

The per-AUD result is a static HTML site. Opening it never triggers crawling, AI or API collection.

Canonical method routes:

```text
index.html
readiness.html
scoring.html
```

The method version is stored in `scoring_version` and rendered in the page, not encoded into the canonical filename.

Report totals for AI consumption are derived from persisted attempt telemetry, not from scraping presentation labels. Calls whose provider did not return usage remain without invented monetary cost.

## 10. Monitoring / Observability / Quality

Monitoring opens persisted AUDs read-only and respects device, URL universe and `scoring_version` comparability.

Observability uses a derived sidecar and explicit provenance. Quality/Verification uses read-only evidence to support decisions without creating another readiness score.

Temporal association is not causal inference.

## 11. Product Platform and SaaS target

Current local control-plane storage is SQLite. SaaS target architecture uses a managed PostgreSQL control plane, a scheduler/queue, Linux/container audit workers and object storage for immutable AUD bundles.

Windows local support remains a first-class execution mode. The migration boundary is the product/control plane, not a rewrite of historical `audit.db` evidence.

## 12. Security and failure isolation

- enforce scope/same-origin rules where applicable;
- no implicit cross-origin expansion;
- no secrets in reports/artifacts/databases intended for evidence;
- external responses are untrusted input;
- derived workflows do not mutate source AUDs;
- optional failures are isolated from the successful primary audit;
- historical `scoring_version` is preserved rather than normalized silently.
