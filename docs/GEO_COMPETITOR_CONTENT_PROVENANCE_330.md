# #330 - Evidência competitiva persistida (somente leitura)

O módulo `rasai.geo_competitor_content_provenance_330` consome exclusivamente um
SQLite `audit.db` existente, com `PRAGMA query_only=ON`. Exige um ID de AUD,
um ID de observação SERP e contexto válido com query, data com fuso horário
e origem OBSERVED_API. Não faz chamadas HTTP, Perplexity ou IA.

A coleta de conteúdo opcional já existe em `search_intelligence/content.py`.
A nova inspeção apenas lê `serp_competitive_pages`: uma página CUSTOMER
e páginas COMPETITOR_CANDIDATE com status OBSERVED, HTTP 2xx, hash SHA-256,
tamanho maior que zero e texto substantivo. URLs inválidas, conteúdo vazio,
hash ausente, dados de outra auditoria ou snippets não constituem prova de HTML.

A diferença de número de palavras é descritiva, nunca causal, não altera
SARI, SCORE-GEO, Apdex, findings nem rankings. O instante da coleta HTTP
do conteúdo não é demonstrado pelo relógio SERP: html_fetch_timestamp=N/D.
A equivalência de contexto de Perplexity também não é inferida.

Exemplo offline:

    python -m rasai.geo_competitor_content_provenance_330 AUD-REFERENCIA/audit.db --audit-id AUD-REFERENCIA --serp-observation-id SERP-REFERENCIA

Limites restantes: novos candidatos exclusivos da Perplexity requerem
opt-in próprio, regras robots, origem/URL, locale, dispositivo, custo e
proveniência física. Esta ponte não abre novo crawler. Fixtures validam
integridade byte a byte da AUD, ausência de provider e fallback N/D.
