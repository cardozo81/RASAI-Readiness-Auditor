# TECHNICAL_ARCHITECTURE.md

**Status:** APPROVED — Rastreamento, descoberta e acesso de crawlers + Synthetic Navigation Apdex + Acessibilidade automatizada e diagnósticos Web + Web Performance externo + Sugestões e remediação de conteúdo por IA + SGRI-001 + REPORT-SITE-GEO-001

## 1. Estilo arquitetural

Aplicação local, modular, CLI-first, single-machine no baseline.

Não exige:

- web server;
- database server;
- Docker;
- daemon/background worker;
- IA externa;
- PageSpeed Insights ou CrUX para a auditoria SearchGEO principal;
- `llms.txt`, IndexNow ou serviço externo de discovery para funcionar.

## 2. Runtime

- CPython 3.13.x;
- Playwright + Chromium;
- SQLite embarcado;
- filesystem local;
- HTTP/HTTPS para target;
- HTTPS para provider externo somente quando habilitado;
- HTTPS para PageSpeed/CrUX somente quando Web Performance externo external collection estiver habilitada;
- aquisição Rastreamento, descoberta e acesso de crawlers adicional limitada ao mesmo origin autorizado, atualmente `/llms.txt`, quando a origem estiver tecnicamente apta.

## 3. Pipeline

```text
CLI
→ configuração/contexto de dispositivo
→ instalação das extensões Rastreamento, descoberta e acesso de crawlers de discovery
→ discovery/acquisition
   → robots.txt
   → sitemap(s) same-origin permitidos
   → XML/urlset + sitemap index + gzip + RSS/Atom + texto plano
→ rendering
→ extraction/evidence
→ deterministic rules
→ semantic provider opcional (Análise semântica e fallback/Análise semântica por IA, roteamento e telemetria)
→ device comparison quando ambos existem
→ scoring (Scoring e confiabilidade)
→ prioritization/remediation base (Priorização e recomendações/Remediação por causa raiz e elemento/Precisão e consistência das recomendações)
→ Sugestões e remediação de conteúdo por IA opcional: sugestão textual evidence-bound + revisão JSON-LD determinística
→ Relatório HTML estático/Análise semântica por IA, roteamento e telemetria intermediate reporting
→ report-site base finalization
→ Sugestões e remediação de conteúdo por IA report projection/navigation enrichment
→ Web Performance externo optional external Web Performance execution
   → PageSpeed Insights/Lighthouse lab
   → CrUX field data quando disponível/configurado
   → persistence + raw JSON artifacts
→ Synthetic Navigation Apdex execution quando habilitado
→ rastreamento e descoberta execution
   → lê audit.db + artifacts já persistidos
   → diagnósticos determinísticos robots/sitemap/discovery
   → `/llms.txt` same-origin quando origem apta
   → IA técnica opcional/evidence-bound, default OFF
   → m24_* persistence + artifacts/m24/
→ Web Performance externo/Synthetic Navigation Apdex/external-integrity/source-quality report enrichments
→ SGRI/reporting final por domínio
→ Rastreamento, descoberta e acesso de crawlers report projection
   → crawling-discovery.html + ai-usage/references enrichment
→ nova projeção SGRI somente para incorporar o item Rastreamento, descoberta e acesso de crawlers à navegação final
→ normalização final dos rótulos compartilhados
```

A segunda projeção SGRI após Rastreamento, descoberta e acesso de crawlers é **projection-only**: não recalcula score nem métricas. Ela existe para que a página criada por Rastreamento, descoberta e acesso de crawlers participe do mesmo menu canônico e para preservar os rótulos finais de Mobile/Desktop definidos pelo domínio SGRI.

Invariantes:

