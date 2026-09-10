# DECISIONS.md

**Contrato vigente:** VIGENTE

Este documento registra somente decisões atualmente válidas para o produto. Decisões abandonadas, etapas de implementação concluídas e regras transitórias de branch/merge não integram a especificação normativa.

## D-001 - Readiness por dispositivo

Desktop e Mobile são contextos independentes. Scores, Coverage, Confidence e Consolidation são calculados e apresentados por dispositivo. Um contexto não executado não pode ser apresentado como defeito do website.

## D-002 - Índice e scoring

O índice público é `SARI-001` e o método de scoring vigente é `SCORE-GEO-004`.

O scoring é determinístico, evidence-bound e usa as **11 dimensões** definidas pelo contrato atual, incluindo `CONTENT_VALUE`. IA não escolhe pesos nem calcula unilateralmente o score. Coverage e Confidence não substituem Score.

Dimensões integralmente e legitimamente `NOT_APPLICABLE` são excluídas do denominador aplicável e não recebem score artificial 0 ou 100. Ausência de evidência suficiente não é convertida em falha.

JSON-LD permanece `OPCIONAL / REFORÇO`. O contrato distingue a **observação persistida pela regra** da **interpretação efetiva do scoring**: quando `BR-GEO-034` registra explicitamente que Structured Data está ausente, o `SCORE-GEO-004` aplica sua política versionada de aplicabilidade e trata essa execução como `NOT_APPLICABLE` para scoring, com `reason=STRUCTURED_DATA_ABSENT_NOT_UNIVERSAL_SARI_REQUIREMENT`, preservando o resultado-fonte no estado observado. `BR-GEO-035..037` também permanecem `NOT_APPLICABLE` quando não existe Structured Data a avaliar. Assim, ausência legítima de JSON-LD não reduz o SARI, não recebe score artificial e não é apresentada como requisito universal.

## D-003 - Evidência de auditoria imutável

Cada `AUD-*` preserva `audit.db`, artifacts e relatórios como evidência reabrível da execução. Estado de produto, tenancy, schedules, milestones, usage, integrações e dados longitudinais pertencem ao control plane e não são gravados retroativamente em `AUD-*/audit.db`.

## D-004 - Persistência do control plane

SQLite é suportado para operação local de autoridade única. PostgreSQL é o backend centralizado do control plane para execução hospedada e cenários que exigem concorrência e autoridade compartilhada.

Quando PostgreSQL estiver explicitamente selecionado, falha de conexão/configuração não provoca fallback silencioso para SQLite.

## D-005 - Hierarquia de produto

A hierarquia canônica é:

```text
Organization
  -> Workspace
      -> Project
          -> Property
              -> Environment
```

Usuários e memberships/RBAC são avaliados dentro dessa hierarquia. Um projeto pode possuir múltiplas propriedades/domínios e uma auditoria pode abranger múltiplas propriedades quando seu escopo persistido assim determinar.

## D-006 - Web/API e workers

A Web API e o SaaS Pilot Web são superfícies do mesmo domínio de produto e não mantêm uma segunda regra de negócio ou uma segunda persistência.

Execuções potencialmente longas, crawling, Search Monitoring e integrações não devem bloquear o processo HTTP. O control plane cria/coordena jobs e workers desacoplados realizam o trabalho autorizado.

## D-007 - Identity & Access

OIDC/JWT é a direção de autenticação do produto hospedado. Identidade autenticada resolve para um `Principal`/usuário interno; autorização continua baseada em memberships e escopo de tenant.

Autenticação válida não cria membership automaticamente. Secrets, access tokens, ID tokens e refresh tokens não são persistidos como metadados ordinários do control plane.

## D-008 - IA opcional e provider-neutral

O auditor deve funcionar sem provider de IA. Integrações de IA são provider-neutral no domínio e provider-specific apenas nos adapters.

Saídas de IA relevantes ao audit devem ser validadas contra schema e `evidence_ids`. Indisponibilidade de provider não constitui baixa qualidade do website.

Remediação textual e técnica por IA são opt-in, evidence-bound, advisory e não podem alterar retrospectivamente RuleExecution, Finding, Recommendation, Score, Coverage, Confidence ou Consolidation já persistidos.

## D-009 - Web Performance externo

Web Performance é enriquecimento externo e fail-open em relação ao audit principal.

O default Lighthouse solicitado pelo RASAi contém:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

Performance, Accessibility, Best Practices e SEO são categorias Lighthouse externas. Agentic Browsing é tratado como categoria experimental e contexto adicional. Sua ausência isolada não invalida uma coleta estável e seu score não entra automaticamente em `SARI-001`/`SCORE-GEO-004`.

Core Web Vitals de campo e métricas Lighthouse de laboratório permanecem semanticamente separados.

## D-010 - Acessibilidade

Diagnósticos automatizados de acessibilidade são auxiliares e não constituem certificação de conformidade WCAG integral. O relatório deve distinguir evidência automatizada, limitação de cobertura e necessidade de validação humana quando aplicável.

## D-011 - Synthetic Apdex

Synthetic Navigation Apdex e Synthetic User Experience Apdex são medições sintéticas separadas do SARI e de RUM real.

O User Experience Apdex pode ser calibrado com configuração externa observável, inclusive Dynatrace, mas continua identificado como medição sintética do RASAi.

## D-012 - Crawling e discovery

`robots.txt` é adquirido no caminho padrão da origem e interpretado conforme o Robots Exclusion Protocol aplicável.

