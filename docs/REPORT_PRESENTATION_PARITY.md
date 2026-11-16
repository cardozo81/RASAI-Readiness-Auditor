# Issue #710 - matriz de paridade informacional e arquitetura editorial

Baseline de análise: `e26d87c038c551e923d30468d9eae5bb6c145fa7` (`main`, merge da PR #709).

Esta matriz antecede a implementação da #710. Ela descreve **paridade de fatos materiais e propósito**, não equivalência visual, HTML-a-HTML ou página-a-página. `audit.db + artifacts` continuam sendo a fonte de verdade material; `report-catalog/` é a projeção canônica auditável; `report-presentation/` permanece uma projeção executiva derivada e read-only.

## Invariantes da decisão

- nenhuma coleta, probe, provider, Search API ou chamada de IA é executada para preencher a apresentação;
- ausência, não solicitação, falha de coleta, bloqueio, não aplicabilidade e observação continuam estados distintos;
- nenhuma ausência vira zero, sucesso ou falha do website;
- nenhuma nova fonte de verdade é criada;
- UI/UX, componentes, navegação, rail, CSS, JavaScript e padrões de acessibilidade existentes são reutilizados;
- detalhe técnico pode permanecer no catálogo/anexo quando a decisão humana recebe síntese suficiente e link explícito;
- família persistida desconhecida não pode ser classificada como “IA, custos e proveniência” por fallback.

## Diagnóstico da arquitetura atual

A apresentação possui dez páginas: Painel, Extração, Descoberta e padrões, Índices, Conteúdo e acessibilidade, Performance e experiência, Search e GEO, Segurança passiva, Plano de ação e IA/custos/proveniência.

Foram identificados três problemas arquiteturais objetivos:

1. `read_model.destination()` envia toda família persistida não reconhecida para `ia-custos`, transformando ausência de roteamento em classificação semântica incorreta.
2. A sonda de rede complementar é resumida em `performance.html`, apesar de responder a uma pergunta distinta de Web Performance e Apdex e possuir escopo próprio de DNS/TCP/TLS/traceroute/ASN/GeoIP.
3. A contagem de scripts da segurança passiva também é acrescentada a `performance.html`, embora pertença à superfície de segurança.

A lacuna de rede é maior que o resumo atual: o catálogo já representa estados de captura e probe, IP público observado, HTTP/TLS, redirects, DNS, TCP/TLS, traceroute, target reached, ASN, GeoIP, precisão, fonte, data, mapa/rota/cronologia e diagnóstico determinístico quando sustentado.

## Matriz canônica `report-catalog -> report-presentation`

| Origem canônica | Propósito | Dados/fatos materiais | Estado atual em presentation | Cobertura | Destino editorial proposto | Justificativa |
| --- | --- | --- | --- | --- | --- | --- |
| `index.html` | Visão geral da AUD | identidade, alvo, estado, síntese, contexto de leitura | Painel + Extração | Parcial adequada | Painel + Extração | Painel deve responder “o que foi auditado e qual o estado”; detalhes de captura permanecem em Extração. |
| `sari.html` | Índice de Prontidão Search & IA | índice, dimensões, cobertura, confiança, consolidação | Painel + Índices | Adequada | Painel + Índices | Síntese no Painel e decomposição em Índices preservam a hierarquia editorial. |
| `cat-01.html` | Fundamentos técnicos e descoberta | robots, sitemap, llms.txt, crawling, padrões e estados de serviços | Descoberta e padrões | Adequada | Descoberta e padrões | Fronteira conceitual já correta. |
| `cat-02.html` | Acessibilidade | score Lighthouse quando persistido, findings e evidências de acessibilidade | Conteúdo e acessibilidade + Performance | Parcial adequada | Conteúdo e acessibilidade + Performance | Findings pertencem à leitura de conteúdo/acessibilidade; score Lighthouse permanece junto ao conjunto de métricas de laboratório, sem misturar denominadores. |
| `cat-03.html` | Conteúdo, semântica e dados estruturados | contexto editorial, coerência, JSON-LD e evidências semânticas | Conteúdo e acessibilidade | Adequada | Conteúdo e acessibilidade | Fronteira conceitual já correta. |
| `cat-04.html` | Web Performance | Lighthouse, laboratório, campo, CWV, fonte/escopo e indisponibilidades | Performance e experiência | Adequada | Performance e experiência | Página já distingue laboratório, campo e sintético. |
| `cat-05.html` | Search & AI Intelligence | SERP, fontes Search, comparação, observabilidade e limitações | Search e GEO; previews contextuais no Painel/Performance | Parcial adequada | Search e GEO; previews somente quando denominador é explícito | Search e GEO continua superfície responsável; CrUX histórico permanece em Performance por ser métrica de experiência, não ranking. |
| `cat-06.html` | Apdex de navegação | amostras, thresholds, distribuição e limitações | Performance e experiência | Adequada | Performance e experiência | Mesmo domínio de experiência, com denominador próprio explícito. |
| `cat-07.html` | Apdex de experiência | população sintética, amostras, thresholds e erros | Performance e experiência | Adequada | Performance e experiência | Mesmo domínio de experiência, sem fundir com Apdex de navegação. |
| `cat-08.html` | Análise profunda e melhorias | findings, recomendações evidence-bound e correlações | Conteúdo e acessibilidade + Plano de ação | Adequada | Conteúdo e acessibilidade + Plano de ação | Evidência fica no domínio observado; ação governada fica no plano. |
| `cat-09.html` | Remediações | ações técnicas/editoriais e validação | Plano de ação | Adequada | Plano de ação | Fronteira conceitual já correta. |
| `cat-10.html` | Segurança passiva | cobertura, scripts, findings, severidade, limitações e remediação | Segurança passiva; contagem de scripts também em Performance | Parcial / deslocada | Segurança passiva | Script observado é evidência de segurança passiva, não métrica de Web Performance. |
| `network.html` | Rede e conectividade | captura passiva, probe autorizado, DNS/TCP/TLS, IP, traceroute, ASN/GeoIP, cronologia e limitações | Performance e experiência, apenas DNS/TCP/TLS resumidos | Parcial / deslocada | **Nova página Rede e conectividade** | Há propósito próprio, fontes/instantes distintos, estados próprios e volume incompatível com Performance. A página evita mistura conceitual e reutiliza o design system existente. |
| `geo.html` | GEO - inteligência competitiva | observações, fontes, comparação e contexto | Search e GEO | Adequada | Search e GEO | Fronteira conceitual já correta. |
| `geo-content-review.html` | Análise reversa SEO/GEO | evidência editorial, semântica e contexto de Search e GEO | Conteúdo e acessibilidade + Search e GEO | Adequada | Conteúdo e acessibilidade + Search e GEO | Dupla projeção é intencional porque a superfície conecta conteúdo observado ao contexto Search e GEO sem fundir as fontes. |
| `directed-analysis.html` | Análise direcionada | inventário de ações, fases e governança | Plano de ação | Adequada | Plano de ação | Fronteira conceitual já correta. |
| `capture-context.html` | Contexto de captura | snapshots, URL solicitada/final, device, timestamp e arquitetura observada | Extração | Adequada | Extração | Fronteira conceitual já correta. |
| `execution-evidence.html` | Evidências da execução | seleção, fulfillment, estado funcional, configuração e pendências | Painel + IA/custos/proveniência | Parcial adequada | Painel; IA/custos apenas para evidência realmente pertencente a IA | O estado global fica no Painel. Evidência específica de IA pode continuar em IA/custos; famílias desconhecidas deixam de cair ali. |
| `ai-integrations.html` | IA e integrações | prontidão, fallback, provider/modelo, tentativas e estados | IA, custos e proveniência | Adequada | IA, custos e proveniência | Fronteira conceitual já correta. |
| `methodology.html` | Método de pontuação | versão, regras, pesos, limites e interpretação | Índices | Adequada | Índices | Fronteira conceitual já correta. |
| `metrics.html` | Índices e métricas | métricas, thresholds, escopos e telemetria | Índices + Performance | Adequada | Índices + Performance | Destino depende da natureza da métrica; não há necessidade de nova página. |

## Cobertura de superfícies transversais exigidas pela #710

| Superfície transversal | Representação editorial | Decisão |
| --- | --- | --- |
| Readiness / scoring | Painel + Índices | manter |
| Contexto de captura / evidências da execução | Extração + Painel | manter |
| Mobile / Desktop | dispositivo preservado em captura, índices, performance e Search quando materializado | não criar páginas por device |
| Acessibilidade | Conteúdo e acessibilidade + score Lighthouse em Performance quando persistido | manter separação entre findings e métrica |
| Performance | Performance e experiência | manter |
| Padrões | Descoberta e padrões | manter |
| Apdex navegação / experiência | Performance e experiência, com universos independentes | manter |
| Search Intelligence / GEO / observabilidade | Search e GEO, com previews somente quando a fonte e o denominador são explícitos | manter |
| Rede / conectividade | nova página Rede e conectividade | criar superfície própria |
| Segurança passiva | Segurança passiva | remover conteúdo deslocado em Performance |
| Improvement Intelligence | Conteúdo + Plano conforme evidência versus ação | manter |
| Conteúdo / JSON-LD | Conteúdo e acessibilidade | manter |
| Remediações | Plano de ação | manter |
| IA / custos / proveniência | IA, custos e proveniência | manter, eliminando fallback genérico |
| Assurance / qualidade | Painel, manifesto, paridade e links técnicos; sem novo score | manter como qualificação/transversal |
| Referências / metodologia | Índices + links explícitos para páginas técnicas canônicas | manter |

## Arquitetura resultante

A apresentação passa de 10 para **11 páginas** apenas porque rede satisfaz os critérios de nova superfície:

- propósito de leitura distinto: conectividade e evidência de transporte;
- fronteira conceitual clara em relação a Web Performance/Apdex;
- volume próprio: captura, probe, estados, DNS, TCP, TLS, traceroute, ASN, GeoIP e cronologia;
- ausência de duplicação: Performance deixa de hospedar o resumo de rede;
- ganho objetivo de decisão: leitor consegue distinguir “experiência web” de “caminho/observação de rede”.

A nova página reutiliza integralmente o shell, navegação, rail, componentes e assets existentes. Não há redesign.

### Política de roteamento

O roteamento passa a ter dois resultados legítimos:

1. **editorial**: família conhecida e semanticamente mapeada para uma página;
2. **technical-only**: família não reconhecida permanece no anexo sanitizado e no mapa de cobertura, sem ser classificada artificialmente em uma página.

`technical-only` não significa dado descartado: a família continua inventariada, hashada, exportada no anexo e registrada no `coverage-map.json`. O mapa deve registrar explicitamente `page: null` e a representação técnica, evitando a falsa associação com IA/custos.

## Escopo da implementação derivado desta matriz

1. adicionar `rede.html` ao contrato interno da apresentação e à navegação;
2. projetar nela somente fatos de rede já persistidos/verificados na mesma AUD;
3. preservar estados por métrica e separar captura passiva de probe complementar;
4. mostrar ausência de probe como indisponibilidade/N/D, nunca falha de conectividade;
5. incluir DNS, TCP/TLS, IP, traceroute/target reached, ASN e GeoIP quando materializados, com escopo, precisão e proveniência;
6. manter cronologia da fonte no Painel e também contextualizar a origem na página de rede;
7. mover a contagem de scripts de segurança para `seguranca.html`;
8. eliminar o fallback de famílias desconhecidas para `ia-custos.html`;
9. atualizar `coverage-map.json` para refletir cobertura real e `technical-only`;
10. adicionar link de aprofundamento para `../report-catalog/network.html`;
11. incrementar somente a versão interna do gerador da apresentação para invalidar pacotes de 10 páginas incompatíveis;
12. manter produto/SemVer, scoring, report-catalog, coletores e fontes inalterados.

## Fora de escopo

Não são autorizados nesta implementação: nova coleta, nova sonda, chamada de IA, recomputação de score, alteração de `audit.db`, alteração de artifacts-fonte, mudança em `report-catalog`, redesign, NDR novo, inferência de causa/rota/IP/ASN ou reescrita de resultados históricos.


## Auditoria complementar de paridade semântica - 15/11/2026

**Status: NO-GO para merge até a homologação na AUD real.** Este adendo registra correções no código da mesma PR #711, sem alegar execução física ou equivalência de fatos da auditoria piloto. A fonte de verdade é `audit.db` e sidecars íntegros, **não** o HTML da superfície técnica. A exigência é equivalência de interpretação, estados e decisão, não igualdade visual ou de quantidade de páginas. O catálogo mantém 21 páginas e a apresentação, 11. Os 46 testes Windows comunicados anteriormente e o CI 9/9 referem-se ao HEAD anterior às correções abaixo; repetir somente os gates focalizados e os checks do HEAD novo.

### Rastreio do conteúdo por domínio e página

As fontes abaixo são contratos de leitura potencial; cada fato só deve aparecer quando existir e corresponder à AUD. `PASS` requer comparação material entre os pacotes gerados da piloto, não apenas campo roteado. O status de homologação neste adendo é `PARTIAL` até essa comparação.

| Destino executivo | Fonte persistida / sidecar; identidade | Conteúdo material requerido e proveniência | Estado/decisão e profundidade técnica | Homologação |
| --- | --- | --- | --- | --- |
| `index.html` | `audits`, `audit_targets`, `audit_fulfillment_work_items`, `recommendation_governance`; audit_id, source_kind/source_id | Alvo, dispositivos, começo/fim, resultado, decisões materializadas, indicadores e pendências | N/D distinto de falha; catálogo `index.html` e `execution-evidence.html` para detalhe da execução | PARTIAL |
| `extracao.html` | `page_snapshots`, `evidence`, sidecars e referências SHA-256; snapshot_id | URL solicitada/observada, capturas, tempo, evidência e arquitetura observada | Status de fonte e limite do DOM; `capture-context.html` e anexos para prova física | PARTIAL |
| `descoberta.html` | `m24_*`, `standards_*`; regra, ocorrência e evidência | Crawling, descoberta, serviços, estados, método e limites | Ausência não equivale a erro do website; `cat-01.html` conserva o detalhamento W3C/posições | PARTIAL |
| `indices.html` | `scores`, `score_contributions`, `rule_executions`; score_id/dimensão | SARI e demais índices, confiança, cobertura e decomposição somente quando materializada | Valor medido preservado sem contribuições inventadas; `sari.html`/`methodology.html` | PARTIAL |
| `conteudo.html` | `content_*`, `semantic_*`, `jsonld_*`, snapshots e projeção offline contextual; task_id/source_ref/SHA | FAQ/SPA/DOM, alegação, evidência observada, verificação editorial, procedimento de validação | `VALIDACAO_NECESSARIA` não é defeito SEO; `geo-content-review.html` conserva ocorrências exaustivas | PARTIAL |
| `performance.html` | `web_performance_*`, `synthetic_*`; URL/device/profile e janela amostral | Lighthouse lab, CrUX/campo, p75 e Apdex em universos separados | Sem supor histórico ausente; `cat-04.html`, `cat-06.html`, `cat-07.html` para amostras e limiares | PARTIAL |
| `rede.html` | Pacote passivo verificado, probes autorizados, função determinística `build_network_assessment`; audit_id/ref da sessão | DNS/TCP/TLS/IP, hops/RTT/ASN/GeoIP quando observados; confiança, ressalva causal e próxima ação | Sem probe = N/D, não falha; nenhum mapa ou causalidade inventados; `network.html` para detalhes | PARTIAL |
| `search-geo.html` | `serp_*`, `geo_*`, `perplexity_*`, `web_archive_*` quando existentes e tarefas contextuais; run_id/observation_id | Cobertura por fonte, mercado/dispositivo/instante, concorrência, limite de citações e validações SEO/GEO | Ausência na amostra não prova ausência global; `cat-05.html`, `geo.html` para trilhas | PARTIAL |
| `seguranca.html` | `passive_security_*`, `recommendation_governance`; finding_id/atribuição de cookie | Cobertura passiva, severidade, scripts, cookies, vínculos de autoria e recomendação | Terceiros não viram domínio próprio; `cat-10.html` para incidência física detalhada | PARTIAL |
| `plano.html` | `directed_analysis_runs` (`strategic_summary_json`, `roadmap_json`), `directed_analysis_actions`, `recommendation_governance`, `improvement_*`; action_id/source_kind/source_id | Pontos fortes, fragilidades, riscos, oportunidades, fases registradas, itens técnicos, ações aceitas vs sem decisão | Somente `ACCEPTED` inequívoco compõe plano aprovado; rejeitadas não são tarefas; `directed-analysis.html` e `cat-09.html` para detalhes | PARTIAL |
| `ia-custos.html` | `ai_provider_attempts`, `content_remediation_attempts`, `ai_tasks`, `ai_exchange_log`; attempt_id/provider | Resultado, tokens, custo por moeda, prontidão/fallback quando persistidos e origem | Desconhecido não é zero; `ai-integrations.html`/`metrics.html` para envelopes e tempos | PARTIAL |

**Lacuna ainda dependente de evidência real:** o antigo extrator de tabelas do catálogo apresentava, na piloto, quadros de causas de limitações de Search, Common Crawl, CrUX histórico, detalhes de campo, resultado/fallback por finalidade, prontidão de IA e arquitetura por captura. As novas projeções diretas não estão comprovadas como equivalentes a cada um desses quadros. Os respectivos registros continuam no anexo técnico sanitizado quando presentes, mas *anexo não equivale a síntese executiva*. Sem comparação campo a campo com os três anexos de auditoria obrigatórios, classificá-los como PASS seria indevido.

### Achados A-01-A-10

| Achado | Correção / estado nesta branch | Gate remanescente |
| --- | --- | --- |
| A-01, parsing do catálogo | **Corrigido no código:** `catalog_context.py` não importa `HTMLParser`, não lê arquivos `*.html` para construir fatos; previews vêm de `tables` da AUD. Manifesto do catálogo verifica somente links. | Executar teste de remoção/alteração do HTML do catálogo e comparar sumários reais; cobrir em especial quadros técnicos substituídos. |
| A-02, sanitização | **Corrigido no código, validação real pendente:** IDs/nomes/ordinais de cookies e seletores CSS seguros preservados; valores secretos continuam censurados; ambiguidade gera `REF` estável. | Comparar 78 atribuições e 7 observações da amostra, validar joins e testar variantes de credenciais. |
| A-03, 4 verificações GEO/SEO | **Corrigido na projeção:** tarefas de `reverse_review` aparecem com título, ID, motivo, escopo, referência, SHA e validação, em Conteúdo e Search/GEO. | Comprovar quatro tarefas e seus estados na piloto; validar ausência de inferência editorial ou recaptura. |
| A-04, mistura governança | **Corrigido na projeção:** ações aceitas, sem decisão e excluídas são classes separadas; sugestões técnicas preservam a decisão. | Conferir 35/7 decisões e 60 ações da AUD, inclusive correspondência `source_kind/source_id`. |
| A-05, rede sem conclusão | **Corrigido na projeção:** usa `build_network_assessment` existente para conclusão, confiança pontual, referências e limitação causal. | Comparar com `network.html` e validar N/D sem probe na AUD. |
| A-06, direcionada sem estratégia | **Corrigido na projeção:** usa `strategic_summary_json` e `roadmap_json` persistidos; contagem de governança por fase. | Conferir sequência das seis fases e conclusões da piloto sem promover sugestões. |
| A-07, SARI contraditório | **Corrigido no código:** ausência de `score_contributions` informa falta de decomposição, não ausência do SARI medido. | Testar SARI 89,8 em `indices.html`. |
| A-08, âncora inexistente | **Não reproduzido no código consultado:** os links atuais para `geo-content-review.html` referem-se a `#contextual-content`, cujo elemento existe; teste focal vigente confere o fragmento. | Conferir manifesto/links da apresentação e do catálogo recém-gerados. |
| A-09, mapa de cobertura otimista | **Corrigido no gerador:** níveis independentes `preserved_annex`, `navigable_record`, `editorial_summary`, `conclusion_or_decision_present`. Fallback desconhecido segue `technical-only`. | Comparar verdade do rótulo com conteúdo editorial da piloto, não só presença no DOM. |
| A-10, imagem fora do ZIP | **Limite de export documentado:** recurso `../artifacts/visual/...` pode existir na AUD completa embora falte em ZIP dos relatórios. | Conferir fonte e caminho na AUD integral; não classificar como link quebrado sem teste. |

### Política dos links técnicos e export isolado

O inventário material fornecido para análise anterior indicou **16 links observados em 9 páginas para 11 destinos técnicos distintos**. A contagem observada depende do pacote efetivamente gerado e **não foi revalidada nesta sessão**, pois o CSV obrigatório não está anexado aqui. O código anterior possuía até 17 posições potenciais (12 inserções condicionais por quadros e 5 referências). O código novo mantém até 11 destinos únicos após consolidar quadros temáticos por fonte estruturada, conforme disponibilidade verificada. Não interpretar redução de links duplicados como prova de retenção de conteúdo: cada quadro substituído requer equivalência decisória.

| Destino técnico | Manter/adaptar e justificativa | Caso de export isolado |
| --- | --- | --- |
| `execution-evidence.html` | Manter link opcional à execução; síntese de fulfillment deve ser legível sem ele | Mensagem informativa se ausente |
| `cat-05.html` | Consolidar links repetidos de Search/Common Crawl; requisitos de cobertura/limitação devem existir na apresentação | Mensagem; comparar os quadros substituídos |
| `cat-04.html` | Consolidar quadros de laboratório/campo/CrUX, desde que índices, escopos e limites independentes permaneçam | Mensagem; sem histórico fabricado |
| `ai-integrations.html` | Consolidar prontidão e resultados/fallback técnicos; decisão sobre tentativas e custos é autônoma | Mensagem; manter estado sem inferir sucesso |
| `index.html` | Manter arquitetura técnica/capturas como aprofundamento da extração | Mensagem se ausente |
| `cat-10.html` | Manter cobertura e ocorrências de segurança como prova técnica opcional | Mensagem; não esconder autoria |
| `methodology.html` | Manter regras, método e limitações de cálculo fora de tabelas exaustivas | Mensagem se ausente |
| `cat-01.html` | Manter detalhe de validador W3C e evidência por ocorrência | Mensagem se ausente |
| `capture-context.html` | Manter materialização da captura e prévia física, fora da síntese | Mensagem se ausente |
| `network.html` | Manter mapa/rota apenas se materializados; texto do link não promete ambos | Mensagem se ausente |
| `metrics.html` | Manter telemetria técnica pormenorizada; somatórios confiáveis ficam na apresentação | Mensagem se ausente |

**Nota sobre catalog `sari.html`, `geo-content-review.html`, `directed-analysis.html`, `cat-09.html`:** são fronteiras de aprofundamento relevantes por tema, mas não estavam no conjunto dos 11 destinos observados do ZIP. A apresentação não deve precisar acessá-los para obter decisão, limitação ou ação; podem ser acrescentados como links opcionais somente com manifesto válido e utilidade demonstrada, não por contagem de páginas.

### Gates para aceite

1. Validar a branch exata contra `main` e o **HEAD final**, executar testes focais com `python -m pytest` (sem novas coletas/IA), revisar CI do SHA final; nunca herdar sucesso de SHA anterior.
2. Validar em Windows/PowerShell 5.1 e Python 3.13 usando **backup fora do diretório de auditoria**, fontes estáveis e sem WAL/SHM/journal ativo. Gerar **somente apresentação** da AUD piloto concluída, preservando `audit.db`, sidecars e catálogo; comparar hashes, manifestos, identidade e conteúdo.
3. Confrontar os links e destinos com `links_report_presentation_para_catalog.csv`, e as evidências semânticas com `PARECER_TECNICO.md`, `resumo_evidencias.json` e o snapshot operacional, depois classificar cada linha como PASS/PARTIAL/MISSING.
4. Navegar `file://` em Chromium offline, com e sem o catálogo contíguo. Exigir os mesmos fatos materiais e decisões nas 11 páginas; se faltar fonte, N/D explícito, nunca zero.
5. **Não fazer merge nem encerrar #710** até aceite humano expresso. Atualização das outras 42 auditorias concluídas somente após gate da piloto e novo inventário.

## Rede: inventário independente (16/11/2026)

A pagina `rede.html` possuia um accordion de inventario sem registros, pois os dados de rede provem de sidecars validados ou projecoes read-only do `audit.db`, e nenhuma tabela SQLite estava roteada para a pagina. Corrigido nesta PR: o inventario exibe registros de captura passiva e sondas autorizadas sanitizados diretamente na apresentacao, inclusive IDs/evidencias verificaveis, ou informa de forma explicita quando nada foi materializado. O acesso principal e um link interno `#network-evidence-inventory`; `report-catalog/network.html` continua estritamente opcional, com rotulo inequivoco. Estilos e estrutura de navegacao nao foram alterados. Exige re-render com gerador `0.4.2` e homologacao da AUD real. Nao equivale a autorizacao para novo probe, coleta ou merge.

## Humanização pt-BR e autonomia do mapa de rede (16/11/2026)

A camada pública do `report-presentation` traduz valores enumerados por campo e domínio, conservando os valores originais apenas nas seções expressamente técnicas de rastreabilidade. Células, tooltips, modal de detalhes, chips, indicadores e cartões utilizam o mesmo interpretador. Dados persistidos de fonte, texto livre, IDs, URLs, seletores e evidências não são modificados.

Inventário das 11 páginas e seus contratos semânticos:

| Página | Valores de interpretação pública |
| --- | --- |
| Painel e estado da execução | component, status, required, dimension, coverage, confidence |
| Extração | device, entity_type, timestamps; metadados das capturas |
| Descoberta e padrões | scope, state, severity, observações de serviços |
| Índices | dimension, result, confidence, consolidation_status, priority |
| Conteúdo e acessibilidade | result, status, source_mode, origin_kind, severity |
| Performance e experiência | field_scope, device, cwv_assessment, status, provenance |
| Rede e conectividade | analysis_method, confidence_scope, status, provenance, hop_state |
| Search e GEO | observation_status, domain_status, device, market, query |
| Segurança passiva | status, severity, domain, origem de observação |
| Plano de ação | priority, source_kind, status, decision, coverage |
| IA, custos e proveniência | status, purpose, outcome, source, source_kind |

Exemplos de vocabulário: `UNAVAILABLE` = Indisponível, `COMPLETE` = Concluído, `CONTENT_VALUE` = Valor do conteúdo, `DETERMINISTIC_PERSISTED_EVIDENCE` = Análise determinística de evidências registradas. Os componentes de execução utilizam a taxonomia pública já consolidada do RASAi; tipos de entidade e escopos de métricas usam dicionários por domínio. Estados futuros ainda não catalogados jamais são exibidos como enum cru em superfície executiva: indicam condição não catalogada, com literal íntegro apenas no bloco técnico.

O link anteriormente destinado a `report-catalog/network.html` foi substituído por uma modal local que resume quais medições e rotas estão efetivamente persistidas e aponta para os registros e mapa na própria apresentação. Não duplica a tabela completa. `rede.html` reutiliza a projeção geográfica offline determinística com apenas coordenadas válidas das sondas autorizadas. Na ausência de coordenadas, a seção informa explicitamente que não há mapa verificável; jamais desenha uma rota física inferida. Sem requisições externas, IA, nova sonda, mudança de `audit.db` ou edição de `report-catalog`.

Contrato de autonomia: as 11 páginas precisam abrir sem o pacote `report-catalog` ao lado. Os demais links para catálogo continuam opcionais e condicionados a manifesto válido, mas não são fonte de fatos. A comprovação de todos os rótulos na auditoria piloto e a inspeção visual em Chromium offline permanecem gates de homologação.
