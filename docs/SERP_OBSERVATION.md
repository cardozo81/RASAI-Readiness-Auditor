# SERP Observation - Search Intelligence foundation

Status: **implemented provider-neutral foundation / operational POC**.

SERP Observation is the factual traditional-Search evidence layer beneath RASAi Competitive Search & Content Intelligence. Vendor-specific request and response semantics remain isolated inside concrete adapters; downstream code consumes canonical `SerpObservation` and `SerpResult` objects.

Related contracts:

- deterministic competitive analysis: `COMPETITIVE_SEARCH_INTELLIGENCE.md`;
- optional evidence-bound semantic recommendations: `COMPETITIVE_AI_INTELLIGENCE.md`;
- deterministic temporal comparison: `SEARCH_INTELLIGENCE_HISTORY.md`;
- recurring longitudinal monitoring: `SEARCH_INTELLIGENCE_MONITORING.md`;
- Web/API and detached execution: `WEB_API_FOUNDATION.md`.

## 1. Scope

SERP means **Search Engine Results Page**. Traditional Search observation and AI-answer observation are separate concepts:

- **Search Observation:** Google, Bing and other traditional search engines;
- **AI Observation:** ChatGPT, Gemini, Claude, Perplexity, Copilot and similar answer engines.

The SERP layer never executes AI and never infers ranking causality. It records bounded facts such as result ordering, the observed position of a configured customer domain and which observed results precede it.

The canonical request contains `engine`, so downstream contracts are not tied to Google.

## 2. Architecture

```text
CMD / Web API / worker
        |
        v
Search Intelligence application service
        |
        v
SerpProvider contract
        |
        +-- FixtureSerpProvider
        +-- SerpApiProvider      -> Google live
        +-- SerpApiBingProvider  -> Bing live
        +-- future adapters
        |
        v
canonical SerpObservation / SerpResult
        |
        +-- customer position / results ahead
        +-- point-in-time audit persistence when requested
        +-- operational evidence sink for recurring monitoring
        |
        +--> Competitive Search Intelligence
        +--> Competitive AI (explicit opt-in)
        +--> SEARCH-HISTORY-001
        +--> SEARCH-MONITOR-001
```

`SearchIntelligenceService` depends only on `SerpProvider`. Provider construction stays in the runtime/composition layer.

The HTTP API does not execute Search collection inside the request process. Hosted-style execution is represented by durable `SEARCH_MONITOR` jobs consumed by workers.

## 3. Modes

### `disabled`

Default. No Search provider is built and no external Search request is made.

### `fixture`

Reads canonical fixture JSON, performs zero network calls and emits `Data mode: FIXTURE`. Intended for tests, CI, development and demos.

### `live`

Builds the configured live adapter.

Current live adapter IDs:

| Adapter ID | Engine | Vendor | Pagination |
|---|---|---|---|
| `serpapi` | Google | SerpApi | Google `start`, bounded 10-position pages |
| `serpapi-bing` | Bing | SerpApi | provider-reported Bing `first` cursor |

Both adapters use the same BYOK credential variable `RASAI_SERPAPI_API_KEY`. Keeping distinct adapter IDs preserves backward compatibility for the existing Google `serpapi` contract while allowing engine-specific pagination rules.

## 4. Google adapter

`serpapi` supports `engine=google` with desktop/mobile context.

Google pagination uses `start` in 10-position increments. For a requested depth greater than 10, RASAi requests additional pages while respecting the configured request budget and provider pagination availability.

The adapter rejects unsupported engines before network access.

## 5. Bing adapter

`serpapi-bing` supports `engine=bing` with desktop/mobile context.

Bing Search through SerpApi does **not** use the same fixed pagination contract as Google. The adapter therefore:

- builds `mkt` from configured language + country;
- forwards optional region through `location`;
- uses the provider-reported `serpapi_pagination.next` / `next_link`;
- extracts only the `first` cursor from that provider URL;
- reconstructs the next request locally instead of following an arbitrary provider-returned URL;
- converts page-local Bing positions into absolute observed positions;
- stops when requested depth is covered, provider pagination ends, or the hard request budget prevents further collection.

The cursor must be positive and strictly advance. Invalid or repeated cursors are treated as malformed provider responses.

## 6. Requested-depth completeness

