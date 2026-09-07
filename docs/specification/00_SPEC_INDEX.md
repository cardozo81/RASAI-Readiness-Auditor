# SearchGEO Readiness Auditor — Specification Index

**Status:** BASELINE VIGENTE — capacidades integradas e documentação reconciliada com `main`.
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
8. especificações funcionais complementares, quando não conflitarem com os itens anteriores.

Nenhuma decisão funcional deve ser alterada silenciosamente durante implementação.

## 4. Catálogo normativo

### Core

- `01_PROJECT_CHARTER_SCOPE.md` — propósito, escopo, princípios e exclusões.
- `02_DOMAIN_MODEL.md` — entidades, relacionamentos, identificadores, estados e invariantes.
- `03_BUSINESS_RULES.md` — Business Rules `BR-GEO-001` a `BR-GEO-054`.
- `04_WORKFLOWS.md` — workflows e ordem de execução.
- `05_SCORING_MODEL.md` — Score, Coverage, Confidence, Consolidation e aplicabilidade. Baseline: `SCORE-GEO-002`.
- `06_PRIORITIZATION_MODEL.md` — Severity, Impact, Effort, Confidence e Priority.
- `07_FUNCTIONAL_REQUIREMENTS.md` — requisitos funcionais e não funcionais vigentes.
- `08_TECHNICAL_ARCHITECTURE.md` — arquitetura local/modular e fronteiras entre domínios.
- `09_IMPLEMENTATION_PLAN.md` — histórico e ordem de implementação das capacidades.
- `10_DECISIONS.md` — decisões humanas consolidadas e pendências corporativas.
- `11_REPORTING_LANGUAGE_GLOSSARY.md` — linguagem e apresentação do relatório.
- `12_AI_HANDOFF.md` — continuidade operacional por IA/desenvolvedor.
- `13_MODEL_ROUTING_POLICY.md` — política de modelos e esforço.

### Especificações funcionais complementares

- `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md` — auditoria multi-URL e evidência visual.
- `15_ERROR_CENTRIC_REPORT_UX.md` — experiência de leitura e organização dos relatórios.
- `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md` — remediação por causa raiz e elemento.
- `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md` — precisão e consistência das recomendações.
- `18_MULTI_AI_PROVIDER_ROUTING.md` — análise semântica por IA, roteamento, fallback e telemetria.
- `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md` — aplicabilidade, mínimos e regras do `SCORE-GEO-002`.
- `20_AI_CONTENT_REMEDIATION.md` — sugestões e remediação de conteúdo por IA, sem alteração retroativa do score.
- `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md` — PageSpeed, Lighthouse e Core Web Vitals/CrUX como evidência externa complementar.
- `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md` — acessibilidade automatizada e diagnósticos Web separados do SearchGEO Readiness.
- `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md` — Synthetic Navigation Apdex.
- `24_CRAWLING_DISCOVERY_AI_ACCESS.md` — rastreamento, descoberta e políticas de crawlers.
- `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md` — Synthetic User Experience Apdex calibrável, separado de RUM.
- `26_OBSERVED_GENERATIVE_VISIBILITY.md` — visibilidade generativa observada/importada, separada de readiness.

## 5. Baseline vigente de scoring e método público

- motor persistido: `SCORE-GEO-002`;
- identidade pública de readiness: `SGRI-001`;
- dimensões legitimamente `NOT_APPLICABLE` não recebem zero e são excluídas conforme `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`;
- Coverage, Confidence e Consolidation permanecem métricas distintas do Score;
- não existe alegação de score GEO/AEO universal ou homologado;
- métricas externas ou resultados observados não são incorporados ao SGRI sem nova decisão, nova versão e validação apropriada.

## 6. REPORT-SITE-GEO-001

O contrato final de saída continua condicional pela existência/materialização do arquivo:

```text
<AUD-ID>/report/index.html
<AUD-ID>/report/searchgeo.html             # SGRI-001 / SearchGEO
<AUD-ID>/report/mobile.html                # condicional
<AUD-ID>/report/desktop.html               # condicional
<AUD-ID>/report/remediation.html
<AUD-ID>/report/content-suggestions.html
<AUD-ID>/report/crawling-discovery.html    # rastreamento e descoberta
<AUD-ID>/report/accessibility.html         # acessibilidade automatizada, condicional
<AUD-ID>/report/web-performance.html       # Lighthouse/Core Web Vitals, quando habilitados
<AUD-ID>/report/apdex.html                 # Synthetic Navigation Apdex, condicional
<AUD-ID>/report/apdex-experience.html      # Synthetic User Experience Apdex, condicional
<AUD-ID>/report/ai-visibility.html         # visibilidade observada, após importação/regeneração
<AUD-ID>/report/ai-usage.html
<AUD-ID>/report/references.html
<AUD-ID>/report/css/site.css
```

Default de dispositivo da CLI: `mobile`. `desktop` e `both` são seleções explícitas/parametrizáveis.

### Propriedade analítica

Cada indicador ou domínio possui uma página canônica. O `index.html` pode resumir um resultado final para navegação executiva, mas não deve duplicar metodologia/evidência detalhada nem fundir métricas diferentes em um score comum.

`searchgeo.html` é a página canônica de SGRI/indicadores proprietários. Acessibilidade, Web Performance, Apdex e visibilidade generativa observada permanecem domínios separados.

