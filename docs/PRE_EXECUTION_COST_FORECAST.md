# Pre-execution Financial Cost Forecast

## Purpose

RASAi can estimate monetary exposure before a human-triggered audit starts when the selected configuration has comparable historical telemetry with known provider cost.

The feature is advisory. It does not replace the provider invoice and does not invent prices for integrations whose monetary billing is unknown.

## Local interactive console

The flow is:

1. the operator selects `R. Executar`;
2. execution profiles/session overlays are applied first;
3. RASAi reads recent immutable `AUD-*/audit.db` histories;
4. comparable provider/model/configuration calls are repriced with the current RASAi pricing catalog when token telemetry is sufficient;
5. only when a monetary forecast exists, the console shows successful-call baseline, expected cost, P25-P75 probable range, P90 potential scenario, sample size, estimated page volume and confidence;
6. the operator explicitly confirms or returns without starting the subprocess.

If no monetary estimate can be produced, execution follows the existing flow without an extra prompt.

For a TXT target the known URL count is used. For a crawl seeded by one URL, the comparable historical page-count median is used, bounded by the current `max_pages`.

Improvement Intelligence is included when its historical provider/model and persisted contract are comparable because its provider attempts use the canonical `ai_provider_attempts` telemetry.

## SaaS / control plane

The SaaS pilot exposes:

```text
POST /api/v1/projects/{project_id}/execution-cost-estimate
```

The request uses the same non-secret AUDIT payload that would be enqueued. The estimator is tenant/project/property/environment scoped and uses the centralized usage ledger plus durable execution-job configuration.

The browser flow is:

```text
configure -> estimate -> show only if monetary -> confirm -> enqueue
```

The existing `POST /execution-jobs` contract is intentionally unchanged. Schedules, workers and API automations therefore remain backward compatible and are not forced through an interactive confirmation.

For `ai_provider=auto`, the SaaS forecast uses the historical provider/model mix actually observed in comparable jobs. It does not infer worker credentials from the browser or control plane.

## Statistical model

For each comparable historical audit, RASAi calculates cost per materialized page.

- successful-call baseline: median successful cost/page;
- expected: median all-known billable cost/page;
- probable range: P25-P75;
- potential scenario: P90.

These rates are multiplied by the estimated page volume of the requested run.

Confidence is based on comparable executions: 1-4 low, 5-19 moderate, 20-49 good and 50+ high. Confidence is reduced when less than 80% of known calls can be repriced from current token telemetry.

## Billing safeguards

RASAi does not assume that every error is billable. A failed attempt contributes to the monetary forecast only when it has enough token/cost telemetry to establish an estimated cost.

RASAi does not perform implicit FX conversion. Mixed-currency comparable histories suppress the forecast rather than manufacture one number.

SERP, PageSpeed, CrUX and other integrations remain outside the monetary confirmation when RASAi has quota/usage telemetry but no canonical monetary estimate.
