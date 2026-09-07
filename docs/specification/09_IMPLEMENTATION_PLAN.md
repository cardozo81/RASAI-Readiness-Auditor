# IMPLEMENTATION_PLAN.md

**Status:** APPROVED — extended through Precisão e consistência das recomendações

## Bootstrap e fundação do projeto — Bootstrap

Objetivo:

- estrutura mínima;
- package Python;
- configuração;
- logging;
- CLI;
- --version;
- `audit <target>`;
- validação básica.

Não implementar módulos futuros vazios.

## Auditoria e persistência — Audit + Persistence

Implementar:

- Audit;
- AuditTarget;
- Page;
- PageSnapshot;
- Evidence;
- RuleExecution;
- Finding;
- repositories mínimos;
- audit.db;
- estrutura filesystem.

Critério: criar, persistir, encerrar, reabrir e recuperar Audit.

## Descoberta e aquisição HTTP — Discovery + HTTP

Implementar:

- seed;
- normalization;
- robots;
- sitemap;
- internal links;
- provenance;
- max_pages;
- HTTP;
- redirects;
- headers;
- network errors.

Primeiras regras técnicas.

## Renderização Desktop e Mobile — Rendering Desktop/Mobile

Implementar:

- Playwright;
- Chromium;
- Desktop profile;
- Mobile profile;
- RAW;
- rendered;
- PageSnapshot independente.

## Extração e evidências — Extraction + Evidence

Implementar:

- content extraction;
- metadata;
- headings;
- links;
- Dados Estruturados;
- Evidence Manager.

## Motor de regras determinísticas — Deterministic Rules Engine

Implementar:

- Rule Registry;
- Check;
- Rule Executor;
- dependencies;
- applicability;
- findings.

Principalmente BR-GEO-001..018.

Checkpoint: Technical Auditor Alpha funcional sem IA.

## JavaScript e SPA — JavaScript / SPA

Implementar:

- BR-GEO-019..024;
- RAW × RENDERED;
- direct routes;
- soft-404;
- lazy loading;
- crawlable navigation.

## Análise semântica e fallback — Semantic Provider + Fallback

Implementar:

- SemanticAnalysisProvider;
- NoneProvider;
- OpenAIProvider;
- FULL / DEGRADED / NO_AI;
- schema validation;
- evidence validation;
- BR-GEO-028..049 progressivamente.

Teste obrigatório com IA e sem IA.

## Comparação Desktop e Mobile — Desktop × Mobile Comparison

Implementar DeviceComparator e BR-GEO-052.

## Scoring e confiabilidade — Scoring + Reliability

Implementar:

- ScoringEngine;
- ScoreContribution;
- Coverage;
- Confidence;
- Consolidation;
- scoring groups;
- Overall por dispositivo.

## Priorização e recomendações — Prioritization + Recommendations

Implementar:

- Severity;
- Impact;
- Effort;
- Priority;
- deterministic recommendation templates;
- RemediationGroup.

## Relatório HTML estático — Static HTML Report

Implementar:

- ReportBuilder;
- localization pt-BR;
- glossary;
- reliability section;
- scorecard;
- findings;
- evidence;
- recommendations;
- limitations.

## Testes críticos e baseline local estável — Critical Tests + Stable Local Baseline

Testar minimamente:

- parsing;
- Rules Engine;
- scoring;
- Desktop/Mobile;
- AI fallback;
- report;
- regressões críticas.

## Remediação GEO acionável — Actionable GEO Remediation Report

Objetivo: evoluir a Stable Local Baseline de `GEO scoring/reporting` para `GEO scoring + evidence-backed actionable remediation`, sem alterar arbitrariamente o scoring aprovado.

Implementar:

- `RemediationRecipe` determinística por `rule_id` ou família de regras;
- recomendações Priorização e recomendações específicas por regra sempre que houver recipe;
- fallback explicitamente identificado;
- `REPORT-GEO-002`;
- resumo executivo com Compatibilidade GEO, Coverage e Confidence separados;
- `NÃO DETERMINADA` quando Overall não for consolidável;
- classificação textual/visual de score;
- principais oportunidades derivadas dos dados persistidos;
- scorecards Desktop/Mobile independentes;
- plano de correção priorizado;
- correções técnicas detalhadas com página, dispositivo, regra, alvo, observado, exemplo, aceite e revalidação;
- separação explícita entre HTML observado e exemplo recomendado;
- canonical acionável e conservadora;
- reutilização de SemanticAssessment, reasoning_summary, entidades e intents persistidos;
- Citation Readiness / Evidence Trust no report;
- diagnóstico de crawl reabrível a partir de estado persistido;
- documentação e testes mínimos de regressão.

