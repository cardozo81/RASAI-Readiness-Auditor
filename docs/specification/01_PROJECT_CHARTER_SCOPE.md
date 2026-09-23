# RASAi - Search & AI Readiness Auditor - visão e escopo do produto

**Estado:** APROVADO / VIGENTE  
**Fase do produto:** desenvolvimento e validação pré-publicação, com operação local e fundação SaaS disponíveis no código atual.

## 1. Visão do produto

O RASAi - Search & AI Readiness Auditor avalia a preparação de websites para mecanismos tradicionais de busca e sistemas generativos baseados em IA, preservando separação metodológica entre **readiness medido**, **desempenho/observabilidade externa** e **visibilidade observada**.

O produto transforma evidências técnicas, estruturais e semânticas em:

- findings verificáveis;
- scores por dimensão;
- **Search & AI Readiness Index - Índice de Prontidão Search & IA**, versão pública **001**, ID técnico `SARI-001`;
- **Método de Pontuação de Prontidão**, versão pública **001**, contrato técnico `SCORE-GEO-004`;
- resultados por contexto Desktop/Mobile quando esses contextos existem;
- riscos e oportunidades;
- recomendações e remediações priorizadas;
- relatórios HTML estáticos;
- comparações longitudinais e before/after;
- observabilidade externa separada do scoring, salvo contratos explicitamente score-eligible;
- Search Intelligence pontual e recorrente;
- superfícies locais, Web/API e de Product Platform.

O produto mede prioritariamente:

```text
READINESS
```

Ele **não garante**:

```text
RANKING
VISIBILITY
CITATION
CAUSALIDADE
```

Resultados externos observados podem ser armazenados e comparados, mas não são convertidos automaticamente em peso de `SARI-001`/`SCORE-GEO-004`. A única exceção externa vigente é `BR-GEO-060`, corroboração positiva Common Crawl definida por contrato específico.

## 2. Contexto operacional atual

O produto oferece operação local e fundação de plataforma/SaaS no mesmo domínio funcional.

### Operação local

- Windows/Python nativo continua suportado;
- console interativo e CLI continuam disponíveis;
- SQLite permanece o backend padrão do control plane local;
- `AUD-*/audit.db` permanece a evidência imutável da execução;
- Docker não é requisito para operação local SQLite;
- providers externos são opcionais e seguem BYOK/configuração explícita quando aplicável.

### Plataforma/SaaS

O código atual contém:

- Product Platform;
- hierarquia `Organization -> Workspace -> Project -> Property -> Environment`;
- users, memberships e RBAC;
- PostgreSQL 18 como backend explícito do control plane centralizado;
- Web API tenant-aware;
- SaaS Pilot Web;
- execution jobs e workers desacoplados;
- scheduling e run-due;
- Identity & Access OIDC/JWT, com modo default fail-closed;
- usage ledger e consumption analytics;
- Search Monitoring longitudinal;
- milestones, golden baselines e comparação before/after;
- Monitor, Observability, Quality e Fix Verification.

A existência dessas capacidades **não significa** que toda infraestrutura necessária a uma operação SaaS de produção esteja implantada. Object storage gerenciado, fila externa definitiva, deployment multi-região, gestor de segredos de produção, billing completo e demais componentes de operação em escala permanecem fora do contrato operacional atual.

## 3. Objetivos da auditoria

A auditoria deve responder, conforme aplicabilidade e evidência disponível:

1. o conteúdo pode ser descoberto e acessado?
2. as páginas estão tecnicamente aptas à indexação?
3. o conteúdo principal pode ser recuperado de forma confiável?
4. a página apresenta estrutura semântica adequada?
5. as entidades relevantes estão claras?
6. dados estruturados estão presentes e coerentes quando aplicáveis?
7. o conteúdo responde às intenções relevantes?
8. as informações possuem características favoráveis à recuperação e citação?
9. existem sinais adequados de evidência, autoria e confiabilidade?
10. existem diferenças materiais entre Desktop e Mobile, quando ambos os contextos foram coletados?
11. quais problemas devem ser tratados primeiro?
12. qual é a qualidade/cobertura da evidência que sustenta cada conclusão?

## 4. Princípios

### Evidência primeiro

Nenhum finding válido pode existir sem evidência rastreável.

### Determinismo primeiro

