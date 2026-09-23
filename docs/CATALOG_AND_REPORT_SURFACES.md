# Referência uniforme dos catálogos e superfícies do relatório

**Estado:** vigente.  
**Contrato de navegação:** `CATALOG-REPORT-002`.  
**Escopo:** todas as páginas HTML canônicas de `report-catalog/`.

Este documento define, com a **mesma estrutura**, o compromisso de cada catálogo e de cada página transversal do relatório. Nenhum CAT recebe tratamento normativo privilegiado: documentos específicos de domínio são aprofundamentos técnicos e não substituem esta referência.

## Estrutura normativa comum

Toda entrada abaixo usa exatamente os mesmos campos:

1. **Identificação**
2. **Propósito**
3. **Pergunta que responde**
4. **Entradas e fonte de verdade**
5. **Processamento**
6. **Uso de IA**
7. **Impacto no Índice de Prontidão / Método de Pontuação**
8. **Resultados apresentados**
9. **Estados e limitações**
10. **Rastreabilidade**
11. **Aprofundamento técnico**

Regras comuns:

- a fonte primária é sempre evidência persistida em `audit.db` e/ou artifacts contratados;
- HTML é projeção read-only e não executa coleta, scoring, provider ou IA;
- ausência de dado não é convertida automaticamente em falha;
- `UNKNOWN`, `ERROR` e `NOT_APPLICABLE` preservam semânticas distintas;
- IA não escolhe pesos de scoring nem altera fato determinístico já observado;
- documentos especializados detalham implementação, fórmulas ou integrações, mas não criam uma hierarquia entre CATs.

# Catálogos

## CAT-01 - Fundamentos técnicos e descoberta

**Identificação:** `CAT-01` - `cat-01.html` - Fundamentos técnicos e descoberta.

**Propósito:** validar a base técnica que permite descobrir, acessar, interpretar e rastrear o alvo auditado.

**Pergunta que responde:** o alvo pode ser descoberto, acessado, interpretado e controlado tecnicamente de forma coerente?

**Entradas e fonte de verdade:** respostas HTTP, redirects, robots.txt, sitemaps, `llms.txt` quando existente, links, snapshots, diretivas de indexabilidade, canonical, evidências de rendering e dados persistidos de padrões relacionados ao domínio técnico.

**Processamento:** regras determinísticas de discovery, crawling, indexabilidade, canonicalização, recuperação de conteúdo e integridade; integrações de padrões permanecem independentes quando configuradas.

**Uso de IA:** opcional somente onde o contrato prevê avaliação técnica evidence-bound já persistida; IA não substitui controles determinísticos.

**Impacto no Índice de Prontidão / Método de Pontuação:** **sim, quando a regra pertence explicitamente ao `SCORE-GEO-004`**. Diagnósticos auxiliares e integrações externas não entram automaticamente no score.

**Resultados apresentados:** estado de descoberta/acesso, regras aplicáveis, findings, evidências, recursos técnicos, limitações e recomendações relacionadas.

**Estados e limitações:** recurso ausente, indisponível ou não aplicável não equivale automaticamente a falha; pré-requisitos insuficientes bloqueiam conclusões derivadas.

**Rastreabilidade:** IDs `BR-GEO-*`, RuleExecution, Evidence, artifacts, configuração efetiva e origem do dado.

**Aprofundamento técnico:** `DISCOVERY_RESOURCES.md`, `RULES_GUIDE.md`, `STANDARDS_METRICS_AND_SERVICES.md` e `SARI_EXTERNAL_CRAWL_CORROBORATION.md`.

## CAT-02 - Acessibilidade

**Identificação:** `CAT-02` - `cat-02.html` - Acessibilidade.

**Propósito:** avaliar barreiras automatizáveis de acessibilidade e preservar evidência técnica separada de qualquer interpretação advisory.

**Pergunta que responde:** quais problemas de acessibilidade foram detectados automaticamente e em quais elementos/contextos?

