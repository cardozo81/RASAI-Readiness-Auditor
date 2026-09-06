# Guia das Business Rules — BR-GEO-001..054

Este guia explica a Stable Local Baseline. A definição normativa prevalente está em [`docs/specification/03_BUSINESS_RULES.md`](specification/03_BUSINESS_RULES.md).

## Contrato comum

Resultados possíveis: `PASS`, `FAIL`, `WARNING`, `UNKNOWN`, `NOT_APPLICABLE`, `ERROR`.

Regras de interpretação:

```text
UNKNOWN != FAIL
ERROR != FAIL
NOT_APPLICABLE != FAIL
```

Finding exige RuleExecution + Evidence rastreável. Falhas de pré-requisito devem bloquear regras derivadas para evitar cascading failures.

### Basis

Nos blocos com `RuleDefinition`, a implementação registra `OFFICIAL`, `STANDARD` ou `HEURISTIC`. As regras 050–054 são executores diretos e não possuem `basis` separado materializado em `RuleDefinition`; este guia marca isso como **não codificado separadamente**, em vez de inventar classificação.

### Scoring

A coluna **Scoring** informa a dimensão vigente de `SCORE-GEO-002`. `—` significa que a regra não pontua diretamente. Grupos correlacionados podem ser consolidados pelo scoring para evitar dupla penalização.

## BR-GEO-001..018 — Acquisition, Technical, Indexability e Robots

| ID | Regra | Basis | Scope / applicability | Evidence principal | Severity | Fallback / interpretação | Scoring |
|---|---|---|---|---|---|---|---|
| 001 | Target válido e normalizado | OFFICIAL | global | target/normalização | CRITICAL | target inválido bloqueia início; integridade do auditor | — |
| 002 | Provenance de URL descoberta | OFFICIAL | Page, sem device | seed/sitemap/link/redirect provenance | INFO | ausência de provenance é erro de integridade | — |
| 003 | Sitemap adquirido/interpretado quando disponível | STANDARD | global | HTTP + sitemap | LOW | ausência de sitemap não é FAIL automático | TECHNICAL_ACCESSIBILITY |
| 004 | Artifacts HTTP preservados | OFFICIAL | Page, sem device | HTTP response/headers + RAW | INFO | body ausente pode não gerar arquivo; aquisição continua rastreável | — |
| 005 | Página tecnicamente recuperável | STANDARD | Page | status/network error | HIGH | DNS/TLS/connection/timeout podem FAIL; dependentes bloqueadas | TECHNICAL_ACCESSIBILITY |
| 006 | Resposta HTTP final utilizável | STANDARD | Page; depende 005 | status/content type/body | HIGH | dependency falha → NOT_APPLICABLE | TECHNICAL_ACCESSIBILITY |
| 007 | Redirect resolve sem loop/invalid hop | STANDARD | Page; depende 005 | redirect chain | HIGH | loop/invalid redirect → FAIL; erro não relacionado → NOT_APPLICABLE | TECHNICAL_ACCESSIBILITY |
| 008 | Redirect chain sem problema material | HEURISTIC | Page; depende 005/007 | redirect chain | LOW | prerequisite bloqueada → NOT_APPLICABLE | TECHNICAL_ACCESSIBILITY |
| 009 | HTML esperado oferece documento analisável | STANDARD | Page; depende 005/006 | HTTP/body/content type | HIGH | sem base técnica → NOT_APPLICABLE | CONTENT_EXTRACTABILITY |
| 010 | Falha de rendering não impede conteúdo essencial | HEURISTIC | snapshot Desktop/Mobile; depende 005/009 | RAW/RENDERED/browser metadata | HIGH | rendering só é problema quando material | CONTENT_EXTRACTABILITY |
| 011 | Diretivas de indexabilidade resolvidas | STANDARD | snapshot; depende 005/009 | meta robots, headers, rendered state | HIGH | insuficiência/dependency → UNKNOWN/NOT_APPLICABLE | INDEXABILITY |
| 012 | noindex explícito identificado | STANDARD | snapshot; depende 011 | robots directives | MEDIUM | 011 bloqueada → NOT_APPLICABLE | INDEXABILITY |
| 013 | Canonical interpretável e não conflitante | STANDARD | snapshot; depende 009 | canonical/DOM | MEDIUM | ausência isolada não implica severidade alta | INDEXABILITY |
| 014 | Canonical target válido/plausível | HEURISTIC | snapshot; depende 013 | canonical + target/context | MEDIUM | canonical indisponível bloqueia derivação | INDEXABILITY |
| 015 | JS não cria conflito de canonical/indexability | STANDARD | snapshot; depende 009/011 | RAW × RENDERED directives | HIGH | sem comparação suficiente → UNKNOWN/NOT_APPLICABLE | INDEXABILITY |
| 016 | Página error-like não se mascara como indexável | HEURISTIC | snapshot; depende 006 | status + conteúdo/rendering | MEDIUM | exige sinais fortes; token isolado “404” não basta | INDEXABILITY |
| 017 | robots.txt interpretável quando presente | STANDARD | global | ROBOTS_RULE + artifact | MEDIUM | ausência/404 não significa bloqueio | TECHNICAL_ACCESSIBILITY |
| 018 | Acesso por crawler resolvido separadamente | STANDARD | global; depende 017 | crawler access | HIGH | Googlebot, Googlebot Smartphone, Bingbot, OAI-SearchBot e GPTBot são independentes; GPTBot bloqueado isoladamente não penaliza Search readiness | TECHNICAL_ACCESSIBILITY |

