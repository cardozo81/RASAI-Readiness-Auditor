# FUNCTIONAL_REQUIREMENTS.md

**Estado no baseline de desenvolvimento:** APPROVED - Rastreamento, descoberta e acesso de crawlers + Synthetic Navigation Apdex + Acessibilidade automatizada e diagnósticos Web + Web Performance externo + Sugestões e remediação de conteúdo por IA + Análise semântica por IA, roteamento e telemetria + SCORE-GEO-004 + SARI-001 + REPORT-SITE-GEO-001

## Requisitos Funcionais

### FR-GEO-001
Criar auditoria com target, project, language, market e max_pages.

### FR-GEO-002
Gerar identificador único de auditoria.

### FR-GEO-003
Operar localmente em Windows, sem servidor web ou banco externo obrigatório.

### FR-GEO-004
Persistir dados localmente utilizando SQLite embarcado + filesystem.

### FR-GEO-005
Descobrir URLs por seed, links internos e sitemap.

### FR-GEO-006
Limitar universo a max_pages de forma determinística e informar limitação.

### FR-GEO-007
Avaliar Desktop e Mobile separadamente quando esses contextos forem selecionados; nunca misturar resultados dos dispositivos em uma única nota.

### FR-GEO-008
Capturar HTTP, headers, redirects, final URL, status e erros.

### FR-GEO-009
Preservar RAW HTML.

### FR-GEO-010
Renderizar página com browser controlado.

### FR-GEO-011
Preservar DOM renderizado.

### FR-GEO-012
Suportar HTML, SSR, SSG, hydration, CSR, SPA e híbridos.

### FR-GEO-013
Comparar RAW × RENDERED.

### FR-GEO-014
Extrair conteúdo principal.

### FR-GEO-015
Interpretar robots.txt e crawlers configurados.

### FR-GEO-016
Avaliar indexabilidade.

### FR-GEO-017
Avaliar problemas materiais de JavaScript e SPA.

### FR-GEO-018
Detectar e validar Dados Estruturados quando presentes.

### FR-GEO-019
Executar BR-GEO-001..056.

### FR-GEO-020
Padronizar resultados PASS, FAIL, WARNING, UNKNOWN, NOT_APPLICABLE, ERROR.

### FR-GEO-021
Evitar cascading failures.

### FR-GEO-022
Registrar evidências rastreáveis.

### FR-GEO-023
Possuir SemanticAnalysisProvider independente de fornecedor.

### FR-GEO-024
Funcionar sem IA.

### FR-GEO-025
Possuir fallback determinístico/heurístico seguro.

### FR-GEO-026
Permitir múltiplos providers, preservando NONE e provider explícito.

### FR-GEO-027
Validar schema e evidence_ids da saída da IA.

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
Avaliar 1 primary intent + até 5 secondary intents.

### FR-GEO-034
Comparar Desktop × Mobile quando ambos os snapshots estiverem no universo selecionado; ausência intencional de um contexto não deve ser apresentada como defeito do website.

### FR-GEO-035
Criar findings estruturados.

### FR-GEO-036
Calcular scores nas 10 dimensões por dispositivo.

### FR-GEO-037
Informar Coverage.

### FR-GEO-038
Informar Confidence.

### FR-GEO-039
Informar Consolidation Status.

### FR-GEO-040
Calcular Overall Desktop e Overall Mobile somente quando o respectivo contexto possuir cobertura suficiente das dimensões aplicáveis.

### FR-GEO-041
Evitar dupla penalização via scoring groups.

### FR-GEO-042
Associar Severity, Impact, Effort, Confidence e Priority.

### FR-GEO-043
Aplicar modelo de priorização aprovado.

### FR-GEO-044
Consolidar recomendações repetitivas por causa raiz.

### FR-GEO-045
Gerar recomendações técnicas mesmo sem IA.

### FR-GEO-046
Gerar report site HTML estático em `report/`, com `report/index.html` como ponto de entrada.

### FR-GEO-047
Produzir report site local e navegável sem servidor web, usando dependências relativas internas ao workspace.

### FR-GEO-048
Utilizar português na camada de apresentação.

### FR-GEO-049
Fornecer legenda, explicações e glossário/metodologia.

