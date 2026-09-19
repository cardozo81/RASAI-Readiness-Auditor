# RASAi - Search & AI Readiness Auditor - índice da especificação

**Contrato vigente:** VIGENTE  
**Scoring:** `SCORE-GEO-004`  
**Índice público:** `SARI-001`  
**Contrato de relatório:** `CATALOG-REPORT-002`  
**Idioma normativo:** português do Brasil, preservando identificadores e termos técnicos quando necessário.

## 1. Objetivo

Este diretório constitui a fonte normativa do RASAi. A especificação deve permitir compreender o produto e seus contratos atuais sem depender de chats, mecanismos de entrega ou estados de desenvolvimento que não façam parte do produto vigente.

A documentação normativa descreve somente o comportamento atual.

As regras gerais de idioma, direitos autorais/citações, credenciais externas e apresentação de default/valores permitidos/recomendados estão definidas em `../README.md`, `../ENVIRONMENT_VARIABLES.md` e `../EXTERNAL_CREDENTIALS.md` e aplicam-se a todos os arquivos deste diretório.

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
18. `18_AI_RUNTIME_ORCHESTRATION.md`
19. `18_MULTI_AI_PROVIDER_ROUTING.md`
20. `19_SCORE_APPLICABILITY_READINESS_MINIMUMS.md`
21. `20_AI_CONTENT_REMEDIATION.md`
22. `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`
23. `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`
24. `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`
25. `24_CRAWLING_DISCOVERY_AI_ACCESS.md`
26. `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
27. `26_OBSERVED_GENERATIVE_VISIBILITY.md`
28. `27_MONITORING_OBSERVABILITY.md`
29. `28_AUDIT_QUALITY_VERIFICATION.md`
30. `29_SAAS_PILOT_WEB.md`
31. `30_IDENTITY_AND_ACCESS.md`
32. `../TIMEZONE_CONTRACT.md` para persistência, comparação, schedules e apresentação temporal.

## 3. Precedência documental

Em caso de conflito:

1. decisões vigentes em `10_DECISIONS.md`;
2. requisitos funcionais atuais em `07_FUNCTIONAL_REQUIREMENTS.md`;
3. escopo em `01_PROJECT_CHARTER_SCOPE.md`;
4. modelos normativos atuais de domínio, regras, workflows, scoring e priorização;
5. arquitetura técnica atual;
6. especificações funcionais complementares.

Quando qualquer documento divergir do comportamento comprovado pelo runtime vigente, a documentação deve ser corrigida para representar o código atual, salvo quando a divergência revelar defeito de implementação catalogado para correção posterior. Revisões documentais não alteram código para preservar texto divergente.

Protótipos em `../../prototypes/` não são fonte normativa. Eles podem representar contratos atuais ou contratos desejados, mas nunca prevalecem sobre runtime, testes e especificação vigente.

## 4. Contrato de scoring

```text
Public index:        SARI-001
Runtime scoring:     SCORE-GEO-004
Overall aggregation: HIERARCHICAL_WEIGHTED_READINESS_V1
Canonical HTML:      report-catalog/methodology.html
```

Princípios:

- o contrato vigente possui 11 dimensões, incluindo `CONTENT_VALUE`;
- dimensões legitimamente `NOT_APPLICABLE` não recebem zero;
- pesos de dimensão e de grupo são versionados pelo contrato e não configuráveis por auditoria;
- o Overall pondera as dimensões aplicáveis e efetivamente medidas e renormaliza o denominador pelos pesos participantes;
- dimensão aplicável sem valor não recebe imputação numérica e reduz Coverage/Confidence conforme o contrato;
- Coverage, Confidence e Consolidation permanecem distintas do Score;
- Overall é determinístico e não exige model artifact externo;
- ausência de evidência suficiente não é transformada em zero;
- métricas externas não entram silenciosamente no SARI;
- `BR-GEO-060` é a única corroboração externa score-eligible vigente e somente contribui quando há evidência positiva Common Crawl persistida e reproduzível;
- IA não calcula diretamente o score;
- mudança metodologicamente incompatível exige nova `scoring_version`.

Detalhes: `05_SCORING_MODEL.md`, `../SCORE_GEO_004.md`, `../SCORING_GUIDE.md` e `../SARI_EXTERNAL_CRAWL_CORROBORATION.md`.

## 5. CATALOG-REPORT-002

A projeção HTML audit-owned suportada é `<AUD-ID>/report-catalog/`. `<AUD-ID>/report/`, `<AUD-ID>/report.html` e `<AUD-ID>/remediation.html` não pertencem ao contrato de saída de `rasai audit`.

Entrada principal:

```text
<AUD-ID>/report-catalog/index.html
```

O contrato vigente inclui a visão geral, SARI, CAT-01 ... CAT-10 conforme o catálogo da auditoria e páginas próprias de governança, com manifest e assets do pacote. A fonte de verdade para filenames, ordem e labels é `src/rasai/catalog_report_contract.py`.

A materialização do catálogo é projeção read-only sobre os dados persistidos. Ela não dispara collectors, APIs, providers, IA, scoring ou workloads sintéticos para preencher HTML. Dados como findings, evidences, recommendations, root cause, precisão, métricas e telemetria continuam sendo produzidos pelas etapas funcionais da auditoria e apenas projetados no catálogo.

## 6. Fronteiras metodológicas

| Domínio | Finalidade | Fronteira |
|---|---|---|
| SARI / SCORE-GEO-004 | readiness | proprietário, determinístico, evidence-bound |
| Web Performance | PageSpeed/Lighthouse/CrUX | externo; não entra diretamente no Overall |
| Acessibilidade automatizada | diagnóstico | não certifica WCAG integral; separado do SARI |
| Synthetic Navigation Apdex | navegação sintética | não é RUM; separado do SARI |
| Synthetic User Experience Apdex | experiência sintética | não é RUM; separado do Navigation Apdex e SARI |
| Crawling/discovery | robots, sitemaps, crawler policy | diagnóstico técnico; somente regras explicitamente versionadas podem pontuar |
| Search Intelligence | SERP e comparação competitiva opcional | observacional/advisory; non-scoring |
| Observed Generative Visibility | outcomes de AI Search | observacional; não entra no score |
| Search & AI Observability | outcomes e diagnósticos externos | sidecar derivado; non-scoring, salvo `BR-GEO-060` conforme contrato específico |
| Monitoring | baseline/current e release gate | read-only; não cria score |
| Quality | qualidade da evidência/decisão | read-only; não cria readiness score |
| Fix Verification | transição de regra entre AUDs | não prova downstream impact |
| Evidence Timeline | série de AUDs | não regrava evidência fonte |
| Product Platform | tenancy, milestones, deploys, usage | control plane separado; não altera audit.db |
| Web/API/SaaS Pilot | browser, API e durable execution jobs | projeção tenant-aware; não altera scoring nem executa crawling em request |
| Identity & Access | autenticação externa, vínculo e sessão | termina em `Principal`; autorização continua em memberships; não altera audit.db |

## 7. Observed Generative Visibility e validação empírica

`26_OBSERVED_GENERATIVE_VISIBILITY.md` define outcomes observados/importados. Esses dados não recalculam o AUD fonte e não entram automaticamente no `SCORE-GEO-004`.

Datasets externos podem ser usados em pesquisa/benchmarking para avaliar associação entre readiness e outcomes. Isso é separado do runtime de scoring e qualquer mudança decorrente exige nova versão metodológica explícita.

## 8. Monitoring, Observability e Quality

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
- não altera `audit.db` nem SARI/SCORE-GEO-004, exceto a Evidence/RuleExecution mínima de `BR-GEO-060` quando a corroboração Common Crawl positiva qualifica para scoring.

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

Os nomes acima podem permanecer em inglês quando correspondem às capacidades/estados técnicos canônicos; a explicação funcional deve permanecer em pt-BR.

## 9. Product Platform, SaaS Pilot Web e Identity & Access

O control plane local usa `audits/.rasai/platform.db` e permanece separado do `audit.db` imutável.

Modela multiusuário, multiworkspace, multiprojeto, multidomínio, milestones/deployments, golden baselines, comparação before/after, schedules, alerts, integrations e usage ledger.

PostgreSQL é o backend centralizado do control plane para operação hospedada. Workers permanecem desacoplados do processo HTTP e `AUD-*/audit.db` continua sendo evidência imutável da execução.

O SaaS Pilot Web adiciona UI de navegador sem segunda persistência e sem mover regra de negócio para o frontend. Reports de um AUD podem ser projetados via HTTP somente após autorização e apenas dentro da árvore pública `report/`.

Identity & Access usa OIDC/JWT provider-neutral, Authorization Code + PKCE para browser, sessão Web curta e vínculo explícito `(issuer, subject) -> USR-*`. Autenticação não cria memberships e não substitui as regras de tenancy.

Detalhes: `../PRODUCT_PLATFORM_ARCHITECTURE.md`, `29_SAAS_PILOT_WEB.md`, `30_IDENTITY_AND_ACCESS.md`, `../SAAS_PILOT_WEB.md`, `../IDENTITY_AND_ACCESS.md` e `../WEB_API_FOUNDATION.md`.

## 10. Tempo e timezone

Persistência e comparação temporal usam UTC como referência canônica. A apresentação converte para o timezone configurado, com `America/Sao_Paulo` como padrão público vigente quando aplicável. Schedules e datas de wall-clock devem respeitar o contrato específico documentado em `../TIMEZONE_CONTRACT.md`.

Nenhum relatório deve reinterpretar timestamp persistido como timezone local sem conversão explícita.

## 11. Fontes externas, direitos autorais e heurística

O RASAi não representa seu score ou thresholds internos como standard GEO/AEO universal.

Referências primárias externas sustentam fenômenos específicos. Elas não homologam automaticamente `SARI-001` ou `SCORE-GEO-004`.

Heurísticas BR-GEO sem equivalente normativo permanecem identificadas como heurística interna.

Quando houver reprodução ou tradução/adaptação de trecho protegido por direitos autorais, a seção correspondente deve incluir a nota definida em `../README.md`, preservar o excerto original estritamente necessário e apresentar a tradução/adaptação pt-BR. Lista de links ou nomes técnicos, isoladamente, não equivale a reprodução da obra.

Credenciais, tokens, API keys e onboarding de serviços externos devem apontar para fonte oficial e seguir `../EXTERNAL_CREDENTIALS.md`.

## 12. Regra de valores configuráveis

Variável, flag, threshold ou limite configurável deve publicar, quando aplicável:

- default efetivo;
- valores permitidos ou tipo/faixa aceita;
- recomendado;
- dependência/obrigatoriedade;
- impacto operacional quando relevante.

Valor metodológico fixo deve ser identificado como fixo/versionado e não como default customizável.

## 13. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context, IA, Web Performance, acessibilidade, Apdex, crawling/discovery, visibilidade observada, monitoring/observability/quality, Product Platform, Web/API/SaaS Pilot ou Identity & Access devem reconciliar código, testes, HTML e documentação normativa na mesma evolução.

## 14. Critério de conclusão

Uma alteração só está concluída quando:

- código e documentação vigente estão consistentes;
- testes dirigidos e regressões relevantes passam;
- CI está verde;
- não há conflito material com `main` atualizado;
- limitações e comportamento fail-closed estão explícitos;
- HTML/menu estão coerentes quando afetados;
- a documentação resultante descreve somente o contrato vigente.