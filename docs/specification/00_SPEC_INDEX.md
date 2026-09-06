# SearchGEO Readiness Auditor — Specification Index

**Status:** APPROVED BASELINE + M14/M15/M16/M17/M18/M20/M21/M22/M23/M24/M25 INTEGRADOS + M26 EM BRANCH + SCORE-GEO-002 + SGRI-001 + REPORT-SITE-GEO-001  
**Baseline:** MVP Functional Specification  
**Idioma normativo:** Português, preservando identificadores e termos técnicos quando necessário.

## 1. Objetivo

Este diretório constitui a fonte normativa do SearchGEO Readiness Auditor.

Uma IA, desenvolvedor ou ferramenta que assuma o projeto não deve depender do histórico de chats para descobrir requisitos formalizados. Os documentos presentes neste diretório prevalecem sobre interpretações informais do histórico de conversa.

## 2. Ordem obrigatória de leitura

1. `00_SPEC_INDEX.md`
2. `12_AI_HANDOFF.md`
3. `10_DECISIONS.md`
4. `01_PROJECT_CHARTER_SCOPE.md`
5. `07_FUNCTIONAL_REQUIREMENTS.md`
6. `02_DOMAIN_MODEL.md`
7. `03_BUSINESS_RULES.md`
8. `04_WORKFLOWS.md`
9. `05_SCORING_MODEL.md`
10. `06_PRIORITIZATION_MODEL.md`
11. `08_TECHNICAL_ARCHITECTURE.md`
12. `09_IMPLEMENTATION_PLAN.md`
13. `11_REPORTING_LANGUAGE_GLOSSARY.md`
14. `13_MODEL_ROUTING_POLICY.md`
15. `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md`
16. `15_ERROR_CENTRIC_REPORT_UX.md`
17. `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md`
18. `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md`
19. `18_MULTI_AI_PROVIDER_ROUTING.md`
20. `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`
21. `20_AI_CONTENT_REMEDIATION.md`
22. `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`
23. `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`
24. `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`
25. `24_CRAWLING_DISCOVERY_AI_ACCESS.md`
26. `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
27. `26_OBSERVED_GENERATIVE_VISIBILITY.md`

## 3. Precedência documental

Em caso de conflito:

1. decisões explicitamente aprovadas em `10_DECISIONS.md`;
2. requisitos funcionais em `07_FUNCTIONAL_REQUIREMENTS.md`;
3. escopo em `01_PROJECT_CHARTER_SCOPE.md`;
4. modelos normativos de domínio, regras, workflows, scoring e priorização;
5. arquitetura técnica;
6. plano de implementação;
7. AI handoff e política operacional de modelos;
8. especificações de evolução de marco, quando não conflitarem com os itens anteriores.

Nenhuma decisão funcional deve ser alterada silenciosamente durante implementação.

## 4. Catálogo normativo

### Core

- `01_PROJECT_CHARTER_SCOPE.md` — propósito, escopo, princípios e exclusões.
- `02_DOMAIN_MODEL.md` — entidades, relacionamentos, identificadores, estados e invariantes.
- `03_BUSINESS_RULES.md` — Business Rules `BR-GEO-001` a `BR-GEO-054`.
- `04_WORKFLOWS.md` — workflows e ordem de execução.
- `05_SCORING_MODEL.md` — Score, Coverage, Confidence, Consolidation e aplicabilidade. Baseline: `SCORE-GEO-002`.
- `06_PRIORITIZATION_MODEL.md` — Severity, Impact, Effort, Confidence e Priority.
- `07_FUNCTIONAL_REQUIREMENTS.md` — requisitos funcionais/não funcionais vigentes.
- `08_TECHNICAL_ARCHITECTURE.md` — arquitetura local/modular e fronteiras entre domínios.
- `09_IMPLEMENTATION_PLAN.md` — baseline de marcos/evoluções.
- `10_DECISIONS.md` — decisões humanas consolidadas e pendências corporativas.
- `11_REPORTING_LANGUAGE_GLOSSARY.md` — linguagem e apresentação do relatório.
- `12_AI_HANDOFF.md` — continuidade operacional por IA/desenvolvedor.
- `13_MODEL_ROUTING_POLICY.md` — política de modelos e esforço.

### Evoluções formalizadas

- `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md` — M14 multi-URL/evidência visual.
- `15_ERROR_CENTRIC_REPORT_UX.md` — M15 UX de report evoluída pelo report site.
- `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md` — M16 causa raiz/elemento.
- `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md` — M17 precisão/consistência.
- `18_MULTI_AI_PROVIDER_ROUTING.md` — M18 multi-provider/failover/telemetria; non-scoring.
- `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md` — `SCORE-GEO-002`, N/A e premissas mínimas.
- `20_AI_CONTENT_REMEDIATION.md` — M20 conteúdo/JSON-LD advisory; downstream do score.
- `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md` — M21 PageSpeed/Lighthouse/CrUX; non-scoring.
- `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md` — M22 Accessibility/Performance separados.
- `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md` — M23 Synthetic Navigation Apdex Standard.
- `24_CRAWLING_DISCOVERY_AI_ACCESS.md` — M24 crawling/discovery/AI access; non-scoring.
- `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md` — M25 Synthetic User Experience Apdex calibrável; non-RUM/non-scoring.
- `26_OBSERVED_GENERATIVE_VISIBILITY.md` — M26 outcomes observados/importados de AI Search; import-first/non-scoring.

## 5. Baseline vigente de scoring e método público

- motor persistido: `SCORE-GEO-002`;
- identidade pública de readiness: `SGRI-001`;
- dimensões legitimamente `NOT_APPLICABLE` não recebem zero e são excluídas conforme `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`;
- Coverage, Confidence e Consolidation permanecem métricas distintas do Score;
- não existe claim de score GEO/AEO universal/homologado;
- métricas externas ou outcomes observados não são incorporados ao SGRI sem nova decisão, nova versão e validação apropriada.

## 6. REPORT-SITE-GEO-001

O contrato final de saída continua condicional pela existência/materialização do arquivo:

```text
<AUD-ID>/report/index.html
<AUD-ID>/report/searchgeo.html             # SGRI-001 / SearchGEO
<AUD-ID>/report/mobile.html                # condicional
<AUD-ID>/report/desktop.html               # condicional
<AUD-ID>/report/remediation.html
<AUD-ID>/report/content-suggestions.html
<AUD-ID>/report/crawling-discovery.html    # M24
<AUD-ID>/report/accessibility.html         # M22, condicional
<AUD-ID>/report/web-performance.html       # M21/M22
<AUD-ID>/report/apdex.html                 # M23, condicional
<AUD-ID>/report/apdex-experience.html      # M25, condicional
<AUD-ID>/report/ai-visibility.html         # M26, após import/report
<AUD-ID>/report/ai-usage.html
<AUD-ID>/report/references.html
<AUD-ID>/report/css/site.css
```

Default de dispositivo da CLI: `mobile`. `desktop` e `both` são seleções explícitas/parametrizáveis.

### Propriedade analítica

Cada indicador/domínio tem uma página canônica. O `index.html` pode resumir um resultado final para navegação executiva, mas não deve duplicar metodologia/evidência detalhada nem fundir métricas diferentes em um score comum.

`searchgeo.html` é a página canônica de SGRI/indicadores proprietários. Acessibilidade, Web Performance, Apdex e Observed Generative Visibility permanecem domínios separados.

## 7. Fronteiras dos marcos externos/non-scoring

| Marco | Domínio | Regra de fronteira |
|---|---|---|
| M21 | PageSpeed/Lighthouse/CrUX | evidência externa; não altera Score |
| M22 | Accessibility/Performance diagnostics | não declara WCAG integral nem infere Apdex |
| M23 | Synthetic Navigation Apdex | T/4T explícito; não é RUM; não altera Score |
| M24 | Crawling/Discovery/AI access | standards/guidance técnicos; `llms.txt` experimental; não altera Score |
| M25 | Synthetic User Experience Apdex | calibrável, non-RUM, separado do M23; não altera Score |
| M26 | Observed Generative Visibility | outcome importado/observado, separado de readiness; não altera Score |

## 8. M26 — Observed Generative Visibility

Fonte normativa: `26_OBSERVED_GENERATIVE_VISIBILITY.md`.

M26:

- está em implementação na branch `m26-observed-generative-visibility`;
- usa contrato `OGV-IMPORT-001`;
- começa como **import-first**, sem scraping de portal e sem endpoint não documentado;
- suporta inicialmente `BING_WEBMASTER_TOOLS_AI_PERFORMANCE` e `CONTROLLED_QUERY_RUNS`;
- preserva o JSON normalizado como artifact e registra SHA-256;
- exige URLs do mesmo `normalized_origin` da auditoria;
- mantém Total Citations/Average Cited Pages como métricas reportadas pela fonte;
- calcula Citation Presence Rate apenas sobre runs controlados `VALID`;
- apresenta `n` e Wilson 95% quando a taxa é calculável;
- cria `report/ai-visibility.html`;
- não escreve/recalcula `scores`, `score_contributions`, `rule_executions`, `findings` ou `recommendations`;
- não cria GEO Score, ranking, autoridade nem probabilidade de citação futura;
- não presume causalidade entre SGRI e visibilidade observada.

## 9. Fontes externas e heurística

O SearchGEO não deve representar seu score ou thresholds como standard GEO/AEO universal.

Referências primárias atuais incluem Google Search Central/Crawling Infrastructure, OpenAI publisher/help documentation, Schema.org, WHATWG, IETF/RFC, Chrome Developers, PageSpeed Insights, Chrome UX Report, W3C/WAI, Apdex Alliance, documentação pública Dynatrace para comparabilidade M25 e documentação pública Bing Webmaster/Search para M26.

Structured Data/JSON-LD é reforço opcional, não requisito universal GEO. Quando M20 propõe/revisa JSON-LD, usa somente conteúdo/evidência persistidos.

M21 introduz métricas externas documentadas para fenômenos específicos. Lighthouse e Core Web Vitals não homologam `SCORE-GEO-002` e não são combinados silenciosamente com ele.

M22 mantém Acessibilidade e Web Performance independentes do GEO. Acessibilidade automatizada Lighthouse não equivale a conformidade WCAG.

M23/M25 usam Apdex em contratos sintéticos próprios; não devem ser derivados de Lighthouse/CrUX nem apresentados como população humana observada.

M24 usa protocolos/guidance públicos para crawling/discovery. `llms.txt` permanece proposta comunitária experimental e sua ausência não é falha de SearchGEO.

M26 separa source-reported metrics de cálculos SearchGEO sobre query-runs. Contagem de citações não deve ser rotulada como ranking/autoridade.

Heurísticas BR-GEO sem equivalente normativo permanecem identificadas como heurísticas/baseline interna.

## 10. Continuidade de branches e integração

Branches de marco são temporárias.

Após validação e merge em `main`:

1. confirmar que `main` contém integralmente o marco;
2. confirmar ausência de conteúdo exclusivo pendente;
3. classificar a branch como removível;
4. excluir fisicamente quando a ferramenta/permissão permitir;
5. impossibilidade de exclusão pelo conector não bloqueia a continuidade quando a integração já está comprovada, conforme decisões vigentes.

Uma branch ativa de outro trabalho não deve ser modificada ou incorporada por um marco concorrente sem necessidade técnica explícita.

## 11. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context público, conteúdo sugerido por IA, consumo externo M21, fronteiras M22, carga sintética M23/M25, aquisição/política M24, outcomes/import M26 ou requisitos corporativos devem ser reconciliadas nesta baseline antes da conclusão do merge.

Decisões puramente internas de implementação podem ser tomadas sem aprovação humana quando não alterarem comportamento funcional.

## 12. Critério de encerramento de marco

Um marco só está apto a merge quando:

- código e documentação normativa estão consistentes;
- testes dirigidos passam;
- regressões relevantes passam;
- suíte completa aplicável passa;
- CI está verde;
- não há conflito material com `main` atualizado;
- limitações/fail-open estão explícitos;
- quando o comportamento exige inspeção visual/operacional, o estado é liberado para smoke humano antes do merge, salvo autorização humana explícita em contrário.
