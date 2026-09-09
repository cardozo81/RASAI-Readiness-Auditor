# Search Intelligence HTML Report

## Objective

`report/search-intelligence.html` is the canonical audit-level HTML surface for persisted Search Intelligence evidence.

The report is intentionally observational and advisory. It consolidates multiple evidence layers without merging their methodologies or changing their ownership.

The page can show, when available:

- observed Search result context and customer-domain position;
- normalized SERP results returned by the configured Search provider;
- deterministic RASAi result classification;
- bounded public-page content evidence;
- deterministic customer-versus-observed-leader differences;
- persisted evidence-bound Competitive AI analysis;
- source, provider, model, artifact reference, hashes and technical limitations.

The page does not create a new score and does not alter `SARI-001` or `SCORE-GEO-004`.

## Canonical filename and navigation

Canonical filename:

```text
report/search-intelligence.html
```

The page is optional. It is generated only when the audit workspace contains at least one persisted SERP observation.

When the file exists, the shared report navigation includes `Search Intelligence`. If no Search Intelligence evidence exists, the page and navigation item remain absent.

This avoids showing an empty product surface for audits that did not execute Search Intelligence.

## Provenance model

The report must preserve ownership for every layer.

### SERP Observation

Origin:

- configured Search provider for the observed result set;
- RASAi for normalization, persistence, integrity metadata and contextual presentation.

Persisted sources:

```text
serp_observations
serp_results
```

Fields such as provider, engine, query, country, region, language, device, requested depth, collection timestamp and data mode are part of the measurement context.

A position is not a timeless property of a domain. It is an observation under one defined context.

### Domain status

`FOUND` means the configured domain of interest matched a normalized result within the collected depth.

`NOT_FOUND_WITHIN_DEPTH` means only that the domain was not observed inside the effective result depth. It must not be translated to:

- "the site does not rank";
- position zero;
- infinite position;
- failure of the website;
- negative readiness score.

### Competitive result classification

Origin:

- deterministic RASAi heuristics applied to the persisted SERP observation.

Persisted source:

```text
serp_competitive_results
```

Classification exists to select reasonable candidates for bounded content inspection. It does not establish that two organizations are business competitors.

When the customer domain is found, only eligible observed results ahead of the first matching customer result can be presented as observed leaders for that query context.

### Public content evidence

Origin:

- public website response observed by the bounded RASAi content collector.

Persisted source:

```text
serp_competitive_pages
```

The report can expose persisted deterministic features including:

- requested and final URL;
- fetch status and HTTP status;
- content type;
- received-byte count when persisted;
- title;
- meta description;
- extracted H1-H3 text;
- approximate visible-text word count;
- normalized query terms;
- query-term presence in title, description, headings and body;
- JSON-LD types;
- content SHA-256;
- fetch errors and redirect metadata when persisted.

Raw customer or competitor HTML is not required by this report and must not be reconstructed or fabricated from the extracted features.

### Deterministic competitive gaps

Origin:

- RASAi deterministic comparison.

Current methodology identifier:

```text
DETERMINISTIC-CORRELATIONAL-001
```

Persisted source:

```text
serp_competitive_analyses
```

These gaps are observed differences, not ranking factors. A lower lexical query coverage, different content volume or different structured-data types can be reported as a difference without claiming that the difference caused the observed ranking order.

## Evidence-bound Competitive AI

Competitive AI is a separate optional semantic layer. The HTML does not call an AI provider by itself. It only projects a persisted result produced by the Search Intelligence runtime.

The report supports the current persistence contract:

```text
serp_competitive_ai_analyses
```

When available, the page can expose:

- state/status;
- reason for skipped or unavailable execution;
- AI provider;
- model;
- contract version;
- prompt identifier and version;
- provider request ID when available;
- query intent assessment;
- YMYL assessment;
- semantic summary;
- number of opportunities;
- persisted opportunity payload;
- evidence artifact reference;
- evidence SHA-256.

An AI opportunity must remain evidence-bound. Evidence IDs referenced by the semantic output belong to the closed evidence set produced by the competitive evidence contract. The report must not replace evidence IDs with invented facts.

## AI interpretation boundary

Competitive AI can produce hypotheses and recommendations. It cannot establish private Search-engine causality.

Valid language includes:

