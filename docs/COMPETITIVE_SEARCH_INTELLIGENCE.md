# Competitive Search & Content Intelligence

Status: **implemented deterministic POC**.

This milestone extends the provider-neutral SERP foundation with bounded result classification and an optional public-page content comparison. It remains non-scoring and does not use AI.

## 1. Purpose

The feature answers a narrower and safer question than "why does competitor X rank?":

> For one observed query, which kinds of results appear ahead of the customer, which of those are reasonable Search competitor candidates, and which deterministic content differences can be observed between the customer page and a bounded sample of those pages?

RASAI does not infer causality from these differences. Ranking position and content features are observations in the same query context, not proof that one caused the other.

## 2. Flow

```text
query
-> provider-neutral SERP observation
-> customer position / NOT_FOUND_WITHIN_DEPTH
-> deterministic result classification
-> bounded candidate selection
-> optional public-web content acquisition
-> deterministic HTML/content feature extraction
-> customer vs observed-leaders comparison
-> evidence-backed correlational differences
```

AI semantic comparison is deliberately not part of this milestone. It can be layered later on top of the deterministic evidence contract.

## 3. Result classification

Classification is local and consumes no additional network or provider quota.

Current classes:

- `CUSTOMER`
- `ORGANIC_CANDIDATE`
- `PUBLIC_AUTHORITY`
- `KNOWLEDGE_REFERENCE`
- `SOCIAL_PLATFORM`
- `VIDEO_PLATFORM`
- `MARKETPLACE`
- `NON_ORGANIC`

Classification is explicitly heuristic. It is used to decide which observed Search results are sensible candidates for bounded content inspection; it is not a claim that two organizations are commercial competitors.

When the customer is `FOUND`, only observed results ahead of the first matching customer result participate in the competitive selection. Results after the customer are not used as "leaders" for that query observation.

When the customer is `NOT_FOUND_WITHIN_DEPTH`, the observed result set can still be classified. Content comparison then requires `--customer-url`, because RASAI must not invent which customer page should represent the query.

Candidate selection is de-duplicated by normalized domain and bounded by `--max-content-pages` as well as the existing `RASAI_SERP_MAX_COMPETITORS` ceiling.

## 4. Content comparison is explicit opt-in

`--competitive` performs classification only. It makes no additional content request.

`--compare-content` enables public-page acquisition for the customer page plus the bounded selected candidate set.

Example:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json `
  --competitive
```

Content comparison:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --max-content-pages 3
```

If the customer is not found within the requested depth:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --customer-url https://cliente.example/seguro-auto
```

An explicit `--customer-url` is supported for a single query per command, avoiding an ambiguous mapping between multiple queries and one page.

## 5. Bounded public-web acquisition

The content fetcher is isolated from the generic SERP provider adapter and from the existing audit acquisition client.

Default bounds:

- content pages per query: `3` competitor candidates plus one customer page;
- timeout per attempt: `10` seconds;
- maximum response body: `2,000,000` bytes;
- maximum redirects: `5`;
- HTTP methods: GET only;
- accepted inspection ports: 80 and 443;
- TLS verification remains enabled.

The CLI exposes:

- `--max-content-pages`
- `--content-timeout`
- `--content-max-bytes`
- `--content-max-redirects`

`--dry-run --compare-content` shows a worst-case content HTTP-attempt ceiling separately from the SERP provider request ceiling. Direct content acquisition does not consume SerpApi quota.

## 6. SSRF / network boundary

SERP result URLs are untrusted external input. Before every direct request and every redirect target, the POC fetcher:

- requires HTTP or HTTPS;
- rejects credentials in URLs through canonical URL validation;
- rejects localhost and `.localhost`, `.local` and `.internal` names;
- rejects non-standard public-web ports;
- rejects non-global IPv4/IPv6 literals;
- resolves hostnames and rejects destinations resolving to non-global addresses;
- validates a redirect target before issuing the next request.

This is intentionally stricter than blindly feeding a provider-returned URL to the generic audit `HttpClient`.

The application-level preflight substantially reduces accidental SSRF exposure, but DNS resolution followed by a separate HTTP connection still has a DNS-rebinding/TOCTOU limitation. A future multi-tenant SaaS deployment must additionally enforce network-layer egress controls or a hardened outbound proxy. The POC does not claim that application validation alone is a complete server-side SSRF sandbox.

## 7. Extracted deterministic features

RASAI currently extracts only bounded features needed for explainable comparison:

- final URL and HTTP status;
- content type;
- response byte count;
- SHA-256 of the received body;
- HTML title;
- meta description;
- H1-H3 text;
- approximate visible-text word count;
- normalized meaningful query terms;
- query-term presence in title;
- query-term presence in meta description;
- query-term presence in H1-H3;
- query-term presence in visible body text;
- JSON-LD `@type` values.

