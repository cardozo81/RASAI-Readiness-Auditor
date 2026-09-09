# Observed Generative Visibility

**Estado no baseline de desenvolvimento:** INTEGRATED / VALIDATED  
**Import contract:** `OGV-IMPORT-001`  
**Scoring impact:** `NONE`

## 1. Objective

Observed Generative Visibility stores observed Search/AI outcomes under an explicitly identified source or controlled protocol.

```text
Measured readiness != Observed visibility
```

OGV import does not recalculate SARI or alter the source audit. Current production scoring is `SCORE-GEO-004`, and OGV data is not an input to its formula.

## 2. Sources

Supported source shapes include normalized Bing AI Performance evidence and controlled query runs according to the import contract.

Where a documented direct API is not implemented, RASAi remains import-first and preserves the source artifact/provenance.

Controlled runs can record engine, query, observed time, validity, citation presence and cited URLs. They are observational evidence only.

## 3. Research boundary

Observed outcomes can support **separate offline validation research** that studies association between readiness and real outcomes.

Such research must not change persisted `SCORE-GEO-004` results. Any future production formula derived from empirical work requires a new explicit scoring version.

## 4. Citation Presence Rate

```text
Citation Presence Rate = valid cited runs / valid runs
```

Invalid runs stay outside numerator and denominator. Sample size and Wilson 95% interval can qualify the observed rate; neither is a universal forecast of future citation.

## 5. Scope, provenance and persistence

URLs subject to same-origin validation must belong to an audited `normalized_origin`.

Artifacts are preserved in the audit workspace under the internal artifact area for Observed Generative Visibility, with SHA-256 and declared capture/source metadata. The physical subdirectory name is an implementation detail and is not part of the public contract. Reimport is idempotent under the deterministic import identity.

Tables include:

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

Import does not write to scores, score contributions, RuleExecutions, findings or recommendations.

## 6. Report and CLI

```text
report/ai-visibility.html
```

The report separates source metrics, URL activity, grounding queries, trends, controlled runs, sample information and provenance. Different sources are not collapsed into a universal score.

Commands:

```powershell
rasai visibility import --audit-id AUD-... --audits-root audits --file observed-visibility.json
rasai visibility report --audit-id AUD-... --audits-root audits
```

Current scoring inspection is:

```powershell
rasai scoring inspect
```

## 7. Interpretation limits

OGV does not establish official GEO scoring, guaranteed citation, ranking authority, causality or universal transferability between engines. Source-reported metrics remain source-reported metrics.

## 8. Acceptance criteria

- import validation and scope enforcement;
- explicit capture provenance;
- preserved SHA-256;
- idempotent reimport;
- source metrics not reinterpreted;
- invalid runs excluded from Citation Presence Rate;
- report with explicit sample/provenance;
- no source-AUD scoring mutation;
- offline research remains separate from runtime scoring.