Restrições:

- preservar `SCORE-GEO-001`;
- preservar `PRIORITY-GEO-001`;
- não converter UNKNOWN/ERROR/NOT_APPLICABLE em FAIL;
- ausência de IA não penaliza o website;
- não criar segunda chamada livre de IA para redação;
- não inventar HTML observado, canonical, noindex policy, structured data, autor, fonte, data ou fatos;
- relatório continua estático, autocontido, responsivo e sem dependência externa obrigatória.

## Auditoria multi-URL e evidência visual — Multi-URL + Visual/DOM Evidence + Actionability

Objetivo: permitir auditoria explícita de várias URLs do mesmo origin em um único `audit_id` e melhorar a rastreabilidade visual/técnica das correções.

Implementar:

- `URL_SET` explícito por múltiplos targets e `--urls-file`;
- normalização/deduplicação determinística;
- aquisição global única de `robots.txt`/sitemaps;
- screenshots Desktop/Mobile;
- `ElementObservation` e vínculo Finding → elemento quando determinístico;
- actionability independente de RuleResult/scoring;
- referências técnicas versionadas;
- `REPORT-GEO-003`;
- distinção obrigatória entre zero calculado e ausência de cálculo.

Restrições:

- preservar `SCORE-GEO-001`;
- não expandir silenciosamente URL_SET por links/sitemap;
- não inventar selector, HTML observado ou referência técnica;
- recursos de domínio não são findings duplicados por página.

## Experiência e organização dos relatórios — Error-Centric Report + Report UX

Objetivo: melhorar navegação, legibilidade e priorização humana sem alterar dados persistidos, scoring ou findings.

Implementar:

- `report.html` preservado como visão principal orientada a página;
- menu lateral fixo em desktop com paths/query das URLs auditadas;
- navegação compacta em viewport estreita;
- tipografia e grid de Score GEO reequilibrados;
- guia das dez dimensões oficiais de `SCORE-GEO-001`;
- seção final explicando Score, Coverage, Confidence, Consolidation e Actionability;
- `remediation.html` no mesmo nível do `report.html`;
- contrato `REMEDIATION-GEO-001`;
- agrupamento transversal por escopo (`GLOBAL`/`PAGE`), `rule_id` e actionability;
- lista das páginas/paths afetados e ocorrências Desktop/Mobile;
- links relativos entre `report.html` e `remediation.html`;
- CLI informando o path dos dois relatórios;
- documentação operacional com exemplos genéricos de múltiplas URLs diretas e `--urls-file`.

Restrições:

- preservar `REPORT-GEO-003` para a projeção principal;
- preservar `SCORE-GEO-001`, Coverage, Confidence, Consolidation e actionability;
- `remediation.html` não recalcula regras, findings ou prioridades;
- não promover repetição em páginas a finding global;
- não introduzir nova chamada de IA;
- problemas do OpenAIProvider permanecem fora do escopo deste marco.

Critérios de conclusão:

1. ambos os HTMLs são gerados no mesmo workspace;
2. problema repetido em duas páginas aparece em um grupo transversal com duas ocorrências/páginas;
3. finding global permanece global;
4. sidebar usa paths sem repetir domínio e trunca somente visualmente;
5. layout do score não quebra tokens curtos de forma agressiva;
6. guia das dez dimensões e interpretação final estão presentes;
7. CLI exibe `report.html` e `remediation.html`;
8. exemplos de execução documental não usam domínio corporativo de smoke;
9. suíte determinística permanece verde;
10. diff final não contém workflow temporário nem secrets.

## Remediação por causa raiz e elemento — Root Cause + Element-Level Remediation

Objetivo: transformar cada finding em diagnóstico técnico por ocorrência, informando a causa raiz, onde ela foi observada e como corrigi-la sem fabricar precisão.

