# FUNCTIONAL_REQUIREMENTS.md

**Estado:** APROVADO / VIGENTE  
**Contrato relacionado:** Rastreamento, descoberta e acesso de crawlers + Synthetic Navigation Apdex + Acessibilidade automatizada e diagnósticos Web + Web Performance + Sugestões e remediação de conteúdo por IA + análise semântica por IA, roteamento e telemetria + `SCORE-GEO-004` + `SARI-001` + `REPORT-SITE-GEO-001`

Os identificadores `FR-GEO-*` e `NFR-GEO-*` são canônicos. Termos de implementação, flags, enums, nomes de classes e arquivos permanecem em inglês quando fazem parte do contrato técnico; a descrição funcional é mantida em português do Brasil.

## Requisitos funcionais

### FR-GEO-001
Criar auditoria com target, projeto, idioma, mercado e `max_pages`.

### FR-GEO-002
Gerar identificador único de auditoria.

### FR-GEO-003
Operar localmente em Windows sem servidor Web ou banco externo obrigatório.

### FR-GEO-004
Persistir dados localmente utilizando SQLite embarcado e filesystem.

### FR-GEO-005
Descobrir URLs por seed, links internos e sitemap.

### FR-GEO-006
Limitar o universo a `max_pages` de forma determinística e informar a limitação.

### FR-GEO-007
Avaliar Desktop e Mobile separadamente quando esses contextos forem selecionados; nunca misturar resultados dos dispositivos em uma única nota.

### FR-GEO-008
Capturar HTTP, headers, redirects, URL final, status e erros.

### FR-GEO-009
Preservar RAW HTML.

### FR-GEO-010
Renderizar página com browser controlado.

### FR-GEO-011
Preservar DOM renderizado.

### FR-GEO-012
Suportar HTML, SSR, SSG, hydration, CSR, SPA e arquiteturas híbridas.

### FR-GEO-013
Comparar estados RAW × RENDERED.

### FR-GEO-014
Extrair conteúdo principal.

### FR-GEO-015
Interpretar `robots.txt` e crawlers configurados.

### FR-GEO-016
Avaliar capacidade de indexação.

### FR-GEO-017
Avaliar problemas materiais de JavaScript e SPA.

### FR-GEO-018
Detectar e validar Dados Estruturados quando presentes.

### FR-GEO-019
Executar o ruleset vigente `BR-GEO-001..059` conforme aplicabilidade, dependências e versão de cada regra.

### FR-GEO-020
Padronizar os resultados técnicos `PASS`, `FAIL`, `WARNING`, `UNKNOWN`, `NOT_APPLICABLE` e `ERROR`.

### FR-GEO-021
Evitar falhas em cascata: falha de pré-requisito não deve gerar múltiplos `FAIL` derivados sem evidência independente.

### FR-GEO-022
Registrar evidências rastreáveis.

### FR-GEO-023
Possuir `SemanticAnalysisProvider` independente de fornecedor.

### FR-GEO-024
Funcionar sem IA.

### FR-GEO-025
Possuir fallback determinístico/heurístico seguro.

### FR-GEO-026
Permitir múltiplos providers, preservando `NONE` e seleção explícita de provider.

### FR-GEO-027
Validar schema e `evidence_ids` da saída da IA.

### FR-GEO-028
Avaliar estrutura semântica.

### FR-GEO-029
Avaliar entidades.

### FR-GEO-030
Avaliar capacidade de resposta.

### FR-GEO-031
Avaliar preparação para citação.

### FR-GEO-032
Avaliar evidência e confiança.

### FR-GEO-033
Avaliar uma intenção primária e até cinco intenções secundárias.

### FR-GEO-034
Comparar Desktop × Mobile quando ambos os snapshots estiverem no universo selecionado; ausência intencional de um contexto não deve ser apresentada como defeito do website.

### FR-GEO-035
Criar findings estruturados.

### FR-GEO-036
Calcular scores nas **11 dimensões vigentes do SARI-001** por dispositivo: `DISCOVERY_ACCESS`, `INDEXABILITY`, `CONTENT_EXTRACTABILITY`, `SEMANTIC_STRUCTURE`, `ENTITY_CLARITY`, `STRUCTURED_DATA`, `ANSWERABILITY`, `CITATION_READINESS`, `EVIDENCE_TRUST`, `INTENT_COVERAGE` e `CONTENT_VALUE`.

