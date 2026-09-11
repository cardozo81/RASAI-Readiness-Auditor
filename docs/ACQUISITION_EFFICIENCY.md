# RASAi acquisition and external-integration efficiency

## Objective

RASAi must minimize load on audited origins without weakening the meaning of any metric. Downstream analysis, scoring, AI and report generation must consume persisted evidence instead of re-opening the audited URL whenever the required information is already available.

The governing rule is:

> A new physical acquisition is allowed only when the observation cannot be derived from already-persisted evidence without changing the metric or context being measured.

## Canonical acquisition classes

### 1. Direct HTTP acquisition - URL scope

For `URL_SET` input, the direct HTTP acquisition stage performs one crawler-like request for each normalized URL in the explicit set. The result persists status, redirect chain, headers, body and elapsed time. This observation is intentionally distinct from a real-browser observation.

Domain resources such as `robots.txt` and eligible sitemap resources are origin-scoped and are not repeated once per page.

### 2. Browser snapshot - URL/device scope

The browser-capture stage performs one normal Chromium navigation for each selected URL/device context. The same navigation is reused for:

- rendered DOM;
- screenshot;
- main-document fingerprint when the already-buffered response can be read safely;
- navigation trace and safe request identity metadata;
- console/page errors and failed-request diagnostics;
- bounded DOM element observations;
- Open Web Metrics baseadas nas W3C Web Performance APIs já presentes no navegador;
- bounded lazy-loading interaction when required by the lazy-content rule;
- downstream deterministic extraction and semantic evidence.

As Open Web Metrics são coletadas antes da interação diagnóstica de lazy loading, no mesmo documento já carregado, e registram `additional_navigation_requests=0` e `additional_external_api_calls=0`. Elas são habilitadas por default porque não usam provider pago, quota externa ou nova aquisição física. Permanecem advisory e não alteram `SARI-001`/`SCORE-GEO-004`.

The lazy-loading interaction runs only when the initial DOM exposes lazy signals and essential content is not yet recoverable. It scrolls the already-open browser page; it does **not** navigate the URL a second time. Primary DOM/screenshot evidence is frozen before the diagnostic interaction.

No downstream rule, score, AI adapter or report generator may re-open the page merely to re-read these facts.

### Browser wall-clock protection

The normal browser renderer is owned by a persistent isolated worker process. Healthy URL/device contexts reuse the same worker/browser session. A complete context has a fixed 60 s caller-side wall-clock safety deadline in addition to Playwright operation-level timeouts.

If the complete render exceeds that deadline:

- the browser worker process and its Chromium descendants are terminated;
- the timed-out URL/device is recorded as a render failure;
- the same URL is **not** retried automatically;
- the next context receives a fresh browser worker and the audit can continue.

Process isolation is used instead of a thread timeout because Playwright's synchronous API is thread-affine and a timed-out worker thread would continue running.

On Windows, where multiprocessing uses `spawn`, the browser worker reinstalls both the canonical device-capture contract and the Open Web Metrics collector before creating the renderer. This prevents same-session metrics from silently disappearing only in the isolated execution path.

### 3. Independent measurements

Some metrics are invalid if projected from the core snapshot and therefore require their own acquisition.

#### PageSpeed Insights / Lighthouse

PageSpeed is an external measurement service. Google performs its own Lighthouse navigation for the URL/device strategy. RASAi therefore permits one PageSpeed call per selected URL/device context.

Current runtime policy:

- one PageSpeed call per selected context;
- all configured Lighthouse categories are requested in that single call;
- no automatic retry by default;
- a caller-side wall-clock deadline bounds the complete provider wait;
- timeout/failure is fail-open and becomes an explicit unavailable/partial observation;
- this phase runs only after the core audit evidence has already been persisted.

A PageSpeed execution is not counted as a second local browser snapshot; it is an independent external measurement required for Lighthouse provenance.

#### CrUX

Direct CrUX access is a data-API lookup. It does not navigate the audited origin. In `field_source=auto`, RASAi first reuses field data already returned by PageSpeed and invokes direct CrUX only when field data is absent and a CrUX client is configured. `field_source=crux` remains an explicit operator choice.

#### Synthetic Apdex