### FR-GEO-050
Explicar limitações provocadas por indisponibilidade de IA sem atribuí-las ao website.

### FR-GEO-051
Preservar termos técnicos quando tradução prejudicar precisão.

### FR-GEO-052
Produzir apresentação profissional com resumo, scorecard, findings, evidências, prioridades, remediações, limitações e detalhes técnicos distribuídos pelos domínios apropriados do report site.

### FR-GEO-053
Exibir readiness geral como não determinado/não consolidado quando `OVERALL_READINESS` não possuir valor consolidado; nunca substituir o Score por Coverage.

### FR-GEO-054
Exibir e explicar separadamente Compatibilidade/Readiness, Coverage e Confidence.

### FR-GEO-055
Aplicar classificação visual interna a scores válidos: 90-100 Excelente, 75-89 Alta, 60-74 Moderada, 40-59 Baixa, 0-39 Crítica; estado sem resultado válido permanece Não Determinado. Essas faixas são internas e não podem ser apresentadas como standard oficial GEO/AEO.

### FR-GEO-056
Produzir principais oportunidades somente de findings/prioridades persistidos, sem transformar UNKNOWN em problema.

### FR-GEO-057
Associar findings aplicáveis a `RemediationRecipe` determinística por `rule_id`, contendo alvo, ação, descrição, aceite e validação e, quando seguro, elemento/localização/exemplo.

### FR-GEO-058
Distinguir efetivamente observado de exemplo recomendado. Se trecho original não estiver persistido, declarar a ausência em vez de inventá-lo.

### FR-GEO-059
Para canonical ausente/conflitante, fornecer remediação sem inventar URL preferencial. Se não determinável pelas evidências, exigir decisão humana.

### FR-GEO-060
Reutilizar SemanticAssessment, reasoning_summary, entidades, intents e evidence_ids persistidos para enriquecer remediação sem executar segunda chamada livre de IA.

### FR-GEO-061
Preservar segurança factual: não inventar autor, fonte, freshness, claim, preço, cobertura comercial, structured data ou informação ausente das evidências.

### FR-GEO-062
Gerar diagnóstico de crawl reabrível a partir do estado persistido.

### FR-GEO-063
Manter scorecards Mobile e Desktop independentes; o report final só deve expor como auditado o dispositivo que possui snapshot no universo executado.

### FR-GEO-064
Ordenar a apresentação por domínio de informação: visão executiva, dispositivo, remediação, telemetria de IA e fundamentação técnica.

### FR-GEO-065
Identificar recipes de fallback quando não houver recipe específica.

### FR-GEO-066
Preservar IDs de Evidence e rastreabilidade no fluxo `evidence → finding → priority → remediation → report`.

### FR-GEO-067
Distinguir dimensão sem RuleExecutions, com aplicabilidade não resolvida e integralmente `NOT_APPLICABLE`.

### FR-GEO-068
Excluir do Overall somente dimensões integralmente e legitimamente `NOT_APPLICABLE`, sem atribuir score 0/100 nem reduzir Overall Coverage.

### FR-GEO-069
Quando tópico opcional passa a existir, suas regras tornam-se aplicáveis. JSON-LD observado torna BR-GEO-034..037 parte do fluxo aplicável.

### FR-GEO-070
Exibir no report site dimensões legitimamente excluídas como `NÃO APLICÁVEL`, diferentes de `NÃO DETERMINADO`, e informar o universo efetivamente considerado no Overall.

### FR-GEO-071
Documentar premissas `MÍNIMO`, `CONTEXTUAL`, `OPCIONAL / REFORÇO` e `NÃO OBRIGATÓRIO`, sem transformar recomendações externas em requisitos artificiais de score.

### FR-GEO-072
Classificar JSON-LD/Structured Data como `OPCIONAL / REFORÇO`: ausência legítima isolada não é FAIL nem impede Overall; quando presente, deve ser interpretável, factual e coerente com o conteúdo visível.

### FR-GEO-073
Expor `--device-context mobile|desktop|both` e `RASAI_DEVICE_CONTEXT`, com precedência flag → ambiente → default `mobile` na CLI.