**Entradas e fonte de verdade:** resultados persistidos de Lighthouse/axe e demais evidências automatizadas contratadas, quando a coleta correspondente foi executada.

**Processamento:** normalização de violações, severidade, elementos afetados, referências técnicas e estado da coleta.

**Uso de IA:** nenhum para determinar a existência da violação; eventual conteúdo advisory externo ao detector não redefine o resultado automatizado.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum impacto automático no `SCORE-GEO-004`**.

**Resultados apresentados:** violações, elementos afetados, severidade, contexto técnico, limitações e estado da fonte de acessibilidade.

**Estados e limitações:** diagnóstico automatizado não equivale a certificação integral WCAG; fonte não executada ou indisponível deve aparecer como estado neutro/limitado.

**Rastreabilidade:** execução da integração, artifact/evidência persistida, identificador oficial da regra quando disponível e snapshot/dispositivo relacionado.

**Aprofundamento técnico:** `LIGHTHOUSE_WEB_QUALITY.md`, `ACCESSIBILITY_PERFORMANCE_DOMAINS.md` e `EXTERNAL_METRICS_INTEGRITY.md`.

## CAT-03 - Conteúdo, semântica e dados estruturados

**Identificação:** `CAT-03` - `cat-03.html` - Conteúdo, semântica e dados estruturados.

**Propósito:** avaliar estrutura, significado, entidades, respostas, dados estruturados e contexto editorial aplicável.

**Pergunta que responde:** o conteúdo é semanticamente compreensível, estruturado, contextualizado e sustentado por evidências adequadas?

**Entradas e fonte de verdade:** HTML bruto/renderizado, conteúdo extraído, headings, title, entidades, JSON-LD, contexto editorial/YMYL configurado, RuleExecutions e evidências persistidas.

**Processamento:** validações determinísticas estruturais e análises semânticas/evidence-bound quando aplicáveis.

**Uso de IA:** opcional para contexto semântico, YMYL, E-E-A-T contextual e avaliações evidence-bound previstas pelo contrato; validações estruturais permanecem determinísticas.

**Impacto no Índice de Prontidão / Método de Pontuação:** **sim, para regras semânticas, de conteúdo, entidade, dados estruturados, answerability, citation/evidence trust e content value explicitamente mapeadas ao `SCORE-GEO-004`**.

**Resultados apresentados:** estrutura semântica, dados estruturados, entidades, contexto editorial, findings, evidências, limitações e recomendações.

**Estados e limitações:** ausência de contexto suficiente deve produzir estado limitado/indeterminado, não inferência inventada; E-E-A-T/YMYL não são notas oficiais de terceiros.

**Rastreabilidade:** regra, evidência, snapshot, contexto efetivo fornecido à análise e telemetria de IA quando usada.

**Aprofundamento técnico:** `CONTENT_ANALYSIS_CONTEXT.md`, `SEMANTIC_COHERENCE_AUDIT.md` e `GOVERNED_EVIDENCE_AI_PIPELINE.md`.

## CAT-04 - Web Performance

**Identificação:** `CAT-04` - `cat-04.html` - Web Performance.

**Propósito:** medir desempenho de laboratório/campo e evidenciar gargalos conforme as fontes configuradas.

**Pergunta que responde:** qual desempenho foi observado e quais métricas técnicas explicam a experiência medida?

**Entradas e fonte de verdade:** PageSpeed/Lighthouse, CrUX quando disponível, estado das integrações, artifacts e telemetria persistida de coleta.

**Processamento:** normalização de métricas de laboratório/campo, categorias solicitadas, diagnósticos e proveniência.

**Uso de IA:** nenhum para produzir as métricas; interpretação adicional não substitui as fontes oficiais.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum impacto automático no `SCORE-GEO-004`**.

**Resultados apresentados:** métricas de performance, Core Web Vitals quando disponíveis, categorias Lighthouse contratadas, diagnósticos e estado das fontes.

**Estados e limitações:** laboratório e campo são universos diferentes; indisponibilidade da API não é falha do website; ausência de CrUX pode refletir falta de amostragem pública.