- Sugestões e remediação de conteúdo por IA começa somente depois de scoring/findings/priorização concluídos e não altera os objetos já avaliados;
- Web Performance externo ocorre depois da auditoria principal e é fail-open;
- Web Performance externo não cria RuleExecution, Finding, Recommendation ou ScoreContribution;
- Web Performance externo não executa LLM;
- Synthetic Navigation Apdex é separado do scoring SearchGEO e não transforma Lighthouse/CrUX em Apdex;
- Rastreamento, descoberta e acesso de crawlers é pós-scoring, aditivo e `scoring_impact=NONE`;
- Rastreamento, descoberta e acesso de crawlers não cria nem altera RuleExecution, Finding GEO, Recommendation GEO, ScoreContribution, Coverage, Confidence, Consolidation, `SCORE-GEO-002` ou `SGRI-001`;
- Rastreamento, descoberta e acesso de crawlers AI, quando habilitada, explica somente diagnósticos já determinados e persistidos;
- as projeções HTML posteriores não fazem aquisição adicional nem chamada de provider;
- PageSpeed/CrUX, Synthetic Navigation Apdex ou Rastreamento, descoberta e acesso de crawlers indisponíveis não invalidam `SCORE-GEO-002`.

## 4. Device context

A CLI resolve exatamente um dos valores:

```text
mobile
desktop
both
```

Default de usuário:

```text
mobile
```

Precedência:

1. `--device-context`;
2. `SEARCHGEO_DEVICE_CONTEXT`;
3. `mobile`.

Renderização Desktop e Mobile renderiza somente o conjunto selecionado. Downstream trabalha sobre os snapshots realmente materializados. Nenhum provider semântico nem Sugestões e remediação de conteúdo por IA deve ser chamado para dispositivo não renderizado.

Web Performance externo também usa somente snapshots existentes:

```text
MOBILE  → PageSpeed strategy=mobile  → CrUX formFactor=PHONE
DESKTOP → PageSpeed strategy=desktop → CrUX formFactor=DESKTOP
```

Rastreamento, descoberta e acesso de crawlers cruza sitemaps/discovery apenas contra a amostra realmente auditada; ausência de URL fora da amostra não pode ser inferida como erro global.

Chamadas internas diretas a Renderização Desktop e Mobile sem variável preservam `both` para compatibilidade interna/testes.

## 5. Persistência

Workspace:

```text
<AUD-ID>/
├─ audit.db
├─ artifacts/
└─ report/
```

SQLite guarda entidades estruturadas; filesystem guarda payloads/artefatos grandes.

Sugestões e remediação de conteúdo por IA adiciona entidades reabríveis separadas:

```text
content_remediation_runs
content_remediation_suggestions
content_remediation_attempts
jsonld_remediation_suggestions
```

Web Performance externo adiciona entidades auxiliares separadas:

```text
web_performance_runs
web_performance_observations
web_performance_attempts
```

Rastreamento, descoberta e acesso de crawlers adiciona entidades auxiliares próprias:

```text
m24_runs
m24_diagnostics
m24_ai_results
```

Tabelas Sugestões e remediação de conteúdo por IA/Web Performance externo/Rastreamento, descoberta e acesso de crawlers não participam do denominador de scoring nem substituem as tabelas normativas de RuleExecution/Score. `m24_diagnostics.scoring_impact` permanece `NONE`.

## 6. Artifacts

Podem incluir:

- RAW HTTP/HTML;
- rendered HTML;
- conteúdo principal;
- structured data;
- screenshots;
- evidence materializada;
- respostas JSON PageSpeed/CrUX quando Web Performance externo executar coleta externa com sucesso;
- artifacts Rastreamento, descoberta e acesso de crawlers quando a aquisição correspondente ocorrer.

Os artifacts são referenciados por caminhos relativos ao workspace.

Sugestões e remediação de conteúdo por IA reutiliza artifacts persistidos e não refaz crawling/rendering.

Web Performance externo escreve respostas externas reabríveis em:

```text
artifacts/web-performance/
```

Rastreamento, descoberta e acesso de crawlers escreve artifacts próprios em:

```text
artifacts/m24/
```

Quando `/llms.txt` same-origin é obtido:

```text
artifacts/m24/llms.txt
```