`NOT_FOUND_WITHIN_DEPTH` is valid only when RASAi has enough evidence to treat the requested Search window as complete.

For provider-driven variable pagination, an execution can end because the configured request budget is exhausted before the requested depth is fully observed. In that state:

```text
requested_depth_complete = false
```

If the customer domain was **not** observed, RASAi returns:

```text
DomainMatchStatus.UNAVAILABLE
SERP_REQUESTED_DEPTH_INCOMPLETE
```

It does **not** return `NOT_FOUND_WITHIN_DEPTH` because doing so would claim more Search evidence than was actually collected.

If the customer domain was already observed in a partial collection, its observed position remains a valid fact and may still be returned as `FOUND`.

Bing quality metadata includes, when applicable:

- `pagination_strategy=serpapi_next_first`;
- `observed_position_ceiling`;
- `requested_depth_complete`;
- `request_budget_ended_before_requested_depth`;
- `pagination_ended_before_requested_depth`;
- provider request IDs and collection window timestamps.

## 7. Canonical request and observation contracts

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

`query_origin` supports `MANUAL`, `SEARCH_CONSOLE`, `BING_WEBMASTER`, `PAGE_CONTENT`, `AI_HYPOTHESIS`, `SERP_RELATED`, `COMPETITOR_DISCOVERY` and `EXTERNAL`.

### `SerpObservation`

Carries:

- observation ID;
- run/query provenance;
- engine/market/language/device;
- collection timestamp;
- provider and provider request IDs;
- requested depth;
- normalized results;
- data mode and observation status;
- raw evidence reference + SHA-256 when persisted;
- config/quality metadata.

### `SerpResult`

Carries:

- absolute observed position;
- normalized domain;
- URL;
- title;
- snippet;
- result type;
- normalized SERP features;
- provider-independent metadata.

Vendor JSON does not enter canonical downstream model objects.

## 8. Domain semantics

Domain matching normalizes case, IDN hostnames and presentation-only `www.`. A configured root domain matches its subdomains; configuring a subdomain does not imply its parent domain.

Current domain statuses:

- `FOUND`
- `NOT_FOUND_WITHIN_DEPTH`
- `NOT_REQUESTED`
- `UNAVAILABLE`
- `ERROR`
- `DISABLED`

`NOT_FOUND_WITHIN_DEPTH` means only that the domain was absent from a Search window that RASAi considers fully observed within the requested depth. It does not mean that the domain never ranks.

## 9. Provenance and persistence

Canonical data modes include:

- `OBSERVED_API`
- `OBSERVED_SYNTHETIC`
- `IMPORTED`
- `FIXTURE`
- `MODELED`
- `AI_INFERRED`

Current live SERP adapters emit `OBSERVED_API`; fixtures emit `FIXTURE`.

Raw provider evidence has two persistence paths:

- point-in-time Search Intelligence can persist inside an existing `AUD-*` workspace;
- recurring Search Monitoring uses a dedicated `.rasai/search-monitoring/` evidence root without mutating historical `AUD-*/audit.db` files.

Secret-looking fields are redacted before evidence persistence.

Point-in-time additive tables:

- `serp_observations`
- `serp_results`
- `serp_competitive_analyses`
- `serp_competitive_results`
- `serp_competitive_pages`
- `serp_competitive_ai_analyses` when Competitive AI is used.

Recurring control-plane tables:

- `search_monitor_queries`
- `search_monitor_runs`

No Search Intelligence table changes `SARI-001`, `SCORE-GEO-004` or scoring tables.

## 10. Safeguards and cost control

| Variable | Default | Purpose |
|---|---:|---|
| `RASAI_SERP_MODE` | `disabled` | global SERP opt-in |
| `RASAI_SERP_PROVIDER` | `serpapi` | live adapter ID |
| `RASAI_SERPAPI_API_KEY` | unset | BYOK SerpApi key |
| `RASAI_SERP_FIXTURE_PATH` | unset | fixture path |
| `RASAI_SERP_MAX_QUERIES` | `10` | query ceiling |
| `RASAI_SERP_MAX_REQUESTS` | `10` | global provider HTTP-attempt budget |
| `RASAI_SERP_MAX_DEPTH` | `20` | requested depth ceiling |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | derived candidate ceiling |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | timeout per provider attempt |
| `RASAI_SERP_RETRIES` | `1` | bounded retries |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | minimum request-start interval |

