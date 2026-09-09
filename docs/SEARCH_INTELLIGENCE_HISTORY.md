# Search Intelligence History

## Objective

Search Intelligence History compares two persisted Search Intelligence observations over time while preserving the exact measurement context.

Current methodology identifier:

```text
SEARCH-HISTORY-001
```

The feature is observational. It does not claim that a deployment, content change or technical change caused a Search ranking movement.

## Comparison identity

A rank delta is computed only when baseline and current observations have the same:

- query;
- Search engine;
- country;
- region;
- language;
- device;
- requested result depth;
- customer domain.

The comparison also requires compatible observation provenance:

- both observations must have status `OBSERVED`;
- provider must remain the same;
- data mode must remain the same.

If any of these conditions changes, the context is reported as non-comparable instead of producing a misleading position delta.

## Position semantics

When the customer domain is `FOUND` in both observations, RASAI can report:

- `POSITION_IMPROVED`;
- `POSITION_REGRESSED`;
- `POSITION_UNCHANGED`.

Lower numeric position is better within the same observed context.

Example:

```text
before: 8
after: 4
delta: -4 positions
status: POSITION_IMPROVED
```

The delta is descriptive only. It is not a causal attribution.

## Observed depth boundary

`NOT_FOUND_WITHIN_DEPTH` is not converted to an artificial numeric rank.

If a customer moves from `NOT_FOUND_WITHIN_DEPTH` to `FOUND`, the event is:

```text
ENTERED_OBSERVED_DEPTH
```

If a customer moves from `FOUND` to `NOT_FOUND_WITHIN_DEPTH`, the event is:

```text
LEFT_OBSERVED_DEPTH
```

These states mean only that the domain entered or left the requested observation window. They do not establish an absolute position outside that depth.

## Deterministic content history

When both baseline and current observations have deterministic competitive comparison status `CONSOLIDATED`, the history layer can also compare persisted customer-page evidence:

- query coverage in visible body;
- query coverage in title;
- query coverage in headings;
- approximate visible-text word count;
- observed JSON-LD types;
- deterministic competitive gap codes.

Current event classes include:

- `CONTENT_SIGNAL_CHANGED`;
- `CONTENT_VOLUME_CHANGED`;
- `STRUCTURED_DATA_CHANGED`;
- `DETERMINISTIC_GAP_ADDED`;
- `DETERMINISTIC_GAP_RESOLVED`.

These events remain correlational evidence. Word count is not quality, markup difference is not an automatic recommendation, and a resolved content gap does not prove why Search position changed.

## Deployment and milestone integration

The history command can use the product platform milestone model that already selects baseline/current audits.

This keeps one before/after contract for the product instead of introducing a parallel deployment-marker system.

The timeline is interpreted as:

```text
baseline Search observation
        |
        v
milestone / deployment marker
        |
        v
current Search observation
        |
        v
observed Search and content differences
```

The marker establishes chronology, not causality.

## CLI

### Direct workspace comparison

```powershell
rasai search-history `
  --baseline-workspace audits/AUD-BASELINE `
  --current-workspace audits/AUD-CURRENT
```

Optional JSON output:

```powershell
rasai search-history `
  --baseline-workspace audits/AUD-BASELINE `
  --current-workspace audits/AUD-CURRENT `
  --json search-history.json
```

### Milestone-based comparison

```powershell
rasai search-history `
  --milestone <milestone-id> `
  --audits-root audits
```

The command supports the same baseline-selection modes used by the product platform:

```text
AUTO
GOLDEN
EXPLICIT
```

For explicit selection:

```powershell
rasai search-history `
  --milestone <milestone-id> `
  --baseline-mode EXPLICIT `
  --baseline-audit <audit-id> `
  --current-audit <audit-id>
```

## Output contract

The JSON/console output includes:

- baseline audit ID;
- current audit ID;
- methodology identifier;
- count of comparable contexts;
- count of non-comparable contexts;
- compatibility notes;
- event list;
- interpretation policy.

Each event can contain:

- exact context key;
- query;
- status;
- label;
- before value;
- after value;
- numeric delta when meaningful;
- unit;
- methodological note.

## Relationship with the HTML report

`report/search-intelligence.html` is the canonical point-in-time audit-level Search Intelligence surface.

`SEARCH-HISTORY-001` is a separate temporal comparison contract. Keeping the contracts separate prevents the point-in-time HTML from silently implying that a later observation was caused by a deployment.

A future historical HTML surface can render this persisted/computed comparison contract without changing its semantics.

## Scoring boundary

Search Intelligence History does not change:

```text
SARI-001
SCORE-GEO-004
```

Position changes, entry/exit from observed depth, deterministic content changes and competitive gaps have no automatic readiness-score weight.

Any future scoring use would require an explicit new methodology and validation contract.

## AI boundary

Competitive AI output is not currently converted into a semantic before/after score.

The deterministic history layer can compare the evidence that exists before and after. Any future semantic historical analysis must remain evidence-bound and must not infer private Search-engine causality.

## Security and persistence

The history layer is read-only with respect to audit workspaces.

It reads persisted evidence from `audit.db` and does not:

- call a Search provider;
- call an AI provider;
- crawl customer or competitor pages;
- rewrite Search observations;
- rewrite scoring tables.

This makes historical comparison reproducible from already persisted evidence.

## Limitations

- comparison currently uses the latest persisted observation for each exact context inside each audit workspace;
- provider or data-mode changes invalidate numeric rank comparison for that context;
- historical semantic comparison of Competitive AI recommendations is not yet a stable contract;
- no dedicated historical HTML page is generated yet;
- Search volatility and personalization remain external factors that must be considered when interpreting observed changes.
