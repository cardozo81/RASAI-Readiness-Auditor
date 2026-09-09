# SERP Observation - Search Intelligence foundation

Status: **implemented provider-neutral foundation / POC**.

SERP Observation is the factual Search evidence layer beneath RASAI Competitive Search & Content Intelligence. SERP adapters observe and normalize Search results; downstream modules may classify, compare and, when explicitly requested, perform evidence-bound semantic analysis without importing vendor response semantics into the core.

Related contracts:

- deterministic comparison: `COMPETITIVE_SEARCH_INTELLIGENCE.md`;
- optional semantic recommendations: `COMPETITIVE_AI_INTELLIGENCE.md`.

## 1. Scope and semantics

SERP means **Search Engine Results Page**. The canonical model is not Google-specific: `engine` is part of every request and observation. The first live adapter is **SerpApi for Google organic results**. Future adapters can support other traditional Search providers without changing downstream analysis contracts.

Traditional Search observation and AI-answer observation are separate concepts:

- **Search Observation:** Google, Bing and other traditional search engines;
- **AI Observation:** ChatGPT, Gemini, Claude, Perplexity, Copilot and similar answer engines.

The SERP provider layer itself never executes AI and never infers ranking causality. It records bounded facts such as result ordering, whether the configured domain was found within the requested depth and which observed results precede it.

An optional downstream Competitive AI layer may analyze already-extracted Search/content evidence. That does **not** convert AI output into SERP evidence and does not modify the observed ranking.

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
        +-- audit.db persistence + raw provider evidence
        |
        +--> Competitive Search Intelligence (optional)
             +-- deterministic result classification
             +-- bounded candidate selection
             +-- public-page comparison (explicit opt-in)
             +-- extracted feature evidence
             |
             +--> Competitive AI (explicit opt-in)
                  +-- closed evidence_ids
                  +-- semantic opportunities / hypotheses
                  +-- no ranking-causality claim
```

`SearchIntelligenceService` depends only on `SerpProvider`. Vendor request parameters, response keys, retries and normalization stay in concrete adapters. Provider construction lives in the runtime/composition layer.

## 3. SERP modes

### `disabled`

Default. No SERP provider is built, no external Search request is executed and no SERP observation is persisted. Existing audit, `SCORE-GEO-004`, `SARI-001`, reports and integrations remain independent.

### `fixture`

Reads canonical JSON from disk, makes zero network requests and emits `Data mode: FIXTURE`. Intended for tests, CI, development and demos without provider quota. Fixture data never masquerades as live evidence.

### `live`

Builds the configured provider adapter. The current implementation supports `serpapi` with Google organic results and mobile/desktop context.

For Google through SerpApi, provider pages contain up to 10 organic positions. Requested depth above 10 advances `start` by 10. Pagination stops if the provider exposes no next page.

## 4. Canonical contracts

### `SerpQueryRequest`

Carries:

- query;
- engine;
- country/market;
- optional region;
- language;
- device;
- requested depth;
- requested timestamp;
- domain of interest;
- run ID;
- query origin;
- provider-independent metadata.

`query_origin` supports `MANUAL`, `SEARCH_CONSOLE`, `BING_WEBMASTER`, `PAGE_CONTENT`, `AI_HYPOTHESIS`, `SERP_RELATED`, `COMPETITOR_DISCOVERY` and `EXTERNAL`. Origin is provenance, not quality or ranking judgment.

### `SerpObservation`

Carries:

- observation ID;
- run ID and query provenance;
- engine/market/language/device;
- collection timestamp;
- provider and optional provider request ID;
- requested depth;
- normalized results;
- data mode and observation status;
- raw evidence reference + SHA-256 when persisted;
- config/quality metadata.

For multi-page observations, the singular `provider_request_id` remains unset and the complete request-ID list is retained in `quality_metadata.provider_request_ids`.

### `SerpResult`

Carries:

- absolute position;
- normalized domain;
- URL;
- title;
- snippet;
- result type;
- normalized SERP feature names;
- provider-independent metadata.

Vendor JSON does not enter canonical downstream model objects.

## 5. Provenance

Canonical data modes:

- `OBSERVED_API`
- `OBSERVED_SYNTHETIC`
- `IMPORTED`
- `FIXTURE`
- `MODELED`
- `AI_INFERRED`

Current SERP providers actively emit `OBSERVED_API` and `FIXTURE`. The other modes reserve explicit provenance semantics for future sources; they are not silently substituted for observed Search results.

Raw provider evidence is stored only when an existing audit workspace is supplied. Secret-looking fields such as API keys, tokens, passwords, credentials and authorization values are recursively redacted before persistence.

## 6. Domain and depth semantics

Domain matching normalizes case, IDN hostnames and presentation-only `www.`. A configured root domain matches its subdomains; configuring a subdomain does not imply its parent/root domain.

Statuses:

- `FOUND`
- `NOT_FOUND_WITHIN_DEPTH`
- `NOT_REQUESTED`
- `UNAVAILABLE`
- `ERROR`
- `DISABLED`

**`NOT_FOUND_WITHIN_DEPTH` does not mean that the domain does not rank.** It states only that the domain was absent from the results observed within the requested ceiling.

If provider pagination ends early, quality metadata records `pagination_ended_before_requested_depth=true`.

## 7. Persistence

With `--audit-workspace`, Search Intelligence uses the existing `audit.db` and artifacts directory.

SERP foundation tables:

- `serp_observations`
- `serp_results`

Deterministic Competitive Search tables, created additively when used:

- `serp_competitive_analyses`
- `serp_competitive_results`
- `serp_competitive_pages`

Competitive AI adds, when invoked:

- `serp_competitive_ai_analyses`

No Search Intelligence table changes `SCORE-GEO-004`, `SARI-001` or scoring tables.

## 8. Provider safeguards and cost control

| Variable | Default | Purpose |
|---|---:|---|
| `RASAI_SERP_MODE` | `disabled` | global SERP opt-in |
| `RASAI_SERP_PROVIDER` | `serpapi` | live adapter ID |
| `RASAI_SERPAPI_API_KEY` | unset | BYOK SerpApi key |
| `RASAI_SERP_FIXTURE_PATH` | unset | fixture path |
| `RASAI_SERP_MAX_QUERIES` | `10` | query ceiling |
| `RASAI_SERP_MAX_REQUESTS` | `10` | provider HTTP-attempt budget |
| `RASAI_SERP_MAX_DEPTH` | `20` | requested depth ceiling |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | derived candidate ceiling |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | provider timeout |
| `RASAI_SERP_RETRIES` | `1` | bounded retries |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | minimum request-start interval |

Worst-case provider attempts per query:

```text
ceil(depth / 10) * (retries + 1)
```

The runtime blocks before provider construction when the projected ceiling exceeds `RASAI_SERP_MAX_REQUESTS`. The hard request budget is also consumed per actual provider attempt.

`--dry-run` validates limits without making provider, content or Competitive AI calls.

RASAI does not invent provider pricing. Actual API cost follows the provider plan/quota.

## 9. Security boundaries

SERP provider boundary:

- BYOK; no hardcoded provider key;
- provider key is never printed;
- external payloads are untrusted and normalized;
- invalid result URLs/schemes/credentials are rejected;
- raw provider evidence is secret-scrubbed before persistence;
- CI uses fixtures/mocks with no live provider request.

Optional competitor-page acquisition has a separate public-web/SSRF boundary documented in `COMPETITIVE_SEARCH_INTELLIGENCE.md`.

Optional Competitive AI has a separate evidence/credential boundary documented in `COMPETITIVE_AI_INTELLIGENCE.md`. It receives structured extracted evidence, not raw HTML or SERP/API credentials.

## 10. CLI

Top-level routes: `search` and technical alias `serp`.

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

Live SERP:

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
rasai search "seguro residencial cobre enchente" `
  --domain cliente.example `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json
```

