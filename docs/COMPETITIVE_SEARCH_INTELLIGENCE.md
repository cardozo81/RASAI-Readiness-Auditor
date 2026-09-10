# Competitive Search & Content Intelligence

**Estado:** camada determinística implementada, com extensão opcional de IA vinculada a evidências.

## 1. Objetivo

Competitive Search Intelligence responde à seguinte pergunta:

> Para uma query observada, quais tipos de resultado aparecem à frente do cliente, quais são candidatos razoáveis a concorrentes em Search, quais diferenças determinísticas de conteúdo são observáveis e - quando solicitado explicitamente - quais oportunidades de melhoria vinculadas a evidências um provider de IA pode propor?

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

Quando o cliente está `FOUND`, somente resultados à frente da primeira correspondência do cliente são considerados. Quando está `NOT_FOUND_WITHIN_DEPTH`, o conjunto observado de resultados ainda pode ser classificado, mas a comparação de conteúdo exige `--customer-url` explícita.

A seleção de candidatos remove duplicatas por domínio normalizado e é limitada por `--max-content-pages` e `RASAI_SERP_MAX_COMPETITORS`.

## 4. Modos explícitos de aquisição

`--competitive` executa apenas a classificação e não adiciona request de conteúdo.

`--compare-content` habilita explicitamente a aquisição de páginas públicas para a página do cliente e para o conjunto limitado de candidatos.

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
| páginas concorrentes por query | `3`, além de uma página do cliente | limitado pelos controles da CLI/runtime | manter `3` no uso normal; ampliar somente com justificativa de cobertura/carga |
| timeout por tentativa | `10` s | valor positivo aceito pelo parâmetro correspondente | `10` s |
| corpo máximo da resposta | `2.000.000` bytes | limite positivo configurável | manter o default salvo necessidade comprovada |
| redirects máximos | `5` | limite não negativo configurável | `5` |
| método | `GET` | `GET` nesta capacidade | default |
| portas públicas aceitas | `80`, `443` | `80`, `443` | `443` quando o destino oferecer HTTPS |
| verificação TLS | habilitada | não deve ser desabilitada no fluxo normal | habilitada |

Controles de CLI:

- `--max-content-pages`;
- `--content-timeout`;
- `--content-max-bytes`;
- `--content-max-redirects`.

`--dry-run --compare-content` mostra o teto de tentativas HTTP diretas no pior caso, separado da quota SERP.

## 6. Limite SSRF / rede

URLs da SERP são entrada externa não confiável. Antes de cada request e redirect, o fetcher:

- exige HTTP/HTTPS;
- rejeita credenciais em URLs;
- rejeita localhost e sufixos locais/internos;
- rejeita portas fora do padrão da web pública;
- rejeita literais IP não globais;
- resolve hostnames e rejeita destinos não globais;
- valida destinos de redirect antes de segui-los.

A validação na aplicação não elimina risco de DNS rebinding/TOCTOU. Um deployment SaaS multi-tenant deve adicionar controles de egress de rede ou proxy de saída endurecido.

## 7. Features determinísticas

O RASAi extrai features limitadas:

- URL final e status HTTP;
- tipo de conteúdo;
- tamanho da resposta;
- SHA-256 do conteúdo;
- título;
- meta description;
- H1-H3;
- contagem aproximada de palavras do texto visível;
- termos significativos da query;
- presença dos termos da query em título, descrição, headings e corpo;
- valores `@type` de JSON-LD.

HTML bruto não é persistido por esta capacidade.

A comparação lexical ignora acentos e é determinística. Ela não representa compreensão semântica.

## 8. Comparação determinística

Metodologia:

```text
DETERMINISTIC-CORRELATIONAL-001
```

Gaps informativos atuais incluem:

- `QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS`;
- `TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`;
- `HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS`;
- `CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS`;
- `STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS`.

As referências usam a mediana das páginas selecionadas observadas com sucesso. Aquisições que falharam ou foram bloqueadas são excluídas, em vez de serem convertidas em zero.

Contagem de palavras mede volume de conteúdo, não qualidade. Diferenças de dados estruturados não são recomendações automáticas de markup. Os sinais são informativos e não participam do scoring.

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

`--ai-competitive` é um opt-in explícito separado e exige `--compare-content`.

Exemplo:

```powershell
rasai search "seguro auto online" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider openai `
  --ymyl-mode AUTO