### FR-GEO-037
Informar Coverage.

### FR-GEO-038
Informar Confidence.

### FR-GEO-039
Informar Consolidation Status.

### FR-GEO-040
Calcular Overall Desktop e Overall Mobile de acordo com o contrato `SCORE-GEO-004`, preservando os critérios de Coverage, Confidence, aplicabilidade e Critical Readiness Gates.

### FR-GEO-041
Evitar dupla penalização por `scoring_group`.

### FR-GEO-042
Associar Severity, Impact, Effort, Confidence e Priority conforme o modelo de priorização vigente.

### FR-GEO-043
Aplicar o modelo de priorização versionado.

### FR-GEO-044
Consolidar recomendações repetitivas por causa raiz quando a evidência permitir.

### FR-GEO-045
Gerar recomendações técnicas mesmo sem IA.

### FR-GEO-046
Gerar mini-site HTML estático em `report/`, com `report/index.html` como ponto de entrada.

### FR-GEO-047
Produzir mini-site local e navegável sem servidor Web, usando dependências relativas internas ao workspace.

### FR-GEO-048
Utilizar português do Brasil na camada de apresentação, preservando termos técnicos canônicos quando a tradução reduzir precisão.

### FR-GEO-049
Fornecer legenda, explicações e glossário/metodologia.

### FR-GEO-050
Explicar limitações provocadas por indisponibilidade de IA sem atribuí-las ao website.

### FR-GEO-051
Preservar termos técnicos quando a tradução prejudicar precisão ou quebrar rastreabilidade.

### FR-GEO-052
Produzir apresentação profissional com resumo, scorecard, findings, evidências, prioridades, remediações, limitações e detalhes técnicos distribuídos pelos domínios apropriados do mini-site.

### FR-GEO-053
Exibir readiness geral como não determinado/não consolidado quando `OVERALL_READINESS` não possuir valor publicável pelo contrato; nunca substituir Score por Coverage.

### FR-GEO-054
Exibir e explicar separadamente Readiness, Coverage, Confidence e Consolidation.

### FR-GEO-055
Aplicar classificação visual interna a scores válidos: 90-100 Excelente, 75-89 Alta, 60-74 Moderada, 40-59 Baixa e 0-39 Crítica; estado sem resultado válido permanece Não Determinado. Essas faixas são internas e não podem ser apresentadas como padrão oficial GEO/AEO.

### FR-GEO-056
Produzir principais oportunidades somente a partir de findings/prioridades persistidos, sem transformar `UNKNOWN` em problema.

### FR-GEO-057
Associar findings aplicáveis a `RemediationRecipe` determinística por `rule_id`, contendo alvo, ação, descrição, aceite e validação e, quando seguro, elemento, localização e exemplo.

### FR-GEO-058
Distinguir conteúdo efetivamente observado de exemplo recomendado. Se trecho original não estiver persistido, declarar a ausência em vez de inventá-lo.

### FR-GEO-059
Para canonical ausente ou conflitante, fornecer remediação sem inventar URL preferencial. Quando não determinável pelas evidências, exigir decisão humana.

### FR-GEO-060
Reutilizar `SemanticAssessment`, `reasoning_summary`, entidades, intents e `evidence_ids` persistidos para enriquecer remediação sem executar segunda chamada livre de IA.

### FR-GEO-061
Preservar segurança factual: não inventar autor, fonte, freshness, claim, preço, cobertura comercial, Dados Estruturados ou informação ausente das evidências.

### FR-GEO-062
Gerar diagnóstico de crawl reabrível a partir do estado persistido.

### FR-GEO-063
Manter scorecards Mobile e Desktop independentes; o relatório final só deve expor como auditado o dispositivo que possui snapshot no universo executado.

### FR-GEO-064
Ordenar a apresentação por domínio de informação: visão executiva, dispositivo, remediação, telemetria de IA e fundamentação técnica.

### FR-GEO-065
Identificar recipes de fallback quando não houver recipe específica.

### FR-GEO-066
Preservar IDs de Evidence e rastreabilidade no fluxo `evidence → finding → priority → remediation → report`.