## BR-GEO-019..024 — JavaScript / SPA

Arquitetura CSR/SPA não é defeito por si só.

| ID | Regra | Basis | Scope | Evidence | Severity | Fallback / interpretação | Scoring |
|---|---|---|---|---|---|---|---|
| 019 | RAW e RENDERED semanticamente consistentes | STANDARD | snapshot; depende 009 | RAW/RENDERED/content/links | HIGH | shell RAW + conteúdo rendered completo pode ser válido | CONTENT_EXTRACTABILITY |
| 020 | Conteúdo essencial recuperável após JS | STANDARD | snapshot; depende 009 | RAW × RENDERED/main content | HIGH | dependência de JS não é penalidade automática | CONTENT_EXTRACTABILITY |
| 021 | Rotas client-side indexáveis funcionam por URL direta | STANDARD | snapshot; depende 005/009 | route/direct navigation | HIGH | só aplica a rota relevante observável | TECHNICAL_ACCESSIBILITY |
| 022 | Navegação interna importante expõe destinos crawlable | STANDARD | snapshot; depende 009 | rendered links | MEDIUM | sem rendering suficiente → UNKNOWN/NOT_APPLICABLE | TECHNICAL_ACCESSIBILITY |
| 023 | Client routing não cria soft-404 enganoso | HEURISTIC | snapshot; depende 006 | status/content/routing | HIGH | soft-404 exige evidência forte | TECHNICAL_ACCESSIBILITY |
| 024 | Lazy loading não impede conteúdo essencial | HEURISTIC | snapshot; depende 009 | bounded probe + rendered content | MEDIUM | interação limitada/previsível; não executa navegação arbitrária | CONTENT_EXTRACTABILITY |

## BR-GEO-025..027 — Content Extractability

| ID | Regra | Basis | Scope | Evidence | Severity | Fallback | Scoring |
|---|---|---|---|---|---|---|---|
| 025 | Conteúdo principal identificável | HEURISTIC | snapshot Desktop/Mobile | rendered DOM/main content | HIGH | rendered indisponível → UNKNOWN; sem mínimo arbitrário de palavras | CONTENT_EXTRACTABILITY |
| 026 | Conteúdo significativo além de boilerplate | HEURISTIC | snapshot; depende 025 | main content/estrutura | HIGH | 025 bloqueada → NOT_APPLICABLE | CONTENT_EXTRACTABILITY |
| 027 | Informação essencial sobrevive à extração | HEURISTIC | snapshot; depende 025 | rendered versus extracted qualifiers | MEDIUM | perda de moeda/unidade/data/labels/relações é material; insuficiência → UNKNOWN | CONTENT_EXTRACTABILITY |

## BR-GEO-028..049 — Semantic, Entity, Structured Data, Answerability, Citation, Trust e Intent

Estas regras são por snapshot. O `NoneProvider` permite operação sem IA. Output externo só é aceito após validação de schema e evidence IDs.