Synthetic Navigation Apdex and Synthetic User Experience Apdex require repeated independent samples by definition. A single core snapshot cannot replace a statistical sample population.

Where the two Apdex methods use an equivalent URL/device/profile acquisition, RASAi may share an eligible physical navigation while preserving separate metric semantics. Repeated samples that are methodologically required are not treated as redundant requests.

#### Lazy-loading interaction probe

The lazy-content analysis no longer performs a default second page navigation. The bounded scroll is captured during the existing browser context and persisted as `bounded_lazy_probe` metadata with `additional_navigation_requests=0`. Downstream rule evaluation consumes that observation later. A separately supplied diagnostic adapter remains only as an explicit test/integration hook.

#### Crawling/discovery resources

Origin resources such as `llms.txt`, robots and sitemap diagnostics are collected at origin/resource scope, not once per audited page. They must not be multiplied by the URL count unless the resource itself is page-specific.

## Zero-cost same-session metrics

The rule “sem custo fica habilitado por default” applies only when the metric can be obtained without creating a new external dependency, quota, public scan or target acquisition.

`OPEN-WEB-METRICS-001` satisfies that requirement because it reads browser-native state from the existing `DEVICE_SNAPSHOT`. It may expose Navigation Timing, Resource Timing, Server-Timing presence, Paint/FCP/LCP observed, CLS observed, Event Timing when an interaction exists, Long Tasks, Long Animation Frames, aggregated User Timing and basic document/platform signals.

This does **not** authorize automatic execution of every nominally free internet service. W3C validators, MDN HTTP Observatory, WebPageTest and similar services remain provider/integration concerns because they create an external dependency or external observation. Browsertime/sitespeed.io similarly require their own runtime/dependencies. Browser-compatibility datasets such as Web Platform Baseline/MDN BCD must be versioned and integrated reproducibly before they can become default evidence.

## External-service phase

External services that are not part of direct core acquisition are treated as downstream enrichments over the persisted audit workspace.

The core audit may complete and persist its immutable evidence before PageSpeed, CrUX, AI or other optional providers finish. Optional-provider failure must not invalidate already-persisted core evidence.

Before external Web Performance collection, the operational log records a plan containing:

- selected contexts;
- planned PageSpeed calls;
- retry count;
- maximum PageSpeed-triggered target navigations;
- CrUX fallback policy;
- whether the core snapshot is being reused as input;
- that the provider phase is externalized after the core.

Before every provider wait, the operational log records URL, device, context index/total and the active timeout. The interactive console uses these events to display measured progress rather than remaining fixed at `~88%` with no internal unit.

## AI integration and token economy

AI must not fetch the audited website. Semantic AI receives only persisted RASAi evidence.

The semantic contract keeps one structured provider call per snapshot for the complete contracted semantic rule set. Device snapshots are not merged when their evidence identities differ.

Token reduction is allowed only when it does not remove semantic information needed by the model. The current lossless policy therefore:

- keeps the complete extracted main content;
- keeps Structured Data;
- keeps evidence ids and observed evidence;
- removes local `artifact_reference` paths because a remote provider cannot dereference them;
- removes the duplicated semantic-input title/excerpt because title and full main content are already present at the top level;
- instructs providers not to restate evidence, rule text or schema in reasoning fields;
- performs report generation without additional AI calls.

Blind truncation of page content is not a default optimization because it could alter semantic, answerability, entity or factual-claim assessments. Any future token budget must preserve deterministic coverage guarantees and expose truncation as an explicit limitation.

## URL-set file contract

User-authored TXT files accept UTF-8 with or without BOM. Blank lines and `#` comments are ignored. Every meaningful line is validated before execution; an invalid target is reported with its exact line number instead of being silently removed from exposure estimates or audit scope.

## Request policy summary

For a normal audit with one selected device and external features disabled, the intended page-level physical observations are:

1. one direct HTTP acquisition per URL;
2. one Chromium snapshot navigation per URL/device.

Open Web Metrics reuse item 2 and therefore do not add a third physical observation. A bounded lazy-load interaction may trigger additional subresource activity on the **same** browser page, but it does not create a second navigation. Additional target loads are permitted only for explicitly independent measurements such as PageSpeed/Lighthouse and Synthetic Apdex. AI, scoring, report generation, comparison and other downstream logic must reuse persisted evidence.