## 7. Fronteiras dos domínios complementares

| Domínio | Finalidade | Regra de fronteira |
|---|---|---|
| Web Performance | PageSpeed/Lighthouse/CrUX | evidência externa; não altera o SearchGEO Readiness Index |
| Acessibilidade automatizada | diagnóstico Lighthouse de acessibilidade | não declara conformidade WCAG integral nem altera o SearchGEO Readiness Index |
| Synthetic Navigation Apdex | navegação sintética controlada | T/4T explícito; não é RUM; não altera o SearchGEO Readiness Index |
| Rastreamento e descoberta | robots.txt, sitemaps, feeds e políticas de crawlers | diagnóstico técnico; não altera o SearchGEO Readiness Index |
| Synthetic User Experience Apdex | experiência sintética calibrável | não é RUM; permanece separado do Synthetic Navigation Apdex e do SearchGEO Readiness Index |
| Observed Generative Visibility | resultados observados/importados de AI Search | permanece separado de readiness e não cria score GEO próprio |

## 8. Observed Generative Visibility

Fonte normativa: `26_OBSERVED_GENERATIVE_VISIBILITY.md`.

A capacidade:

- está integrada à baseline vigente;
- usa contrato `OGV-IMPORT-001`;
- funciona por importação de evidência normalizada, sem scraping de portal e sem presumir endpoint não documentado;
- suporta inicialmente `BING_WEBMASTER_TOOLS_AI_PERFORMANCE` e `CONTROLLED_QUERY_RUNS`;
- preserva o JSON normalizado como artifact e registra SHA-256;
- exige URLs do mesmo `normalized_origin` da auditoria;
- mantém Total Citations/Average Cited Pages como métricas reportadas pela fonte;
- calcula Citation Presence Rate apenas sobre runs controlados `VALID`;
- apresenta `n` e Wilson 95% quando a taxa é calculável;
- cria `report/ai-visibility.html`;
- não escreve nem recalcula `scores`, `score_contributions`, `rule_executions`, `findings` ou `recommendations`;
- não cria GEO Score, ranking, autoridade nem probabilidade de citação futura;
- não presume causalidade entre SGRI e visibilidade observada.

## 9. Fontes externas e heurística

O SearchGEO não deve representar seu score ou thresholds como standard GEO/AEO universal.

Referências primárias atuais incluem Google Search Central/Crawling Infrastructure, OpenAI publisher/help documentation, Schema.org, WHATWG, IETF/RFC, Chrome Developers, PageSpeed Insights, Chrome UX Report, W3C/WAI, Apdex Alliance, documentação pública Dynatrace para comparabilidade do Synthetic User Experience Apdex e documentação pública Bing Webmaster/Search para visibilidade observada.

Structured Data/JSON-LD é reforço opcional, não requisito universal GEO. Quando a remediação de conteúdo por IA propõe ou revisa JSON-LD, usa somente conteúdo/evidência persistidos.

Lighthouse e Core Web Vitals introduzem métricas externas documentadas para fenômenos específicos. Não homologam `SCORE-GEO-002` e não são combinados silenciosamente com ele.

Acessibilidade automatizada Lighthouse permanece independente do GEO e não equivale a conformidade WCAG integral.

Os dois domínios Synthetic Apdex usam contratos sintéticos próprios; não são derivados de Lighthouse/CrUX e não devem ser apresentados como população humana observada.

Rastreamento e descoberta usam protocolos e orientações públicas aplicáveis. `llms.txt` permanece proposta comunitária experimental e sua ausência não é falha de SearchGEO.

Observed Generative Visibility separa métricas reportadas pela fonte de cálculos SearchGEO sobre query-runs. Contagem de citações não deve ser rotulada como ranking ou autoridade.

Heurísticas BR-GEO sem equivalente normativo permanecem identificadas como heurísticas/baseline interna.

## 10. Continuidade de branches e integração

Branches de trabalho são temporárias.

Após validação e merge em `main`:

1. confirmar que `main` contém integralmente a alteração;
2. confirmar ausência de conteúdo exclusivo pendente;
3. classificar a branch como removível;
4. excluir fisicamente quando a ferramenta/permissão permitir;
5. impossibilidade de exclusão pelo conector não bloqueia a continuidade quando a integração já está comprovada, conforme decisões vigentes.

Uma branch ativa de outro trabalho não deve ser modificada ou incorporada por uma alteração concorrente sem necessidade técnica explícita.

## 11. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context público, conteúdo sugerido por IA, consumo de Web Performance, fronteiras de acessibilidade, carga sintética, aquisição/rastreamento, visibilidade observada ou requisitos corporativos devem ser reconciliadas nesta baseline antes da conclusão do merge.

Decisões puramente internas de implementação podem ser tomadas sem aprovação humana quando não alterarem comportamento funcional.

## 12. Critério de encerramento de alteração

Uma alteração só está apta a merge quando:

- código e documentação normativa estão consistentes;
- testes dirigidos passam;
- regressões relevantes passam;
- suíte completa aplicável passa;
- CI está verde;
- não há conflito material com `main` atualizado;
- limitações/fail-open estão explícitos;
- quando o comportamento exige inspeção visual/operacional, o estado é liberado para smoke humano antes do merge, salvo autorização humana explícita em contrário.
