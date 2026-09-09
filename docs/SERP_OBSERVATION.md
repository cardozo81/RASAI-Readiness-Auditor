# SERP Observation — Search Intelligence foundation

Status: **implemented foundation / POC**.

This milestone adds a provider-neutral SERP observation layer to RASAi. It does **not** implement Competitive Content Intelligence, AI Search observation, historical rank tracking, Search Console ingestion, investment recommendations, or a new HTML report.

## 1. Scope and semantics

SERP means **Search Engine Results Page**. The model is intentionally not Google-specific. `engine` is part of the canonical request and observation contract. The first live adapter currently implemented is **SerpApi for Google organic results**; future adapters can add Bing, Brave or other traditional Search engines without changing Search Intelligence analysis code.

Traditional Search and AI observation remain separate concepts:

- Search Observation: Google, Bing and other traditional search engines.
- AI Observation: ChatGPT, Gemini, Claude, Perplexity, Copilot and similar answer engines — **not implemented by this SERP module**.

The SERP layer never executes IA and does not infer causality. It observes results, normalizes them and derives only bounded facts such as whether the configured domain was found within the requested depth and which observed results precede it.

## 2. Implemented architecture

```text
CMD / future Web API
        |
        v
Search Intelligence application service
        |
        v
SerpProvider contract
        |
        +-- FixtureSerpProvider   (implemented)
        +-- SerpApiProvider      (implemented; Google live)
        +-- future adapters      (Bing/DataForSEO/distributed probes/...)
        |
        v
canonical SerpObservation / SerpResult
        |
        +-- domain position / results-ahead analysis
        +-- additive audit.db persistence (when an audit workspace is supplied)
        +-- raw evidence artifact (when available)
```

`SearchIntelligenceService` depends only on the `SerpProvider` abstraction. Vendor request parameters, response keys, retries and normalization details are confined to the concrete adapter. There is no `if provider == "serpapi"` logic inside the Search Intelligence service.

Provider construction lives in the runtime/composition layer. This is the only layer that knows which concrete adapters are installed.

## 3. Modes

### disabled

Default. No provider is built, no external request is executed and no SERP observation is persisted. Existing RASAi audits, SCORE-GEO-004, SARI-001, reports, IA-off mode, Lighthouse/CrUX and current CLI behavior remain independent of SERP.

### fixture

Reads a canonical JSON fixture from disk. It performs **zero network requests** and marks the observation as `FIXTURE`. This mode is intended for tests, CI, regression, local development and demos without quota consumption.

Fixtures must never be presented as observed live data.

### live

Builds the configured live adapter. The first implementation is `serpapi`, currently supporting `engine=google`, `device=mobile|desktop` and organic results. Unsupported engines/devices fail explicitly rather than being silently coerced.

## 4. Canonical model

### `SerpQueryRequest`

- `query`
- `engine`
- `country`
- `region`
- `language`
- `device`
- `depth`
- `requested_at`
- `domain_of_interest` (optional in the model; required by the current `rasai search` ranking command)
- `run_id`
- `query_origin`
- provider-independent configuration metadata

`query_origin` currently supports `MANUAL`, `SEARCH_CONSOLE`, `BING_WEBMASTER`, `PAGE_CONTENT`, `AI_HYPOTHESIS`, `SERP_RELATED`, `COMPETITOR_DISCOVERY` and `EXTERNAL`. These values describe provenance only; they do not imply those integrations are implemented.

### `SerpObservation`

- `observation_id`
- `run_id`
- query and query origin
- engine / country / region / language / device
- collection timestamp
- provider and optional provider request id
- requested depth
- normalized result count
- normalized `results[]`
- data mode
- observation status
- optional raw evidence reference + SHA-256
- configuration and quality metadata

### `SerpResult`

- `position`
- normalized domain
- URL
- title
- snippet
- result type
- provider-independent SERP feature names when mapped
- provider-independent metadata when useful

The vendor JSON is **not** embedded in canonical model objects. When available it is stored only as opaque raw evidence.

## 5. Data provenance

Supported canonical data modes are:

- `OBSERVED_API`
- `OBSERVED_SYNTHETIC`
- `IMPORTED`
- `FIXTURE`
- `MODELED`
- `AI_INFERRED`

This milestone actively emits `OBSERVED_API` for SerpApi and `FIXTURE` for fixture mode. The other values reserve explicit provenance semantics for future sources; they are not claims that those sources already exist.

Raw JSON evidence is stored under the existing audit workspace `artifacts/serp/<observation>/` only when an existing audit workspace is supplied. JSON evidence is recursively scrubbed for field names that look like API keys, tokens, passwords, credentials, authorization values or secrets before persistence.

## 6. Domain matching and depth semantics

The domain matcher normalizes case, IDN hostnames and the presentation-only `www.` prefix. A configured root domain also matches its subdomains. A configured subdomain does not automatically claim its parent domain.

The first matching result determines the observed customer position. Multiple results from the same domain remain valid SERP rows. The derived list of competitor domains ahead is de-duplicated while preserving observed order.

Statuses are explicit:

- `FOUND`: the domain was found inside the requested depth.
- `NOT_FOUND_WITHIN_DEPTH`: the domain was not present in the observed results up to the requested depth.
- `UNAVAILABLE`: the provider/request was unavailable.
- `ERROR`: provider payload/configuration could not be interpreted safely.
- `DISABLED`: SERP mode is disabled.
- `NOT_REQUESTED`: canonical observation exists but no domain was requested for matching.