Condições objetivamente verificáveis devem ser resolvidas de forma determinística sempre que possível.

Exemplos:

- HTTP;
- redirects;
- canonical;
- robots;
- `noindex`;
- parsing JSON-LD;
- links;
- sitemap.

### IA para análise semântica

IA é opcional e usada para interpretação semântica ou remediação consultiva quando a execução correspondente estiver habilitada.

Exemplos:

- entidades;
- answerability;
- claims;
- intenção;
- contexto;
- evidência textual;
- análise competitiva vinculada a evidências.

IA não escolhe arbitrariamente o score oficial e não pode substituir evidência ausente por fatos inventados.

### Scoring explicável

Todo score deve ser reconstruível a partir de regras, contribuições e versões metodológicas persistidas.

### Contextos de dispositivo independentes

Desktop e Mobile são contextos independentes. Comparação Desktop x Mobile só é aplicável quando ambos existem; a ausência deliberada de um contexto não deve ser convertida automaticamente em falha do website.

### Separação entre readiness e resultados

Lighthouse, CrUX, Search Console, SERP Observation, Observed Generative Visibility e outros resultados externos mantêm proveniência/metodologia próprias. Sua existência não autoriza fusão automática com `SARI-001`/`SCORE-GEO-004`.

`BR-GEO-060` é exceção explícita e limitada: Common Crawl pode corroborar positivamente `DISCOVERY_ACCESS` quando a evidência qualifica, sem penalizar ausência ou erro.

### Imutabilidade da auditoria

`AUD-*/audit.db` e seus artefatos são evidência da execução. Estado mutável de produto, agendamento, identidade, consumo e monitoramento longitudinal pertence ao control plane separado.

## 5. Entrada e configuração da auditoria

Entradas mínimas dependem da superfície usada, mas podem incluir:

- domínio ou URL inicial;
- projeto/contexto de Product Platform;
- idioma;
- mercado;
- limite de páginas;
- contexto(s) de dispositivo;
- providers externos opcionais;
- controles de Web Performance, Apdex, IA e Search Intelligence quando deliberadamente habilitados.

### Limite de páginas

O estado do console mantém `max_pages = 100` como valor inicial do fluxo interativo, sujeito à configuração explícita da execução. Quando um documento publicar variáveis/limites operacionais, deve distinguir **default efetivo**, **valores permitidos** e **recomendado**.

Referência central: `../ENVIRONMENT_VARIABLES.md` e `../CONFIGURATION.md`.

Para credenciais e tokens externos, incluindo finalidade, dependências e links oficiais de criação, consultar `../EXTERNAL_CREDENTIALS.md`.

## 6. Descoberta e aquisição

A descoberta pode considerar:

- seed;
- links internos;
- sitemap;
- fontes adicionais explicitamente suportadas pelo runtime.

Para páginas e dispositivos aplicáveis, a aquisição pode preservar/derivar:

- HTTP;
- redirects;
- headers;
- HTML bruto, conforme contrato do módulo;
- DOM renderizado, conforme contrato do módulo;
- canonical;
- robots;
- title e description;
- headings;
- links;
- dados estruturados;
- conteúdo principal;
- artefatos e evidências necessários à reprodutibilidade.

## 7. Crawlers e acesso de agentes

O ruleset possui tratamento separado para crawlers/agentes configurados. O conjunto documentado inclui, entre outros:

- Googlebot;
- Googlebot Smartphone;
- Bingbot;
- OAI-SearchBot;
- GPTBot.

OAI-SearchBot e GPTBot não são equivalentes. Bloqueio de um crawler específico deve ser interpretado conforme finalidade, regra e aplicabilidade; não pode ser convertido automaticamente em penalidade genérica de Search readiness.

## 8. Arquiteturas web

O auditor deve tratar, sem penalização pelo framework em si:

- HTML tradicional;
- SSR;
- SSG;
- hydration;
- CSR;
- SPA;
- arquiteturas híbridas.

O que importa é o resultado observável e recuperável, não a tecnologia escolhida isoladamente.

## 9. IA e modos degradados

IA é opcional. O sistema deve continuar operacional sem provider de IA.

O contrato de avaliação semântica inclui baseline determinístico/local e providers externos opcionais. Ausência ou indisponibilidade do provider não é falha do website e não deve ser convertida automaticamente em `FAIL`.