For the Google adapter, the deterministic preflight ceiling is:

```text
ceil(depth / 10) * (retries + 1)
```

For `serpapi-bing`, organic rows per page are provider-variable, so `--dry-run` reports the configured global `RASAI_SERP_MAX_REQUESTS` as the conservative Search-provider ceiling. Actual attempts remain hard-bounded by the shared `RequestBudget`.

RASAi does not invent provider pricing. Actual cost follows the customer/provider plan and quota.

## 11. Security boundaries

- BYOK; no hardcoded Search-provider key;
- provider key is never printed;
- external payloads are untrusted and normalized;
- invalid result URLs/schemes/credentials are rejected;
- Bing pagination never follows an arbitrary provider-returned URL; only the validated numeric cursor is reused;
- raw provider evidence is secret-scrubbed before persistence;
- CI uses fixtures/mocks and must not consume live Search quota.

Optional competitor-page acquisition has a separate SSRF/public-web boundary documented in `COMPETITIVE_SEARCH_INTELLIGENCE.md`.

Optional Competitive AI receives structured evidence, not raw provider credentials or raw HTML.

For multi-tenant hosted execution, application-level URL validation is not a substitute for network-layer egress controls.

## 12. CLI examples

Google:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine google `
  --country BR `
  --language pt-BR `
  --device mobile `
  --depth 20
```

Bing:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi-bing"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine bing `
  --country BR `
  --language pt-BR `
  --region "Porto Alegre, RS, Brazil" `
  --device desktop `
  --depth 20
```

Dry-run:

```powershell
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine bing `
  --provider serpapi-bing `
  --mode live `
  --depth 20 `
  --dry-run
```

Fixture, Competitive Search, content comparison and Competitive AI continue to use the existing provider-neutral downstream contracts.

Recurring observation is exposed through `rasai search-monitor` and stores the selected adapter/engine in the registered query context so incompatible provider changes are never silently compared.

## 13. Search Console and Bing Webmaster are different evidence sources

Search Console and Bing Webmaster represent aggregated first-party performance/observability data. SERP Observation is a controlled point-in-time Search query observation.

A Search Console/Bing Webmaster average position is not expected to equal one controlled SERP observation.

Those ingestion surfaces remain separate from the live SERP adapter contract.

## 14. Reporting and history

Point-in-time audit report:

```text
AUD-*/report/search-intelligence.html
```

Pair-level deterministic history:

```text
search-history/SH-*/report.html
search-history/SH-*/manifest.json
```

Recurring longitudinal report:

```text
platform-report/search-intelligence.html
```

All are persisted-evidence projections. Rendering does not call Search or AI providers.

## 15. Current limitations

- live traditional Search adapters currently use one vendor, SerpApi, for Google and Bing;
- normalized Search rows remain focused on organic results;
- no provider billing/quota endpoint integration;
- competitive result classification is heuristic, not a commercial entity graph;
- competitor content comparison uses static HTTP HTML rather than rendered browser DOM;
- no canonical/hreflang/link-graph competitive comparison contract yet;
- Competitive AI live support currently starts with OpenAI;
- historical semantic comparison of Competitive AI output is not yet a stable contract;
- recurring monitoring detects changes but does not yet expose a complete external notification product surface;
- no distributed regional Search probes;
- portable recurring schedule execution remains single-machine; hosted horizontal execution depends on the durable worker/queue deployment model.

## 16. Next evolution

Periodic query observation is already implemented under `SEARCH-MONITOR-001`. The next Search Intelligence extensions should therefore focus on:

1. adding an independent second Search-data vendor/provider behind `SerpProvider`, reducing vendor concentration;
2. expanding normalized SERP-feature coverage where provider evidence supports it;
3. adding rendered-DOM competitive acquisition for client-rendered pages while preserving bounded static acquisition;
4. adding deterministic canonical, hreflang and bounded link-graph comparisons;
5. exposing material Search-monitor change events through controlled notification destinations;
6. adding distributed/regional observation only when SaaS demand justifies its operational cost;
7. defining semantic longitudinal comparison only after a reproducible evidence-bound methodology exists.

Search volatility remains observational. Neither ranking movement, alert timing nor temporal proximity to a deployment may be presented as proof of ranking causality.
