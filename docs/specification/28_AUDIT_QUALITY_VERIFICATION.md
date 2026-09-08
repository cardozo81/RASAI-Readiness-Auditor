# 28 - Audit Quality, Verification & Decision Support

**Estado no baseline de desenvolvimento:** APPROVED / IMPLEMENTED / INTEGRATED IN `main`

## 1. Purpose

This domain provides derived, read-only capabilities that assess RASAi evidence quality and support remediation decisions without creating another readiness score.

It answers whether the persisted AUD is healthy, how strong finding evidence is, which findings deserve operational attention, whether recommendations still reference valid unresolved evidence, whether a later audit demonstrates a rule-level fix, and how evidence evolved across AUDs.

None of these capabilities changes `SARI-001` or `SCORE-GEO-004`.

## 2. Normative boundaries

Quality/Verification MUST:

1. open source `audit.db` read-only;
2. treat `observability.db` as derived sidecar evidence;
3. never mutate findings, recommendations, RuleExecution, scores or historical AUDs;
4. never convert missing evidence into a failure by default;
5. distinguish Evidence Confidence from SARI dimension Confidence;
6. distinguish Operational Priority from scoring/severity;
7. describe Fix Verification as persisted rule-state evidence only;
8. never claim that a verified technical fix caused Search/AI outcome changes;
9. keep publisher content-use controls non-scoring;
10. preserve source `scoring_version` and comparability boundaries.

## 3. Quality report

```text
rasai quality report --audit AUD-* [--audits-root audits]
```

Output:

```text
<AUD-ID>/report/quality.html
```

### Audit Health

Audit Health evaluates collection/data quality, not website readiness. Checks can include SQLite integrity, completion state, snapshot coverage, inconclusive/error RuleExecutions, score-version availability, artifact existence, report materialization, sidecar integrity and provenance.

### Evidence Confidence

Values:

```text
HIGH
MEDIUM
LOW
```

This confidence describes evidence supporting a finding. It is distinct from the dimension-level `Confidence` used by the readiness scoring pipeline.

### Operational Priority

Classes:

```text
P0
P1
P2
P3
```

Operational Priority combines persisted finding characteristics, affected scope, evidence confidence and remediation effort. It does not alter Severity or SARI/SCORE values.

### Coverage Map

`NOT_OBSERVED` means evidence was not available in that URL/device/domain scope; it does not mean FAIL.

### Recommendation Validation

Possible states include:

```text
SUPPORTED_BY_PERSISTED_EVIDENCE
SUPPORTED_BY_GROUP
INVALID_REFERENCE
STALE_RESOLVED
CONFIDENCE_MISMATCH
```

This validates structural/evidence coherence, not universal correctness of recommendation wording.

## 4. Search & AI content-use controls

Quality can record observed publisher controls such as:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

Restrictive publisher policy is not represented as an automatic SARI penalty.

## 5. Fix Verification

```text
rasai quality verify --baseline AUD-A --current AUD-B [--url URL] [--rule BR-GEO-NNN]
```

Default output:

```text
audits/verification/VER-*/report.html
```

Statuses:

- `FIXED`;
- `PARTIALLY_FIXED`;
- `NOT_FIXED`;
- `NOT_VERIFIABLE`.

Fix Verification uses persisted comparison evidence and cannot assert downstream Search/AI impact.

## 6. Evidence Timeline

```text
rasai quality timeline [--audits-root audits] [--domain DOMAIN] [--url URL]
```

Default output:

```text
audits/quality/TIMELINE-*/report.html
```

The timeline can project audit time, auditor/ruleset/scoring versions, URL count, FAIL/WARNING counts, dimension values and selected page state. Historical workspaces remain read-only.

## 7. Reproducibility

Time-dependent checks use persisted audit/observation timestamps so regenerating a report later does not change conclusions merely because wall-clock time advanced.

Preferred time anchors are `completed_at`, then `started_at`, `created_at`, then persisted snapshot capture time.

## 8. Relationship with Observability

Quality may inspect `observability.db` for data-quality/provenance checks, but observed outcomes remain separate from SARI/SCORE-GEO-004.

Current sidecar contract:

```text
RASAI-OBS-002
identity = (dataset_id, record_id)
```

## 9. Reporting language

Prefer terms such as observed, persisted, comparable, supported by evidence, operational priority and not verifiable.

Avoid guaranteed ranking gain, causal claims from temporal coincidence, universal Search & AI score claims or compliance claims not established by the method.

## 10. Automated safety gates

Coverage should include sidecar migration/identity, NULL preservation, temporal comparability, release-gate boundaries, content-control detection, persisted-time freshness, Quality report/menu materialization, Fix Verification semantics and preservation of historical `scoring_version`.