**Rastreabilidade:** provider/fonte, timestamp, dispositivo, artifact, tentativa e configuração da coleta.

**Aprofundamento técnico:** `LIGHTHOUSE_WEB_QUALITY.md`, `LIGHTHOUSE_PAGESPEED_TRANSPORT.md` e `OPEN_WEB_METRICS.md`.

## CAT-05 - Search & AI Intelligence

**Identificação:** `CAT-05` - `cat-05.html` - Search & AI Intelligence.

**Propósito:** reunir observações de Search, SERP, GSC, visibilidade generativa e observabilidade sem fundir metodologias independentes.

**Pergunta que responde:** o que foi observado externamente sobre presença, descoberta, queries, concorrência e visibilidade, e como isso se relaciona ao alvo auditado?

**Entradas e fonte de verdade:** SERP Observation, Search Console, observability sidecar, imports generativos, Common Crawl quando aplicável, comparação competitiva e evidências persistidas.

**Processamento:** normalização por dataset/proveniência, comparação determinística, correlações e diagnósticos observacionais.

**Uso de IA:** opcional para Competitive AI e interpretação semântica evidence-bound; a página não chama IA durante a renderização.

**Impacto no Índice de Prontidão / Método de Pontuação:** **normalmente nenhum**. A exceção vigente é a corroboração positiva `BR-GEO-060`, quando elegível pelo contrato, com influência máxima controlada no grupo de Discovery.

**Resultados apresentados:** posições/estados observados, queries, candidatos competitivos, dados GSC, visibilidade generativa, observabilidade e limitações de cobertura.

**Estados e limitações:** observação externa não prova causalidade; `NOT_FOUND_WITHIN_DEPTH` não vira posição inventada; ausência de dataset não vira zero.

**Rastreabilidade:** dataset, provider, query/engine/mercado/dispositivo quando aplicável, artifact/SHA-256, timestamps e evidências relacionadas.

**Aprofundamento técnico:** `SEARCH_INTELLIGENCE_REPORT.md`, `SERP_OBSERVATION.md`, `GSC_OBSERVATIONAL_METRICS.md`, `EXTERNAL_OBSERVABILITY_INTEGRATIONS.md` e `COMPETITIVE_AI_INTELLIGENCE.md`.

## CAT-06 - Apdex de navegação

**Identificação:** `CAT-06` - `cat-06.html` - Apdex de navegação.

**Propósito:** mensurar navegação sintética segundo thresholds, amostras e carga definidos.

**Pergunta que responde:** qual foi a experiência sintética de navegação medida e como as amostras se distribuem entre satisfeitas, toleráveis e frustradas?

**Entradas e fonte de verdade:** execuções sintéticas, amostras, thresholds, perfis, tempos e estados persistidos.

**Processamento:** classificação de cada amostra e cálculo Apdex conforme o contrato sintético vigente.

**Uso de IA:** nenhum no cálculo.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum**. Apdex é domínio independente do Índice de Prontidão Search & IA.

**Resultados apresentados:** score Apdex, Satisfied/Tolerating/Frustrated, amostras, estabilidade, erros, perfil e parâmetros de execução.

**Estados e limitações:** resultado sintético não equivale a RUM; erro operacional e resultado de experiência são estados distintos; comparações exigem parâmetros compatíveis.

**Rastreabilidade:** run, sample, perfil, threshold `T`, dispositivo, timestamps e artifacts aplicáveis.

**Aprofundamento técnico:** `SYNTHETIC_APDEX.md`, `SYNTHETIC_SHARED_ACQUISITION.md` e `SYNTHETIC_RUNTIME_PROFILES.md`.

## CAT-07 - Apdex de experiência

**Identificação:** `CAT-07` - `cat-07.html` - Apdex de experiência.

**Propósito:** mensurar experiência sintética e distribuição populacional sobre a base de navegação contratada.

**Pergunta que responde:** como a experiência sintética se distribui para os perfis e ações configurados?

