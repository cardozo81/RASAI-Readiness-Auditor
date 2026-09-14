# Competitive Search & Content Intelligence

**Estado:** camada determinística implementada, com extensão opcional de IA vinculada a evidências e ao runtime canônico de providers.

## 1. Objetivo

Competitive Search Intelligence responde à seguinte pergunta:

> Para uma query observada, quais tipos de resultado aparecem à frente do cliente, quais são candidatos razoáveis a concorrentes em Search, quais diferenças determinísticas de conteúdo são observáveis e - quando solicitado explicitamente - quais oportunidades de melhoria vinculadas a evidências a IA pode propor?

A camada determinística permanece autoritativa para as observações. IA é downstream e opcional.

O RASAi não infere causalidade de ranking a partir de diferenças de conteúdo nem de recomendações de IA.

## 2. Fluxo

```text
query
-> observação SERP independente de provider
-> posição do cliente / NOT_FOUND_WITHIN_DEPTH
-> classificação determinística dos resultados
-> seleção limitada de candidatos
-> aquisição opcional de conteúdo da web pública
-> extração determinística de features HTML/conteúdo
-> comparação cliente × líderes observados
-> diferenças correlacionais sustentadas por evidências
-> Competitive AI opcional usando evidence_ids fechados
-> runtime canônico de IA (provider explícito ou AUTO)
-> HTML pontual de Search Intelligence
-> comparação histórica determinística opcional
```

A camada semântica opcional está documentada em `COMPETITIVE_AI_INTELLIGENCE.md`.
O contrato HTML pontual está documentado em `SEARCH_INTELLIGENCE_REPORT.md`.
O contrato de comparação temporal está documentado em `SEARCH_INTELLIGENCE_HISTORY.md`.

## 3. Classificação de resultados

A classificação é local e não consome rede adicional nem quota de provider.

Classes atuais:

- `CUSTOMER`;
- `ORGANIC_CANDIDATE`;
- `PUBLIC_AUTHORITY`;
- `KNOWLEDGE_REFERENCE`;
- `SOCIAL_PLATFORM`;
- `VIDEO_PLATFORM`;
- `MARKETPLACE`;
- `NON_ORGANIC`.

A classificação é heurística. Ela seleciona candidatos para inspeção limitada; não declara que duas organizações sejam concorrentes comerciais.

Quando o cliente está `FOUND`, somente resultados à frente da primeira correspondência do cliente são considerados. Quando está `NOT_FOUND_WITHIN_DEPTH`, o conjunto observado ainda pode ser classificado, mas a comparação de conteúdo exige `--customer-url` explícita.

A seleção remove duplicatas por domínio normalizado e é limitada por `--max-content-pages` e `RASAI_SERP_MAX_COMPETITORS`.

## 4. Modos explícitos de aquisição

`--competitive` executa apenas a classificação e não adiciona request de conteúdo.

`--compare-content` habilita explicitamente aquisição de páginas públicas para o cliente e conjunto limitado de candidatos.

Exemplo:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --max-content-pages 3
```

Se o cliente não for encontrado:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --depth 20 `
  --compare-content `
  --customer-url https://cliente.example/seguro-auto
```

Uma `--customer-url` explícita é suportada para uma query por comando.

## 5. Aquisição limitada da web pública

Defaults operacionais:

| Parâmetro | Default | Valores permitidos/limite | Recomendado |
|---|---:|---|---|
| páginas concorrentes por query | `3`, além de uma página do cliente | limitado pela CLI/runtime | manter `3` no uso normal |
| timeout por tentativa | `10` s | valor positivo | `10` s |
| corpo máximo | `2.000.000` bytes | limite positivo configurável | default |
| redirects máximos | `5` | limite não negativo | `5` |
| método | `GET` | `GET` | default |
| portas públicas | `80`, `443` | `80`, `443` | `443` quando disponível |
| TLS | habilitado | não desabilitar | habilitado |

Controles: `--max-content-pages`, `--content-timeout`, `--content-max-bytes`, `--content-max-redirects`.

`--dry-run --compare-content` mostra o teto de tentativas HTTP diretas separado da quota SERP.

## 6. Limite SSRF / rede

URLs da SERP são entrada externa não confiável. Antes de cada request e redirect, o fetcher exige HTTP/HTTPS, rejeita credenciais em URL, localhost/sufixos internos, portas fora do padrão, IPs não globais e destinos resolvidos não globais.

Deploy SaaS multi-tenant deve complementar essas validações com controle de egress/proxy endurecido.

## 7. Features determinísticas

O RASAi extrai features limitadas como URL final/status, tipo/tamanho da resposta, SHA-256, título, meta description, H1-H3, volume aproximado de texto visível, presença dos termos da query e tipos JSON-LD.

