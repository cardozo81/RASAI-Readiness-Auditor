# BUSINESS_RULES.md

**Estado no baseline de desenvolvimento:** APPROVED
**Ruleset:** BR-GEO-001..056

## 1. Contrato comum

Cada regra possui:

- rule_id;
- version;
- name;
- description;
- dimension;
- category;
- execution_type;
- device_scope;
- architecture_scope;
- engine_scope;
- basis;
- applicability;
- dependencies;
- inputs;
- checks;
- result conditions;
- evidence requirements;
- finding policy;
- severity;
- scoring metadata;
- fallback policy;
- traceability metadata.

Resultados:

- PASS
- FAIL
- WARNING
- NOT_APPLICABLE
- UNKNOWN
- ERROR

Princípios:

UNKNOWN != FAIL
ERROR != FAIL
NOT_APPLICABLE != FAIL

## 2. Acquisition

### BR-GEO-001 - Audit target must be valid and normalized

Valida target e normalização.
Global. Determinística. Blocking. Não afeta score.

### BR-GEO-002 - Every discovered URL must have traceable discovery provenance

Toda Page deve registrar SEED, SITEMAP, INTERNAL_LINK, REDIRECT ou MANUAL.
Global. Determinística. Auditor Integrity.

### BR-GEO-003 - Sitemap resources must be acquired and interpreted when available

Avalia sitemap declarado/encontrado, parsing e URLs.
Ausência de sitemap não é automaticamente FAIL.

### BR-GEO-004 - HTTP acquisition artifacts must be preserved for reproducible analysis

Preserva requested URL, device, timestamp, network result, status, headers, final URL, body artifact e redirect chain.

## 3. Technical Accessibility

### BR-GEO-005 - Page must be technically retrievable

Falha para DNS, TLS, connection, timeout ou ausência de resposta técnica utilizável.

### BR-GEO-006 - Final HTTP response must be usable for intended page content

Avalia status final e adequação da resposta ao tipo de página.

### BR-GEO-007 - Redirect behavior must resolve without loops or invalid chains

Detecta loops e cadeias incapazes de atingir destino válido.

### BR-GEO-008 - Redirect chains must not introduce material crawl/accessibility problems

Detecta cadeias excessivas/problemáticas. Thresholds versionados.

### BR-GEO-009 - Expected HTML documents must provide analyzable document content

Aplica-se a páginas que deveriam fornecer HTML.

### BR-GEO-010 - Rendering failures must not prevent access to essential content

Somente erros de rendering com impacto material geram problema.

## 4. Indexability

### BR-GEO-011 - Indexability directives must be consistently resolved

Combina meta robots, X-Robots-Tag e rendered directives.

### BR-GEO-012 - Explicit noindex directives must be identified correctly

Detecta noindex genérico ou específico de crawler.

### BR-GEO-013 - Canonical declarations must be interpretable and non-conflicting

Detecta canonical ausente, inválida, múltipla ou conflitante. Ausência isolada não gera severidade alta automática.

### BR-GEO-014 - Canonical target must be technically valid and contextually plausible

Verifica target, status, redirects e plausibilidade contextual.

### BR-GEO-015 - JavaScript must not introduce unsafe canonical/indexability conflicts

Compara RAW e RENDERED para canonical e robots.

### BR-GEO-016 - Error-like pages must not masquerade as valid indexable pages

Detecta soft-404 e estados equivalentes com forte evidência.

## 5. Robots & Crawlers

### BR-GEO-017 - robots.txt must be interpretable when present

Ausência/404 não significa bloqueio.

### BR-GEO-018 - Crawler access must be resolved independently per configured crawler

Baseline:

- Googlebot;
- Googlebot Smartphone;
- Bingbot;
- OAI-SearchBot;
- GPTBot.

OAI-SearchBot e GPTBot nunca devem ser tratados como equivalentes.

GPTBot bloqueado não deve, por si só, penalizar Search readiness.

## 6. JavaScript / Rendering / SPA

### BR-GEO-019 - Raw and rendered page states must remain semantically consistent

Compara title, description, canonical, robots, headings, conteúdo, links e Dados Estruturados.

### BR-GEO-020 - Essential content must remain recoverable after JavaScript rendering

Shell RAW + conteúdo RENDERED completo é válido. Conteúdo não recuperável após rendering é problema.