### FR-GEO-067
Distinguir dimensão sem `RuleExecution`, com aplicabilidade não resolvida e integralmente `NOT_APPLICABLE`.

### FR-GEO-068
Excluir do Overall somente dimensões integralmente e legitimamente `NOT_APPLICABLE`, sem atribuir score 0/100 nem reduzir artificialmente Overall Coverage.

### FR-GEO-069
Quando tópico opcional passa a existir, suas regras tornam-se aplicáveis. JSON-LD observado torna `BR-GEO-034..037` parte do fluxo aplicável.

### FR-GEO-070
Exibir no mini-site dimensões legitimamente excluídas como `NÃO APLICÁVEL`, diferentes de `NÃO DETERMINADO`, e informar o universo efetivamente considerado no Overall.

### FR-GEO-071
Documentar premissas `MÍNIMO`, `CONTEXTUAL`, `OPCIONAL / REFORÇO` e `NÃO OBRIGATÓRIO`, sem transformar recomendações externas em requisitos artificiais de score.

### FR-GEO-072
Classificar JSON-LD/Dados Estruturados como `OPCIONAL / REFORÇO`: ausência legítima isolada não é `FAIL` nem impede Overall; quando presente, deve ser interpretável, factual e coerente com conteúdo visível.

### FR-GEO-073
Expor `--device-context mobile|desktop|both` e `RASAI_DEVICE_CONTEXT`, com precedência flag → ambiente → default `mobile` na CLI.

### FR-GEO-074
O contexto de dispositivo selecionado deve controlar rendering e, por consequência, os contextos enviados ao provider semântico; nenhum provider deve ser chamado para dispositivo sem snapshot selecionado.

### FR-GEO-075
Separar `report/mobile.html` e `report/desktop.html`; gerar cada página somente quando o respectivo contexto foi auditado.

### FR-GEO-076
Separar telemetria operacional em `report/ai-usage.html` e fundamentação técnica em `report/references.html`, evitando confundir erro de provider com qualidade do website.

### FR-GEO-077
Todos os HTMLs finais devem usar navegação consistente e stylesheet compartilhado `report/css/site.css`; CSS estrutural inline/embutido não deve compor o mini-site final.

### FR-GEO-078
Explicar que Confidence representa força da conclusão do auditor e que `LOW`, isoladamente, não significa baixa qualidade ou não aderência do texto.

### FR-GEO-079
A fundamentação deve distinguir norma/padrão externo de heurística interna e declarar que o RASAi não representa suas faixas de score como padrão GEO/AEO oficial.

### FR-GEO-080
Expor remediação textual por IA por `--ai-content-remediation`, `--no-ai-content-remediation` e `RASAI_AI_CONTENT_REMEDIATION`, com default público `false`.

### FR-GEO-081
Executar remediação textual por IA somente depois de findings, scoring e priorização; essa camada não pode alterar retrospectivamente `RuleExecution`, Finding, Recommendation, Score, Coverage, Confidence ou Consolidation.

### FR-GEO-082
Disparar remediação textual por IA somente a partir de findings de conteúdo/semântica elegíveis e persistidos. `Confidence LOW`, isoladamente, nunca é gatilho.

### FR-GEO-083
Restringir cada request de remediação por IA a uma página/snapshot/device e aos findings/`evidence_ids` persistidos daquele contexto. Referências externas ao universo fornecido devem ser rejeitadas.

### FR-GEO-084
Cada sugestão textual aceita deve informar objetivo, localização alvo, texto exato proposto, `evidence_ids`, confiança da sugestão, provider/modelo e aviso de revisão humana obrigatória.

### FR-GEO-085
Aplicar contrato people-first e antifabricação à remediação por IA: não solicitar keyword stuffing, contagem arbitrária de palavras, reescrita apenas para IA, chunking artificial, fake freshness, claims, preços, datas, estatísticas, experiência, credenciais ou fontes não sustentadas.

### FR-GEO-086
Reutilizar providers configurados e saudáveis do runtime de IA para remediação, sem credencial paralela; respeitar quarentena/circuit breaker, execução sequencial, parada no primeiro resultado válido e pinning de provider por URL quando previsto pelo runtime.

### FR-GEO-087
Persistir telemetria de remediação por IA separadamente da telemetria de análise semântica, incluindo provider/modelo, tokens, duração, erro sanitizado e custo estimado quando calculável.

