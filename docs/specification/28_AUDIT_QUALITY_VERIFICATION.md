# 28 — Audit Quality, Verification & Decision Support

**Status:** APPROVED / IMPLEMENTED — candidate for smoke in PR #82.

## 1. Purpose

This specification defines derived, read-only capabilities that assess the quality of RASAi evidence and support remediation decisions without creating another readiness score.

The domain answers:

- is the persisted AUD structurally healthy and sufficiently complete?
- how strong is the evidence supporting each finding?
- which findings deserve operational attention first?
- which evidence domains were actually observed for each URL/device?
- do persisted recommendations still reference valid unresolved evidence?
- did a later audit demonstrate that a specific rule-level issue was fixed?
- how did persisted evidence evolve across multiple AUDs?

None of these questions changes `SARI-001` or `SCORE-GEO-003`.

## 2. Normative boundaries

Quality/Verification MUST:

1. open source `audit.db` in read-only mode;
2. treat `observability.db` as derived sidecar evidence;
3. never mutate findings, recommendations, RuleExecution, scores or historical AUDs;
4. never convert missing evidence into a failure by default;
5. distinguish evidence confidence from SARI dimension Confidence;
6. distinguish operational priority from scoring/severity;
7. describe fix verification as persisted rule-state evidence only;
8. never claim that a verified technical fix caused Search/AI outcome changes;
9. keep publisher content-use controls non-scoring;
10. use canonical report navigation when `quality.html` is materialized.

## 3. `rasai quality report`

```text
rasai quality report --audit AUD-* [--audits-root audits]
```

Output:

```text
<AUD-ID>/report/quality.html
```

### 3.1 Audit Health

Audit Health is a collection-quality assessment, not readiness.

Checks may include:

- SQLite integrity of `audit.db`;
- completion state;
- URL × device snapshot coverage;
- inconclusive/error RuleExecutions;
- score/scoring-version availability;
- referenced artifact existence;
- report index materialization;
- sidecar integrity;
- OBS-002 composite-key contract;
- overlapping observed datasets;
- external artifact SHA/provenance.

The aggregate health state MUST NOT be exposed as SARI or a substitute for SARI.

### 3.2 Evidence Confidence per finding

Values:

```text
HIGH
MEDIUM
LOW
```

Evidence Confidence may use:

- deterministic vs semantic/derived rule provenance;
- resolved RuleExecution;
- execution error/inconclusive state;
- explicit persisted evidence IDs.

It is distinct from the dimension-level `Confidence` persisted by the readiness scoring pipeline.

### 3.3 Operational Priority

Operational Priority is an independent remediation heuristic. Current output classes:

```text
P0
P1
P2
P3
```

The calculation combines, transparently:

- finding severity;
- affected scope;
- evidence confidence;
- estimated remediation effort.

It MUST NOT alter finding severity or any SARI/SCORE value.

### 3.4 Coverage Map

The Coverage Map projects URL/device evidence into domains such as:

- `TECHNICAL_ACCESS`;
- `CONTENT_RENDERING`;
- `SEMANTIC_ENTITY`;
- `ANSWER_EVIDENCE_INTENT`;
- `GOVERNANCE`.

`NOT_OBSERVED` means evidence was not available in that scope; it does not mean FAIL.

### 3.5 Recommendation Validation

Recommendation Validation checks persisted references/state coherence.

Possible states include:

- `SUPPORTED_BY_PERSISTED_EVIDENCE`;
- `SUPPORTED_BY_GROUP`;
- `INVALID_REFERENCE`;
- `STALE_RESOLVED`;
- `CONFIDENCE_MISMATCH`.

This is structural/evidence validation; it does not guarantee that recommendation wording is universally correct.

## 4. Search & AI content-use controls

The Quality domain records publisher controls as observed facts:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

Interpretations may include:

- `DIRECT_SNIPPET_USE_RESTRICTED`;
- `DIRECT_SNIPPET_USE_LIMITED`;
- `SELECTIVE_CONTENT_EXCLUSION`;
- `NO_SNIPPET_RESTRICTION_OBSERVED`.

A restrictive publisher policy MUST NOT be represented as a Search/SARI penalty.

Only `X-Robots-Tag` is retained from the relevant HTTP response-header evidence for this feature; unrelated response headers are not copied merely to support Quality.

## 5. Fix Verification

```text
rasai quality verify --baseline AUD-A --current AUD-B [--url URL] [--rule BR-GEO-NNN]
```

Default output:

```text
audits/verification/VER-*/report.html
```

Rule-level statuses:

- `FIXED` — baseline FAIL/WARNING reached PASS;
- `PARTIALLY_FIXED` — rule improved but is not proven fully resolved;
- `NOT_FIXED` — issue remains or degraded;
- `NOT_VERIFIABLE` — current evidence is unavailable/incomparable.

Fix Verification MUST use the persisted comparison contract. It cannot assert downstream Search/AI impact.

## 6. Evidence Timeline

```text
rasai quality timeline [--audits-root audits] [--domain DOMAIN] [--url URL]
```

Default output:

```text
audits/quality/TIMELINE-*/report.html
```

The timeline can project:

- AUD event time;
- auditor/ruleset/scoring versions;
- URL count;
- FAIL/WARNING counts;
- dimension values;
- selected page state.

Historical workspaces are read-only.

## 7. Reproducibility

Time-dependent derived checks MUST use persisted audit/observation timestamps whenever the result would otherwise drift over time.

Freshness uses, in order when available:

1. audit `completed_at`;
2. audit `started_at`;
3. audit `created_at`;
4. latest persisted snapshot capture time.

If no persisted time anchor exists, a future-date claim MUST NOT be created merely from the machine wall clock.

## 8. Relationship with Observability

Quality may inspect `observability.db` to assess data quality/provenance, but observed outcomes remain separate from SARI.

The current sidecar contract is `RASAI-OBS-002`, whose observation row identity is:

```text
(dataset_id, record_id)
```

This prevents independent datasets from colliding when they legitimately reuse local record IDs.

## 9. Reporting language

Reports must prefer precise language such as:

- observed;
- persisted;
- comparable/not comparable;
- supported by evidence;
- operational priority;
- candidate;
- not verifiable.

Avoid:

- guaranteed ranking gain;
- proven causal impact from temporal coincidence;
- universal GEO score;
- compliance claims not established by the method.

## 10. Tests / safety gates

Minimum automated coverage includes:

- OBS-001 → OBS-002 migration and row preservation;
- reused local `record_id` across datasets;
- no NULL-to-zero outcome conversion;
- temporal comparability before Change Impact association;
- default release-gate provenance boundary;
- content-control detection;
- persisted-time freshness;
- Quality report/menu materialization;
- Fix Verification transition semantics.
