# RASAi - Search & AI Readiness Auditor - Specification Index

**Estado no baseline de desenvolvimento:** BASELINE VIGENTE - reconciliada com `main`  
**Scoring vigente:** `SCORE-GEO-004`  
**Índice público:** `SARI-001`  
**Idioma normativo:** Português, preservando identificadores e termos técnicos quando necessário.

## 1. Objetivo

Este diretório constitui a fonte normativa do RASAi. Histórico de chats não deve ser necessário para descobrir requisitos já formalizados.

Quando um documento histórico conflitar com uma especificação marcada como vigente, prevalece o contrato vigente e o histórico deve ser interpretado como contexto de evolução, não como runtime atual.

## 2. Ordem recomendada de leitura

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
12. `11_REPORTING_LANGUAGE_GLOSSARY.md`
13. `13_MODEL_ROUTING_POLICY.md`
14. `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md`
15. `15_ERROR_CENTRIC_REPORT_UX.md`
16. `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md`
17. `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md`
18. `18_MULTI_AI_PROVIDER_ROUTING.md`
19. `19_SCORE_APPLICABILITY_READINESS_MINIMUMS.md`
20. `20_AI_CONTENT_REMEDIATION.md`
21. `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`
22. `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`
23. `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`
24. `24_CRAWLING_DISCOVERY_AI_ACCESS.md`
25. `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
26. `26_OBSERVED_GENERATIVE_VISIBILITY.md`
27. `27_MONITORING_OBSERVABILITY.md`
28. `28_AUDIT_QUALITY_VERIFICATION.md`
29. `09_IMPLEMENTATION_PLAN.md` - histórico de implementação; não deve sobrescrever contratos vigentes.

## 3. Precedência documental

Em caso de conflito:

1. decisões vigentes em `10_DECISIONS.md`;
2. requisitos funcionais atuais em `07_FUNCTIONAL_REQUIREMENTS.md`;
3. escopo em `01_PROJECT_CHARTER_SCOPE.md`;
4. modelos normativos atuais de domínio, regras, workflows, scoring e priorização;
5. arquitetura técnica atual;
6. especificações funcionais complementares;
7. documentos explicitamente históricos, roadmaps e planos de implementação.

Nenhuma decisão funcional deve ser alterada silenciosamente durante implementação.

## 4. Baseline vigente de scoring

```text
Public index:        SARI-001
Runtime scoring:     SCORE-GEO-004
Overall aggregation: EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
Canonical HTML:      report/scoring.html
```

Princípios:

- dimensões legitimamente `NOT_APPLICABLE` não recebem zero;
- Coverage, Confidence e Consolidation permanecem distintas do Score;
- Overall 004 é determinístico e não exige model artifact externo;
- ausência de evidência suficiente não é transformada em zero;
- métricas externas não entram silenciosamente no SARI;
- IA não calcula diretamente o score;
- mudança incompatível exige nova `scoring_version`.

`SCORE-GEO-003` é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica. Seu Overall dependia de calibração/model artifact. Referências históricas legítimas ao 003 devem ser preservadas para rastreabilidade e nunca reescritas cegamente como 004.

Detalhes: `05_SCORING_MODEL.md`, `../SCORE_GEO_004.md` e `../SCORING_GUIDE.md`.

## 5. REPORT-SITE-GEO-001

Contrato de saída por auditoria, condicionado à materialização:

```text
<AUD-ID>/report/index.html
<AUD-ID>/report/readiness.html
<AUD-ID>/report/scoring.html
<AUD-ID>/report/score-geo-004.html       # alias de compatibilidade; não canônico
<AUD-ID>/report/mobile.html
<AUD-ID>/report/desktop.html
<AUD-ID>/report/remediation.html
<AUD-ID>/report/content-suggestions.html
<AUD-ID>/report/crawling-discovery.html
<AUD-ID>/report/accessibility.html
<AUD-ID>/report/web-performance.html
<AUD-ID>/report/apdex.html
<AUD-ID>/report/apdex-experience.html
<AUD-ID>/report/ai-visibility.html
<AUD-ID>/report/observability.html
<AUD-ID>/report/quality.html
<AUD-ID>/report/ai-usage.html
<AUD-ID>/report/references.html
<AUD-ID>/report/css/site.css
```

`readiness.html` é a página canônica do SARI. `scoring.html` é a página canônica estável da metodologia de scoring e deve exibir a versão efetivamente persistida.

O alias versionado existe somente para compatibilidade e não recebe item próprio no menu.

## 6. Fronteiras metodológicas

| Domínio | Finalidade | Fronteira |
|---|---|---|
| SARI / SCORE-GEO-004 | readiness | proprietário, determinístico, evidence-bound |
| Web Performance | PageSpeed/Lighthouse/CrUX | externo; não entra diretamente no Overall |
| Acessibilidade automatizada | diagnóstico | não certifica WCAG integral; separado do SARI |
| Synthetic Navigation Apdex | navegação sintética | não é RUM; separado do SARI |
| Synthetic User Experience Apdex | experiência sintética | não é RUM; separado do Navigation Apdex e SARI |
| Crawling/discovery | robots, sitemaps, crawler policy | diagnóstico técnico non-scoring |
| Observed Generative Visibility | outcomes de AI Search | observacional; não entra no score |
| Search & AI Observability | outcomes e diagnósticos externos | sidecar derivado; non-scoring |
| Monitoring | baseline/current e release gate | read-only; não cria score |
| Quality | qualidade da evidência/decisão | read-only; não cria readiness score |
| Fix Verification | transição de regra entre AUDs | não prova downstream impact |
| Evidence Timeline | histórico de AUDs | não regrava evidência fonte |
| Product Platform | tenancy, milestones, deploys, usage | control plane separado; não altera audit.db |

## 7. Observed Generative Visibility e validação empírica

`26_OBSERVED_GENERATIVE_VISIBILITY.md` define outcomes observados/importados. Esses dados não recalculam o AUD fonte e não entram automaticamente no `SCORE-GEO-004`.

Datasets externos podem ser usados em pesquisa/benchmarking para avaliar associação entre readiness e outcomes. Isso é separado do runtime de scoring e qualquer mudança decorrente exige nova versão metodológica explícita.

Fluxos históricos de calibração do `SCORE-GEO-003` não devem ser documentados como comandos vigentes do entrypoint 004.

## 8. Monitoring, Observability & Quality

### Monitoring

```text
rasai monitor compare
rasai monitor impact
rasai monitor gate
```

- abre AUDs em modo read-only;
- respeita `scoring_version`, device e universo de URLs;
- não presume causalidade;
- dados complementares entram no gate apenas por opt-in quando documentado.

### Observability

```text
rasai observe ...
rasai observability ...
```

- sidecar atual `RASAI-OBS-002`;
- identidade `(dataset_id, record_id)`;
- provenance explícita;
- `NULL` externo não vira zero;
- não altera `audit.db` nem SARI/SCORE-GEO-004.

### Quality

```text
rasai quality report
rasai quality verify
rasai quality timeline
```

- Audit Health;
- Evidence Confidence;
- Operational Priority;
- Coverage Map;
- Recommendation Validation;
- content-use controls;
- Fix Verification e Timeline read-only.

## 9. Product Platform

O control plane local usa `audits/.rasai/platform.db` e permanece separado do `audit.db` imutável.

Modela multiusuário, multiworkspace, multiprojeto, multidomínio, milestones/deployments, golden baselines, comparação before/after, schedules, alerts, integrations e usage ledger.

A arquitetura alvo SaaS migra o control plane para PostgreSQL e workers Linux/containerizados, preservando a evidência AUD como bundle imutável.

Detalhes: `../PRODUCT_PLATFORM_ARCHITECTURE.md`.

## 10. Fontes externas e heurística

O RASAi não representa seu score ou thresholds como standard GEO/AEO universal.

Referências primárias externas sustentam fenômenos específicos. Elas não homologam automaticamente `SARI-001` ou `SCORE-GEO-004`.

Heurísticas BR-GEO sem equivalente normativo permanecem identificadas como heurística/baseline interna.

## 11. Continuidade de branches e integração

Branches de trabalho são temporárias. Após validação e merge em `main`, confirmar que não existe conteúdo exclusivo pendente antes de excluir branch.

## 12. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context, IA, Web Performance, acessibilidade, Apdex, crawling/discovery, visibilidade observada, monitoring/observability/quality ou Product Platform devem reconciliar código, testes, HTML e documentação normativa.

## 13. Critério de encerramento de alteração

Uma alteração só está concluída quando:

- código e documentação vigente estão consistentes;
- testes dirigidos e regressões relevantes passam;
- CI está verde;
- não há conflito material com `main` atualizado;
- limitações/fail-open estão explícitos;
- HTML/menu estão coerentes;
- referências históricas são preservadas quando materialmente necessárias.