### FR-GEO-088
Gerar revisão determinística de JSON-LD por snapshot/dispositivo auditado mesmo quando remediação textual por IA estiver desabilitada ou nenhum provider externo estiver configurado.

### FR-GEO-089
Quando JSON-LD estiver ausente, propor somente baseline Schema.org conservador sustentado por dados persistidos/observados, preferindo `WebPage` genérico e omissão a tipos/propriedades especulativos.

### FR-GEO-090
Quando JSON-LD estiver presente, não o sobrescrever integralmente; apontar problemas genéricos verificáveis, como erros de parsing, duplicação idêntica, ausência de `@context`, nós sem `@type` e propriedades genéricas ausentes cujo valor já seja conhecido.

### FR-GEO-091
Expor remediação por IA em `report/content-suggestions.html`, com navegação/CSS compartilhados, e telemetria correspondente em `report/ai-usage.html`, separada da finalidade de análise semântica.

### FR-GEO-092
Informar que JSON-LD é reforço opcional, que não existe markup especial GEO/AEO obrigatório, que propriedades de rich result dependem do tipo/feature e que markup válido não garante exibição de rich result.

### FR-GEO-093
Expor Web Performance por `--web-performance`, `--no-web-performance` e `RASAI_WEB_PERFORMANCE`, com default público `false` e nenhuma chamada PageSpeed/CrUX quando desabilitado.

### FR-GEO-095
Coletar Core Web Vitals de campo LCP, INP e CLS em p75 quando disponíveis, distinguindo dados CrUX de métricas Lighthouse de laboratório.

### FR-GEO-096
Avaliar Core Web Vitals com thresholds oficiais aplicáveis à integração e usar `INCOMPLETE`/`UNAVAILABLE` quando amostra ou métrica necessária não existir; ausência de CrUX nunca deve virar `FAIL` do website.

### FR-GEO-097
Expor política de dados de campo `auto|pagespeed|crux|none`; `auto` deve preferir dados CrUX devolvidos pelo PageSpeed e usar CrUX API direta somente como fallback quando necessário e configurado.

### FR-GEO-098
Expor `--web-performance-max-pages`, `--web-performance-timeout-seconds` e `--lighthouse-categories`, com equivalentes por ambiente, para controlar quota, duração e escopo de chamadas externas.

### FR-GEO-099
Isolar `RASAI_PAGESPEED_API_KEY` e `RASAI_CRUX_API_KEY` entre si e das credenciais de IA; nenhuma credencial de Web Performance deve ser persistida ou exibida.

### FR-GEO-100
Web Performance deve adicionar zero chamadas LLM e não pode reutilizar automaticamente provider semântico/remediação por IA para interpretar métricas externas.

### FR-GEO-101
Persistir Web Performance em tabelas auxiliares e artifacts JSON reabríveis, mantendo tentativas/erros de PageSpeed/CrUX como telemetria operacional externa e não como Finding/Recommendation do website.

### FR-GEO-102
Materializar `report/web-performance.html` com navegação/CSS compartilhados, separando Lighthouse lab, Core Web Vitals de campo, source/scope, indisponibilidade e telemetria de coleta.

### FR-GEO-103
Projetar em `report/index.html` somente resumo explicitamente rotulado como Web Performance externo, sem substituir ou recalcular Overall Readiness, Coverage ou Confidence.

### FR-GEO-105
Executar Web Performance como enriquecimento pós-auditoria/fail-open: indisponibilidade ou erro do serviço externo não pode invalidar `RuleExecution`, Finding, Recommendation ou score já concluídos.

### FR-GEO-106
Executar diagnósticos determinísticos de rastreamento, descoberta e acesso de crawlers como advisory/non-scoring. Quando IA técnica estiver explicitamente habilitada e produzir saída evidence-bound válida, permitir somente BR-GEO-055/056 nos grupos SITEMAP/ROBOTS, sem escolha de pesos pelo provider, sem bônus duplicado e sem alteração direta de Coverage, Confidence ou Consolidation. O runtime vigente permanece `SCORE-GEO-004`/`SARI-001`.

