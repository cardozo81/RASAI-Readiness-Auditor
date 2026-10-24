# AUD-A167: descoberta bounded, armazenamento e elegibilidade GEO/semântica

AUD de referência: `AUD-A16711D11A8A40BDA303A362C45CCEDD` (NYTimes, uma URL). Os resultados históricos, seu SQLite, artefatos e scores **não são sobrescritos** por este macrolote.

## Lote 1 - descoberta, tempo e volume

- **Limites explícitos de aquisição**, separados de `max_pages`: `sitemap_resource_budget=max(12, min(128, max_pages*4))`; para auditoria de uma página, são até **12 recursos de sitemap**, independentemente dos links publicados. `discovery_candidate_budget=max(2000,min(50000,max_pages*100))`: para uma página, até **2000 candidatos retidos**.
- Limite aplicado tanto a `DiscoveryEngine.discover` quanto a `discover_url_set`. Uma descoberta truncada emite `SITEMAP_RESOURCE_BUDGET_EXHAUSTED` e/ou `DISCOVERY_CANDIDATE_BUDGET_EXHAUSTED` em `audits.limitations`. `MAX_PAGES_REACHED` mantém o seu significado de universo de páginas.
- O M24 preserva o inventário efetivamente adquirido e emite `M24-SITEMAP-BOUNDED-INVENTORY` sem alegar ausência de URL nos sitemaps quando o inventário está incompleto. A ausência isolada de arquivo convencional continua não sendo falha SEO.
- Deduplicação de URLs agora é linear em listas grandes (conjuntos auxiliares); evita comparação quadrática em coletores e M24.
- Respostas `/sitemap.xml.gz` já descomprimidas pelo transporte passam pelo parser XML, sem segunda descompressão baseada no nome; bytes que realmente começam com magic gzip seguem o descompressor bounded.
- A tabela `evidence` não duplica mais inventários completos de sitemap: `page_urls` e `child_sitemaps` contêm até 16 referências por recurso com `inventory_projection=SAMPLE_16_RAW_ARTIFACT_AUTHORITATIVE`, contagens completas e SHA-256 da lista processada. O corpo HTTP original permanece acessível pelo mesmo `artifact_reference` para o M24, relatório e reconciliação. Não apagar artefatos, arquivos de integridade nem evidências históricas.

## Lote 2 - consultas e proveniência do bloqueio de IA

- A preparação CAT-05 exibe alinhamento entre termos SERP e Perplexity, distinguindo consulta equivalente de divergência sem alegar equivalência de localização, idioma, janela temporal ou dispositivo. O consentimento para Perplexity continua **por execução**, com autorização comercial específica; não há mudança automática dos termos nem requisição adicional.
- O GEO exibe as consultas efetivamente persistidas (quando ambas têm fontes verificáveis) ao explicar `NO_EQUIVALENT_OBSERVED_SERP_QUERY`. A comparação continua `N/D`, não vira zero de participação nem ausência de citação generativa.
- Para um caso estreito em que o HTTP bruto retornou **403**, mas o *mesmo snapshot da AUD* possui Chromium **200**, conteúdo principal material, estado `READY/RECOVERED`, hash SHA-256 do DOM preso à captura e texto extraído substancial, o M7 pode analisar o conteúdo renderizado. `BR-GEO-006`, `BR-GEO-009` e `BR-GEO-020` mantêm seus resultados técnicos originais (não viram PASS). Esse caminho é independente de coleta externa adicional e não permite liberar HTML sem hash correspondente.
- Em caso de artefato inexistente/trocado, contexto de AUD divergente, RAW HTTP diferente de 403, texto insuficiente, qualidade incompleta ou SHA inconsistente, o gate permanece bloqueado, com custo de IA zero antes do gate.
- A elegibilidade de análise não certifica que a página seja indexável nem garante qualidade de conteúdo para buscadores. Scores dependem de regras por dimensão e seu universo efetivo; a exceção é exclusivamente de fonte semântica renderizada.

## Validação focal

Executar somente regressões offline `test_sitemap_budget_aud_a167.py` e `test_a167_semantic_geo_alignment.py`. Não ligar SERP/Perplexity reais, não iniciar Docker/browser, não provocar cobrança, não modificar auditorias já seladas. O aceite físico futuro compara volume/tempo em uma nova AUD e confirma diagnóstico caso a descoberta precise ser truncada.