Implementar:

- materialização aditiva `root_cause_analyses`, uma análise por `finding_id`;
- `cause_type`, `cause_summary`, evidências-base, observado versus esperado;
- classificação do escopo como elemento exato, conjunto/região contextual ou recurso/documento;
- reaproveitamento do vínculo Finding → `ElementObservation` quando determinístico;
- listagem de múltiplos headings quando a hierarquia é propriedade do conjunto;
- localização de `BR-GEO-034..037` nos blocos `script[type="application/ld+json"]` observados;
- uso de `<main>` apenas como região contextual para regras semânticas quando não houver localização mais precisa evidence-backed;
- selector, tag/id/classes e `outer_html` somente quando persistidos/prováveis;
- mudança exata derivada da `RemediationRecipe`;
- exemplo pós-correção, critérios de aceite, revalidação e decisão humana quando aplicável;
- bloco de causa raiz em cada finding do `report.html`;
- diagnóstico por ocorrência dentro de cada grupo do `remediation.html`;
- guia operacional específico e testes de regressão.

Restrições:

- não inventar selector, elemento, HTML observado, causa técnica ou conteúdo;
- `<main>` contextual não deve ser apresentado como elemento defeituoso por si só;
- regras globais/HTTP/robots/sitemap não recebem selector DOM artificial;
- diagnóstico Remediação por causa raiz e elemento não altera Business Rules, severity, actionability, prioridade, Score, Coverage, Confidence ou Consolidation;
- `diagnostic_confidence` mede apenas precisão de localização/causa e não participa de `SCORE-GEO-001`;
- não introduzir chamada adicional de IA para redigir causa raiz.

Critérios de conclusão:

1. finding com elemento único mostra selector/HTML observado quando persistidos;
2. finding de conjunto não recebe elemento único arbitrário;
3. headings podem listar múltiplos nós;
4. dados estruturados apontam para script JSON-LD, inclusive como conjunto quando houver vários blocos;
5. regra semântica pode usar região contextual sem atribuir defeito à tag contêiner;
6. recurso global mostra selector `NÃO APLICÁVEL`;
7. observado, esperado, causa, mudança, aceite e revalidação são rastreáveis;
8. ambos os relatórios projetam a mesma análise materializada;
9. suíte determinística permanece verde;
10. diff final não contém workflow temporário nem secrets.

## Precisão e consistência das recomendações — Remediation Precision + Report Consistency

Objetivo: tornar o diagnóstico técnico inequívoco para implementação e alinhar os dois relatórios à actionability real, sem alterar regras, scoring ou prioridade.

Implementar:

- projeção aditiva `root_cause_precision` por `finding_id`;
- `reason_code` evidence-backed com precedência sobre resumo genérico da família da regra;
- causa precisa para condições conhecidas, como `CANONICAL_ABSENT`;
- separação explícita entre estado/selector do elemento observado e elemento/selector alvo da correção;
- estados `PRESENT`, `ABSENT`, `CONTEXT_ONLY`, `NOT_APPLICABLE` e `NOT_DETERMINED` para elemento observado;
- selector técnico alvo derivado deterministicamente da regra/recipe sem ser apresentado como observação;
- copy de IA distinguindo ausência, tentativa sem sucesso, sucesso e disponibilidade parcial;
- resumo executivo separando Findings, ações necessárias, revisões e melhorias opcionais;
- plano priorizado que combina actionability e prioridade sem converter WARNING em FAIL;
- `report.html` mais compacto, preservando causa, evidência, recipe e rastreabilidade mínima;
- `remediation.html` como projeção completa da recipe e dos diagnósticos por ocorrência;
- evidência sanitizada reutilizando a política de redaction existente;
- diagnóstico explícito de integridade RuleExecution → Finding;
- regressão multi-URL com a mesma regra em páginas distintas.

Restrições:

- preservar Business Rules e RuleResult;
- preservar `SCORE-GEO-001`, `PRIORITY-GEO-001`, severity, actionability, Coverage, Confidence e Consolidation;
- não criar Finding automaticamente para corrigir divergência de integridade;
- não apresentar selector alvo como selector observado;
- não inventar HTML ou causa técnica;
- não expor credenciais ou valores sensíveis em evidências de rastreabilidade;
- não introduzir nova chamada de IA para redigir remediações.

