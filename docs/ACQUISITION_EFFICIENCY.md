# RASAi acquisition and external-integration efficiency

## Objective

RASAi must minimize load on audited origins without weakening the meaning of any metric. Downstream analysis, scoring, AI and report generation must consume persisted evidence instead of re-opening the audited URL whenever the required information is already available.

The governing rule is:

> A new physical acquisition is allowed only when the observation cannot be derived from already-persisted evidence without changing the metric or context being measured.

## Canonical acquisition classes

### 1. Direct HTTP acquisition — URL scope

For `URL_SET` input, the direct HTTP acquisition stage performs one crawler-like request for each normalized URL in the explicit set. The result persists status, redirect chain, headers, body and elapsed time. This observation is intentionally distinct from a real-browser observation.

Domain resources such as `robots.txt` and eligible sitemap resources are origin-scoped and are not repeated once per page.

### 2. Browser snapshot — URL/device scope

The browser-capture stage performs one normal Chromium navigation for each selected URL/device context. The same navigation is reused for:

- rendered DOM;
- screenshot;
- main-document fingerprint when the already-buffered response can be read safely;
- navigation trace and safe request identity metadata;
- console/page errors and failed-request diagnostics;
- bounded DOM element observations;
- downstream deterministic extraction and semantic evidence.

No downstream rule, score, AI adapter or report generator may re-open the page merely to re-read these facts.

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

A bounded extra browser observation may be required when the initial rendered state exposes lazy-loading signals but essential content is still not recoverable. This is a conditional diagnostic acquisition, not a general second pass over every URL. It should remain a candidate for future same-session reuse when the browser-capture contract can preserve the post-interaction evidence without weakening traceability.

#### Crawling/discovery resources

Origin resources such as `llms.txt`, robots and sitemap diagnostics are collected at origin/resource scope, not once per audited page. They must not be multiplied by the URL count unless the resource itself is page-specific.

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

## Request policy summary

For a normal audit with one selected device and external features disabled, the intended page-level physical observations are:

1. one direct HTTP acquisition per URL;
2. one Chromium snapshot navigation per URL/device.

Additional target loads are permitted only for explicitly independent measurements such as PageSpeed/Lighthouse, Synthetic Apdex, or a bounded conditional interaction diagnostic. AI, scoring, report generation, comparison and other downstream logic must reuse persisted evidence.