### FR-GEO-107
Aprofundar a interpretação de `robots.txt` com evidência reabrível de grupos de crawler, `Allow`, `Disallow`, `Sitemap`, linhas inválidas, tamanho e campos relevantes, sem transformar ausência legítima do arquivo em bloqueio artificial.

### FR-GEO-108
Preservar declarações `Sitemap:` absolutas mesmo quando apontarem para host externo, mas não realizar fetch cross-origin automático sem política de aquisição segura e explicitamente autorizada.

### FR-GEO-109
Suportar no discovery sitemap XML `urlset`, sitemap index, gzip, RSS 2.0, Atom 1.0 e sitemap texto plano, mantendo somente URLs de página pertinentes ao formato.

### FR-GEO-110
Avaliar, quando observável, limites de sitemap de 50 MB descompactado e 50.000 URLs, URLs absolutas, duplicatas, `lastmod`, extensões e presença de `priority`/`changefreq` sem representá-las como sinal de ranking.

### FR-GEO-111
Cruzar URLs de sitemap com a amostra auditada para identificar não-2xx, `noindex`, canonical conflitante e bloqueio robots observados; ausência de URL auditada no sitemap deve permanecer diagnóstico da amostra e não prova de erro global do site.

### FR-GEO-112
Expor separadamente Googlebot, OAI-SearchBot, GPTBot e Google-Extended conforme suas finalidades públicas; bloqueio de GPTBot ou Google-Extended não pode ser convertido automaticamente em bloqueio de Search.

### FR-GEO-113
Tratar Google-Extended como token de produto em `robots.txt`, sem user-agent HTTP separado, e preservar a interpretação documentada pelo Google sem transformá-la em regra proprietária de ranking.

### FR-GEO-114
Descobrir e adquirir `llms.txt` same-origin como recurso múltiplo e scoped: tentar `/llms.txt` e seguir candidatos explicitamente anunciados por HTML `link rel="describedby"`, HTTP `Link: ...; rel="describedby"` e hints `LLMS:`/`LLMS-TXT:` observados em `robots.txt`. Hints em `robots.txt` para `llms.txt` devem ser identificados como não padronizados; não realizar brute force de diretórios. Cada arquivo adquirido deve preservar URL, scope, origem da descoberta e artifact próprio. Ausência ou erro permanece informativo/non-scoring.

### FR-GEO-115
Tratar `llms.txt` como proposta comunitária experimental, não como web standard nem requisito universal de Search & AI, e nunca usá-lo como substituto de robots, sitemap, canonical, HTML semântico ou conteúdo acessível.

### FR-GEO-116
Registrar feeds RSS/Atom observados como sinais adicionais de discovery sem atribuir score obrigatório pela presença ou ausência de feed.

### FR-GEO-117
Reportar configuração/submissão IndexNow como não determinável quando a auditoria passiva não possuir evidência explícita, log ou artifact verificável; não inferir sucesso de submissão por mera observação do site.

### FR-GEO-118
Expor remediação técnica de crawling/discovery por `--ai-technical-remediation`, `--no-ai-technical-remediation` e `RASAI_AI_TECHNICAL_REMEDIATION`, com default público `false` e precedência CLI explícito → ambiente → `false`.

### FR-GEO-119
Restringir a IA técnica a diagnósticos/evidências persistidos, rejeitar invenção de URL, policy, canonical, data ou crawler token, exigir revisão humana e não permitir que o provider decida unilateralmente política de treinamento/crawler da organização.

### FR-GEO-120
Persistir estado/telemetria de crawling/discovery em tabelas auxiliares próprias, mantendo separação entre qualidade do website, diagnósticos técnicos e consumo de provider.

### FR-GEO-121
Materializar `report/crawling-discovery.html` com navegação/CSS compartilhados, robots/crawler policy, múltiplos sitemaps, múltiplos `llms.txt` raiz/scoped, feeds, IndexNow, conteúdo capturado reabrível/copiável, limitações de segurança, referências e eventual orientação técnica por IA.

### FR-GEO-122
Quando houver hard source blocker confirmado, evitar aquisição adicional de `llms.txt` e chamada técnica de IA dependente do corpus, persistindo estado de skip/fail-open sem invalidar a auditoria principal.

## Requisitos não funcionais

### NFR-GEO-001
Executar em Windows no runtime local suportado.

