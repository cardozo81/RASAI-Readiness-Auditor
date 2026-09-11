# Multi-URL report scope and aggregation

RASAi reports must make the ownership of every value explicit when an audit contains more than one URL. A reader must be able to distinguish a value for one URL, one URL/device context, an origin-level fact, a synthetic population, and an audit-level aggregate without inferring it from visual position.

## Overview dashboard

`index.html` is a synthesis surface; it does not imply that a card belongs to the first URL in the audit.

For multiple URLs:

- **SARI-001 Mobile/Desktop** is an audit-set aggregate for that device. SCORE-GEO-004 divides each scoring-group weight across its applicable page scopes, so adding URLs does not multiply the methodological weight of that group. It is neither one page's score nor an arithmetic average of independent page scores.
- **Core Web Vitals** is presented as valid contexts passing / valid contexts evaluated.
- **Lighthouse Performance** and **Lighthouse Accessibility** are presented as minimum-to-maximum ranges across valid URL/device contexts when more than one value exists. No unlabeled average is created.
- **Synthetic Navigation Apdex** is likewise summarized as a range across valid URL/device summaries. Each underlying summary still belongs to one URL/device sample population.

The generated report injects an `Escopo e agregação` disclosure with the URL count, available devices, and the aggregation rule used by the executive cards.

## Per-URL and per-context reports

`web-performance.html`, `accessibility.html`, `apdex.html`, `apdex-experience.html`, `mobile.html`, `desktop.html` and `context.html` receive an explicit scope disclosure when they are materialized.

Tables and cards preserve their native granularity. Client-side filtering and pagination change only what is visible; they do not recalculate scores or remove evidence from the HTML artifact.

## URL filter and pagination contract

The scalable report UI indexes each row/card from stable DOM `textContent` before/independently of display state. It must not use layout-dependent `innerText` as the source of truth because paginated rows use `display:none` and would otherwise become unsearchable after the first filter/page transition.

Consequences:

- switching repeatedly between URL filters must be idempotent;
- a row hidden by pagination remains eligible for later URL/search filters;
- returning to `Todas as URLs` restores the correct filtered collection;
- pagination always applies *after* the current filters;
- print output can expose the complete collection.

## Synthetic User Experience Apdex layout

The `Apdex calibrado por população e dispositivo` section can contain one population card per URL. For multi-URL audits these cards are laid out in a responsive grid instead of one long vertical column. The grid changes presentation only: each card remains one URL population and its Apdex value/sample counts are unchanged.

## No hidden aggregation

A new report surface that combines multiple URLs must choose and label one of these semantics explicitly:

1. individual URL or URL/device value;
2. count / pass ratio;
3. minimum-to-maximum range;
4. formally defined weighted aggregate;
5. explicitly labeled arithmetic statistic when the methodology genuinely defines one.

A report must not display a single value over multiple URLs without declaring which rule produced it.
