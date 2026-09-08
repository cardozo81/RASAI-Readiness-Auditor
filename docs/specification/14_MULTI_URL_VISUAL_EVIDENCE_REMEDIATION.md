# Auditoria multi-URL e evidência visual - Multi-URL Audit + Visual/DOM Evidence + Actionable Remediation

**Estado no baseline de desenvolvimento:** NORMATIVE EVOLUTION
**Capacidade:** Auditoria multi-URL e evidência visual
**Report contract:** `REPORT-GEO-003`
**Scoring contract:** `SCORE-GEO-003` - unchanged by this capability

## 1. Purpose

Auditoria multi-URL e evidência visual evolves the persisted audit chain from score/finding/remediation text to a traceable structure capable of answering, from persisted evidence, what domain and page were audited, which Desktop/Mobile snapshot was used, what DOM element was observed when determinable, what visual evidence exists, what action is justified, how the correction is validated, and which technical authority or internal heuristic supports the recommendation.

The report remains a projection. Persisted audit state is the source of truth.

## 2. URL_SET input

A single positional target remains backward compatible.

An explicit sequence of targets or `--urls-file` creates `TargetType.URL_SET`, even if normalization/deduplication results in one unique URL. The explicit page universe must not silently fall back to ordinary discovery expansion.

For URL_SET:

- normalize URLs using the project URL policy;
- preserve ordered, deduplicated normalized input URLs;
- preserve separately the raw supplied count and normalized unique count;
- reject invalid URLs before audit acquisition;
- reject targets outside the same normalized origin before acquisition;
- require `max_pages` large enough for every unique explicit URL;
- create one `audit_id` and one workspace;
- persist all pages under that audit;
- keep Desktop and Mobile as independent `PageSnapshot` records.

## 3. Domain resources

`robots.txt` and sitemap resources are domain-scoped evidence. They are acquired once per audit/domain execution, not once per page.

Architecture:

```text
Audit
├── Domain context
│   ├── robots.txt
│   ├── sitemap(s)
│   └── domain-level Evidence
└── Pages
    ├── Page
    │   ├── Desktop PageSnapshot
    │   └── Mobile PageSnapshot
    └── ...
```

Domain-level evidence uses `page_id = null`, `snapshot_id = null`, `device = null`. Site-level findings must not be cloned into identical page-level findings merely because several explicit URLs were audited.

Sitemap evidence records at least state, discovery origin, HTTP acquisition, URL count, page URLs when interpretable, child sitemap references, redirects/network evidence through the persisted HTTP observation, and parsing error when present.

Absence of `robots.txt` or sitemap is not converted automatically into a `FAIL` unless an approved business rule explicitly defines that result. `BR-GEO-003` continues to prohibit automatic sitemap failure based only on absence.

## 4. Three evidence planes

Auditoria multi-URL e evidência visual preserves three distinct evidence planes:

```text
RAW HTTP
→ bytes and protocol response received from the server

Rendered DOM
→ HTML/DOM state after JavaScript rendering

Visual Snapshot
→ viewport image observed by Chromium
```

Visual evidence never replaces RAW or rendered evidence.

## 5. Visual snapshot

For each valid rendered `PageSnapshot`, Chromium attempts to persist a PNG viewport screenshot under the audit workspace using a relative path.

Baseline profiles remain:

- Desktop: `1440 × 900`;
- Mobile: `412 × 915`.

Metadata remains linked to the same snapshot and includes requested URL, final URL, viewport, device profile, captured timestamp and artifact reference. Report assets must remain local to the audit workspace/ZIP; no remote image dependency is allowed.

Screenshot capture failure must be represented as a limitation/evidence state and must not fabricate an image.

## 6. ElementObservation

Auditoria multi-URL e evidência visual adds an additive persisted `ElementObservation` concept with at least:

- `element_observation_id`;
- `audit_id`;
- `page_id`;
- `snapshot_id`;
- `device`;
- URL;
- selector CSS when determinable;
- tag name;
- element id;
- relevant classes;
- bounded/sanitized `outer_html`;
- bounded text excerpt;
- bounding box when the element is visibly located in the viewport;
- local artifact reference when applicable;
- captured timestamp.

