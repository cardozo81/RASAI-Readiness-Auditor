# 28 — Audit Quality, Verification & Decision Support

**Estado no baseline de desenvolvimento:** aprovado / implementado / integrado à `main`.

## 1. Objetivo

Este domínio fornece capacidades derivadas e somente leitura que avaliam a qualidade da evidência do RASAi e apoiam decisões de remediação sem criar outro score de readiness.

Ele responde se o `AUD-*` persistido está saudável, qual é a força da evidência de cada finding, quais findings merecem atenção operacional, se recomendações ainda referenciam evidências válidas e não resolvidas, se uma auditoria posterior demonstra correção no nível de regra e como a evidência evoluiu entre `AUD-*`.

Nenhuma dessas capacidades altera `SARI-001` ou `SCORE-GEO-004`.

## 2. Limites normativos

Quality/Verification deve:

1. abrir o `audit.db` de origem somente leitura;
2. tratar `observability.db` como evidência sidecar derivada;
3. nunca modificar findings, recommendations, RuleExecution, scores ou `AUD-*` históricos;
4. nunca converter evidência ausente em falha por default;
5. distinguir Evidence Confidence da Confidence de dimensão usada pelo SARI;
6. distinguir Operational Priority de scoring/severity;
7. descrever Fix Verification apenas como evidência persistida do estado da regra;
8. nunca afirmar que uma correção técnica verificada causou mudança de outcome em Search/IA;
9. manter controles do publicador sobre uso de conteúdo fora do scoring;
10. preservar `scoring_version` da origem e limites de comparabilidade.

## 3. Relatório Quality

```text
rasai quality report --audit AUD-* [--audits-root audits]
```

Saída:

```text
<AUD-ID>/report/quality.html
```

### Audit Health

Audit Health avalia qualidade de coleta/dados, não readiness do website. As verificações podem incluir integridade SQLite, estado de conclusão, cobertura de snapshots, RuleExecutions inconclusivas/com erro, disponibilidade da versão de scoring, existência de artefatos, materialização de relatórios, integridade do sidecar e proveniência.

### Evidence Confidence

Valores permitidos:

```text
HIGH
MEDIUM
LOW
```

Essa confiança descreve a evidência que sustenta um finding. É distinta da `Confidence` em nível de dimensão usada pelo pipeline de scoring de readiness.

### Operational Priority

Classes permitidas:

```text
P0
P1
P2
P3
```

Operational Priority combina características persistidas do finding, escopo afetado, Evidence Confidence e esforço de remediação. Não altera Severity nem valores SARI/SCORE.

### Coverage Map

`NOT_OBSERVED` significa que evidência não estava disponível naquele escopo de URL/dispositivo/domínio; não significa `FAIL`.

### Recommendation Validation

Estados possíveis incluem:

```text
SUPPORTED_BY_PERSISTED_EVIDENCE
SUPPORTED_BY_GROUP
INVALID_REFERENCE
STALE_RESOLVED
CONFIDENCE_MISMATCH
```

Essa validação verifica coerência estrutural/de evidência, não correção universal do texto da recomendação.

## 4. Controles de uso de conteúdo em Search & AI

Quality pode registrar controles observados do publicador, como:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

Política restritiva do publicador não é representada como penalidade automática no SARI.

## 5. Fix Verification

```text
rasai quality verify --baseline AUD-A --current AUD-B [--url URL] [--rule BR-GEO-NNN]
```

Saída default:

```text
audits/verification/VER-*/report.html
```

Status permitidos:

- `FIXED`;
- `PARTIALLY_FIXED`;
- `NOT_FIXED`;
- `NOT_VERIFIABLE`.

Fix Verification usa evidência de comparação persistida e não pode afirmar impacto downstream em Search/IA.

## 6. Evidence Timeline

```text
rasai quality timeline [--audits-root audits] [--domain DOMAIN] [--url URL]
```

Saída default:

```text
audits/quality/TIMELINE-*/report.html
```

A timeline pode projetar horário da auditoria, versões do auditor/ruleset/scoring, quantidade de URLs, contagens `FAIL`/`WARNING`, valores das dimensões e estado selecionado de páginas. Workspaces históricos permanecem somente leitura.

## 7. Reprodutibilidade

Verificações dependentes de tempo usam timestamps persistidos da auditoria/observação para que regenerar o relatório mais tarde não altere conclusões apenas porque o relógio avançou.

Âncoras de tempo preferidas são, nesta ordem: `completed_at`, `started_at`, `created_at` e timestamp persistido de captura do snapshot.

## 8. Relação com Observability

Quality pode inspecionar `observability.db` para verificações de qualidade/proveniência, mas outcomes observados permanecem separados de SARI/SCORE-GEO-004.

Contrato sidecar atual:

```text
RASAI-OBS-002
identity = (dataset_id, record_id)
```

## 9. Linguagem dos relatórios

Prefira termos como observado, persistido, comparável, sustentado por evidência, prioridade operacional e não verificável.

Evite garantia de ganho de ranking, alegações causais derivadas de coincidência temporal, scores universais de Search & AI ou alegações de conformidade não estabelecidas pelo método.

## 10. Gates automatizados de segurança

A cobertura deve incluir migration/identidade do sidecar, preservação de `NULL`, comparabilidade temporal, limites do release gate, detecção de controles de conteúdo, avaliação de atualização baseada em horário persistido, materialização do relatório/menu Quality, semântica de Fix Verification e preservação histórica de `scoring_version`.
