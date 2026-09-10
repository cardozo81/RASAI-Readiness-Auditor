# RASAi — Monitoramento, observabilidade e qualidade

**Estado no baseline de desenvolvimento:** implementado e integrado à `main`.

## Objetivo

Esta capacidade transforma auditorias RASAi isoladas em um fluxo longitudinal vinculado a evidências, sem alterar a fonte de verdade da auditoria nem adicionar silenciosamente novos sinais ao `SARI-001`/`SCORE-GEO-004`.

Ela mantém separadas as seguintes perguntas:

1. **Readiness:** quais condições técnicas e semânticas foram observadas pela auditoria?
2. **Resultados observados:** o que sistemas externos de Search/AI reportaram?
3. **Mudança:** o que mudou de forma material entre auditorias persistidas?
4. **Associação:** um resultado mudou ao longo de um período comparável enquanto também existia uma regressão técnica?
5. **Qualidade da decisão:** a evidência da auditoria está completa e confiável o suficiente para sustentar decisões de remediação?

Coincidência temporal não constitui inferência causal.

## Arquitetura

```text
AUD-BASELINE/audit.db -----\
                            > RASAi Monitor -> MON-*/report.html + manifest.json + impact.html
AUD-CURRENT/audit.db ------/

AUD-CURRENT/audit.db (somente leitura)
          |
          +--> observability.db          # RASAI-OBS-002
          +--> artifacts/observability/*
          +--> report/observability.html
          +--> report/quality.html

coleção AUD-*
          |
          +--> Fix Verification -> verification/VER-*/report.html
          +--> Evidence Timeline -> quality/TIMELINE-*/report.html
```

`audit.db` não é migrado por Monitor, Observability ou Quality. Observações externas são dados derivados/reconstruíveis armazenados em sidecar.

## Limite metodológico

Monitoring, Observability e Quality não criam outro score de readiness. Resultados externos, Lighthouse/CrUX e métricas sintéticas não são adicionados implicitamente ao Overall.

Os termos em inglês nesta seção correspondem a nomes técnicos ou rótulos do produto e, por isso, são preservados.

## Sidecar de observabilidade

Contrato atual:

```text
RASAI-OBS-002
identity = (dataset_id, record_id)
```

A proveniência do dataset persiste tipo de origem, método de captura, período, caminho/SHA-256 do artefato, horário da coleta e metadados. Segredos existem somente em runtime.

## RASAi Monitor

### Comparação

```powershell
rasai monitor compare --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

Estados possíveis incluem `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `UNCHANGED`, `DATA_UNAVAILABLE` e `NOT_COMPARABLE`.

Valores distintos de `scoring_version` não são convertidos silenciosamente nem tratados como equivalentes.

### Release Gate

```powershell
rasai monitor gate --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

O gate padrão é determinístico e *fail-closed*. Famílias opcionais exigem ativação explícita:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

Sobrescritas operacionais são explícitas:

```text
--allow-noncomparable
--allow-new-failures
```

### Change Impact

```powershell
rasai monitor impact --audits-root audits --baseline AUD-BASELINE --current AUD-CURRENT
```

É selecionado um único dataset mais recente por origem/`AUD-*`. Históricos sobrepostos não são somados. Valores ausentes permanecem ausentes. Associações temporais são reportadas sem linguagem causal.

## Observabilidade de Search & AI

Comando principal:

```text
rasai observe ...
```

Alias:

```text
rasai observability ...
```

As superfícies operacionais suportadas incluem importação genérica, Bing em modelo *import-first*, Google AI import/control, Search Console property/sitemap/Search Analytics/Search Appearance/URL Inspection, CrUX History e comandos de relatório/status.

Regras comuns à coleta externa:

- o escopo de target/origem é validado contra o `AUD-*`;
- tokens OAuth e chaves de API não são persistidos;
- erros de autenticação, quota ou rede são falhas operacionais, não findings do site;
- dados ausentes na origem não são inventados;
- `NULL` nunca é normalizado para zero, exceto quando a própria origem reporta um zero numérico com essa semântica;
- origem, superfície e proveniência permanecem explícitas.

## Diagnósticos de observabilidade

`report/observability.html` pode incluir:

- Indexability Reality Matrix;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- diagnósticos de dados estruturados, entidade, atualização, `hreflang` e recuperação;
- clusters por template/causa raiz;
- CrUX History;
- proveniência do dataset.

Esses são diagnósticos derivados e não alteram automaticamente `SARI-001`/`SCORE-GEO-004`.

## RASAi Quality

```powershell
rasai quality report --audit AUD-...
rasai quality verify --baseline AUD-A --current AUD-B
rasai quality timeline --audits-root audits
```

Quality inclui Audit Health, Evidence Confidence, Operational Priority, Coverage Map, controles de uso de conteúdo pelo publicador, Recommendation Validation, Fix Verification e Evidence Timeline.

Quality oferece suporte à decisão; não é outro score de readiness.

## Superfície de comando de scoring

Runtime atual:

```powershell
rasai scoring inspect
```

## Superfícies HTML

A navegação canônica por `AUD-*` é condicional à existência do arquivo:

```text
index.html
readiness.html
scoring.html
mobile.html
desktop.html
remediation.html
content-suggestions.html
crawling-discovery.html
accessibility.html
web-performance.html
apdex.html
apdex-experience.html
ai-visibility.html
observability.html
quality.html
ai-usage.html
references.html
```

## Expectativas de validação

A validação automatizada deve cobrir comportamento somente leitura, comparabilidade, política do gate, identidade/migração `OBS-002`, escopo de dados externos, exclusão de segredos, preservação de `NULL`, semântica de Quality/Verification/Timeline e navegação canônica.

Smoke test humano continua apropriado para validar credenciais reais, comportamento de providers externos ou comportamento visual/operacional. Isso não representa status de merge pendente para capacidades já integradas à `main`.