Critérios de conclusão:

1. reason específico prevalece quando persistido;
2. canonical ausente mostra elemento `ABSENT`, selector observado `NÃO APLICÁVEL` e selector alvo separado;
3. tentativa OpenAI indisponível não é descrita como análise externa concluída;
4. resumo diferencia Finding de ação necessária/revisão/melhoria;
5. `REVIEW_RECOMMENDED · P1` permanece semanticamente revisão;
6. `report.html` reduz duplicação mantendo rastreabilidade mínima e evidência sanitizada;
7. `remediation.html` preserva exemplo, decisão humana, aceite e revalidação por ocorrência;
8. RuleExecution FAIL/WARNING sem Finding é sinalizada explicitamente;
9. teste de duas páginas comprova um grupo transversal e diagnósticos independentes;
10. suíte determinística permanece verde;
11. diff final não contém workflow temporário nem secrets.

## Stable Local Baseline

Critérios:

- recebe domínio ou URL_SET explícito;
- descobre/processa URLs conforme o modo de entrada;
- respeita max_pages;
- Desktop/Mobile;
- RAW/rendered/visual;
- SPA/non-SPA;
- evidence;
- rules;
- findings;
- causa raiz e localização técnica evidence-backed;
- distinção entre elemento observado e alvo técnico da correção;
- IA opcional;
- coverage/confidence;
- scoring;
- prioritization;
- `report.html` orientado a página e diagnóstico;
- `remediation.html` orientado a problema/remediação completa;
- integridade RuleExecution → Finding explicitável;
- limitações explícitas;
- testes críticos.

Após Precisão e consistência das recomendações, a baseline de reporting possui duas projeções complementares, causa raiz por ocorrência e uma camada aditiva de precisão de diagnóstico/remediação sem alterar os contratos de scoring ou regras.

Git/GitHub já são utilizados a partir do Bootstrap e fundação do projeto para controle de versão e repositório de desenvolvimento. A adoção antecipada de Git/GitHub é uma decisão de processo de desenvolvimento e não torna GitHub dependência de execução do produto.

## Regra operacional

Cada marco deve ser tratado como unidade independente e somente pode ser considerado concluído após:

1. implementação integral do escopo permitido;
2. validação e testes obrigatórios;
3. comparação com seus critérios e gates;
4. revisão de escopo, regressões, rastreabilidade, dependências e segredos;
5. integração integral em `main` por PR validado;
6. confirmação pós-merge de que `main` contém o resultado aprovado;
7. confirmação de que a branch não possui conteúdo exclusivo e registro da branch para limpeza manual diferida conforme D-036;
8. encerramento sem pendências bloqueantes.

Quando todos esses gates forem satisfeitos, o avanço automático ao marco seguinte é autorizado conforme D-034, sem necessidade de nova aprovação humana.

A exclusão física das branches não bloqueia o avanço quando os controles de D-036 forem satisfeitos. Quando o humano solicitar exclusão manual, a automação não deve excluir a branch.

A lista acumulada de branches encerradas deve ser apresentada ao humano ao final para exclusão manual.

A execução deve interromper diante dos blockers reais definidos em D-034 ou em outra decisão normativa aplicável. Problemas técnicos ordinários e solucionáveis devem ser diagnosticados, corrigidos, revalidados e não constituem, por si só, motivo para solicitar aprovação humana.

Nenhum marco pode ser declarado concluído apenas para permitir avanço, e nenhum escopo do marco seguinte deve ser antecipado materialmente antes do encerramento do marco atual, salvo infraestrutura estritamente necessária e já permitida pela especificação.

<!-- M18_MULTI_AI_PROVIDER_ROUTING -->
## Análise semântica por IA, roteamento e telemetria — Multi-AI Provider Abstraction, Reliability Routing & Usage Telemetry
Implementar adapters provider-neutral para OpenAI/DeepSeek/MiMo, AUTO determinístico com quarantine e URL provider lock, telemetria persistida, catálogo versionado de preços e projeção operacional nos HTMLs. Preservar NoneProvider/OpenAI compatibility e invariantes de scoring. Testes externos usam mocks/fakes; live smoke é condicionado à presença de tokens.