**Entradas e fonte de verdade:** runs/amostras de Synthetic User Experience, perfis, KPM/fallback, thresholds e dados de navegação reutilizáveis quando aplicáveis.

**Processamento:** cálculo do Apdex de experiência, classificação populacional e diagnósticos de estabilidade/erro.

**Uso de IA:** nenhum no cálculo.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum**.

**Resultados apresentados:** Apdex de experiência, distribuição populacional, perfil, amostras, estados, comparabilidade e limitações.

**Estados e limitações:** experiência sintética não é RUM; o resultado depende do perfil e da configuração de amostragem; fallback deve permanecer identificável.

**Rastreabilidade:** run, sample, perfil, dispositivo, KPM/fallback efetivo, threshold e configuração persistida.

**Aprofundamento técnico:** `SYNTHETIC_USER_EXPERIENCE_APDEX.md`, `SYNTHETIC_SHARED_ACQUISITION.md` e `SYNTHETIC_RUNTIME_PROFILES.md`.

## CAT-08 - Análise profunda e melhorias

**Identificação:** `CAT-08` - `cat-08.html` - Análise profunda e melhorias.

**Propósito:** consumir evidências já produzidas pelos catálogos selecionados e gerar análise adicional multidimensional, evidence-bound.

**Pergunta que responde:** considerando as evidências disponíveis, quais problemas e oportunidades merecem prioridade e por quê?

**Entradas e fonte de verdade:** findings, métricas, evidências, contexto de conteúdo, Search, performance, acessibilidade, segurança e demais dados persistidos elegíveis.

**Processamento:** seleção e compactação governada de contexto, análise correlacional e priorização sobre o corpus persistido.

**Uso de IA:** **obrigatório para produzir o resultado próprio do CAT-08**; usa o orquestrador principal, contexto governado e telemetria canônica.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum**. CAT-08 interpreta evidências e não recalcula nem altera `SARI-001`/`SCORE-GEO-004`.

**Resultados apresentados:** prioridades, explicações, correlações, benefícios esperados, esforço, ações e referências às evidências de origem.

**Estados e limitações:** IA deve declarar insuficiência quando necessário; correlação não é causalidade; recomendações não são garantia de ganho.

**Rastreabilidade:** run de Improvement Intelligence, evidence IDs, provider/modelo, prompt/contexto governado, tentativa, tokens e custo.

**Aprofundamento técnico:** `IMPROVEMENT_INTELLIGENCE.md`, `AI_DEPENDENCY_TRACEABILITY.md` e `GOVERNED_EVIDENCE_AI_PIPELINE.md`.

## CAT-09 - Remediações

**Identificação:** `CAT-09` - `cat-09.html` - Remediações.

**Propósito:** transformar findings e evidências em ações técnicas/editoriais rastreáveis.

**Pergunta que responde:** o que deve ser corrigido, por que, onde e como validar a correção?

**Entradas e fonte de verdade:** findings, RuleExecutions, Evidence, causa raiz/elemento quando identificáveis, recomendações determinísticas e contexto persistido.

**Processamento:** governança da recomendação, classificação do alvo, precisão da correção, exemplos técnicos quando sustentáveis e critérios de verificação.

**Uso de IA:** opcional para contextualização e exemplos adicionais; remediações determinísticas permanecem válidas sem IA.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum direto**. Aplicar uma remediação exige nova auditoria para medir novo estado.

**Resultados apresentados:** problema, alvo, evidência, causa/contexto, ação, exemplo quando seguro, severidade/prioridade e validação esperada.

**Estados e limitações:** recomendações de terceiros, estados neutros e problemas internos do auditor não devem ser convertidos em ação do cliente sem evidência adequada.

**Rastreabilidade:** finding, evidence, regra, seletor/elemento quando disponível, origem da recomendação e IA quando utilizada.

**Aprofundamento técnico:** `RECOMMENDATION_GOVERNANCE.md`, `ROOT_CAUSE_REMEDIATION_GUIDE.md` e `REQUEST_REMEDIATION_INTELLIGENCE.md`.

