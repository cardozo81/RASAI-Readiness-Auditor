# Rastreamento, descoberta e acesso de crawlers — Crawling, Discovery & AI Access

**Status:** INTEGRATED BASELINE
**Natureza:** enriquecimento técnico pós-auditoria, determinístico por padrão e não-scoring
**Runtime:** `src/searchgeo/m24_crawling_discovery.py`, `m24_discovery_extensions.py`, `m24_ai.py`, `m24_reporting.py`, `m24_cli.py`

## 1. Objetivo

Rastreamento, descoberta e acesso de crawlers aprofunda a análise de rastreamento e descoberta sem alterar a aritmética do RASAi. O marco consolida evidências relacionadas a `robots.txt`, sitemaps, políticas de crawlers, `llms.txt`, feeds e sinais de submissão/discovery, produzindo uma página técnica dedicada e, opcionalmente, explicações/remediações por IA estritamente evidence-bound.

Rastreamento, descoberta e acesso de crawlers não cria um novo score, não altera `SARI-001` e não recalibra `SCORE-GEO-003`.

## 2. Invariantes

1. execução determinística é a fonte de verdade para os diagnósticos técnicos;
2. LLM nunca decide `RuleExecution`, `Finding`, `Recommendation`, Score, Coverage, Confidence ou Consolidation;
3. todo diagnóstico Rastreamento, descoberta e acesso de crawlers é persistido com `scoring_impact=NONE`;
4. falha Rastreamento, descoberta e acesso de crawlers é fail-open em relação à auditoria principal;
5. ausência de `llms.txt` não reduz score/readiness;
6. bloqueio de GPTBot não deve ser interpretado como bloqueio de Search;
7. OAI-SearchBot, GPTBot e Google-Extended possuem papéis distintos e devem ser apresentados separadamente;
8. evidência externa não observada não pode ser inferida como configurada ou ausente.

## 3. Fontes de dados

Rastreamento, descoberta e acesso de crawlers reutiliza o estado já persistido pela auditoria principal e somente adiciona aquisição quando explicitamente prevista pelo marco.

Fontes principais:

- evidência `robots.txt` obtida no discovery;
- sitemaps adquiridos no discovery;
- páginas, respostas HTTP e snapshots persistidos;
- canonical e meta robots observados;
- recursos same-origin referenciados;
- aquisição same-origin de `/llms.txt`, quando a origem não está em hard source blocker;
- provider de IA já configurado, somente quando remediação técnica Rastreamento, descoberta e acesso de crawlers é explicitamente habilitada.

## 4. robots.txt

A análise deve, no mínimo:

- preservar e interpretar grupos `User-agent`, `Allow`, `Disallow` e `Sitemap`;
- registrar estado de aquisição e tamanho do arquivo;
- identificar linhas inválidas e campos sem suporte relevante;
- detectar `Sitemap:` relativo quando a sintaxe exige URL absoluta;
- preservar múltiplas declarações de sitemap;
- distinguir crawler Search de tokens de produto/treinamento;
- verificar acesso de recursos same-origin observados quando houver política aplicável;
- não transformar ausência legítima de `robots.txt` em bloqueio artificial.

O campo `Sitemap:` pode apontar para host diferente do `robots.txt`. Rastreamento, descoberta e acesso de crawlers preserva essa declaração como evidência, mas não faz fetch cross-origin automático a partir dela. Essa fronteira é uma decisão de segurança do auditor para evitar expansão SSRF/host não autorizado; não é finding do website.

## 5. Crawlers e tokens

### Googlebot

Crawler usado pela Pesquisa Google e outras superfícies Search compatíveis com a documentação pública do Google.

### OAI-SearchBot

Crawler de descoberta para superfícies de busca/citação da OpenAI. Bloqueá-lo pode limitar a capacidade de conteúdo ser descoberto e usado em resumos/snippets de Search compatíveis.

### GPTBot

Token relacionado a controle de potencial uso de conteúdo para treinamento. Seu estado deve ser exibido separadamente de OAI-SearchBot e não deve ser convertido em penalidade automática de Search readiness.

### Google-Extended

Token de produto em `robots.txt`; não possui user-agent HTTP separado. Controla usos documentados pelo Google relacionados a Gemini/Vertex AI e grounding. Não afeta inclusão nem ranking na Pesquisa Google e não deve ser representado como crawler Search independente.

## 6. Sitemaps

Rastreamento, descoberta e acesso de crawlers estende a interpretação para os formatos suportados pelo runtime:

- XML `urlset`;
- sitemap index;
- gzip;
- RSS 2.0;
- Atom 1.0;
- sitemap texto plano.

A análise determinística considera, quando observável:

- URL absoluta e válida;
- duplicatas;
- limite de 50 MB descompactado;
- limite de 50.000 URLs por sitemap;
- `lastmod` futuro ou inconsistente;
- presença de `priority`/`changefreq` apenas como informação, sem tratá-los como sinal de ranking;
- extensões de imagem, vídeo, notícias e hreflang;
- URLs do sitemap que, dentro da amostra auditada, responderam não-2xx;
- conflito observado com `noindex`;
- canonical observado para outra URL;
- bloqueio observado por robots;
- URLs auditadas não encontradas nos sitemaps somente como diagnóstico de cobertura da amostra, não prova de erro global do sitemap.

Sitemap é sinal de descoberta/canonical preference, não garantia de crawl, indexação ou ranking.

## 7. llms.txt