**`NOT_FOUND_WITHIN_DEPTH` does not mean “the domain does not rank”.** If depth is 10 and the domain is at position 37, the correct result remains `NOT_FOUND_WITHIN_DEPTH` for that observation.

## 7. Persistence

When `--audit-workspace` is supplied, SERP uses the existing workspace database (`audit.db`) and artifacts directory. It does not create a parallel database.

Additive tables:

- `serp_observations`
- `serp_results`

The tables keep audit/run/query/engine/market/device/timestamp/provider/depth/data-mode/status/raw-evidence provenance and normalized results. Existing audit/scoring tables are not modified by SERP analysis.

Without `--audit-workspace`, the command returns/prints the observation but does not invent a second persistence location.

## 8. POC safeguards and cost control

Environment defaults are conservative:

| Variable | Default | Purpose |
|---|---:|---|
| `RASAI_SERP_MODE` | `disabled` | global opt-in mode |
| `RASAI_SERP_PROVIDER` | `serpapi` | live adapter id |
| `RASAI_SERPAPI_API_KEY` | unset | BYOK SerpApi key; secret |
| `RASAI_SERP_FIXTURE_PATH` | unset | canonical fixture path |
| `RASAI_SERP_MAX_QUERIES` | `10` | max queries in one execution |
| `RASAI_SERP_MAX_REQUESTS` | `10` | hard HTTP request budget |
| `RASAI_SERP_MAX_DEPTH` | `20` | max requested depth |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | max unique derived competitor domains |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | timeout per live HTTP attempt |
| `RASAI_SERP_RETRIES` | `1` | bounded retries after first attempt |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | minimum interval between live request starts |

Before provider construction, the runtime computes the **worst-case HTTP request ceiling** as `queries × (retries + 1)` for live mode. If this exceeds `RASAI_SERP_MAX_REQUESTS`, execution is blocked before any external request.

`--dry-run` validates the same query/depth/request ceilings without provider construction and without consuming quota.

RASAi does not invent a monetary SerpApi price. Actual cost depends on the customer's provider plan and quota. This milestone tracks/limits request count; provider account/billing telemetry is not yet integrated.

## 9. Security

- no provider API key is hardcoded;
- `RASAI_SERPAPI_API_KEY` is read from the process environment/BYOK configuration;
- the key is never printed by the SERP CLI;
- vendor-specific URLs containing the key are not propagated into canonical models or error messages;
- raw JSON evidence is secret-scrubbed before disk persistence;
- external payloads are treated as untrusted and validated;
- result URLs with unsupported schemes, credentials or invalid hostnames are dropped from normalized results and counted in quality metadata;
- tests use fixtures/mocks and never require a real provider key or network.

## 10. CLI / CMD usage

The top-level RASAi router exposes both `search` and the technical alias `serp`.

### Default / disabled

```powershell
rasai search "seguro residencial cobre enchente" --domain loja.exemplo.com.br
```

With default configuration this returns `DISABLED` and performs zero external requests.

### Dry-run before live usage

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --country BR `
  --region "Porto Alegre, RS, Brazil" `
  --device mobile `
  --depth 20 `
  --dry-run
```

### Live SerpApi / Google

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

### Fixture mode

```powershell
$env:RASAI_SERP_MODE="fixture"
rasai search "seguro residencial cobre enchente" `
  --domain cliente.example `
  --fixture tests\fixtures\serp\canonical_google.json
```

Fixture output is marked `Data mode: FIXTURE`.

### Persist into an existing RASAi audit workspace

```powershell
rasai search "seguro residencial cobre enchente" `
  --domain loja.exemplo.com.br `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json `
  --audit-workspace audits\<AUDIT_ID>
```

This writes to that workspace's `audit.db` and `artifacts/`; it does not modify scoring.

## 11. Canonical fixture format

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

Context fields present in a fixture must match the corresponding request. Omitting an optional context field makes the fixture reusable for that field; it does not turn fixture data into live evidence.

## 12. Search Console is not SERP

Future Search Console ingestion will represent aggregated historical first-party metrics such as impressions, clicks, CTR and average position. SERP observation is a point-in-time controlled observation of a specific query/engine/market/device/depth.

A future difference between Search Console average position and a current SERP observation is therefore not inherently an error.

## 13. HTML report decision for this milestone

No new HTML report is introduced yet. The foundation persists canonical observations and exposes them via the CLI. This avoids presenting Competitive Content Intelligence, content gaps or recommendations before those capabilities exist.

A dedicated Search Intelligence report is appropriate in the next milestone once result selection, competitive comparison and historical/before-after views have a stable public contract.

## 14. Known limitations

- live adapter currently implements Google through SerpApi only;
- normalization currently focuses on organic results; rich/non-organic SERP features are not yet modeled as standalone result rows;
- no provider-account quota/billing endpoint is queried;
- no historical scheduler/rank tracker yet;
- no Search Console/Bing Webmaster ingestion yet;
- no automatic business-competitor classification; observed domains are Search/query competitors only;
- no Competitive Content Intelligence or AI semantic gap analysis yet;
- no AI Search observation in this package;
- no distributed regional probes yet;
- no HTML Search Intelligence report yet.

## 15. Next milestone

Recommended next milestone: **Competitive Search & Content Intelligence**.

```text
query
→ SERP observation
→ customer ranking
→ selected results ahead
→ public-page crawl using existing RASAi controls
→ structured technical/content comparison
→ evidence-backed gaps
→ optional semantic analysis
→ recommendations expressed as correlations/hypotheses, not causal claims
```

Historical SERP/rank tracking and before/after measurement should follow after the observation and comparison contracts are stable.