### NFR-GEO-002
Operar preferencialmente sem privilégios administrativos.

### NFR-GEO-003
Não exigir database server, web server, Docker, IA ou GitHub para o runtime local básico.

### NFR-GEO-004
Priorizar distribuição portátil.

### NFR-GEO-005
Resultados determinísticos devem ser reproduzíveis.

### NFR-GEO-006
Toda conclusão deve ser rastreável.

### NFR-GEO-007
Versionar auditor, ruleset, prompts, rendering policy, scoring, priorização e contrato do relatório.

### NFR-GEO-008
Falhas localizadas não devem encerrar toda auditoria quando for possível continuar de forma segura.

### NFR-GEO-009
Dados permanecem locais, exceto conteúdo explicitamente enviado a provider configurado ou integração externa habilitada pelo operador.

### NFR-GEO-010
Resultado com cobertura/confiabilidade insuficiente não pode ser apresentado como conclusivo.

### NFR-GEO-011
O mini-site deve ser responsivo, imprimível, navegável localmente e sem dependências externas obrigatórias de runtime.

### NFR-GEO-012
`RemediationRecipe` e apresentação devem ser determinísticas/reproduzíveis a partir do estado persistido e versão do código/ruleset.

### NFR-GEO-013
Aplicabilidade e exclusão do Overall devem ser reproduzíveis a partir das RuleExecutions e versão do scoring.

### NFR-GEO-014
A projeção final não deve recalcular score/finding nem chamar IA. `audit.db` e artifacts permanecem fonte de verdade. Capacidades que chamam IA devem concluir a respectiva coleta/análise antes da projeção; o renderer do relatório não chama provider.

### NFR-GEO-015
Remediação de conteúdo por IA deve ser fail-open em relação ao audit: indisponibilidade da finalidade de remediação textual não pode invalidar score/findings já concluídos.

### NFR-GEO-016
Sugestões de IA e JSON-LD devem permanecer advisory, reabríveis no `audit.db` e separadas dos objetos normativos de scoring.

### NFR-GEO-017
Web Performance deve permanecer opcional, com rede externa desabilitada por default e limites explícitos de páginas/timeout para impedir consumo PageSpeed/CrUX não previsto.

### NFR-GEO-019
Métricas de Web Performance devem permanecer reabríveis a partir de `audit.db` + artifacts JSON sem nova chamada externa, preservando source, device, URL/origin scope e versão Lighthouse quando disponível.

### NFR-GEO-020
Web Performance não pode persistir API keys, URLs contendo parâmetros de chave, Authorization ou erro externo não sanitizado; telemetria de coleta deve permanecer separada da telemetria de IA.

### NFR-GEO-021
Crawling/discovery deve permanecer fail-open e não pode introduzir dependência obrigatória de `llms.txt`, IndexNow ou provider de IA para executar a auditoria principal.

### NFR-GEO-022
Crawling/discovery deve limitar aquisição adicional automática ao escopo same-origin autorizado; declarações externas podem ser preservadas sem serem seguidas automaticamente.

### NFR-GEO-023
Resultados de crawling/discovery devem ser reabríveis a partir de `audit.db` + artifacts locais sem nova chamada externa durante renderização do relatório.

### NFR-GEO-024
CI permanente deve cobrir compile/import da superfície de crawling/discovery, testes específicos, regressões de integração afetadas e suíte completa antes de considerar mudanças homologadas.

### FR-GEO-173
A camada de apresentação não deve expor identificadores internos de etapas de entrega; capacidades devem ser nomeadas pelo domínio funcional.

### FR-GEO-174
O HTML deve ser compreensível por analista de dados/SEO sem conhecimento do código, preservando apenas termos técnicos externamente documentados e difundidos, com contexto/glossário quando necessário.

### FR-GEO-175
Estados `UNAVAILABLE`, `INCOMPLETE`, ausência de evidência ou coleta não executada devem ser apresentados de forma neutra e nunca como resultado ruim, zero ou prova de ausência de falha do website.

## Observação sobre numeração

Os identificadores existentes são preservados por compatibilidade documental. Lacunas numéricas neste arquivo não devem ser preenchidas por renumeração automática, pois um identificador funcional já publicado não deve mudar de significado apenas para produzir sequência contínua.