The implementation must validate audit/page/snapshot/device consistency before persistence.

Current bounds:

- `outer_html`: 4096 characters;
- text excerpt: 512 characters;
- classes: at most 12, each bounded;
- selector: bounded and persisted only when actually generated from the observed DOM.

A missing or ambiguous selector remains `NÃO DETERMINADO`. No selector may be invented from a generic rule label.

## 7. Finding-to-element linkage

A finding may link to an `ElementObservation` only when the rule and persisted snapshot identify one concrete node deterministically.

If zero or multiple candidate nodes exist, the finding remains document/set-level. Example: heading hierarchy can be a relationship across several nodes; the auditor must not choose an arbitrary heading merely to populate a selector field.

When a linked observation has a valid visible bounding box and screenshot, the report may visually highlight that area. Non-visual findings such as HTTP headers, canonical/meta state, JSON-LD not visible in the viewport, robots and sitemap do not require finding-specific screenshots.

## 8. Actionability

Raw technical result and actionability are independent concepts.

Normative actionability values:

| Value | Report label | Meaning |
| --- | --- | --- |
| `REQUIRED_FIX` | AÇÃO NECESSÁRIA | Evidence-backed defect whose remediation is required by the applicable rule semantics. |
| `REVIEW_RECOMMENDED` | REVISÃO RECOMENDADA | Contextual or policy-sensitive condition requiring human review before deciding a site change. |
| `OPTIONAL_IMPROVEMENT` | MELHORIA OPCIONAL | Non-blocking capability/good practice; not an automatic defect. |
| `NO_ACTION` | NENHUMA AÇÃO NECESSÁRIA | Passed or not applicable. |
| `INSUFFICIENT_EVIDENCE` | AÇÃO NO SITE NÃO DETERMINADA | Auditor/tool lacks sufficient evidence; remediation must target evidence/audit conditions, not invent a site fix. |

Baseline deterministic projection:

- `PASS` / `NOT_APPLICABLE` → `NO_ACTION`;
- `UNKNOWN` / analysis/tool `ERROR` → `INSUFFICIENT_EVIDENCE`;
- `FAIL` → `REQUIRED_FIX` unless the approved rule semantics require contextual review;
- `WARNING` → normally `REVIEW_RECOMMENDED`;
- optional capability absence remains `OPTIONAL_IMPROVEMENT` when the rule explicitly makes it non-blocking.

Actionability never changes `RuleResult`, scoring contribution, weight, score, Coverage, Confidence or Consolidation.

## 9. Scoring invariants

Auditoria multi-URL e evidência visual não altera `SCORE-GEO-003` nem o `SARI-001`.

Mandatory invariants remain:

- `UNKNOWN != FAIL`;
- `ERROR != FAIL`;
- `NOT_APPLICABLE != FAIL`;
- missing AI does not create an artificial penalty;
- Coverage is not Score;
- Confidence is not Score;
- Desktop and Mobile are independent;
- Overall exists only when consolidation criteria are met.

### Zero versus absence

The report must render these states distinctly:

```text
Score: 0.0
Estado: CALCULADO
```

versus:

```text
Score: NÃO DETERMINADO
Estado: NÃO CALCULADO
```

and independently:

```text
Coverage: 0%
```

No report component may use numeric zero as a fallback for `None`/missing score.

## 10. Technical references

Auditoria multi-URL e evidência visual introduces a versioned rule-reference projection. Primary/authoritative technical sources must be preferred when they directly support a rule, including as applicable:

- IETF/RFC Editor;
- WHATWG;
- Google Search Central / Google crawling documentation;
- Schema.org when relevant;
- official OpenAI crawler/publisher documentation;
- official documentation for the technology being evaluated.

A heuristic rule without a directly applicable normative external source must render explicitly:

```text
Base: HEURISTIC
Fonte externa normativa: não aplicável / não identificada
Referência interna: BR-GEO-XXX
```

The auditor must never manufacture external authority.

Official links persisted in the Auditoria multi-URL e evidência visual rule-reference catalog were verified on `2026-09-02`.

## 11. OAI-SearchBot and GPTBot