## CAT-10 - Segurança passiva

**Identificação:** `CAT-10` - `cat-10.html` - Segurança passiva.

**Propósito:** avaliar postura de segurança web observável por meios passivos, sem exploração ativa.

**Pergunta que responde:** quais riscos, controles e vulnerabilidades conhecidas podem ser sustentados pelas evidências passivamente observadas?

**Entradas e fonte de verdade:** HTTP/TLS observável, headers, cookies sem valores sensíveis, recursos first/third-party, HTML/browser/runtime, componentes/versionamento identificáveis, MDN HTTP Observatory, OSV e CISA KEV quando aplicáveis.

**Processamento:** análise determinística passiva, identificação governada de componentes/versões, correlação de vulnerabilidades e remediação por finding.

**Uso de IA:** opcional e advisory após consolidação da evidência; IA não decide presença de controle, versão ou CVE.

**Impacto no Índice de Prontidão / Método de Pontuação:** **nenhum impacto automático no `SCORE-GEO-004`**.

**Resultados apresentados:** cobertura, findings, severidade/classificação, componentes, correlações CVE/KEV, evidências, contenção/correção e validação.

**Estados e limitações:** não executa pentest, exploit, brute force, fuzzing, bypass ou port scan; ausência de finding não significa certificação de segurança.

**Rastreabilidade:** run, recurso, componente, integração, advisory, finding, remediation, artifact e origem externa quando houver.

**Aprofundamento técnico:** `PASSIVE_SECURITY_CATALOG.md`.

# Páginas transversais do relatório

## Visão geral

**Identificação:** `overview` - `index.html` - Visão geral.

**Propósito:** sintetizar o estado da auditoria e orientar a navegação.

**Pergunta que responde:** qual é o estado geral desta AUD e onde estão os resultados relevantes?

**Entradas e fonte de verdade:** resultados persistidos da auditoria, estados dos CATs, Índice de Prontidão Search & IA, fulfillment e dados necessários à Matriz de encerramento estrutural.

**Processamento:** agregação de apresentação; não cria nova análise.

**Uso de IA:** somente projeta resultados de IA já persistidos.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum; apresenta valores existentes.

**Resultados apresentados:** síntese executiva, estado dos CATs, indicadores principais e Matriz de encerramento estrutural.

**Estados e limitações:** resumo não substitui páginas de detalhe; percentual/estado deve preservar o significado do domínio.

**Rastreabilidade:** links para CATs, Índice de Prontidão Search & IA, evidências, método de pontuação e demais superfícies.

**Aprofundamento técnico:** `REPORT_GUIDE.md` e `REPORT_PRESENTATION_CONTRACT.md`.

## Índice de Prontidão Search & IA

**Nome em inglês:** **Search & AI Readiness Index**  
**Tradução:** **Índice de Prontidão Search & IA**  
**Versão pública:** **001**  
**Identificação técnica:** `sari` - `sari.html` - ID metodológico `SARI-001`.

**Propósito:** apresentar o índice, dimensões, Cobertura, Confiança, Consolidação e Critérios Críticos de Prontidão.

**Pergunta que responde:** qual prontidão foi medida, com qual cobertura e força de medição?

**Entradas e fonte de verdade:** scores e contribuições persistidos em `audit.db`.

**Processamento:** somente leitura/apresentação do scoring já calculado.

**Uso de IA:** nenhuma chamada na página; evidências produzidas anteriormente podem ter participado de regras contratadas.

**Impacto no Índice de Prontidão / Método de Pontuação:** é a projeção do resultado; não recalcula o índice.

**Resultados apresentados:** Overall, dimensões, Coverage, Confidence, Consolidation, limitações e Critical Readiness Gates.

**Estados e limitações:** Score, Coverage, Confidence e Consolidation não são sinônimos.

**Rastreabilidade:** IDs técnicos `SARI-001`, `SCORE-GEO-004`, registros de pontuação, contribuições, regras e evidências.

