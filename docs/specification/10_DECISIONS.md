# DECISIONS.md

**Estado no baseline de desenvolvimento:** CURRENT

## DECIDED

### D-001
Desktop e Mobile serão avaliados separadamente.

### D-002
Relatório oficial será HTML estruturado e profissional.

### D-003
Testes mínimos orientados a risco.

### D-004
Decisão original: GitHub somente após baseline local estável.

Status: **SUPERSEDED por D-032**.

### D-005
Uma máquina e um operador humano no MVP.

### D-006
Arquitetura distribuída não é requisito inicial.

### D-007
Multiusuário não é requisito inicial.

### D-008
As 10 dimensões permanecem no MVP.

### D-009
Existirá Overall Readiness separado para Desktop e Mobile, somente quando consolidável.

### D-010
`max_pages` padrão = 100, configurável.

### D-011
Intent analysis entra no MVP de forma controlada: 1 primary + até 5 secondary intents.

### D-012
Benchmark de concorrentes fica para V1.

### D-013
Interface inicial será CLI, não aplicação web.

### D-014
Rendering baseline será Playwright + Chromium.

### D-015
Organização conceitual/física: Audit → Page → Device Context. Dados estruturados em SQLite embarcado; artefatos grandes em filesystem.

### D-016
Nenhum database server ou serviço externo de banco será obrigatório.

### D-017
IA é opcional. Auditor deve funcionar sem provider.

### D-018
Resultados relevantes devem informar Coverage, Confidence e Consolidation Status.

### D-019
Ausência de IA nunca representa baixa qualidade do website.

### D-020
Camada semântica será independente de fornecedor/modelo.

### D-021
MVP implementará NoneProvider e pelo menos um provider real; baseline real inicial: OpenAI.

### D-022
Score oficial deve conter Value, Coverage, Confidence e Consolidation.

### D-023
Ausência de IA reduz cobertura/consolidação, nunca score do website diretamente.

### D-024
Pesos iguais entre dimensões no MVP.

### D-025
Scoring groups impedem dupla penalização de causa correlacionada.

### D-026
Na máquina de desenvolvimento/MVP, uso de API externa de IA é permitido.

### D-027
OpenAI é o provider inicial previsto para o MVP, sem dependência arquitetural.

### D-030
Relatório destinado ao usuário será prioritariamente em português.

### D-031
Termos técnicos oficiais podem permanecer em inglês quando tradução reduzir precisão; glossário/contexto são obrigatórios.

### D-032
Git/GitHub são adotados a partir do Bootstrap e fundação do projeto como controle de versão e repositório de desenvolvimento.

Essa adoção não altera o requisito de execução local e não torna GitHub dependência de runtime do produto.

### D-033
Quando um escopo ou alteração implementada em branch estiver encerrado, validado e aprovado para integração, todo o conteúdo validado deve ser integrado em `main`.

Após o merge, deve-se confirmar que `main` contém integralmente o resultado aprovado e que a branch de trabalho não possui conteúdo exclusivo pendente.

A regra anterior de contingência que permitia manter branch sincronizada com `main` quando a ferramenta não pudesse removê-la foi **SUPERSEDED por D-035**.

### D-034
Após um marco ser implementado, validado, comparado com seus critérios, integrado integralmente em `main` e encerrado sem pendências bloqueantes, fica autorizado o avanço automático ao marco seguinte previsto em `09_IMPLEMENTATION_PLAN.md`, sem necessidade de nova aprovação humana.

Cada marco continua sendo unidade independente de implementação, validação, branch, PR, merge e encerramento.

O avanço automático deve interromper somente diante de conflito normativo não solucionável pela precedência documental, impossibilidade técnica relevante, alteração material de escopo ou comportamento funcional, falha persistente de validação obrigatória, necessidade de credencial/segredo indisponível, ação externa indispensável que a ferramenta não possa executar, impacto de política corporativa ou outra decisão/ação que dependa necessariamente de humano.

Problemas técnicos ordinários e solucionáveis não constituem motivo para solicitar aprovação humana. A execução deve diagnosticar, corrigir, revalidar e continuar automaticamente quando possível.