Esses artifacts não contêm credenciais e são usados pela projeção sem nova chamada externa.

## 7. IA

`SemanticAnalysisProvider` é abstração independente de fornecedor.

Providers suportados na baseline operacional são definidos pelo registry. `NONE` continua válido; AUTO e providers explícitos respeitam a política Análise semântica por IA, roteamento e telemetria vigente.

Análise semântica por IA, roteamento e telemetria persiste sessão/tentativas da finalidade de análise semântica. IA não executa scoring.

Sugestões e remediação de conteúdo por IA, quando habilitado, cria uma sessão de remediação derivada dos providers Análise semântica por IA, roteamento e telemetria ainda saudáveis. Não existe credencial paralela; Sugestões e remediação de conteúdo por IA preserva quarantine anterior e mantém telemetria separada.

Web Performance externo não usa `SemanticAnalysisProvider` e não acrescenta consumo LLM.

Rastreamento, descoberta e acesso de crawlers possui uma finalidade técnica independente de Sugestões e remediação de conteúdo por IA:

```text
--ai-technical-remediation / --no-ai-technical-remediation
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Default OFF. O provider recebe somente diagnósticos/evidências Rastreamento, descoberta e acesso de crawlers persistidos. A saída é advisory, requer revisão humana e não pode decidir scoring, canonical preferencial sem evidência, política de treinamento/crawler ou fatos não observados.

## 8. Sugestões e remediação de conteúdo por IA

### 8.1 Texto

Input por snapshot/device:

```text
URL + title + conteúdo principal persistido
+ findings elegíveis
+ evidence IDs/observed values desses findings
```

Output validado:

```text
finding_id
objective
target_location
proposed_text
evidence_ids
confidence
review_note
```

Respostas que escapem do finding/evidence universe são rejeitadas. Tokens numéricos novos ausentes do corpus persistido também são rejeitados como contenção contra fabricação factual.

### 8.2 JSON-LD

A orientação JSON-LD é determinística e independente da ativação da chamada textual por IA.

Sem JSON-LD, o módulo pode produzir um baseline conservador `WebPage` com valores persistidos. Com JSON-LD, realiza revisão genérica não destrutiva e não substitui graphs existentes.

## 9. Web Performance externo — External Web Performance Evidence

### 9.1 Ativação

Coleta externa é `false` por padrão. Os controles públicos incluem:

```text
--web-performance / --no-web-performance
--web-performance-max-pages
--web-performance-timeout-seconds
--web-performance-field-source auto|pagespeed|crux|none
--lighthouse-categories
```

Com Web Performance externo desligado, auditorias reais podem materializar estado `DISABLED` e a página explicativa, mas não fazem requisição PageSpeed/CrUX.

### 9.2 PageSpeed Insights

Uma chamada por snapshot/dispositivo selecionado solicita as categorias configuradas. Persistem-se somente valores efetivamente retornados, incluindo versão/fetch time Lighthouse e métricas de laboratório relevantes.

### 9.3 Core Web Vitals / CrUX

Política default `auto`:

1. usar field data CrUX devolvido pelo PageSpeed quando utilizável;
2. se ausente e existir `SEARCHGEO_CRUX_API_KEY`, consultar CrUX API direta;
3. sem dados suficientes, manter `INCOMPLETE`/`UNAVAILABLE` sem website finding.

`pagespeed`, `crux` e `none` permitem controlar explicitamente a fonte/ausência de field data.

### 9.4 Credenciais e consumo

Credenciais isoladas:

```text
SEARCHGEO_PAGESPEED_API_KEY
SEARCHGEO_CRUX_API_KEY
```

Elas nunca substituem credenciais de IA.

`--web-performance-max-pages` limita logical pages externas; `0` significa todas. Em `both`, cada página pode produzir dois contextos PageSpeed. Timeout não gera retry automático.

### 9.5 Falha

Após `run_audit` concluir, Web Performance externo é enrichment. Falha inesperada deve ser registrada/logada como problema operacional de coleta e não destruir o resultado principal já produzido.

## 10. Rastreamento, descoberta e acesso de crawlers — Crawling, Discovery & AI Access

### 10.1 Discovery extensions

Rastreamento, descoberta e acesso de crawlers instala extensões determinísticas sobre `DiscoveryEngine` antes da auditoria CLI. O contrato acrescenta interpretação de sitemap sem substituir a proveniência Descoberta e aquisição HTTP existente.

Formatos aceitos pelo runtime Rastreamento, descoberta e acesso de crawlers:

```text
XML urlset
XML sitemapindex
gzip
RSS 2.0
Atom 1.0
text/plain sitemap
```

Para `urlset`, apenas `<url><loc>` representa URL de página; `<loc>` de extensões de imagem/vídeo não deve ser promovido a página.

### 10.2 robots e sitemap externo

Declarações `Sitemap:` absolutas são preservadas mesmo quando externas ao origin auditado. O runtime não as segue automaticamente quando cross-origin.

Essa fronteira evita expansão de escopo/SSRF e não significa que sitemap externo seja inválido. Qualquer evolução para fetch externo requer política própria de validação DNS/IP/redirect/autorização.

### 10.3 llms.txt

Rastreamento, descoberta e acesso de crawlers pode adquirir somente:

```text
<origin>/llms.txt
```

Ausência, 404/410 ou indisponibilidade não reduzem score. O arquivo é tratado como proposta comunitária experimental, não web standard nem requisito de Search/GEO.

Hard source blocker confirmado impede essa aquisição adicional.

### 10.4 IA técnica

Quando explicitamente habilitada, a IA recebe somente o universo persistido Rastreamento, descoberta e acesso de crawlers e não pode inventar URL/policy/canonical/data/crawler token. O resultado é persistido antes da projeção HTML.

Sem provider apto, Rastreamento, descoberta e acesso de crawlers permanece determinístico e a finalidade AI fica `NOT_CONFIGURED`/indisponível sem finding do website.

### 10.5 Falha

Rastreamento, descoberta e acesso de crawlers é fail-open. Falha operacional do enrichment/report deve ser registrada sem invalidar a auditoria SearchGEO já concluída.

## 11. Scoring

`SCORE-GEO-002` é determinístico sobre RuleExecutions persistidas.

A camada de scoring não deve reexecutar website ou IA.

Sugestões e remediação de conteúdo por IA é estritamente downstream e não pode invalidar ou recalcular scoring já concluído.

Web Performance externo também é estritamente externo ao scoring. Nenhum Lighthouse score, LCP/INP/CLS, PageSpeed category score ou estado CWV é automaticamente convertido em peso, RuleResult, ScoreContribution, Coverage, Confidence ou Overall Readiness.

Synthetic Navigation Apdex e Rastreamento, descoberta e acesso de crawlers permanecem igualmente separados do scoring. Diagnósticos de crawling/discovery Rastreamento, descoberta e acesso de crawlers não criam contribuição implícita para `SCORE-GEO-002` ou `SGRI-001`.

## 12. Reporting interno

Relatório HTML estático/Experiência e organização dos relatórios/Remediação por causa raiz e elemento/Precisão e consistência das recomendações/Análise semântica por IA, roteamento e telemetria preservam seus contratos intermediários para compatibilidade de testes/módulos.

Durante `run_audit`, esses HTMLs intermediários não são o contrato final do usuário.

## 13. Report site final

O contrato final pode materializar:

```text
report/
├─ index.html
├─ searchgeo.html
├─ mobile.html                 # condicional
├─ desktop.html                # condicional
├─ remediation.html
├─ content-suggestions.html
├─ crawling-discovery.html     # Rastreamento, descoberta e acesso de crawlers
├─ accessibility.html          # quando materializado
├─ web-performance.html
├─ apdex.html                  # quando habilitado/materializado
├─ ai-usage.html
├─ references.html
└─ css/
   └─ site.css