### BR-GEO-021 - Indexable client-side routes must resolve through direct URL access

Rota relevante deve funcionar em navegação direta.

### BR-GEO-022 - Important internal navigation must expose crawlable destinations

Navegação para páginas relevantes deve expor destinos recuperáveis.

### BR-GEO-023 - Client-side routing must not create misleading soft-404 states

Especialmente relevante para SPA.

### BR-GEO-024 - Lazy loading must not prevent recovery of essential content

Interação limitada e previsível pode ser usada; conteúdo essencial não deve exigir comportamento arbitrário.

## 7. Content Extractability

### BR-GEO-025 - Main content must be identifiable

Identifica conteúdo principal com DOM, landmarks, densidade e outros sinais.

### BR-GEO-026 - Page must contain meaningful content beyond navigation and boilerplate

Não utiliza mínimo arbitrário de palavras.

### BR-GEO-027 - Essential information must survive extraction without material loss

Preserva contexto como moeda, unidade, data, labels, relações e texto relevante.

## 8. Semantic Structure

### BR-GEO-028 - Page title must be present and semantically representative

Parte determinística + parte semântica.

### BR-GEO-029 - Main content must expose an understandable semantic hierarchy

Não considera automaticamente múltiplos H1 como erro.

### BR-GEO-030 - Primary topic and major sections must be identifiable

Semântica. Baixa confiança tende a UNKNOWN.

## 9. Entity Clarity

### BR-GEO-031 - Primary entity must be identifiable when applicable

Organization, Person, Product, Service, Place, Brand, Topic ou Other.

### BR-GEO-032 - Important entity types and relationships must have sufficient context

Ex.: Product → Brand, Person → Organization.

### BR-GEO-033 - Material entity ambiguity must be detectable

Finding somente quando ambiguidade é material.

## 10. Structured Data

### BR-GEO-034 - Structured Data must be syntactically interpretable when present

Parsing, @context, @type e estrutura.

### BR-GEO-035 - Structured Data types and relevant properties must be identifiable

Identifica tipos e propriedades.

### BR-GEO-036 - Structured Data must remain consistent with visible page content

Compara dados estruturados com valores e conteúdo visível.

### BR-GEO-037 - Structured Data entities must be consistent with observed page entities

Compara entidades declaradas e observadas.

Ausência de Dados Estruturados não implica FAIL automático.

## 11. Answerability

### BR-GEO-038 - Primary user intent must be identifiable

Classifica intenção principal com evidência.

### BR-GEO-039 - Relevant primary questions must receive explicit answers when applicable

Resultados:

- ANSWERED
- PARTIALLY_ANSWERED
- NOT_ANSWERED
- UNKNOWN

### BR-GEO-040 - Answers must contain sufficient context

Resposta deve ser compreensível e contextualizada.

## 12. Citation Readiness

### BR-GEO-041 - Material factual claims must be explicitly identifiable

Diferencia claims factuais de frases puramente promocionais.

### BR-GEO-042 - Factual statements must contain sufficient factual context

Avalia quem, o quê, quanto, quando e contexto quando aplicável.

### BR-GEO-043 - Numeric, temporal and quantitative claims must include necessary qualifiers

Números, unidades, moeda, porcentagem, data, duração e período.

### BR-GEO-044 - Important information must be understandable without excessive inference

Não exige que toda frase funcione isoladamente.

## 13. Evidence & Trust

### BR-GEO-045 - Material claims should expose appropriate attribution or supporting evidence when required

Aplicabilidade depende do claim.

### BR-GEO-046 - Publisher, author or responsible entity should be identifiable when relevant

Tipo da página determina aplicabilidade.

### BR-GEO-047 - Publication and freshness signals must remain internally consistent

Compara visible date, datePublished, dateModified, sitemap lastmod e HTTP Last-Modified sem presumir equivalência rígida.

## 14. Intent Coverage

### BR-GEO-048 - Primary and relevant secondary intents must be represented

MVP:

- 1 primary intent;
- até 5 secondary intents.

### BR-GEO-049 - Material intent coverage gaps must be evidence-backed

Estados:

- COVERED
- PARTIALLY_COVERED
- NOT_COVERED
- UNKNOWN

## 15. Internal Links / Duplicate

### BR-GEO-050 - Internal links must expose technically usable destinations

Avalia href, normalização, status e destino.

### BR-GEO-051 - Material duplicate or near-duplicate pages must be identifiable