Estados e nomenclaturas específicos são definidos nos contratos vigentes de IA/runtime, especialmente `18_AI_RUNTIME_ORCHESTRATION.md`, `20_AI_CONTENT_REMEDIATION.md` e documentação operacional correspondente.

## 10. Relatórios

O formato principal de publicação de auditoria é HTML estático em `report-catalog/`, com navegação canônica e superfícies estáveis definidas por `CATALOG-REPORT-002`.

Toda auditoria concluída com sucesso materializa as páginas canônicas registradas em `src/rasai/catalog_report_contract.py`. Quando o domínio correspondente não foi solicitado, não está configurado, não se aplica ou não possui dados, a página permanece presente e apresenta estado neutro explícito. A existência da superfície não dispara coleta adicional.

Características esperadas:

- estático e reprodutível a partir de dados persistidos sempre que o contrato permitir;
- responsivo;
- navegável;
- texto contextual em pt-BR;
- termos técnicos/identificadores preservados quando sua tradução comprometer o contrato;
- adequado a público técnico e executivo sem esconder limitações metodológicas;
- proveniência explícita de métricas externas;
- distinção clara entre página existente e capacidade efetivamente executada.

## 11. Dimensões de readiness

O modelo vigente mantém dimensões metodológicas próprias do `SCORE-GEO-004`. A definição normativa dos pesos, aplicabilidade, cobertura, confiança e consolidação pertence a `05_SCORING_MODEL.md` e à documentação canônica `../SCORE_GEO_004.md`.

Nenhuma lista resumida neste charter deve substituir o contrato de scoring versionado.

## 12. Capacidades adjacentes vigentes

Além da auditoria pontual, o produto possui capacidades independentes/aditivas, incluindo:

- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- Web Performance/Lighthouse/CrUX;
- Observed Generative Visibility;
- SERP Observation;
- Competitive Search & Content Intelligence;
- Competitive AI opcional;
- Search Intelligence History;
- Search Monitoring recorrente;
- Monitoring/Release Gate/Change Impact;
- Observability;
- Quality/Fix Verification/Evidence Timeline;
- Product Platform e relatórios de portfólio;
- Web API e SaaS Pilot Web;
- PostgreSQL control plane;
- Identity & Access.

Cada capacidade mantém seu próprio limite metodológico e de persistência conforme as respectivas especificações.

## 13. Fora do contrato atual de garantia

O RASAi não promete:

- alteração automática do website sem ação/autorização externa explícita;
- garantia de ranking;
- garantia de citação por mecanismos de IA;
- previsão causal privada de algoritmos de Search/IA;
- equivalência perfeita entre sintético e RUM;
- identidade comprovada de crawler baseada apenas em User-Agent;
- que persistir schedules em PostgreSQL torne a execução horizontal automaticamente segura;
- que a existência da fundação Web/SaaS represente uma infraestrutura SaaS de produção completa.

## 14. Testes e validação

Regressões automatizadas protegem contratos críticos, incluindo:

- parsing e Rules Engine;
- scoring e aplicabilidade;
- finding -> evidence;
- contexto de dispositivo;
- relatórios HTML;
- persistência/imutabilidade de `AUD-*`;
- Product Platform e tenant scope;
- PostgreSQL/SQLite parity nas superfícies cobertas;
- Search Intelligence;
- observabilidade/quality;
- Web/API e Identity & Access nas superfícies implementadas;
- segurança e ausência de segredos em artefatos públicos/persistidos.

Testes que exigiriam credenciais reais, quota externa ou crawling público devem usar fixtures/mocks no CI, deixando smoke ambiental explícito para cenários autorizados.

## 15. Critério de consistência do produto

Uma mudança é aceitável quando preserva, conforme aplicabilidade:

1. rastreabilidade da evidência;
2. imutabilidade do `AUD-*` como fonte de evidência;
3. reprodutibilidade do scoring versionado;
4. separação entre readiness e resultados externos, respeitando exceções explicitamente versionadas como `BR-GEO-060`;
5. isolamento de falhas de providers externos;
6. escopo/tenancy do control plane;
7. ausência de exposição de segredos;
8. documentação aderente ao runtime atual;
9. relatórios e CLI coerentes com os contratos persistidos;
10. operação local sem dependências SaaS obrigatórias.