Classification only, without extra network:

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain cliente.example `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json `
  --competitive
```

Content comparison:

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --mode live `
  --depth 20 `
  --compare-content `
  --max-content-pages 3
```

Evidence-bound Competitive AI:

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --mode live `
  --depth 20 `
  --compare-content `
  --ai-competitive `
  --ai-provider openai `
  --ymyl-mode AUTO
```

`--ai-competitive` requires `--compare-content` and is called only for deterministic analyses with status `CONSOLIDATED`.

Persist into an existing workspace with `--audit-workspace audits\<AUDIT_ID>`.

## 11. Fixture policy

A canonical SERP fixture represents normalized Search evidence and must match any context fields it declares. Omitting an optional context field makes the fixture reusable for that field.

Competitive AI has a separate fixture schema described in `COMPETITIVE_AI_INTELLIGENCE.md`; a semantic fixture is never promoted to live Search evidence.

## 12. Search Console is not point-in-time SERP

Search Console represents aggregated historical first-party metrics such as impressions, clicks, CTR and average position. SERP Observation is a point-in-time controlled query/engine/market/device/depth observation.

A difference between Search Console average position and one current SERP observation is not inherently an error.

## 13. Relationship with downstream analysis

The deterministic Competitive Search layer adds:

- heuristic result classification;
- bounded candidate selection;
- optional public-page acquisition;
- title/meta/H1-H3/body-query/JSON-LD feature extraction;
- median-based observed-leader comparisons;
- content SHA-256 evidence without raw HTML persistence;
- correlation-only interpretation.

The optional Competitive AI layer runs **after** that deterministic context is consolidated. It may propose evidence-linked content/search opportunities but cannot rewrite positions, invent evidence or claim that a difference caused ranking.

Neither downstream layer changes `SARI-001` or `SCORE-GEO-004`.

## 14. HTML report decision

No Search Intelligence-specific HTML report is introduced yet. CLI plus `audit.db`/artifact evidence remain the POC surface.

The platform already has deployment markers and before/after audit resolution. Historical Search Intelligence should first extend that existing comparison architecture; a dedicated HTML surface should then consume the stabilized historical + deterministic + optional semantic contracts rather than introducing a parallel model prematurely.

## 15. Known limitations

- current live SERP adapter is Google via SerpApi;
- normalized SERP rows focus on organic results;
- no SERP-provider billing/quota endpoint integration;
- Search Console/Bing Webmaster ingestion remains separate from this provider adapter;
- competitive classification is a bounded heuristic, not a commercial entity graph;
- content comparison uses static HTTP HTML, not browser-rendered DOM;
- Competitive AI live support initially uses OpenAI behind a provider-neutral contract;
- Competitive AI receives extracted features rather than full raw HTML;
- historical Search Intelligence before/after is not yet integrated into platform comparisons;
- no distributed regional probes;
- no Search Intelligence-specific HTML report yet.

## 16. Next evolution

The next structural extension is historical Search Intelligence using the platform's existing deployment/before-after model:

```text
same query + engine + market + language + device
+ baseline Search observation
+ post-deploy Search observation
-> comparable position/result/content changes
-> deterministic difference evolution
-> optional semantic opportunity evolution
```

Temporal association remains observational. A post-deploy ranking/content movement must not be presented automatically as caused by the deployment.