**Aprofundamento técnico:** `SARI_READINESS_INDEX.md`, `SCORE_GEO_004.md` e `SCORING_GUIDE.md`.

## Análise Direcionada

**Identificação:** `directed-analysis` - `directed-analysis.html` - Análise Direcionada.

**Propósito:** transformar dados já coletados em estratégia de ação multidimensional com referências às origens.

**Pergunta que responde:** quais ações priorizadas podem melhorar os domínios avaliados e em quais evidências elas se baseiam?

**Entradas e fonte de verdade:** resultados dos CATs, findings, evidências, métricas e contexto persistido elegível.

**Processamento:** correlação estratégica e priorização sobre dados existentes.

**Uso de IA:** conforme contrato da Análise Direcionada e somente sobre contexto governado; reconstrução não implica nova chamada quando o contexto não mudou.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum; é análise estratégica derivada.

**Resultados apresentados:** ações, benefício, esforço, prioridade, racional e links para CAT/seção/evidência.

**Estados e limitações:** não inventa evidência nem garante ganho; ausência de base suficiente deve ser explícita.

**Rastreabilidade:** ação -> tópico -> CAT -> seção -> evidence/finding de origem e telemetria de IA quando aplicável.

**Aprofundamento técnico:** `DIRECTED_ANALYSIS.md`.

## Captura e contexto

**Identificação:** `capture-context` - `capture-context.html` - Captura e contexto.

**Propósito:** expor o universo efetivamente observado e a topologia de captura.

**Pergunta que responde:** o que exatamente foi capturado, em qual contexto, dispositivo e escopo?

**Entradas e fonte de verdade:** snapshots, páginas, browser metadata, identidade ORIGIN/URL/DEVICE_SNAPSHOT/PROFILE_MEASUREMENT e configuração relacionada.

**Processamento:** organização de contexto persistido.

**Uso de IA:** nenhum.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum direto.

**Resultados apresentados:** topologia de captura, dispositivos, páginas/snapshots, variações e contexto operacional.

**Estados e limitações:** descreve observação realizada, não extrapola para universos não capturados.

**Rastreabilidade:** audit ID, page/snapshot IDs, device, timestamps e metadata.

**Aprofundamento técnico:** `CAPTURE_CONTEXT_MODEL.md`.

## Evidências da execução

**Identificação:** `execution-evidence` - `execution-evidence.html` - Evidências da execução.

**Propósito:** demonstrar o que foi solicitado, executado, atendido, bloqueado ou não solicitado.

**Pergunta que responde:** a configuração escolhida foi realmente cumprida e quais dependências explicam pendências?

**Entradas e fonte de verdade:** snapshot secret-free da configuração, fulfillment, work-items, tentativas e estados persistidos.

**Processamento:** projeção de proveniência operacional e integridade.

**Uso de IA:** nenhum.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum; pode explicar por que medição ficou parcial/pendente.

**Resultados apresentados:** capacidades solicitadas, estado efetivo, erros, tentativas, dependências e integridade da configuração.

**Estados e limitações:** distingue `DISABLED`, `NOT_APPLICABLE`, pendência recuperável, bloqueio e falha.

**Rastreabilidade:** configuration hash, work-item, tentativa, componente, scope e erro persistido.

**Aprofundamento técnico:** `EXECUTION_EVIDENCE_AND_CONFIGURATION_INTEGRITY.md` e `AUDIT_REPROCESSING.md`.

## IA e integrações

**Identificação:** `ai-integrations` - `ai-integrations.html` - IA e integrações.

**Propósito:** apresentar uso, disponibilidade, tentativas e custo das integrações externas e de IA.

**Pergunta que responde:** quais integrações foram usadas, com quais resultados, custos e limitações?

**Entradas e fonte de verdade:** telemetria persistida de providers, integrações, tentativas, tokens, custo e estados.

**Processamento:** agregação de telemetria; não executa integração.

**Uso de IA:** a página registra uso de IA, mas não inicia chamada.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum por custo/telemetria; somente regras explicitamente contratadas podem ter utilizado evidência produzida antes.