Nenhum marco pode ser considerado concluído apenas para permitir avanço. Todos os respectivos critérios e gates obrigatórios permanecem válidos.

### D-035
Status: **SUPERSEDED parcialmente por D-036 quanto ao momento da exclusão física e ao caráter bloqueante da limpeza de branch durante a cascata.**

Toda branch criada especificamente para implementação de um marco ou alteração de governança é temporária.

Após o merge em `main`, é obrigatório:

1. confirmar que o merge foi concluído;
2. confirmar que `main` contém integralmente todo o conteúdo aprovado;
3. comparar a branch com `main`;
4. confirmar que a branch não contém commits, arquivos ou alterações exclusivas pendentes;
5. excluir a branch remota do GitHub;
6. quando aplicável, excluir também a branch local;
7. somente então considerar concluída a limpeza Git do marco ou alteração de governança.

Uma branch já integrada em `main` não deve permanecer existente apenas por estar sincronizada. O estado `identical / 0 ahead / 0 behind` comprova que a exclusão é segura, mas não constitui estado final aceitável.

Sincronizar a branch com `main` após o merge não substitui sua exclusão.

Se a ferramenta utilizada não permitir excluir a branch remota, deve-se registrar explicitamente a limitação e informar a ação manual necessária. Enquanto a branch permanecer existente, a limpeza Git fica pendente e o ciclo Git não pode ser apresentado como completamente encerrado.

A pendência de limpeza não invalida o código já integrado em `main`. Porém, quando a conclusão integral do marco ou da alteração de governança for gate para avanço em cascata, aplica-se D-036.

Nenhuma branch de trabalho encerrado deve permanecer no repositório, salvo exceção futura explicitamente justificada e documentada.

### D-036
Para a execução automática sequencial Extração e evidências → Testes críticos e baseline local estável, a exclusão física das branches remotas encerradas fica diferida para uma rotina manual única ao final da cascata.

A exclusão de branch deixa de ser blocker entre marcos, desde que, após cada merge:

1. `main` contenha integralmente o conteúdo aprovado;
2. a branch seja comparada com `main`;
3. fique comprovado que a branch não possui commits, arquivos ou alterações exclusivas pendentes;
4. a branch seja registrada em uma lista acumulada de exclusão manual.

Branches registradas nessa lista não podem ser reutilizadas para novos marcos nem receber novos commits após o encerramento correspondente.

Ao final da cascata, deve ser apresentada ao humano a lista completa das branches remotas que podem e devem ser excluídas manualmente. A limpeza física continua obrigatória como housekeeping do repositório, mas sua execução diferida não bloqueia o avanço Extração e evidências → Testes críticos e baseline local estável nem invalida o encerramento funcional de cada marco.

A mesma regra de limpeza diferida aplica-se às branches de governança criadas especificamente para viabilizar esta cascata.

### D-037 - Aplicabilidade de dimensões no SARI

As dez dimensões permanecem no modelo, preservando D-008. Uma dimensão cujas RuleExecutions existam e estejam **todas legitimamente `NOT_APPLICABLE`** não pode ser tratada como `NOT_CONSOLIDATED` nem bloquear o Overall.

Regra aprovada:

1. ausência completa de RuleExecutions continua `NOT_CONSOLIDATED`;
2. `NOT_APPLICABLE` provocado apenas por pré-requisito bloqueado continua `NOT_CONSOLIDATED`;
3. dimensão integralmente e legitimamente `NOT_APPLICABLE` recebe estado de consolidação `NOT_APPLICABLE`;
4. dimensão `NOT_APPLICABLE` não recebe score 0 nem 100;
5. dimensão `NOT_APPLICABLE` é excluída do denominador do Overall e de sua Coverage;
6. todas as dimensões aplicáveis restantes precisam estar suficientemente consolidadas para existir Overall;
7. a exclusão deve ser persistida/rastreável como `DIMENSION_NOT_APPLICABLE:<DIMENSION>`;
8. se um tópico opcional passar a existir - por exemplo JSON-LD - suas regras passam a ser aplicáveis e seus resultados entram normalmente no score.