Apenas dentro do universo auditado.

## 16. Desktop × Mobile

### BR-GEO-052 - Material Desktop/Mobile differences must be explicitly detected and classified

Compara HTTP, redirects, canonical, robots, title, headings, conteúdo, links, Dados Estruturados, entidades e avaliações semânticas.

Resultado:

- SAME
- DIFFERENT
- NOT_APPLICABLE
- UNKNOWN

Diferença não implica automaticamente problema.

## 17. Auditor Integrity

### BR-GEO-053 - Every finding must be fully traceable

Finding inválido sem RuleExecution, Rule e Evidence.

### BR-GEO-054 - Every score must be reproducible and reliability-aware

Todo score deve ser reconstruível com ruleset e scoring version.

### BR-GEO-055 - Evidence-bound sitemap quality assessment may refine the SITEMAP scoring group

Regra opcional, HEURISTIC e dependente de IA técnica explicitamente habilitada. Recebe somente evidence IDs persistidos do recurso sitemap, produz verdict POSITIVE/NEUTRAL/NEGATIVE e nunca escolhe peso numérico. Compartilha o grupo `SITEMAP` e o peso da BR-GEO-003; resultado positivo não soma bônus e baixa confiança do provider não pode produzir PASS/FAIL duro.

### BR-GEO-056 - Evidence-bound robots quality assessment may refine the ROBOTS scoring group

Regra opcional, HEURISTIC e dependente de IA técnica explicitamente habilitada. Recebe somente evidence IDs persistidos de robots.txt, produz verdict POSITIVE/NEUTRAL/NEGATIVE e nunca escolhe peso numérico. Compartilha o grupo `ROBOTS` e o peso das BR-GEO-017/018; resultado positivo não soma bônus e baixa confiança do provider não pode produzir PASS/FAIL duro.

## 18. Dependency / Blocking

Antes de executar regra:

1. verificar applicability;
2. verificar dependencies;
3. verificar blocking;
4. executar;
5. registrar RuleExecution.

Falha de pré-requisito não deve provocar múltiplos FAIL derivados.

Exemplo:

HTTP 500
→ finding técnico

Regras semânticas dependentes
→ NOT_APPLICABLE ou UNKNOWN

Nunca:
HTTP 500 + sem entidade + sem resposta + sem intent + baixa citation readiness.

## 19. IA e fallback

A análise semântica possui dois caminhos de evidência, preservando a mesma camada posterior de scoring:

```text
baseline local: SEMANTIC-BASELINE-001
provider externo: opcional
```

### NO_AI / provider não configurado

O baseline determinístico executa primeiro os critérios que podem ser sustentados por evidência persistida do snapshot, como title, headings, conteúdo principal, links e Structured Data.

Política:

- `PASS` somente com evidência positiva suficiente;
- `NOT_APPLICABLE` somente quando a aplicabilidade puder ser resolvida de forma defensável;
- ausência de evidência não vira `PASS`;
- ausência de evidência não vira `FAIL`;
- critério não resolvido permanece `UNKNOWN`.

Portanto, `NO_AI` **não significa automaticamente baixa Coverage**. A auditoria pode ser consolidada sem IA quando os grupos aplicáveis forem suficientemente avaliados e os gates normais do `SCORE-GEO-004` forem satisfeitos.

### Provider configurado

Uma resposta válida e evidence-bound do provider pode aprofundar a avaliação semântica. Fatos determinísticos fortes continuam tendo precedência.

Falha de provider explicitamente configurado permanece visível como degradação (`AI_PROVIDER_UNAVAILABLE`) quando o critério não possui resultado válido; essa falha nunca é convertida em `FAIL` do website.

### Provenance

Avaliações do baseline são persistidas com:

```text
provider = DETERMINISTIC_BASELINE
configuration_version = SEMANTIC-BASELINE-001
rule_version = 2
```

A capability `semantic_baseline:SEMANTIC-BASELINE-001` identifica auditorias em que o baseline foi efetivamente utilizado.

Ausência de IA nunca gera penalidade do website e deixa de ser, por si só, bloqueador mecânico de consolidação.

## 20. Basis Type

Toda regra deve indicar quando aplicável:

- OFFICIAL
- STANDARD
- HEURISTIC
- EXPERIMENTAL

Regras específicas de mecanismo devem indicar engine_scope.
