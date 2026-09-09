# SERP Observation - Search Intelligence foundation

Status: **implemented provider-neutral foundation / POC**.

SERP Observation is the evidence layer beneath RASAI Competitive Search & Content Intelligence. The provider contract remains independent from content analysis: SERP adapters observe and normalize Search results; downstream modules classify and compare those canonical results without importing vendor response semantics.

For the deterministic competitive layer, see `docs/COMPETITIVE_SEARCH_INTELLIGENCE.md`.

## 1. Scope and semantics

SERP means **Search Engine Results Page**. The model is not Google-specific. `engine` is part of the canonical request/observation contract. The first live adapter is **SerpApi for Google organic results**; future adapters can support other traditional Search providers without changing analysis code.

Traditional Search and AI observation remain separate concepts:

- Search Observation: Google, Bing and other traditional search engines.
- AI Observation: ChatGPT, Gemini, Claude, Perplexity, Copilot and similar answer engines - not implemented by this SERP module.

SERP Observation never executes IA and never infers ranking causality. It records bounded facts: result ordering, whether the configured domain was found within the requested depth, and which observed results precede it.

The next implemented downstream layer can additionally classify those results and, only with explicit opt-in, compare deterministic content features. That downstream capability remains non-scoring and provider-neutral.

## 2. Architecture

```text
CMD / future Web API
        |
        v
Search Intelligence application service
        |
        v
SerpProvider contract
        |
        +-- FixtureSerpProvider
        +-- SerpApiProvider (Google live)
        +-- future adapters
        |
        v
canonical SerpObservation / SerpResult
        |
        +-- domain position / results-ahead analysis
        +-- audit.db persistence + raw evidence
        |
        +--> optional Competitive Search Intelligence
             +-- deterministic result classification
             +-- bounded candidate selection
             +-- optional public-page comparison
```

`SearchIntelligenceService` depends only on `SerpProvider`. Vendor request parameters, response keys, retries and normalization stay in concrete adapters. Provider construction lives in the runtime/composition layer.

## 3. Modes

### disabled

Default. No provider is built, no external request is executed and no SERP observation is persisted. Existing audit, SCORE-GEO-004, SARI-001, reports and other integrations remain independent.

### fixture

Reads canonical JSON from disk, performs zero network requests and emits `Data mode: FIXTURE`. Intended for tests, CI, local development and demos without provider quota.

Fixture data must never masquerade as live evidence.

### live

Builds the configured provider adapter. Current implementation supports `serpapi` with Google organic results and mobile/desktop device context.

For Google through SerpApi, provider pages contain up to 10 organic positions. Depth above 10 advances `start` by 10. Pagination stops if the provider exposes no next page.

## 4. Canonical contracts

### `SerpQueryRequest`

- query
- engine
- country
- region
- language
- device
- depth
- requested timestamp
- domain of interest
- run id
- query origin
- provider-independent metadata

`query_origin` supports `MANUAL`, `SEARCH_CONSOLE`, `BING_WEBMASTER`, `PAGE_CONTENT`, `AI_HYPOTHESIS`, `SERP_RELATED`, `COMPETITOR_DISCOVERY` and `EXTERNAL`. These describe provenance only.

### `SerpObservation`

- observation id
- run id and query provenance
- engine/market/language/device
- collection timestamp
- provider and optional provider request id
- requested depth
- normalized results
- data mode
- status
- raw evidence reference + SHA-256 when persisted
- config/quality metadata

For multi-page observations, the singular `provider_request_id` is left unset and the complete request-id list is preserved in `quality_metadata.provider_request_ids`.

### `SerpResult`

- absolute position
- normalized domain
- URL
- title
- snippet
- result type
- normalized SERP feature names
- provider-independent metadata

Vendor JSON does not enter canonical model objects.

## 5. Provenance

Canonical data modes:

- `OBSERVED_API`
- `OBSERVED_SYNTHETIC`
- `IMPORTED`
- `FIXTURE`
- `MODELED`
- `AI_INFERRED`

Current providers actively emit `OBSERVED_API` and `FIXTURE`. The remaining modes reserve explicit provenance semantics for future sources.

Raw provider evidence is stored only when an existing audit workspace is supplied. Secret-looking fields such as API keys, tokens, passwords, credentials and authorization values are recursively redacted before persistence.

## 6. Domain/depth semantics

Domain matching normalizes case, IDN hostnames and presentation-only `www.`. A configured root domain matches its subdomains; configuring a subdomain does not claim its parent domain.

Statuses:

- `FOUND`
- `NOT_FOUND_WITHIN_DEPTH`
- `NOT_REQUESTED`
- `UNAVAILABLE`
- `ERROR`
- `DISABLED`

**`NOT_FOUND_WITHIN_DEPTH` does not mean that the domain does not rank.** It states only that the domain was absent from the results actually observed within the requested ceiling.

If provider pagination ends early, quality metadata records `pagination_ended_before_requested_depth=true`.

## 7. Persistence

With `--audit-workspace`, SERP uses the existing `audit.db` and artifacts directory.

SERP foundation tables:

- `serp_observations`
- `serp_results`

Competitive Search Intelligence adds separate additive tables only when invoked:

- `serp_competitive_analyses`
- `serp_competitive_results`
- `serp_competitive_pages`