Crawler policy reporting must keep `OAI-SearchBot` and `GPTBot` separate. Their purposes and controls are not interchangeable. The crawler matrix may also include the existing baseline crawlers such as Googlebot, Googlebot Smartphone and Bingbot.

No business recommendation may claim that permitting either crawler guarantees indexing, ranking, citation or inclusion in generated answers.

## 12. Report contract - REPORT-GEO-003

The Auditoria multi-URL e evidência visual report must visibly contain:

1. executive identification of project, `audit_id`, domain, input mode, raw supplied URL count, audited page count, time, AI provider/model state and limitations;
2. GEO compatibility, Coverage, Confidence and Consolidation without conflating them;
3. explicit Score zero versus not-calculated state;
4. linked inventory of audited URLs;
5. domain resources, including robots and sitemap state;
6. text-based status/actionability legend;
7. required actions and review items;
8. non-blocking optional improvements separated from defects;
9. Desktop and Mobile score/readiness projections where methodologically available;
10. page-by-page sections with URL prominence, snapshot states, viewport screenshots, findings, selectors/DOM observations when deterministic and remediation details;
11. prioritized correction plan;
12. semantic/entity/intent and citation/evidence-trust sections from persisted Análise semântica e fallback/Remediação GEO acionável state;
13. crawl/URL_SET coverage and limitations;
14. methodology and glossary.

Long URLs, selectors, HTML, JSON, IDs and model names must remain inside their containers. Required defensive CSS includes `min-width: 0`, safe wrapping, horizontal overflow for code/pre blocks, responsive grids/typography and `max-width: 100%` for screenshots.

## 13. Finding remediation projection

For an actionable finding, render when applicable:

- URL;
- Device;
- Rule;
- GEO category;
- raw result;
- Actionability;
- Priority;
- Selector;
- Element;
- observed HTML;
- problem;
- why it matters for GEO;
- exact change guidance bounded by evidence;
- recommended example clearly labeled as example;
- acceptance criteria;
- revalidation steps;
- technical reference.

Observed HTML must come from persisted evidence/observation. Recommended examples must never be presented as observed HTML.

If original HTML was not persisted, use the exact semantic message:

`Trecho HTML original não persistido para esta evidência.`

## 14. AI invariants

OpenAI remains optional. Auditoria multi-URL e evidência visual does not add a free-form LLM call to generate remediation.

Persisted Análise semântica e fallback outputs may be reused. AI:

- does not calculate official score;
- does not choose weights;
- does not convert unknown/error to fail;
- does not create selector/HTML/evidence/source/fact/claim not present in persisted state;
- does not create author, date, price, product coverage or structured data as facts.

When OpenAI is enabled, existing provider/model/assessment/reasoning/evidence/entity/intent traceability remains mandatory.

## 15. Persistence and backward compatibility

Auditoria multi-URL e evidência visual persistence is additive in the existing audit SQLite workspace. Base Auditoria e persistência tables are not rewritten merely to add Auditoria multi-URL e evidência visual evidence.

Additional tables may store:

- normalized URL input universe and raw/unique input summary;
- `ElementObservation`;
- finding-to-element linkage.

Existing single-target CLI options remain supported:

- `--project`;
- `--language`;
- `--market`;
- `--max-pages`;
- `--audits-root`;
- `--ai-provider`;
- `--ai-model`.

## 16. Minimum validation

Focused regression coverage must include:

- classic single URL input;
- same-origin multi-URL input;
- normalization/deduplication;
- incompatible-origin rejection before acquisition;
- `--urls-file` when implemented;
- one audit workspace for an explicit set;
- one robots acquisition and one acquisition per sitemap URL/domain resource;
- Desktop/Mobile screenshot artifacts and snapshot linkage;
- actual selector when deterministic and absence when not;
- bounded observed HTML/text;
- `UNKNOWN`, `ERROR`, `NOT_APPLICABLE` scoring invariants;
- `None != 0` report behavior;
- actionability mapping;
- report presence of domain, audit ID, URL inventory, page URL prominence, visual/DOM evidence, references, robots, sitemap and responsive wrapping;
- regression against invented canonical, author, date, structured data, claim, commercial fact, selector and observed HTML.

A real smoke may use the Bradesco Seguros store homologation domain when environment/connectivity permits. External websites are never unit-test fixtures.