Sitemaps podem existir em múltiplos arquivos e em caminhos diferentes da raiz. O discovery deve preservar múltiplas declarações `Sitemap:` de `robots.txt`, seguir sitemap indexes dentro dos limites de segurança e suportar os formatos documentados pelo contrato atual.

Declarações cross-origin podem ser registradas como evidência, mas não são seguidas automaticamente sem política explícita de segurança/autorização.

## D-013 - llms.txt

`llms.txt` é uma proposta comunitária experimental e não um requisito universal de Search & AI readiness.

O RASAi pode observar múltiplos arquivos `llms.txt` same-origin:

- `/llms.txt` na raiz;
- arquivos scoped em subdiretórios explicitamente descobertos por HTML `<link rel="describedby">`;
- arquivos scoped explicitamente descobertos por HTTP `Link` com `rel="describedby"`;
- URLs explicitamente declaradas em hints `LLMS:`/`LLMS-TXT:` de `robots.txt`, sempre identificados como convenção não padronizada.

Não é permitido brute-force de diretórios para adivinhar arquivos `llms.txt`. A presença ou ausência desses arquivos não substitui robots, sitemap, canonical, HTML semântico ou conteúdo acessível e não altera automaticamente o SARI.

## D-014 - Crawlers e controles de IA

OAI-SearchBot, GPTBot, Googlebot e Google-Extended devem ser apresentados conforme suas finalidades públicas e sem inferência indevida entre controles distintos.

Bloquear GPTBot não equivale automaticamente a bloquear Search. Google-Extended é um token de produto em `robots.txt`, não um user-agent HTTP separado da Pesquisa Google.

## D-015 - Search Intelligence

SERP Observation é provider-neutral e registra observação limitada de Search tradicional. Google, Bing e futuros engines permanecem adapters do mesmo contrato canônico.

`NOT_FOUND_WITHIN_DEPTH` somente pode ser emitido quando a profundidade solicitada tiver sido suficientemente observada. Orçamento esgotado antes dessa comprovação produz estado de indisponibilidade/parcialidade, não uma posição inventada.

Search Intelligence, Competitive Search, Search History e Search Monitoring são non-scoring por default e não alteram automaticamente `SARI-001` ou `SCORE-GEO-004`.

## D-016 - Monitoring, observability e outcomes

Comparações before/after, milestones, release gates e timelines usam evidência persistida e devem declarar limitações de comparabilidade.

Associação temporal não é causalidade. Observed Generative Visibility, Search Console, Bing, CrUX, GA4, logs e demais outcomes externos não entram automaticamente no score de readiness.

Dados ausentes permanecem ausentes; `NULL` externo não é convertido em zero.

## D-017 - Multi-URL e recursos de domínio

Uma auditoria pode receber múltiplas URLs/targets conforme o contrato da CLI/API e preservar um único `audit_id` quando o escopo for válido.

`robots.txt`, sitemaps, feeds e demais recursos de domínio são evidências de domínio e não devem ser artificialmente duplicados como findings por página.

RAW HTTP, DOM renderizado e visual snapshot são planos de evidência distintos.

## D-018 - Remediação e segurança factual

Recomendações devem ser sustentadas por evidência persistida. O RASAi não inventa canonical preferencial, selector, HTML observado, autor, data, credencial, preço, claim, structured data ou fonte ausente.

Quando uma decisão não puder ser determinada pelas evidências, o relatório deve declarar a necessidade de decisão humana em vez de fabricar um valor.

## D-019 - Contrato público de relatório

O mini-site de relatório é HTML estático, navegável, responsivo e reabrível a partir do workspace persistido.

`report/readiness.html` é a superfície canônica do SARI. `report/scoring.html` é a superfície canônica da metodologia. A versão metodológica pertence a `scoring_version`, banco, manifests, metadados e conteúdo do relatório; não a um filename público alternativo.

Páginas opcionais são materializadas quando o respectivo domínio possui estado a apresentar e devem compartilhar navegação e CSS do mini-site.

## D-020 - Linguagem e semântica de apresentação

A camada de apresentação é prioritariamente em português do Brasil. Termos técnicos consolidados, enums, IDs, APIs e formatos podem permanecer em inglês quando isso melhora precisão e rastreabilidade.

Estados de indisponibilidade, ausência de evidência, coleta não executada e `NOT_APPLICABLE` devem ser visualmente e semanticamente distintos de falha ou score zero.

## D-021 - Segurança de secrets e rede

Secrets não devem ser incluídos em documentação de exemplo real, banco de evidência, artifacts, reports, schedules ou logs.

Aquisição de URLs externas deve respeitar controles de escopo, redirects, DNS/IP, same-origin e SSRF definidos pela superfície correspondente. Execução hospedada requer também controles de egress e gestão de secrets apropriados ao ambiente.

## D-022 - Uso e consumo

O usage ledger é separado de findings/scoring e registra consumo operacional necessário para analytics, limites, custo e futura medição SaaS, preservando proveniência de provider/source e sem transformar consumo em indicador de qualidade do website.

## D-023 - Regra documental de pré-publicação

O RASAi ainda está em desenvolvimento e validação. A documentação normativa descreve somente o contrato vigente do produto.

Não devem permanecer na documentação pública/normativa decisões descartadas, nomes de branches de entrega, números de PR usados como status de implementação, planos concluídos ou superfícies removidas. Git continua responsável pelo histórico técnico dessas mudanças.

Toda alteração funcional deve manter código, testes, HTML, CLI/API e documentação aderentes ao mesmo contrato.