No Search Intelligence table changes SCORE-GEO-004 or SARI-001.

## 8. Provider safeguards and cost control

| Variable | Default | Purpose |
|---|---:|---|
| `RASAI_SERP_MODE` | `disabled` | global opt-in |
| `RASAI_SERP_PROVIDER` | `serpapi` | live adapter id |
| `RASAI_SERPAPI_API_KEY` | unset | BYOK SerpApi key |
| `RASAI_SERP_FIXTURE_PATH` | unset | fixture path |
| `RASAI_SERP_MAX_QUERIES` | `10` | query ceiling |
| `RASAI_SERP_MAX_REQUESTS` | `10` | provider HTTP-attempt budget |
| `RASAI_SERP_MAX_DEPTH` | `20` | requested depth ceiling |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | derived competitor/candidate ceiling |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | provider timeout |
| `RASAI_SERP_RETRIES` | `1` | bounded retries |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | minimum request-start interval |

Worst-case provider HTTP attempts per query:

```text
ceil(depth / 10) * (retries + 1)
```

The runtime blocks before provider construction if projected attempts exceed `RASAI_SERP_MAX_REQUESTS`, and the hard request budget is also consumed per actual attempt.

`--dry-run` validates these limits without external provider calls.

RASAI does not invent monetary provider pricing. Provider plan/quota determines actual API cost.

## 9. Security

- BYOK only; no provider key is hardcoded.
- Provider key is never printed.
- Vendor URLs containing secrets are not propagated to canonical objects/errors.
- Raw JSON evidence is secret-scrubbed before disk persistence.
- External payloads are untrusted and validated.
- Invalid result URLs/schemes/credentials are rejected by normalization.
- CI uses fixtures/mocks and no live provider/network.
- Optional competitor-page acquisition has a separate public-web safety boundary documented in `COMPETITIVE_SEARCH_INTELLIGENCE.md`.

## 10. CLI

The top-level router exposes `search` and technical alias `serp`.

Default/disabled:

```powershell
rasai search "seguro residencial cobre enchente" --domain loja.exemplo.com.br
```

Dry-run:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --depth 20 `
  --dry-run
```

Live:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --engine google `
  --country BR `
  --language pt-BR `
  --device mobile `
  --depth 20
```

Fixture:

```powershell
$env:RASAI_SERP_MODE="fixture"
rasai search "seguro residencial cobre enchente" `
  --domain cliente.example `
  --fixture tests\fixtures\serp\canonical_google.json
```

Deterministic competitive classification, no extra network:

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain cliente.example `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json `
  --competitive
```

Optional content comparison:

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --mode live `
  --depth 20 `
  --compare-content `
  --max-content-pages 3
```

Persist to an existing workspace by adding `--audit-workspace audits\<AUDIT_ID>`.

## 11. Fixture contract

Canonical fixture example:

```json
{
  "fixture_version": "SERP-FIXTURE-001",
  "query": "seguro residencial cobre enchente",
  "engine": "google",
  "country": "BR",
  "language": "pt-BR",
  "device": "desktop",
  "results": [
    {
      "position": 1,
      "url": "https://leader.example/page",
      "title": "Leader",
      "snippet": "Controlled fixture"
    }
  ]
}
```

Context values present in a fixture must match the request. Omitting an optional context field makes the fixture reusable for that field.

## 12. Search Console is not SERP

Future Search Console ingestion represents aggregated historical first-party metrics such as impressions, clicks, CTR and average position. SERP Observation is a point-in-time controlled query/engine/market/device/depth observation.

A difference between Search Console average position and one current SERP observation is not inherently an error.

## 13. Competitive layer relationship

Competitive Search & Content Intelligence is now implemented as an optional downstream consumer of canonical SERP evidence.

It adds:

- heuristic result-type classification;
- bounded candidate selection;
- optional public-page acquisition;
- deterministic title/meta/H1-H3/body-query/JSON-LD feature extraction;
- median-based observed-leader comparisons;
- content SHA-256 evidence without raw HTML persistence;
- explicit correlation-only interpretation.

It does **not** add ranking causality, AI semantic judgment or scoring impact.

## 14. HTML report decision

No new Search Intelligence HTML report is introduced yet. CLI plus `audit.db`/artifact evidence remain the POC surface while the competitive comparison contract is exercised.

A dedicated report becomes appropriate after historical/before-after and semantic evidence contracts are stable enough to avoid premature UI coupling.

## 15. Known limitations

- live adapter is currently Google via SerpApi;
- normalized rows focus on organic results;
- no provider billing/quota endpoint integration;
- no Search Console/Bing Webmaster ingestion;
- no historical rank tracker yet;
- competitive classification is a bounded heuristic, not a commercial entity graph;
- content comparison is static HTML and non-semantic;
- no AI Search observation in this package;
- no evidence-bound AI semantic competitive analysis yet;
- no distributed regional probes;
- no Search Intelligence HTML report yet.

## 16. Next milestones

The deterministic competitive layer is now the base for **Evidence-bound Semantic Competitive Analysis**:

```text
query + SERP evidence
+ extracted customer/candidate evidence
-> bounded semantic comparison
-> evidence-linked hypotheses/recommendations
```

Historical rank tracking and before/after comparison should also follow using the stable query/market/device/observation identity already persisted by Search Intelligence.