### FR-GEO-074
O contexto de dispositivo selecionado deve controlar rendering e, por consequência, os contextos enviados ao provider semântico; nenhum provider deve ser chamado para dispositivo que não possui snapshot selecionado.

### FR-GEO-075
Separar `report/mobile.html` e `report/desktop.html`; gerar cada página somente quando o respectivo contexto foi auditado.

### FR-GEO-076
Separar telemetria operacional em `report/ai-usage.html` e fundamentação técnica em `report/references.html`, evitando confundir erro de provider com qualidade do website.

### FR-GEO-077
Todos os HTMLs finais devem usar estrutura de navegação consistente e stylesheet compartilhado `report/css/site.css`; CSS inline/embutido não deve compor o report site final.

### FR-GEO-078
Explicar explicitamente que Confidence é força da conclusão do auditor e que `LOW` não significa, isoladamente, baixa qualidade ou não aderência do texto.

### FR-GEO-079
A fundamentação deve distinguir norma/standard externo de heurística interna e declarar que o RASAi não representa suas faixas de score como standard GEO/AEO oficial.

### FR-GEO-080
Expor remediação textual por IA por `--ai-content-remediation`, `--no-ai-content-remediation` e `RASAI_AI_CONTENT_REMEDIATION`, com default público `false`.

### FR-GEO-081
Executar Sugestões e remediação de conteúdo por IA textual somente depois de findings, scoring e priorização; Sugestões e remediação de conteúdo por IA não pode alterar retrospectivamente RuleExecution, Finding, Recommendation, Score, Coverage, Confidence ou Consolidation.

### FR-GEO-082
Disparar Sugestões e remediação de conteúdo por IA textual somente a partir de findings contentuais/semânticos elegíveis persistidos. `Confidence LOW`, isoladamente, nunca é gatilho.

### FR-GEO-083
Restringir cada request Sugestões e remediação de conteúdo por IA a uma página/snapshot/device e aos findings/evidence_ids persistidos daquele contexto. Respostas com finding/evidence reference externa ao universo fornecido devem ser rejeitadas.

### FR-GEO-084
Cada sugestão textual Sugestões e remediação de conteúdo por IA aceita deve informar objetivo, localização alvo, texto exato proposto, evidence_ids, confiança da sugestão, provider/model e aviso de revisão humana obrigatória.

### FR-GEO-085
Aplicar contrato people-first e anti-fabricação ao Sugestões e remediação de conteúdo por IA: não solicitar keyword stuffing, word count arbitrário, reescrita apenas para IA, chunking artificial, fake freshness, claims, preços, datas, estatísticas, experiência, credenciais ou fontes não sustentadas.

### FR-GEO-086
Reutilizar providers configurados/saudáveis do Análise semântica por IA, roteamento e telemetria para Sugestões e remediação de conteúdo por IA, sem credencial paralela; respeitar quarantine já ocorrido, execução sequencial, parada no primeiro resultado válido e URL provider pinning na finalidade Sugestões e remediação de conteúdo por IA.

### FR-GEO-087
Persistir telemetria Sugestões e remediação de conteúdo por IA separadamente da telemetria semântica Análise semântica por IA, roteamento e telemetria, incluindo provider/model, tokens, duração, erro sanitizado e custo estimado quando calculável.

### FR-GEO-088
Gerar revisão determinística de JSON-LD por snapshot/dispositivo auditado mesmo quando Sugestões e remediação de conteúdo por IA textual estiver desabilitado ou nenhum provider externo estiver configurado.

### FR-GEO-089
Quando JSON-LD estiver ausente, propor somente um baseline Schema.org conservador sustentado por dados persistidos/observados, preferindo `WebPage` genérico e omissão a tipos/propriedades especulativos.

### FR-GEO-090
Quando JSON-LD estiver presente, não o sobrescrever integralmente; apontar problemas genéricos verificáveis, como parse errors, duplicação idêntica, ausência de `@context`, nós sem `@type` e propriedades genéricas ausentes cujo valor já seja conhecido.

### FR-GEO-091
Expor Sugestões e remediação de conteúdo por IA em `report/content-suggestions.html`, com shared navigation/CSS, e exibir telemetria Sugestões e remediação de conteúdo por IA em `report/ai-usage.html` separada da finalidade semântica Análise semântica por IA, roteamento e telemetria.

