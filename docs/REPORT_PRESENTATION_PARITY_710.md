# Issue #710 — matriz de paridade informacional e arquitetura editorial

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
| `cat-05.html` | Search & AI Intelligence | SERP, fontes Search, comparação, observabilidade e limitações | Search e GEO; previews contextuais no Painel/Performance | Parcial adequada | Search e GEO; previews somente quando denominador é explícito | Search/GEO continua superfície responsável; CrUX histórico permanece em Performance por ser métrica de experiência, não ranking. |
| `cat-06.html` | Apdex de navegação | amostras, thresholds, distribuição e limitações | Performance e experiência | Adequada | Performance e experiência | Mesmo domínio de experiência, com denominador próprio explícito. |
| `cat-07.html` | Apdex de experiência | população sintética, amostras, thresholds e erros | Performance e experiência | Adequada | Performance e experiência | Mesmo domínio de experiência, sem fundir com Apdex de navegação. |
| `cat-08.html` | Análise profunda e melhorias | findings, recomendações evidence-bound e correlações | Conteúdo e acessibilidade + Plano de ação | Adequada | Conteúdo e acessibilidade + Plano de ação | Evidência fica no domínio observado; ação governada fica no plano. |
| `cat-09.html` | Remediações | ações técnicas/editoriais e validação | Plano de ação | Adequada | Plano de ação | Fronteira conceitual já correta. |
| `cat-10.html` | Segurança passiva | cobertura, scripts, findings, severidade, limitações e remediação | Segurança passiva; contagem de scripts também em Performance | Parcial / deslocada | Segurança passiva | Script observado é evidência de segurança passiva, não métrica de Web Performance. |
| `network.html` | Rede e conectividade | captura passiva, probe autorizado, DNS/TCP/TLS, IP, traceroute, ASN/GeoIP, cronologia e limitações | Performance e experiência, apenas DNS/TCP/TLS resumidos | Parcial / deslocada | **Nova página Rede e conectividade** | Há propósito próprio, fontes/instantes distintos, estados próprios e volume incompatível com Performance. A página evita mistura conceitual e reutiliza o design system existente. |
| `geo.html` | GEO — inteligência competitiva | observações, fontes, comparação e contexto | Search e GEO | Adequada | Search e GEO | Fronteira conceitual já correta. |
| `geo-content-review.html` | Análise reversa SEO/GEO | evidência editorial, semântica e contexto de Search/GEO | Conteúdo e acessibilidade + Search e GEO | Adequada | Conteúdo e acessibilidade + Search e GEO | Dupla projeção é intencional porque a superfície conecta conteúdo observado ao contexto Search/GEO sem fundir as fontes. |
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