HTML bruto não é persistido por esta capacidade.

A comparação lexical é determinística e não representa compreensão semântica.

## 8. Comparação determinística

Metodologia: `DETERMINISTIC-CORRELATIONAL-001`.

Gaps informativos incluem:

- `QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS`;
- `TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`;
- `HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`;
- `CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS`;
- `STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS`.

Referências usam a mediana das páginas observadas com sucesso. Falhas de aquisição são excluídas, não convertidas em zero. Os sinais são informativos e não participam do scoring.

## 9. Status da comparação

- `CONTENT_COMPARISON_DISABLED`;
- `SERP_OBSERVATION_UNAVAILABLE`;
- `CUSTOMER_URL_REQUIRED`;
- `CUSTOMER_CONTENT_UNAVAILABLE`;
- `NO_ELIGIBLE_COMPETITOR_CANDIDATES`;
- `COMPETITOR_CONTENT_UNAVAILABLE`;
- `CONSOLIDATED`.

Somente `CONSOLIDATED` é elegível para Competitive AI.

## 10. Competitive AI opcional

`--ai-competitive` é opt-in e exige `--compare-content`.

Com orquestração automática:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider auto `
  --ymyl-mode AUTO
```

Também é possível selecionar explicitamente qualquer provider suportado pelo registry canônico.

Competitive AI recebe apenas evidência determinística estruturada com IDs fechados `CE-QUERY`, `CE-CUSTOMER`, `CE-COMP-###` e `CE-GAP-###`. IDs desconhecidos invalidam a resposta. IA não pode reparar evidência determinística ausente.

Não existe provider de produção exclusivo de Search Intelligence. A necessidade `COMPETITIVE_INTELLIGENCE` usa o mesmo registry, adapters, estimativa de custo, elegibilidade, quarentena, circuit breaker e fallback do core. `fixture` é somente para testes/CI.

Consulte `COMPETITIVE_AI_INTELLIGENCE.md`.

## 11. Evidência e persistência

Quando `--audit-workspace` é fornecido, as camadas permanecem dentro do workspace e `audit.db`.

Tabelas determinísticas:

- `serp_competitive_analyses`;
- `serp_competitive_results`;
- `serp_competitive_pages`.

Tabela de Competitive AI:

- `serp_competitive_ai_analyses`.

Artefatos:

```text
artifacts/search-intelligence/competitive/<observation_id>.json
artifacts/search-intelligence/competitive-ai/<observation_id>.json
```

Nenhuma tabela de scoring é modificada.

## 12. Custo e desempenho

- classificação: sem rede adicional;
- comparação de conteúdo: HTTP direto para web pública, sem quota SERP;
- Competitive AI: chamada somente quando habilitada e o contexto está `CONSOLIDATED`;
- `AUTO`: candidato priorizado conforme a política de custo vigente e estado do coordenador;
- renderização HTML: somente dados persistidos;
- histórico: somente leitura;
- `--dry-run`: tetos separados para SERP, conteúdo e IA.

Credenciais não são persistidas nos artefatos.

## 13. Comportamento aditivo

Sem `--competitive`, `--compare-content` ou `--ai-competitive`, o comportamento SERP comum permanece inalterado.

Sem `--ai-competitive`, nenhuma chamada de Competitive AI é feita. Falha de IA não reescreve evidência SERP nem a comparação determinística.

`SARI-001` e `SCORE-GEO-004` são independentes.

## 14. Política de testes

CI usa fixtures, HTML falso e transports/resolvers injetados. Não deve chamar Search/IA live nem depender de DNS/internet públicos.

Os testes cobrem classificação, limites, extração, SSRF, gaps, evidence IDs, contrato de IA, provider registry, `AUTO`, persistência e projeção HTML.

## 15. Relatório e histórico

Relatório pontual: `report/search-intelligence.html`.

Comparação temporal determinística: `SEARCH-HISTORY-001`.

A camada histórica compara somente contextos Search com proveniência compatível e não estabelece causalidade de ranking.

## 16. Limitações funcionais

- taxonomia de classificação ainda é heurística;
- não existe grafo de equivalência de entidades/empresas;
- extração de conteúdo usa HTML estático por HTTP;
- não existe comparação de canonical/`hreflang`/link graph nesta camada;
- a IA recebe features extraídas, não HTML bruto completo;
- comparação semântica before/after da saída de Competitive AI não é contrato estável;
- deploy SaaS multi-tenant ainda exige reforço de egress além da validação de aplicação.

Search Intelligence History reutiliza milestones e auditorias before/after da Product Platform; não existe modelo paralelo de deployment.