**Resultados apresentados:** provider/modelo, status, tentativas, tokens, custo estimado, reasoning configurado quando disponível e falhas/retries.

**Estados e limitações:** custo é estimativa operacional, não invoice; uso ausente não deve ser inventado.

**Rastreabilidade:** attempt/session IDs, provider/modelo, timestamps, uso e contrato semântico quando aplicável.

**Aprofundamento técnico:** `AI_RUNTIME_ORCHESTRATION.md`, `CONSOLE_COST_AND_USAGE.md` e `REPORTING_AI_USAGE.md`.

## Metodologia e scoring

**Identificação:** `methodology` - `methodology.html` - Metodologia e scoring.

**Propósito:** explicar o contrato metodológico aplicado à AUD.

**Pergunta que responde:** como o RASAi transformou evidências em scores, cobertura, confiança e estados?

**Entradas e fonte de verdade:** `scoring_version`, pesos, grupos, gates, scores e limitações persistidas.

**Processamento:** documentação/apresentação do método; não recalcula resultados.

**Uso de IA:** fórmula, pesos e thresholds são determinísticos; IA não escolhe pesos.

**Impacto no Índice de Prontidão / Método de Pontuação:** explica o método usado, sem alterá-lo.

**Resultados apresentados:** fórmula, dimensões, pesos, fatores, Coverage, Confidence, Consolidation, gates e reprodutibilidade.

**Estados e limitações:** versão metodológica pertence ao conteúdo/metadata, não ao filename.

**Rastreabilidade:** `SCORE-GEO-004`, versões auxiliares de pesos/gates e IDs metodológicos.

**Aprofundamento técnico:** `SCORE_GEO_004.md`, `SCORING_GUIDE.md` e `SARI_READINESS_INDEX.md`.

## Índices e métricas

**Identificação:** `metrics` - `metrics.html` - Índices e métricas.

**Propósito:** inventariar métricas persistidas sem misturar metodologias independentes.

**Pergunta que responde:** quais métricas foram observadas/calculadas, de qual domínio e com qual contexto?

**Entradas e fonte de verdade:** métricas persistidas do Índice de Prontidão Search & IA, performance, Apdex, observabilidade, padrões e outros domínios habilitados.

**Processamento:** inventário e rotulagem de apresentação.

**Uso de IA:** nenhum cálculo por IA nesta página.

**Impacto no Índice de Prontidão / Método de Pontuação:** nenhum adicional; cada métrica mantém o contrato do seu domínio.

**Resultados apresentados:** indicador, valor, contexto, tipo, confiança/proveniência quando aplicável.

**Estados e limitações:** não compara diretamente grandezas incompatíveis nem transforma ausência em zero.

**Rastreabilidade:** domínio, fonte, artifact/dataset e identificadores persistidos.

**Aprofundamento técnico:** `GLOSSARY.md`, `INDICATOR_PROVENANCE.md`, `OPEN_WEB_METRICS.md` e documentos específicos de cada métrica.

## Recursos do pacote que não são páginas analíticas

`manifest.json`, `integrity/` e `css/site.css` integram o pacote `report-catalog/`, mas não são páginas analíticas. O manifest e os artifacts de integridade suportam verificação/rastreabilidade; o CSS é apenas apresentação.

## Relação com documentos especializados

A existência de documentação detalhada para um domínio não altera o nível hierárquico do CAT correspondente. Assim:

- CAT-06 não é mais ou menos normativo porque existe `SYNTHETIC_APDEX.md`;
- CAT-08 não é mais ou menos normativo porque existe `IMPROVEMENT_INTELLIGENCE.md`;
- CAT-10 não é mais ou menos normativo porque existe `PASSIVE_SECURITY_CATALOG.md`.

Todos os CATs têm seu contrato primário nesta referência uniforme. Os documentos especializados apenas aprofundam implementação, configuração, fórmulas, integrações e limitações próprias do domínio.