```text
Observed leaders contain broader coverage of topic X than the customer page.
Consider evaluating whether topic X is relevant to the customer's search intent and product scope.
Evidence: CE-CUSTOMER, CE-COMP-001.
```

Invalid language includes:

```text
Google ranks the competitor higher because topic X is present.
Adding topic X will increase the customer to position 1.
```

The second form claims access to a causal mechanism that the evidence does not establish.

## Separation from readiness scoring

Search Intelligence remains separate from the proprietary readiness indices.

```text
Search provider evidence
        |
        v
SERP Observation
        |
        +--> RASAi deterministic competitive evidence
        |          |
        |          +--> optional bounded content evidence
        |                     |
        |                     +--> optional evidence-bound Competitive AI
        |
        +--> Search Intelligence HTML

SARI-001 / SCORE-GEO-004
        |
        +--> separate scoring contract and separate evidence set
```

No observed position, competitor classification, content difference or Competitive AI recommendation receives automatic score weight.

Any future attempt to introduce Search Intelligence into scoring requires a new explicit methodological contract, documented validation and compatibility policy. It must not happen implicitly in report rendering.

## Separation from Lighthouse and CrUX

`search-intelligence.html` must not present Lighthouse or CrUX metrics as Search Intelligence indicators.

The ownership boundaries are:

- Lighthouse Performance, Accessibility, Best Practices and SEO technical scores belong to Google Chrome Lighthouse;
- field Core Web Vitals belong to CrUX/Web Vitals;
- SERP observations belong to the configured Search provider observation;
- deterministic competitive classification and comparison belong to RASAi;
- semantic competitive output belongs to the RASAi AI workflow plus its explicitly identified provider/model;
- SARI-001 and SCORE-GEO-004 belong to their RASAi scoring contracts.

Cross-links are acceptable. Methodological fusion without an explicit contract is not.

## Report refresh behavior

When an audit workspace is supplied, Search Intelligence persistence is authoritative. Report generation is ancillary.

The Search runtime performs a best-effort report refresh after a persisted observation. The deterministic competitive runtime also performs a best-effort refresh after its additive evidence is persisted.

A report rendering problem must not convert a successfully persisted SERP observation or competitive comparison into a provider/runtime failure. The HTML can be regenerated later from `audit.db`.

The Competitive AI runtime should follow the same contract: after semantic evidence is persisted, refresh the report from persisted state rather than passing an in-memory AI object directly into the renderer.

This keeps the HTML reproducible from its persisted sources of truth.

## Executive summary

When `report/index.html` already exists, Search Intelligence reporting can add an idempotent summary panel containing:

- persisted observation count;
- number of observations where the domain was found;
- latest observation timestamp;
- link to `search-intelligence.html`.

The summary is descriptive only. It must not be presented as an average ranking score or site-wide Search score.

## Integrity and traceability

Where available, expose:

- observation ID;
- Search run ID;
- provider request ID;
- raw evidence artifact reference;
- raw artifact SHA-256;
- competitive artifact reference and SHA-256;
- Competitive AI artifact reference and SHA-256;
- provider/model identifiers;
- errors and unavailable states.

An unavailable layer stays unavailable. The report must never fill a missing provider result, content feature or AI interpretation with a zero-valued synthetic result.

## Security and privacy

The HTML does not display API secrets.

Provider keys remain outside persisted report data. Public-page inspection continues to use the Search Intelligence network-safety policy, including bounded acquisition and SSRF-oriented validation.

Competitive AI receives the bounded evidence contract rather than raw competitor HTML. This reduces unnecessary content disclosure and keeps the semantic request tied to reproducible extracted evidence.

## Compatibility

The Search Intelligence report is additive.

Without persisted SERP observations:

- no `search-intelligence.html` is produced;
- existing audit reports remain unchanged;
- existing scoring remains unchanged.

With SERP Observation only:

- the report can show the observed SERP and domain position;
- competitive and AI sections remain explicitly unavailable rather than fabricated.

With deterministic competitive evidence:

- the report adds classification, content evidence and deterministic gaps.

With Competitive AI evidence:

- the report additionally projects the persisted semantic result with provider/model/evidence provenance.

This progressive disclosure allows Search Intelligence to evolve independently while keeping one stable public HTML surface.