### FR-GEO-092
Informar explicitamente que JSON-LD é reforço opcional, que não existe markup especial GEO/AEO obrigatório, que propriedades de rich result dependem do tipo/feature e que markup válido não garante exibição de rich result.

### FR-GEO-093
Expor Web Performance externo por `--web-performance`, `--no-web-performance` e `RASAI_WEB_PERFORMANCE`, com default público `false` e nenhuma chamada PageSpeed/CrUX quando desabilitado.

### FR-GEO-094
Quando Web Performance externo estiver habilitado, coletar por página/dispositivo selecionado evidência Lighthouse por PageSpeed Insights API e persistir scores/metricas retornados sem convertê-los em contribuição de `SCORE-GEO-003`.

### FR-GEO-095
Coletar Core Web Vitals de campo LCP, INP e CLS em p75 quando disponíveis, distinguindo explicitamente dados CrUX reais de métricas Lighthouse de laboratório.

### FR-GEO-096
Avaliar Core Web Vitals com thresholds oficiais vigentes da implementação e usar `INCOMPLETE`/`UNAVAILABLE` quando a amostra ou uma métrica necessária não existir; ausência de CrUX nunca deve virar website FAIL.

### FR-GEO-097
Expor política de field data `auto|pagespeed|crux|none`; `auto` deve preferir dados CrUX devolvidos pelo PageSpeed e usar CrUX API direta somente como fallback quando necessário e configurado.

### FR-GEO-098
Expor `--web-performance-max-pages`, `--web-performance-timeout-seconds` e `--lighthouse-categories`, com equivalentes por ambiente, para controlar quota, duração e escopo de chamadas externas.

### FR-GEO-099
Isolar `RASAI_PAGESPEED_API_KEY` e `RASAI_CRUX_API_KEY` entre si e das credenciais OpenAI/DeepSeek/MiMo; nenhuma credencial Web Performance externo deve ser persistida ou exibida.

### FR-GEO-100
Web Performance externo deve adicionar zero chamadas LLM e não pode reutilizar automaticamente SemanticProvider/Sugestões e remediação de conteúdo por IA para interpretar métricas externas.

### FR-GEO-101
Persistir Web Performance externo em tabelas auxiliares e artifacts JSON reabríveis, mantendo tentativas/erros de PageSpeed/CrUX como telemetria operacional externa e não como Finding/Recommendation do website.

### FR-GEO-102
Materializar `report/web-performance.html` com navegação/CSS compartilhados, separando Lighthouse lab, Core Web Vitals field, source/scope, indisponibilidade e telemetria de coleta.

### FR-GEO-103
Projetar no `report/index.html` somente resumo explicitamente rotulado como Web Performance externo, sem substituir ou recalcular Overall Readiness, Coverage ou Confidence.

### FR-GEO-104
Adicionar ao `report/references.html` fontes oficiais de PageSpeed Insights, CrUX, Lighthouse e Core Web Vitals e declarar que essas fontes sustentam os fenômenos medidos, não homologam `SCORE-GEO-003` como standard GEO/AEO.

### FR-GEO-105
Executar Web Performance externo como enriquecimento pós-auditoria/fail-open: indisponibilidade ou erro do serviço externo não pode invalidar RuleExecution, Finding, Recommendation ou score já concluídos.

### FR-GEO-106
Executar Rastreamento, descoberta e acesso de crawlers com diagnósticos determinísticos advisory/non-scoring. Quando IA técnica estiver explicitamente habilitada e produzir saída evidence-bound válida, permitir somente BR-GEO-055/056 bounded nos grupos SITEMAP/ROBOTS, sem escolha de pesos pelo provider, sem bônus duplicado e sem alteração direta de Coverage, Confidence ou Consolidation. O runtime vigente permanece SCORE-GEO-004/SARI-001.

### FR-GEO-107
Aprofundar a interpretação de `robots.txt` com evidência reabrível de grupos crawler, `Allow`, `Disallow`, `Sitemap`, linhas inválidas, tamanho e campos relevantes, sem transformar ausência legítima de robots em bloqueio artificial.