Script/style/template/noscript content is excluded from normal visible-text extraction. JSON-LD is parsed separately only for structured-data type observation.

The lexical comparison is accent-insensitive and uses a small deterministic stopword set. This is not semantic understanding and is not presented as such.

## 8. Current comparison signals

The methodology identifier is:

`DETERMINISTIC-CORRELATIONAL-001`

Current informational gap codes include:

- `QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS`
- `TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`
- `HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`
- `CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS`
- `STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS`

Numeric references use the median of successfully observed selected pages ahead. Failed/blocked content acquisitions do not become zero-valued measurements.

Word count is explicitly treated as observed content volume, not content quality. Structured-data differences are not automatic recommendations to add markup. Every signal is informational and non-scoring.

## 9. Comparison statuses

- `CONTENT_COMPARISON_DISABLED`: classification was requested without content acquisition.
- `SERP_OBSERVATION_UNAVAILABLE`: no usable observed SERP exists; content is not fetched.
- `CUSTOMER_URL_REQUIRED`: customer was not observed and no explicit customer page was supplied.
- `CUSTOMER_CONTENT_UNAVAILABLE`: the selected customer page could not be observed safely.
- `NO_ELIGIBLE_COMPETITOR_CANDIDATES`: no bounded candidate page exists after classification.
- `COMPETITOR_CONTENT_UNAVAILABLE`: candidates exist but none produced usable observed HTML.
- `CONSOLIDATED`: customer content and at least one selected page ahead were observed and compared.

Failure is fail-open for Search Intelligence and never changes SCORE-GEO-004 or SARI-001.

## 10. Evidence and persistence

When `--audit-workspace` is supplied, the feature remains inside the existing audit workspace and `audit.db`.

Additive tables:

- `serp_competitive_analyses`
- `serp_competitive_results`
- `serp_competitive_pages`

They reference the existing `serp_observations` row. No parallel database is introduced and no scoring table is modified.

Evidence artifacts are written under:

```text
artifacts/search-intelligence/competitive/<observation_id>.json
```

The artifact has its own SHA-256 and records classification, selected candidates, extracted page features, content hashes, gaps and interpretation policy.

**Raw competitor/customer HTML is not persisted by this feature.** This reduces storage volume and the chance of retaining unrelated page secrets or personalized markup. The body SHA-256 provides content identity for the observed extraction without storing the body itself.

## 11. Cost and performance semantics

Competitive classification adds no network cost.

Content comparison uses direct public HTTP requests and therefore has infrastructure/runtime cost but no SERP-provider API quota cost. Redirect attempts count as HTTP attempts and are exposed by the CLI.

The feature is deliberately opt-in so an ordinary `rasai search` command retains the prior SERP-only behavior.

## 12. Compatibility

When neither `--competitive` nor `--compare-content` is supplied:

- existing SERP behavior remains unchanged;
- no competitor page is fetched;
- no competitive table is initialized unless the feature is invoked with a workspace;
- existing audit/report/scoring flows remain independent;
- no IA provider is required.

No new HTML report is introduced in this milestone. CLI + additive evidence/persistence remain the public POC surface until the comparison contract is exercised sufficiently to stabilize a report UX.

## 13. Test policy

Automated tests use controlled `SerpObservation` objects, fake HTML and injected fake network/resolver functions.

CI must not:

- call SerpApi live;
- consume a customer API key;
- crawl a real competitor site;
- depend on public DNS or internet availability.

Tests cover result classification, candidate bounding, lexical extraction, JSON-LD type extraction, private-address blocking, redirect blocking, `NOT_FOUND_WITHIN_DEPTH` handling, comparison gaps and additive persistence.

## 14. Known limitations

- result-classification domain lists are intentionally small heuristics, not an industry taxonomy;
- no entity/business-equivalence model yet;
- content extraction is static HTTP HTML, not browser-rendered DOM;
- no robots.txt policy interpretation for competitor pages in this POC;
- no canonical/hreflang/link-graph comparison yet;
- no E-E-A-T/YMYL semantic comparison yet;
- no AI semantic comparison yet;
- no historical trend or before/after competitive comparison yet;
- no multi-region distributed content probes;
- application-level public-IP validation must be reinforced by network egress controls before multi-tenant SaaS exposure;
- no Search Intelligence HTML report yet.

## 15. Next phase

The recommended next phase is **Evidence-bound Semantic Competitive Analysis** on top of this deterministic layer:

```text
query + canonical SERP evidence
+ extracted customer/candidate page evidence
-> bounded semantic comparison
-> query-intent/content coverage assessment
-> evidence IDs attached to every AI claim
-> hypotheses/recommendations, never fabricated ranking causality
```

Historical rank tracking / before-after comparison can proceed in parallel once query identity, market/device context and observation persistence are treated as stable contracts.
