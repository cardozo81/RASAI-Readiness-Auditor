# RASAI / SARI — identidade e compatibilidade

## Identidade pública

- **Produto:** RASAI
- **Expansão:** Readiness Assessment for Search & AI
- **Descriptor:** Search & AI Readiness Auditor
- **Framework:** RASAI Framework
- **Índice público:** Search & AI Readiness Index — `SARI-001`
- **Índice público legado:** `SGRI-001`

## Mudança pública

A apresentação, documentação, console, user-agent e relatórios usam RASAI/SARI. A página canônica do índice é `report/readiness.html`. `report/searchgeo.html` permanece como redirect de compatibilidade.

Os comandos preferenciais são `rasai`, `rasai-console`, `rasai audit`, `rasai visibility` e `rasai scoring`.

## Compatibilidade preservada

- `searchgeo` e `searchgeo-console` permanecem aliases funcionais;
- `src/searchgeo/` permanece como namespace Python;
- `SEARCHGEO_*` permanece como família de variáveis de ambiente;
- `searchgeo.toml`, `searchgeo-console.ini` e marcadores locais continuam válidos;
- `searchgeo-readiness-auditor` permanece como nome da distribuição Python nesta etapa;
- `BR-GEO-*`, `SCORE-GEO-002`, `SCORE-GEO-003` e outros IDs versionados não são renomeados;
- auditorias e artifacts históricos não são regravados.

## SARI versus scoring engine

`SARI-001` identifica publicamente o Search & AI Readiness Index. Ele não substitui a versão do motor persistido. A troca `SGRI-001` → `SARI-001` é nominal e não altera pesos, fatores, thresholds, fórmula ou calibração.

Novas auditorias usam `SCORE-GEO-003`; `SCORE-GEO-002` permanece histórico e não é recalculado. O identificador SARI e o `scoring_version` devem ser apresentados separadamente.

Lighthouse, Core Web Vitals, Acessibilidade, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Observed AI Visibility continuam metodologias independentes e não são combinadas silenciosamente no SARI.