| ID | Regra | Basis | Severity | Evidence / applicability | Fallback | Scoring |
|---|---|---|---|---|---|---|
| 028 | Title presente e semanticamente representativo | STANDARD | HIGH | title + main content + semantic evidence | componente determinístico pode continuar; parte semântica insuficiente → UNKNOWN | SEMANTIC_STRUCTURE |
| 029 | Hierarquia semântica compreensível | HEURISTIC | MEDIUM | headings/main content | múltiplos H1 não são FAIL automático; sem base → UNKNOWN | SEMANTIC_STRUCTURE |
| 030 | Tópico principal e seções identificáveis | HEURISTIC | MEDIUM | main content + assessment | baixa confiança → UNKNOWN | SEMANTIC_STRUCTURE |
| 031 | Entidade principal identificável quando aplicável | HEURISTIC | MEDIUM | EntityObservation + source evidence | sem provider/evidence → UNKNOWN | ENTITY_CLARITY |
| 032 | Tipos/relações de entidades têm contexto | HEURISTIC | MEDIUM | entities + content/SD | não aplicável → NOT_APPLICABLE; insuficiência → UNKNOWN | ENTITY_CLARITY |
| 033 | Ambiguidade material de entidade detectável | HEURISTIC | MEDIUM | semantic/entity evidence | finding somente quando material/evidence-backed | ENTITY_CLARITY |
| 034 | Structured Data sintaticamente interpretável | STANDARD | MEDIUM | JSON-LD raw/parsed/parse_error | ausência de SD não é FAIL automático | STRUCTURED_DATA |
| 035 | Tipos/propriedades de SD identificáveis | STANDARD | LOW | @context/@type/properties | ausência pode ser NOT_APPLICABLE | STRUCTURED_DATA |
| 036 | SD consistente com conteúdo visível | HEURISTIC | MEDIUM | JSON-LD + visible content | ausência/insuficiência → UNKNOWN/NOT_APPLICABLE | STRUCTURED_DATA |
| 037 | Entidades de SD consistentes com entidades observadas | HEURISTIC | MEDIUM | JSON-LD + EntityObservation | sem base → UNKNOWN/NOT_APPLICABLE | STRUCTURED_DATA |
| 038 | Intenção primária identificável | HEURISTIC | HIGH | content + assessment | IA/evidence insuficiente → UNKNOWN | ANSWERABILITY |
| 039 | Perguntas primárias relevantes recebem resposta explícita | HEURISTIC | MEDIUM | content + assessment | não inventar pergunta; insuficiência → UNKNOWN | ANSWERABILITY |
| 040 | Respostas têm contexto suficiente | HEURISTIC | MEDIUM | answer/context evidence | sem resposta aplicável → NOT_APPLICABLE | ANSWERABILITY |
| 041 | Claims factuais materiais identificáveis | HEURISTIC | LOW | content + semantic evidence | frase promocional pura não é claim factual automático | CITATION_READINESS |
| 042 | Claims factuais possuem contexto suficiente | HEURISTIC | MEDIUM | claim/context | sem claim → NOT_APPLICABLE; sem provider → UNKNOWN | CITATION_READINESS |
| 043 | Claims numéricos/temporais têm qualificadores | HEURISTIC | MEDIUM | números, unidade, moeda, data/período | sem claim quantitativo → NOT_APPLICABLE | CITATION_READINESS |
| 044 | Informação importante não exige inferência excessiva | HEURISTIC | MEDIUM | content/context | não exige que toda frase funcione isoladamente | CITATION_READINESS |
| 045 | Claim material expõe atribuição/suporte quando requerido | HEURISTIC | MEDIUM | claim/source evidence | aplicabilidade contextual; sem regra universal de fonte | EVIDENCE_TRUST |
| 046 | Publisher/author/responsável identificável quando relevante | HEURISTIC | LOW | content/entity/metadata | tipo de página pode tornar regra NOT_APPLICABLE | EVIDENCE_TRUST |
| 047 | Sinais de publicação/freshness são consistentes | HEURISTIC | MEDIUM | visible date, JSON-LD, sitemap, HTTP | não presume equivalência rígida entre fontes | EVIDENCE_TRUST |
| 048 | Primary + secondary intents representadas | HEURISTIC | MEDIUM | 1 primary + até 5 secondary + content | provider/evidence insuficiente → UNKNOWN | INTENT_COVERAGE |
| 049 | Gaps materiais de intenção são evidence-backed | HEURISTIC | MEDIUM | intents + source evidence | gap sem evidence não vira finding | INTENT_COVERAGE |

## BR-GEO-050..051 — Internal Links e Duplicate