```

`report/index.html` permanece ponto de entrada do workspace.

`m20_reporting` projeta `content-suggestions.html` sem chamar provider.

`m21_reporting` projeta `web-performance.html` sem reexecutar PageSpeed/CrUX.

`searchgeo_readiness_reporting` projeta `searchgeo.html`/dashboard sem recalcular score.

`m24_reporting` projeta `crawling-discovery.html`, complementa `ai-usage.html`/`references.html` e normaliza a navegação usando apenas estado Rastreamento, descoberta e acesso de crawlers já persistido; o renderer não chama provider nem faz aquisição de website.

Após Rastreamento, descoberta e acesso de crawlers criar seu arquivo, `enrich_searchgeo_reporting` pode ser executado novamente somente como projeção idempotente para que todos os HTMLs compartilhem o menu/rótulos finais. As medições persistidas não são modificadas.

## 14. Separação de domínio na apresentação

- `index.html`: visão executiva e links para páginas canônicas;
- `searchgeo.html`: `SGRI-001`, dimensões, Coverage, Confidence e Consolidation;
- `mobile.html`: evidência/findings Mobile;
- `desktop.html`: evidência/findings Desktop;
- `remediation.html`: causa/prioridade/correção;
- `content-suggestions.html`: texto opcional e JSON-LD advisory;
- `crawling-discovery.html`: robots, crawler policies, sitemaps, discovery, `llms.txt`, feeds, IndexNow e orientação técnica Rastreamento, descoberta e acesso de crawlers;
- `web-performance.html`: Lighthouse lab, CrUX/Core Web Vitals e telemetria externa;
- `apdex.html`: Synthetic Navigation Apdex;
- `ai-usage.html`: operação/telemetria de IA separada por finalidade;
- `references.html`: fontes externas, metodologia e decisões internas claramente separadas.

Essa separação impede confundir falha de provider/medição ou diagnóstico Rastreamento, descoberta e acesso de crawlers com score do website.

## 15. CSS

Todas as páginas finais referenciam:

```text
report/css/site.css
```

CSS inline/embutido não pertence ao contrato final do report site.

## 16. Segurança

Secrets nunca devem ser persistidos em:

- audit.db como valor de credencial;
- artifacts;
- report site;
- logging operacional.

Payload estruturado exibido deve passar por escaping/redaction apropriado.

Sugestões e remediação de conteúdo por IA não persiste headers de autenticação nem bodies de erro de provider não sanitizados.

Web Performance externo não persiste API keys, URL de requisição contendo `key=`, headers de autenticação ou corpo de erro externo não sanitizado.

Rastreamento, descoberta e acesso de crawlers não segue automaticamente sitemap cross-origin declarado e não persiste credenciais. A aquisição adicional `/llms.txt` é same-origin e é suprimida quando há hard source blocker confirmado.

## 17. Fonte de verdade

```text
audit.db + artifacts
```

HTML é projeção. Report generation não pode recalcular Score/Finding nem chamar provider externo.

Sugestões e remediação de conteúdo por IA external calls, quando habilitadas, ocorrem antes da projeção correspondente e persistem o resultado.

Web Performance externo external calls, quando habilitadas, ocorrem como enrichment após a auditoria principal; sua projeção lê o estado persistido.

Rastreamento, descoberta e acesso de crawlers acquisition/AI opcional ocorre no estágio de execution Rastreamento, descoberta e acesso de crawlers, depois da execução Web Performance externo/Synthetic Navigation Apdex e antes das projeções finais; depois de persistido `m24_*`/artifacts, `crawling-discovery.html` é reabrível sem nova chamada.

## 18. Reprodutibilidade

Versionar:

- auditor;
- ruleset;
- rendering policy;
- prompt/contract semântico quando aplicável;
- contrato Sugestões e remediação de conteúdo por IA;
- contrato Web Performance externo e interpretação de field/lab data;
- contrato Synthetic Navigation Apdex/Apdex;
- contrato Rastreamento, descoberta e acesso de crawlers e sua política de aquisição/IA;
- scoring;
- prioritization;
- reporting contract.