Rastreamento, descoberta e acesso de crawlers trata `llms.txt` como proposta comunitária experimental, não como web standard nem requisito Google/OpenAI de Search.

Política:

- tentativa em `/llms.txt` somente same-origin;
- ausência: `INFO`, sem impacto em scoring;
- presença: artifact persistido em `artifacts/m24/llms.txt`;
- estrutura pode ser comparada com a proposta vigente, incluindo H1 inicial;
- links observados podem ser classificados como same-origin ou externos;
- o arquivo não substitui `robots.txt`, sitemap, HTML semântico, canonical, indexabilidade ou conteúdo acessível.

## 8. RSS/Atom e discovery complementar

Links `rel=alternate` para feeds RSS/Atom observados podem ser registrados como sinais adicionais de discovery. A existência de feed não é requisito universal de GEO/Search e não deve ser pontuada isoladamente.

## 9. IndexNow

Uma auditoria passiva do website não consegue provar, de forma geral, que URLs foram submetidas com sucesso via IndexNow.

Quando não houver evidência explícita do operador, log de submissão ou artifact verificável, Rastreamento, descoberta e acesso de crawlers deve reportar o estado como não determinável em vez de inferir configuração a partir do conteúdo público do site.

## 10. Remediação técnica por IA

Superfície pública:

```text
--ai-technical-remediation
--no-ai-technical-remediation
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Default: **OFF**.

Precedência:

1. argumento CLI explícito;
2. variável `SEARCHGEO_AI_TECHNICAL_REMEDIATION`;
3. `false`.

Valores de ambiente aceitos:

```text
true / false
1 / 0
yes / no
on / off
```

A IA técnica:

- reutiliza providers compatíveis já configurados;
- recebe somente diagnósticos/evidências Rastreamento, descoberta e acesso de crawlers persistidos;
- não pode inventar URL, policy, canonical, data ou crawler token;
- não decide se a organização deve permitir treinamento;
- não transforma `llms.txt` em requisito;
- exige revisão humana;
- persiste telemetria e artifact próprio quando executada;
- não altera scoring.

Quando não existe provider apto, a finalidade fica `NOT_CONFIGURED`/indisponível sem virar finding do website.

## 11. Persistência

Rastreamento, descoberta e acesso de crawlers usa tabelas aditivas próprias no `audit.db`, incluindo:

```text
m24_runs
m24_diagnostics
m24_ai_results
```

Os dados são reabríveis a partir do workspace. `m24_diagnostics.scoring_impact` permanece `NONE`.

Artifacts específicos podem ser gravados em:

```text
artifacts/m24/
```

## 12. Relatório

Página canônica:

```text
report/crawling-discovery.html
```

A página deve usar o menu/camada visual compartilhados e apresentar, conforme disponibilidade:

- resumo do run Rastreamento, descoberta e acesso de crawlers;
- robots e políticas de crawler;
- sitemaps e formatos observados;
- diagnósticos técnicos com evidência/remediação;
- `llms.txt`, feeds e IndexNow;
- explicação das fronteiras de segurança;
- sugestões técnicas de IA quando habilitadas;
- fontes públicas primárias.

A telemetria dessa remediação técnica por IA também pode ser projetada em `report/ai-usage.html`, sem somar artificialmente qualidade do website e consumo de API.

## 13. Source blocker e segurança

Quando a origem está em hard source blocker confirmado, Rastreamento, descoberta e acesso de crawlers não deve iniciar aquisição adicional de `/llms.txt` nem chamada técnica de IA dependente do corpus indisponível. O estado deve ser persistido como `SKIPPED_SOURCE_BLOCKER`/equivalente e a auditoria principal deve permanecer íntegra.

Sitemaps declarados em host externo são preservados, mas não adquiridos automaticamente. Uma evolução futura só pode alterar essa política com validação explícita de SSRF, DNS/IP, redirects e autorização de escopo.

## 14. Critérios de aceite

Rastreamento, descoberta e acesso de crawlers é considerado íntegro quando:

- formatos adicionais de sitemap possuem testes;
- sitemap externo declarado não dispara fetch externo automático;
- ausência de robots não cria falso bloqueio;
- `llms.txt` é claramente experimental e non-scoring;
- remediação técnica default OFF respeita precedência CLI/ambiente;
- execução Rastreamento, descoberta e acesso de crawlers não altera contagem/resultado das entidades de scoring;
- report é idempotente e usa CSS/menu compartilhados;
- source blocker elimina aquisição adicional dependente da origem;
- regressões Rastreamento, descoberta e acesso de crawlers e suíte afetada são cobertas por CI.

## 15. Referências públicas

Fontes normativas/primárias usadas para os fenômenos externos:

- RFC 9309 — Robots Exclusion Protocol: <https://www.rfc-editor.org/rfc/rfc9309>
- Google robots.txt specification: <https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec>
- Google sitemap guidance: <https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap>
- Google common crawlers / Google-Extended: <https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers>
- OpenAI Publishers and Developers FAQ: <https://help.openai.com/en/articles/12627856-publishers-and-developers-faq>
- IndexNow protocol: <https://www.indexnow.org/documentation>
- llms.txt proposal v2: <https://llmstxt.org/>

Essas fontes documentam fenômenos e contratos externos. Elas não homologam `SARI-001`, `SCORE-GEO-003`, severidades de rastreamento/descoberta nem qualquer índice proprietário do RASAi.