Executadas em `pre_scoring_rules.py`; `basis` não é codificado separadamente em `RuleDefinition`.

| ID | Regra | Basis materializada | Scope | Evidence/comportamento | Severity | Fallback | Scoring |
|---|---|---|---|---|---|---|---|
| 050 | Links internos expõem destinos tecnicamente utilizáveis | não codificada separadamente; executor determinístico | snapshot Desktop/Mobile | links normalizados + aquisições conhecidas | MEDIUM | destino fora do budget não é adivinhado; conhecido indisponível → WARNING | TECHNICAL_ACCESSIBILITY |
| 051 | Duplicatas/near-duplicates materiais identificáveis | não codificada separadamente; heurística determinística | por device, universo auditado | main content; exact ou Jaccard >= 0,90 | MEDIUM | páginas fora do universo não são comparadas; match → WARNING | CONTENT_EXTRACTABILITY |

## BR-GEO-052 — Desktop × Mobile

| Campo | Contrato |
|---|---|
| Regra | Material Desktop/Mobile differences must be explicitly detected and classified |
| Basis materializada | não há `RuleDefinition.basis` separado no executor M8 |
| Scope | por Page, compara snapshots Desktop e Mobile |
| Evidence | `COMPARISON` com estado Desktop/Mobile, campos alterados, materialidade e limitações |
| Resultado | `PASS`, `WARNING`, `UNKNOWN` ou `NOT_APPLICABLE`; classificação interna SAME/DIFFERENT/UNKNOWN/NOT_APPLICABLE |
| Severity do finding | MEDIUM quando diferença material gera WARNING |
| Fallback | um device ausente → UNKNOWN; ambos ausentes → NOT_APPLICABLE; diferença por si só não é defeito |
| Scoring | não pontua diretamente |

## BR-GEO-053 — Finding traceability

Executada antes do scoring sobre os Findings produzidos até aquele ponto.

| Campo | Contrato |
|---|---|
| Basis materializada | não codificada separadamente; auditor-integrity executor |
| Scope | global |
| Evidence | verifica reabertura do Finding, RuleExecution e Evidence referenciadas |
| Severity | CRITICAL quando o executor gera finding de integridade |
| Resultado | PASS se todos reabrem; FAIL se houver referência inválida |
| Scoring | não pontua diretamente |

## BR-GEO-054 — Score reproducibility

Executada por M9 após o cálculo/persistência dos scores.

| Campo | Contrato |
|---|---|
| Basis materializada | não codificada separadamente; auditor-integrity executor |
| Scope | global |
| Evidence | recalcula `SCORE-GEO-002`, reabre scores/contributions e compara resultados |
| Resultado | PASS quando score é reproduzível; FAIL em inconsistência |
| Finding | M9 não publica Finding de qualidade do website para esta regra; é integridade do auditor |
| Scoring | não pontua diretamente |

## Dependências e cascading failures

A ordem correta de execução é:

1. verificar applicability;
2. verificar dependencies;
3. verificar blocking;
4. executar;
5. registrar RuleExecution.

Exemplo esperado:

```text
HTTP 500 / falha de acesso
  -> finding técnico causal
  -> regras semânticas dependentes = NOT_APPLICABLE ou UNKNOWN
```

Não é aceitável transformar uma única falha de acesso em cadeia automática de FAIL de entidade, answerability, intent e citation readiness.

## IA e fallback

- semantic-only + IA não configurada: `UNKNOWN`, com reason equivalente a `AI_NOT_CONFIGURED`;
- provider indisponível/saída inválida: análise degrada; não vira FAIL do website;
- regras híbridas executam componentes determinísticos seguros e deixam componente semântico inconclusivo quando necessário;
- ausência de IA pode reduzir Coverage/Confidence/Consolidation, nunca aplicar fator zero artificial ao site.

Consulte [AI_GUIDE.md](AI_GUIDE.md) e [SCORING_GUIDE.md](SCORING_GUIDE.md).

## Proveniência metodológica

A classificação `OFFICIAL` / `STANDARD` / `HEURISTIC` de cada BR-GEO deve ser lida junto às fontes exibidas no report. Uma referência externa não promove automaticamente uma heurística a standard. O inventário consolidado está em [INDICATOR_PROVENANCE.md](INDICATOR_PROVENANCE.md) e em `report/references.html#indicator-provenance`.

