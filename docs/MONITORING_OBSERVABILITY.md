# RASAi - Monitoramento, observabilidade e qualidade

**Estado:** vigente.

## Objetivo

Esta capacidade transforma auditorias RASAi isoladas em um fluxo longitudinal vinculado a evidências, sem alterar a fonte de verdade da auditoria nem adicionar silenciosamente novos sinais ao `SARI-001`/`SCORE-GEO-005`.

Ela mantém separadas as seguintes perguntas:

1. **Readiness:** quais condições técnicas e semânticas foram observadas pela auditoria?
2. **Resultados observados:** o que sistemas externos de Search/AI reportaram?
3. **Mudança:** o que mudou de forma material entre auditorias persistidas?
4. **Associação:** um resultado mudou ao longo de um período comparável enquanto também existia uma regressão técnica?
5. **Qualidade da decisão:** a evidência da auditoria está completa e confiável o suficiente para sustentar decisões de remediação?

Coincidência temporal não constitui inferência causal. Novas AUDs usam `SCORE-GEO-005`; preservar a versão de scoring persistida nas AUDs históricas, inclusive `SCORE-GEO-004`. Não comparar notas de contratos distintos como se fossem metodologicamente equivalentes.

## Arquitetura

```text
AUD-BASELINE/audit.db -----\
                            > RASAi Monitor -> MON-*/report.html + manifest.json + impact.html
AUD-CURRENT/audit.db ------/

AUD-CURRENT/audit.db (somente leitura)
          |
          +--> artifacts/observability/observability.db   # RASAI-OBS-002
          +--> artifacts/observability/*
          +--> report-catalog/cat-05.html
          +--> report-catalog/metrics.html

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

A proveniência do dataset persiste tipo de origem, método de captura, período, caminho/SHA-256 do artefato, horário da coleta e metadados. Credenciais devem ser resolvidas em runtime, sem persistência de seus valores pelo contrato de observabilidade. Artefatos e metadados externos podem conter dados sensíveis residuais; aplique a [política de segurança](SECRET_AND_CONFIGURATION_SAFETY.md).

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

É selecionado um único dataset mais recente por origem/`AUD-*`. Datasets com períodos sobrepostos não são somados. Valores ausentes permanecem ausentes. Associações temporais são reportadas sem linguagem causal.

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

`report-catalog/cat-05.html` e `report-catalog/metrics.html` podem projetar:

- Indexability Reality Matrix;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- diagnósticos de dados estruturados, entidade, atualização, `hreflang` e recuperação;
- clusters por template/causa raiz;
- CrUX History;
- proveniência do dataset.

Esses são diagnósticos derivados e não alteram automaticamente `SARI-001`/`SCORE-GEO-005`.

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

## Superfícies HTML da auditoria

O catálogo técnico `report-catalog/` segue `src/rasai/catalog_report_contract.py`. Consulte `cat-05.html` e `metrics.html` para os dados de observabilidade e `execution-evidence.html` para estados operacionais. A apresentação executiva `report-presentation/` é independente: `search-geo.html` contextualiza resultados observados de busca e GEO; `indices.html` e `index.html` sintetizam índices e situação da AUD conforme as evidências disponíveis. Não se presume projeção de todos os campos de observabilidade. O inventário completo e a especialização das 21 páginas técnicas e 11 executivas estão no [guia de relatórios](REPORT_GUIDE.md#correspondência-temática-entre-os-relatórios), sem duplicar aqui a lista de navegação.

A ausência de execução ou de dado em uma capacidade não autoriza criar uma página paralela nem disparar coleta para preencher HTML. O catálogo deve projetar o estado persistido correspondente, inclusive ausência, indisponibilidade, parcialidade ou não aplicabilidade.

Outputs derivados como `MON-*/report.html`, `verification/VER-*/report.html` e `quality/TIMELINE-*/report.html` possuem contratos standalone próprios e não fazem parte de nenhum dos dois pacotes HTML da AUD.

## Expectativas de validação

A validação automatizada deve cobrir comportamento somente leitura, comparabilidade, política do gate, identidade/migração `OBS-002`, escopo de dados externos, exclusão de segredos, preservação de `NULL`, semântica de Quality/Verification/Timeline e navegação canônica.

Smoke test humano é apropriado para validar credenciais reais, comportamento de providers externos ou comportamento visual/operacional quando a mudança depende do ambiente.