JSON-LD/Structured Data é classificado como **OPCIONAL / REFORÇO**, não como requisito universal para GEO funcional. Sua ausência legítima, isoladamente, não é FAIL nem impedimento para Readiness Search & AI mensurável. Quando presente, deve ser interpretável e coerente com o conteúdo visível; markup inválido ou contraditório pode reduzir o score.

**Refinamento vigente no SCORE-GEO-004:** a ausência de JSON-LD é materializada por `BR-GEO-034` como `WARNING` de baixo impacto (fator 0,80) para tornar a lacuna visível e comparável; `BR-GEO-035..037` permanecem `NOT_APPLICABLE` enquanto não houver JSON-LD. Isso não transforma JSON-LD em requisito universal nem converte ausência em `FAIL`.

O foco primário desta classificação é Google Search e seus recursos de IA. Outros mecanismos podem ser documentados como sinais complementares sem alterar a regra de scoring.

### D-038 - Web Performance externo e separação metodológica

Core Web Vitals/CrUX e Lighthouse entram como **evidência externa complementar** e não como substituição ou calibração implícita do `SARI-001`/`SCORE-GEO-003`.

Decisão aprovada:

1. `SARI-001` é o índice de Readiness e `SCORE-GEO-003` é o método de scoring aplicado;
2. Lighthouse Performance, Accessibility, Best Practices e SEO permanecem scores do Lighthouse e devem ser rotulados como tais;
3. LCP, INP e CLS de CrUX representam experiência real agregada quando houver amostra suficiente e não constituem automaticamente RuleExecution/ScoreContribution do RASAi;
4. ausência/erro de PageSpeed ou CrUX é limitação de coleta, nunca website FAIL por si só;
5. coleta externa Web Performance externo é default OFF, com limite de páginas e timeout parametrizáveis;
6. Web Performance externo adiciona zero chamadas LLM e não pode aumentar consumo OpenAI/DeepSeek/MiMo por efeito colateral;
7. PageSpeed/CrUX possuem credenciais isoladas e opcionais conforme o serviço;
8. Web Performance externo é enrichment pós-auditoria e fail-open em relação ao resultado principal;
9. resultados Web Performance externo são persistidos em tabelas/artifacts auxiliares e apresentados em `report/web-performance.html`;
10. qualquer futura incorporação de métrica Web Performance externo ao scoring exigirá decisão humana explícita, novo contrato/versionamento de scoring, documentação de fundamento e regressão comparativa; não pode ocorrer silenciosamente.

D-038 complementa D-037; não a supersede.

### D-039 - Rastreamento, descoberta e acesso de crawlers Crawling/Discovery, políticas de crawler e IA técnica

Rastreamento, descoberta e acesso de crawlers é aprovado como domínio técnico **aditivo, pós-scoring e não-scoring**. Ele aprofunda evidências de rastreamento/descoberta sem criar um novo índice nem recalibrar `SARI-001`/`SCORE-GEO-003`.

Decisão aprovada:

1. diagnósticos determinísticos de rastreamento e descoberta permanecem advisory e persistidos com `scoring_impact=NONE`; avaliações técnicas evidence-bound explicitamente habilitadas podem materializar somente BR-GEO-055/056 bounded, registrando `BOUNDED_AI_RESOURCE_ASSESSMENT` no run sem criar peso adicional;
2. `robots.txt` e sitemaps devem seguir standards/guidance públicos aplicáveis, mas severidades Rastreamento, descoberta e acesso de crawlers continuam metodologia interna do RASAi;
3. uma declaração absoluta `Sitemap:` pode apontar para host diferente; o auditor preserva essa declaração, porém não faz fetch cross-origin automático a partir dela enquanto não existir política explícita de SSRF/DNS/IP/redirect/autorização;
4. a restrição de fetch cross-origin é limite de segurança/escopo do auditor e não finding do website;
5. OAI-SearchBot representa descoberta/surfacing para Search da OpenAI; GPTBot permanece controle relacionado a potencial treinamento. O estado de um não pode ser inferido a partir do outro;
6. Google-Extended é token de produto em `robots.txt`, não user-agent HTTP Search independente, e não afeta inclusão/ranking na Pesquisa Google conforme documentação pública do Google;
7. `llms.txt` permanece proposta comunitária experimental: ausência, erro ou não adoção não reduz score/readiness e o arquivo não substitui robots, sitemap, canonical, HTML semântico ou conteúdo acessível;
8. IndexNow não pode ser declarado configurado/bem-sucedido por auditoria passiva sem evidência explícita, log ou artifact verificável; na ausência disso, o estado é não determinável;
9. remediação técnica Rastreamento, descoberta e acesso de crawlers por IA é default OFF, evidence-bound, advisory e exige revisão humana;
10. IA Rastreamento, descoberta e acesso de crawlers não pode inventar URLs/policies/canonicals/datas/tokens, decidir unilateralmente política de treinamento/crawler nem alterar RuleExecution, Finding GEO, Recommendation GEO, Score, Coverage, Confidence ou Consolidation;
11. hard source blocker confirmado impede aquisição adicional `/llms.txt` e chamada técnica de IA dependente do corpus;
12. `report/crawling-discovery.html` é a página canônica desse domínio e deve usar navegação/CSS compartilhados;
13. qualquer futura incorporação de diagnóstico Rastreamento, descoberta e acesso de crawlers ao scoring exige decisão explícita, novo versionamento e regressão comparativa; não pode ocorrer implicitamente.

D-039 complementa D-037/D-038; não as supersede.

### D-040 - Observed Generative Visibility separado de readiness

Outcomes observados de Search/AI Search são aprovados como domínio **aditivo, import-first e não-scoring**, separado do `SARI-001` e sem alterar `SCORE-GEO-003`.

Decisão aprovada:

1. `Readiness` e `Observed Generative Visibility` são conceitos distintos e não podem ser fundidos em um score comum sem nova decisão/versionamento/validação;
2. Observed Generative Visibility inicia com contrato local versionado `OGV-IMPORT-001`, sem scraping de portal de webmaster e sem endpoint de API presumido ou não documentado;
3. `BING_WEBMASTER_TOOLS_AI_PERFORMANCE` preserva Total Citations e Average Cited Pages como métricas reportadas pela fonte; o RASAi não inventa fórmula equivalente para recalculá-las;
4. `CONTROLLED_QUERY_RUNS` pode produzir Citation Presence Rate somente sobre runs `VALID`, com runs `INVALID` fora do denominador;
5. Citation Presence Rate deve ser acompanhado de tamanho amostral e intervalo Wilson 95% quando calculável; isso mede incerteza amostral e não é probabilidade preditiva de citação futura;
6. contagem de citações não pode ser rotulada como ranking, autoridade ou preferência universal de engine;
7. toda URL Observed Generative Visibility deve pertencer ao `normalized_origin` da auditoria; dados cross-origin são rejeitados;
8. o artifact importado deve ser preservado com SHA-256 e reimportação do mesmo conteúdo deve ser idempotente;
9. `report/ai-visibility.html` é a página canônica do domínio Observed Generative Visibility;
10. Observed Generative Visibility não escreve nem recalcula `Score`, `Coverage`, `Confidence`, `Consolidation`, `RuleExecution`, `Finding` ou `Recommendation`;
11. correlação/calibração futura entre SARI e outcomes Observed Generative Visibility exige dataset longitudinal, separação por domínio entre treino/calibração/teste e validação fora da amostra antes de qualquer claim preditivo;
12. adapters automáticos para plataformas externas só podem ser introduzidos quando houver contrato público/documentado e política de credenciais/segurança correspondente.

D-040 complementa D-037/D-038/D-039; não as supersede.

## PENDING ENVIRONMENT VALIDATION

### D-028
Verificar acesso técnico à API OpenAI na máquina/rede corporativa.

Validar:

- DNS;
- TLS;
- proxy;
- firewall;
- endpoint API;
- authentication;
- timeout;
- políticas de saída.

Acessibilidade técnica não significa autorização corporativa.

## PENDING CORPORATE VALIDATION