```

Competitive AI recebe apenas evidência determinística estruturada com IDs fechados:

- `CE-QUERY`;
- `CE-CUSTOMER`;
- `CE-COMP-###`;
- `CE-GAP-###`.

IDs de evidência desconhecidos invalidam a resposta do provider. IA não pode reparar evidência determinística ausente.

Adapter live atual: `openai`. `fixture` valida o contrato sem rede. Default: `none`.

Consulte `COMPETITIVE_AI_INTELLIGENCE.md`.

## 11. Evidência e persistência

Quando `--audit-workspace` é fornecido, todas as camadas permanecem dentro do workspace de auditoria existente e de `audit.db`.

Tabelas determinísticas aditivas:

- `serp_competitive_analyses`;
- `serp_competitive_results`;
- `serp_competitive_pages`.

Tabela aditiva de Competitive AI:

- `serp_competitive_ai_analyses`.

Artefatos determinísticos:

```text
artifacts/search-intelligence/competitive/<observation_id>.json
```

Artefatos de Competitive AI:

```text
artifacts/search-intelligence/competitive-ai/<observation_id>.json
```

Nenhum banco paralelo é introduzido. Nenhuma tabela de scoring é modificada.

## 12. Custo e desempenho

- classificação: nenhuma rede adicional;
- comparação de conteúdo: HTTP direto para web pública, sem quota do provider SERP;
- Competitive AI: chamada ao provider apenas quando explicitamente habilitada e o contexto determinístico está `CONSOLIDATED`;
- renderização do HTML pontual: somente projeção de dados persistidos;
- comparação histórica: somente leitura de dados persistidos, sem chamada a Search, conteúdo ou provider de IA;
- `--dry-run`: mostra tetos separados para SERP, aquisição de conteúdo e IA.

Credenciais dos providers não são persistidas nesses artefatos.

## 13. Comportamento aditivo

Sem `--competitive`, `--compare-content` ou `--ai-competitive`, o comportamento SERP comum permanece inalterado.

Sem `--ai-competitive`:

- nenhum provider de IA é instanciado;
- nenhuma chamada de Competitive AI é feita;
- Search Intelligence determinística permanece totalmente utilizável.

Falha de Competitive AI não reescreve evidência SERP nem evidência da comparação determinística.

`SARI-001` e `SCORE-GEO-004` são independentes.

## 14. Política de testes

CI usa fixtures, HTML falso e transports/resolvers injetados.

CI não deve:

- chamar SerpApi live;
- consumir chaves de clientes;
- fazer crawl de sites públicos de concorrentes;
- chamar provider de IA live;
- depender de DNS/internet públicos.

Os testes cobrem classificação, limites, extração, bloqueio de endereços não públicos, gaps de comparação, fechamento de evidence IDs, validação do contrato de IA, persistência aditiva, projeção HTML e comparação histórica determinística.

## 15. Relatório e histórico atuais

O relatório pontual canônico é:

```text
report/search-intelligence.html
```

Ele renderiza evidência persistida e não chama providers de Search ou IA.

A comparação temporal determinística está disponível em:

```text
SEARCH-HISTORY-001
```

A camada histórica compara apenas contextos Search exatos com proveniência compatível de provider/modo de dados. Pode descrever mudanças de posição observada, entrada/saída da profundidade solicitada de resultados, mudanças determinísticas de conteúdo do cliente e códigos de gaps competitivos adicionados/resolvidos.

Nem o relatório pontual nem a camada histórica estabelecem causalidade de ranking.

## 16. Limitações atuais

- a classificação de resultados permanece uma taxonomia heurística pequena;
- ainda não existe grafo de equivalência de entidades/empresas;
- extração de conteúdo usa HTML estático por HTTP, não DOM renderizado em browser;
- ainda não existe comparação de canonical/`hreflang`/link graph;
- suporte live de Competitive AI começa por OpenAI; outros adapters podem ser adicionados por trás do mesmo contrato;
- a IA recebe features extraídas, não HTML bruto completo;
- comparação histórica e seu HTML/manifest independente são determinísticos; comparação semântica before/after da saída de Competitive AI ainda não é contrato estável;
- validação de IP público ainda exige reforço na camada de rede antes de SaaS multi-tenant.

O modelo de milestone e auditoria before/after da Product Platform é reutilizado por Search Intelligence History. Nenhum modelo paralelo de marcador de deployment é introduzido.
