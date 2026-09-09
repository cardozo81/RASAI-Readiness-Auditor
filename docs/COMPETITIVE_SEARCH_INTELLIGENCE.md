# Competitive Search & Content Intelligence

Status: **implemented deterministic layer with optional evidence-bound AI extension**.

## 1. Purpose

Competitive Search Intelligence answers:

> For an observed query, which result types appear ahead of the customer, which are reasonable Search competitor candidates, what deterministic content differences are observable, and—when explicitly requested—what evidence-bound improvement opportunities can an AI provider propose?

The deterministic layer remains authoritative for observations. AI is downstream and optional.

RASAI does not infer ranking causality from content differences or AI recommendations.

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
-> optional Competitive AI using closed evidence_ids
```

The optional semantic layer is documented in `COMPETITIVE_AI_INTELLIGENCE.md`.

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

Classification is heuristic. It selects candidates for bounded inspection; it is not a declaration that two organizations are commercial competitors.

When the customer is `FOUND`, only results ahead of the first matching customer result are considered. When the customer is `NOT_FOUND_WITHIN_DEPTH`, the observed result set may still be classified, but content comparison requires an explicit `--customer-url`.

Candidate selection is de-duplicated by normalized domain and bounded by `--max-content-pages` plus `RASAI_SERP_MAX_COMPETITORS`.

## 4. Explicit acquisition modes

`--competitive` performs classification only and adds no content request.

`--compare-content` explicitly enables public-page acquisition for the customer page plus the bounded candidate set.

Example:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --max-content-pages 3
```

If the customer is not found:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --customer-url https://cliente.example/seguro-auto
```

An explicit `--customer-url` is supported for one query per command.

## 5. Bounded public-web acquisition

Default bounds:

- competitor pages per query: `3`, plus one customer page;
- timeout per attempt: `10` seconds;
- maximum response body: `2,000,000` bytes;
- maximum redirects: `5`;
- method: GET;
- accepted ports: 80/443;
- TLS verification enabled.

CLI controls:

- `--max-content-pages`
- `--content-timeout`
- `--content-max-bytes`
- `--content-max-redirects`

`--dry-run --compare-content` shows the worst-case direct HTTP-attempt ceiling separately from SERP quota.

## 6. SSRF / network boundary

SERP URLs are untrusted external input. Before every request and redirect, the fetcher:

- requires HTTP/HTTPS;
- rejects credentials in URLs;
- rejects localhost and local/internal suffixes;
- rejects non-standard public-web ports;
- rejects non-global IP literals;
- resolves hostnames and rejects non-global destinations;
- validates redirect targets before following them.

Application validation does not eliminate DNS-rebinding/TOCTOU risk. A multi-tenant SaaS deployment must additionally use network egress controls or a hardened outbound proxy.

## 7. Deterministic features

RASAI extracts bounded features:

- final URL and HTTP status;
- content type;
- response size;
- content SHA-256;
- title;
- meta description;
- H1-H3;
- approximate visible-text word count;
- meaningful query terms;
- query-term presence in title, description, headings and body;
- JSON-LD `@type` values.

Raw HTML is not persisted by this feature.

The lexical comparison is accent-insensitive and deterministic. It is not semantic understanding.

## 8. Deterministic comparison

Methodology:

`DETERMINISTIC-CORRELATIONAL-001`

Current informational gaps include:

- `QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS`
- `TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`
- `HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`
- `CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS`
- `STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS`

References use the median of successfully observed selected pages. Failed or blocked acquisitions are excluded instead of becoming zero.

Word count is content volume, not content quality. Structured-data differences are not automatic markup recommendations. Signals are informational and non-scoring.

## 9. Comparison statuses

- `CONTENT_COMPARISON_DISABLED`
- `SERP_OBSERVATION_UNAVAILABLE`
- `CUSTOMER_URL_REQUIRED`
- `CUSTOMER_CONTENT_UNAVAILABLE`
- `NO_ELIGIBLE_COMPETITOR_CANDIDATES`
- `COMPETITOR_CONTENT_UNAVAILABLE`
- `CONSOLIDATED`

Only `CONSOLIDATED` is eligible for Competitive AI.

## 10. Optional Competitive AI

`--ai-competitive` is a separate explicit opt-in and requires `--compare-content`.

Example:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider openai `
  --ymyl-mode AUTO
```

Competitive AI receives only structured deterministic evidence with closed IDs:

- `CE-QUERY`
- `CE-CUSTOMER`
- `CE-COMP-###`
- `CE-GAP-###`

Unknown evidence IDs invalidate the provider response. AI cannot repair missing deterministic evidence.

Current live adapter: `openai`. `fixture` validates the contract without network. Default: `none`.

See `COMPETITIVE_AI_INTELLIGENCE.md`.

## 11. Evidence and persistence

When `--audit-workspace` is supplied, all layers remain inside the existing audit workspace and `audit.db`.

Deterministic additive tables:

- `serp_competitive_analyses`
- `serp_competitive_results`
- `serp_competitive_pages`

Competitive AI additive table:

- `serp_competitive_ai_analyses`

Deterministic artifacts:

```text
artifacts/search-intelligence/competitive/<observation_id>.json
```

Competitive AI artifacts:

```text
artifacts/search-intelligence/competitive-ai/<observation_id>.json
```

No parallel database is introduced. No scoring table is modified.

## 12. Cost and performance

- classification: no additional network;
- content comparison: direct public HTTP, no SERP-provider quota;
- Competitive AI: provider call only when explicitly enabled and deterministic context is `CONSOLIDATED`;
- `--dry-run` shows separate ceilings for SERP, content acquisition and AI.

Provider credentials are not persisted in these artifacts.

## 13. Compatibility

Without `--competitive`, `--compare-content` or `--ai-competitive`, ordinary SERP behavior is unchanged.

Without `--ai-competitive`:

- no AI provider is instantiated;
- no Competitive AI call is made;
- deterministic Search Intelligence remains fully usable.

Competitive AI failure does not rewrite SERP or deterministic comparison evidence.

`SARI-001` and `SCORE-GEO-004` are independent.

## 14. Test policy

CI uses fixtures, fake HTML and injected transports/resolvers.

CI must not:

- call SerpApi live;
- consume customer keys;
- crawl public competitor sites;
- call an AI provider live;
- depend on public DNS/internet.

Tests cover classification, bounds, extraction, public-address blocking, comparison gaps, evidence-ID closure, AI contract validation and additive persistence.

## 15. Current limitations

- result classification remains a small heuristic taxonomy;
- no entity/business-equivalence graph yet;
- content extraction uses static HTTP HTML, not rendered browser DOM;
- no canonical/hreflang/link-graph comparison yet;
- Competitive AI live support starts with OpenAI; other adapters can be added behind the same contract;
- AI sees extracted features rather than full raw HTML;
- no Search Intelligence-specific HTML report yet;
- no semantic historical comparison of two Search Intelligence observations yet;
- public-IP validation still requires network-layer reinforcement before multi-tenant SaaS.

The product platform already has deployment markers and before/after audit resolution. Search Intelligence historical comparison should extend that existing platform instead of creating a parallel marker model.