### D-029
Identificar provider de IA permitido/preferido corporativamente.

Possibilidades arquiteturais:

- OpenAI;
- Azure OpenAI;
- Google;
- Anthropic;
- AWS Bedrock;
- modelo local;
- nenhum.

Também validar corporativamente:

- autorização para envio de conteúdo a IA externa;
- execução de Chromium/browser;
- executável portátil;
- escrita em filesystem;
- SQLite embarcado;
- antivírus/EDR;
- políticas de execução.

Essas pendências não bloqueiam desenvolvimento local do MVP.

## Restrições aprovadas adicionais

- aplicação local Windows;
- não web;
- sem Docker obrigatório;
- sem admin como objetivo de distribuição;
- relatório estático;
- SQLite não é considerado dependência de database server;
- RAW + RENDERED sempre preservados no baseline;
- arquitetura do site não gera penalidade por si só;
- `llms.txt` não impacta score automaticamente;
- GPTBot e OAI-SearchBot possuem papéis distintos;
- Google-Extended não é crawler Search independente e não afeta ranking/inclusão da Pesquisa Google;
- sitemap externo declarado não é seguido automaticamente pelo Rastreamento, descoberta e acesso de crawlers enquanto não houver política segura de aquisição cross-origin;
- findings devem ser evidence-backed;
- LLM nunca é scoring engine;
- cascading failures devem ser controladas;
- métricas PageSpeed/CrUX/Lighthouse não alteram `SARI-001`/`SCORE-GEO-004` sem decisão e contrato metodológico explícitos;
- diagnósticos de rastreamento e descoberta também não alteram `SARI-001`/`SCORE-GEO-004` sem decisão e contrato metodológico explícitos;
- outcomes Observed Generative Visibility não alteram `SARI-001`/`SCORE-GEO-004` e não podem ser apresentados como causalidade/predição sem validação empírica específica.

### D-041 - Linguagem pública por domínio funcional

A documentação de produto, o console e os relatórios destinados ao usuário devem nomear capacidades pelo domínio funcional, não por identificadores históricos de etapas de entrega. Termos técnicos na apresentação só são admitidos quando documentados por fonte pública reconhecida e difundidos no domínio; vocabulário de código/runtime deve ficar oculto da leitura principal. O público-alvo primário é o analista de dados/SEO.

### D-042 - SCORE-GEO-004 e contrato público estável

Esta decisão registra a evolução metodológica posterior às D-038, D-039 e D-040 sem reescrever retroativamente o contexto em que elas foram aprovadas.

1. `SCORE-GEO-004` substitui `SCORE-GEO-003` como **runtime de scoring vigente** para novas auditorias.
2. O Overall do `SCORE-GEO-004` é determinístico e não depende de model artifact, dataset de calibração ou fitting externo para existir.
3. As decisões anteriores de separação metodológica entre Readiness, Web Performance, Acessibilidade, crawling/discovery e outcomes observacionais continuam válidas.
4. D-038, D-039, D-040 e decisões correlatas são superseded **somente quanto à referência à versão vigente do scoring**; seu conteúdo histórico e suas fronteiras de domínio permanecem preservados.
5. Auditorias históricas continuam imutáveis e são abertas/comparadas pela respectiva `scoring_version`; o report não converte silenciosamente 002/003 para 004.
6. Nenhuma série histórica pode misturar `SCORE-GEO-002`, `SCORE-GEO-003` e `SCORE-GEO-004` como se fossem a mesma metodologia. Pares incompatíveis devem ser `NOT_COMPARABLE` para métricas de score.
7. A superfície pública canônica da metodologia passa a ser `report/scoring.html`, independente da versão. `report/score-geo-004.html` é somente alias de compatibilidade quando o AUD efetivamente usa 004 e não é item de navegação.
8. A identidade pública do índice permanece `SARI-001`.
9. Versão do produto, `ruleset_version`, `sari_version`, `scoring_version`, `report_contract_version` e `observability_contract_version` são eixos distintos e não devem ser colapsados em uma única versão.

D-042 não autoriza recalcular auditorias históricas nem alterar evidência persistida.