### FR-GEO-108
Preservar declarações `Sitemap:` absolutas mesmo quando apontarem para host externo, mas não realizar fetch cross-origin automático a partir dessa declaração sem uma política de aquisição segura/explicitamente autorizada.

### FR-GEO-109
Suportar no discovery Rastreamento, descoberta e acesso de crawlers sitemap XML `urlset`, sitemap index, gzip, RSS 2.0, Atom 1.0 e sitemap texto plano, mantendo somente URLs de página pertinentes ao formato em vez de confundir `<loc>` de extensões com páginas.

### FR-GEO-110
Avaliar, quando observável, limites de sitemap de 50 MB descompactado e 50.000 URLs, URLs absolutas, duplicatas, `lastmod`, extensões e presença de `priority`/`changefreq` sem representá-las como sinal de ranking.

### FR-GEO-111
Cruzar URLs de sitemap com a amostra efetivamente auditada para identificar não-2xx, `noindex`, canonical conflitante e bloqueio robots observados; ausência de uma URL auditada no sitemap deve permanecer diagnóstico de cobertura da amostra e não prova de erro global do site.

### FR-GEO-112
Expor separadamente Googlebot, OAI-SearchBot, GPTBot e Google-Extended de acordo com suas finalidades públicas; bloqueio de GPTBot ou Google-Extended não pode ser convertido automaticamente em bloqueio de Search.

### FR-GEO-113
Tratar Google-Extended como token de produto em robots.txt sem user-agent HTTP separado e declarar que ele não afeta inclusão/ranking na Pesquisa Google conforme documentação pública do Google.

### FR-GEO-114
Tentar `/llms.txt` somente same-origin quando a origem estiver tecnicamente apta; ausência ou erro deve ser informativo/non-scoring e presença deve ser persistível em `artifacts/m24/llms.txt`.

### FR-GEO-115
Tratar `llms.txt` como proposta comunitária experimental, não como web standard nem requisito universal de Search & AI, e nunca usá-lo como substituto de robots, sitemap, canonical, HTML semântico ou conteúdo acessível.

### FR-GEO-116
Registrar feeds RSS/Atom observados como sinais adicionais de discovery sem atribuir score obrigatório pela presença/ausência de feed.

### FR-GEO-117
Reportar configuração/submissão IndexNow como não determinável quando a auditoria passiva não possuir evidência explícita, log ou artifact verificável; não inferir sucesso de submissão por mera observação do site.

### FR-GEO-118
Expor a remediação técnica Rastreamento, descoberta e acesso de crawlers por `--ai-technical-remediation`, `--no-ai-technical-remediation` e `RASAI_AI_TECHNICAL_REMEDIATION`, com default público `false` e precedência CLI explícito → ambiente → false.

### FR-GEO-119
Restringir a IA Rastreamento, descoberta e acesso de crawlers a diagnósticos/evidências persistidos, rejeitar invenção de URL/policy/canonical/data/crawler token, exigir revisão humana e não permitir que o provider decida unilateralmente política de treinamento/crawler da organização.

### FR-GEO-120
Persistir estado/telemetria Rastreamento, descoberta e acesso de crawlers em tabelas auxiliares próprias, mantendo separação entre qualidade do website, diagnósticos técnicos e consumo de provider.

### FR-GEO-121
Materializar `report/crawling-discovery.html` com navegação/CSS compartilhados, robots/crawler policy, sitemaps/discovery, `llms.txt`, feeds, IndexNow, limitações de segurança, referências e eventual orientação técnica por IA.

### FR-GEO-122
Quando houver hard source blocker confirmado, Rastreamento, descoberta e acesso de crawlers deve evitar aquisição adicional de `/llms.txt` e chamada técnica de IA dependente do corpus, persistindo estado de skip/fail-open sem invalidar a auditoria principal.

## Requisitos Não Funcionais

### NFR-GEO-001
Executar em Windows.

### NFR-GEO-002
Preferencialmente sem privilégios administrativos.

### NFR-GEO-003
Não exigir database server, web server, Docker, IA ou GitHub para runtime local.

### NFR-GEO-004
Priorizar distribuição portátil.

### NFR-GEO-005
Resultados determinísticos devem ser reproduzíveis.

### NFR-GEO-006
Toda conclusão deve ser rastreável.

### NFR-GEO-007
Versionar auditor, ruleset, prompts, rendering policy, scoring, prioritization e contrato do relatório.

### NFR-GEO-008
Falhas localizadas não devem encerrar toda auditoria quando for possível continuar.

### NFR-GEO-009
Dados permanecem locais, exceto conteúdo explicitamente enviado a provider configurado.

### NFR-GEO-010
Resultado com cobertura/confiabilidade insuficiente não pode ser apresentado como conclusivo.

### NFR-GEO-011
O report site deve ser responsivo, imprimível, navegável localmente e sem dependências externas obrigatórias de runtime.

### NFR-GEO-012
RemediationRecipe e apresentação devem ser determinísticas/reprodutíveis a partir do estado persistido e versão do código/ruleset.

### NFR-GEO-013
Aplicabilidade e exclusão do Overall devem ser reproduzíveis a partir das RuleExecutions e versão do scoring.

### NFR-GEO-014
A projeção final não deve recalcular score/finding nem chamar IA; `audit.db` e artifacts permanecem fonte de verdade. Exceções arquiteturais explícitas, como Sugestões e remediação de conteúdo por IA e Rastreamento, descoberta e acesso de crawlers AI, devem concluir suas chamadas antes da projeção final correspondente; o renderer do report não chama provider.

### NFR-GEO-015
Sugestões e remediação de conteúdo por IA deve ser fail-open em relação ao audit: indisponibilidade da finalidade de remediação textual não pode invalidar score/findings já concluídos.

### NFR-GEO-016
Sugestões Sugestões e remediação de conteúdo por IA e JSON-LD devem permanecer advisory, reabríveis no `audit.db` e separadas dos objetos normativos de scoring.

### NFR-GEO-017
Web Performance externo deve permanecer opcional, default OFF para rede externa, com limite explícito de páginas e timeout configurável para impedir consumo PageSpeed/CrUX não previsto.

### NFR-GEO-018
Web Performance externo deve ser fail-open em relação à auditoria principal e não introduzir dependência obrigatória de PageSpeed, CrUX ou credencial Google para funcionamento de `SCORE-GEO-003`.

### NFR-GEO-019
Métricas Web Performance externo devem permanecer reabríveis a partir de `audit.db` + artifacts JSON sem nova chamada externa, preservando source, device, URL/origin scope e versão Lighthouse quando disponível.

### NFR-GEO-020
Web Performance externo não pode persistir API keys, URLs contendo parâmetros de chave, Authorization ou erro externo não sanitizado; telemetria de coleta deve permanecer separada da telemetria IA.

### NFR-GEO-021
Rastreamento, descoberta e acesso de crawlers deve permanecer fail-open e não pode introduzir dependência obrigatória de `llms.txt`, IndexNow ou provider de IA para executar a auditoria principal.

### NFR-GEO-022
Rastreamento, descoberta e acesso de crawlers deve limitar aquisição adicional automática ao escopo same-origin autorizado; declarações externas podem ser preservadas sem serem seguidas automaticamente.

### NFR-GEO-023
Resultados Rastreamento, descoberta e acesso de crawlers devem ser reabríveis a partir de `audit.db` + artifacts locais sem nova chamada externa para renderização do report.

### NFR-GEO-024
CI permanente deve cobrir compile da superfície Rastreamento, descoberta e acesso de crawlers, testes específicos de discovery/Rastreamento, descoberta e acesso de crawlers, regressões de integração afetadas e suíte completa antes de considerar mudanças Rastreamento, descoberta e acesso de crawlers homologadas.


### FR-GEO-173
A camada de apresentação não deve expor identificadores históricos de etapas de entrega; capacidades devem ser nomeadas pelo domínio funcional.

### FR-GEO-174
O HTML deve ser compreensível por analista de dados/SEO sem conhecimento do código, preservando apenas termos técnicos externamente documentados e difundidos, com contexto/glossário quando necessário.

### FR-GEO-175
Estados `UNAVAILABLE`, `INCOMPLETE`, ausência de evidência ou coleta não executada devem ser apresentados de forma neutra e nunca como resultado ruim, zero ou ausência de falha do website.
