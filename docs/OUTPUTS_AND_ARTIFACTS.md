# Outputs e artifacts

## Workspace

Cada auditoria materializa um workspace próprio:

```text
audits/<AUD-ID>/
├─ audit.db
├─ artifacts/
├─ logs/
│  └─ audit.log
└─ report/
   ├─ index.html
   ├─ mobile.html              # condicional
   ├─ desktop.html             # condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ accessibility.html       # quando materializado
   ├─ web-performance.html
   ├─ apdex.html               # quando habilitado/materializado
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

## Fonte de verdade

`audit.db` e `artifacts/` são a persistência principal. `audit.log` registra eventos operacionais sanitizados. O HTML é projeção humana derivada desses dados.

Relatórios históricos/consolidados não mudam essa regra: `AUD-*/audit.db` continua sendo a fonte oficial e é aberto em modo somente leitura.

## Banco SQLite

O banco contém entidades da auditoria principal, evidências, execuções de regras, findings, scores, recomendações e telemetria opcional.

Grupos relevantes incluem:

### IA

```text
ai_audit_sessions
ai_provider_attempts
content_remediation_runs
content_remediation_attempts
content_remediation_suggestions
provider_pricing_catalog
```

### Web Performance

```text
web_performance_runs
web_performance_attempts
web_performance_observations
```

Essas tabelas permitem distinguir tentativa, sucesso, falha, HTTP, timeout, artifact e dados efetivamente obtidos.

### Synthetic Apdex

```text
synthetic_apdex_runs
synthetic_apdex_samples
synthetic_apdex_summaries
lighthouse_execution_profiles
```

Os nomes internos permanecem estáveis para compatibilidade de schema. A documentação operacional e os relatórios usam nomenclatura funcional.

## Índice analítico reconstruível

A consolidação histórica mantém um cache derivado fora de qualquer workspace `AUD-*`:

```text
audits/.searchgeo/consolidated-index.db
```

Esse banco contém somente projeções necessárias para filtro e estatística histórica, como metadados de auditoria, domínios, URLs, dispositivos, versões, scores, Web Performance, Apdex e classificações de findings.

Ele **não é fonte de verdade**. Pode ser removido e reconstruído a partir dos `AUD-*/audit.db` sem perda de evidência.

## Relatórios consolidados

Cada snapshot novo é salvo separadamente:

```text
audits/consolidated/CONS-<timestamp>/
├─ report.html
└─ manifest.json
```

`report.html` é estático: ao ser aberto não relê `audit.db`, não chama APIs e não recalcula indicadores.

`manifest.json` registra filtros, data de geração, fingerprints das fontes, AUDs considerados, período efetivamente observado, versões metodológicas, limitações e resultado da atualização do índice.

Quando versão do formato, filtros canônicos e fingerprints do conjunto elegível de AUDs são idênticos a um snapshot anterior, o `CONS-*` existente é reutilizado em vez de gerar uma duplicata. Novo AUD elegível ou alteração de filtro produz novo snapshot.

Detalhes: [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md).

## Artifacts de Web Performance

Quando uma resposta externa é obtida, o SearchGEO pode persistir JSON em:

```text
artifacts/web-performance/
```

Exemplos:

```text
<WPE-ID>.pagespeed.json
<WPE-ID>.crux.json
```

Se PageSpeed falhar por timeout/HTTP/quota, não existe artifact Lighthouse correspondente. O banco/log preserva a falha e o report explica quais métricas ficaram indisponíveis.

## Acessibilidade

Acessibilidade automatizada não possui uma segunda chamada externa própria. Ela reutiliza a categoria `accessibility` do artifact Lighthouse obtido via PageSpeed.

Consequência:

```text
PageSpeed falha
→ artifact Lighthouse ausente
→ score/diagnostics de acessibilidade não obtidos
→ accessibility.html deve registrar a causa
```

Isso é limitação de coleta, não ausência de problemas de acessibilidade.

## Web Performance parcial

É possível ter:

```text
PageSpeed: ERROR
CrUX: SUCCESS
Web Performance: PARTIAL
```

Nesse caso, dados de campo CrUX podem ser válidos enquanto Lighthouse lab/Acessibilidade permanecem indisponíveis.

## Synthetic Apdex

Synthetic Apdex possui persistência própria e não reutiliza duração PageSpeed como amostra.

O report dedicado é:

```text
report/apdex.html
```

Grupos abaixo de 100 amostras válidas são explicitamente identificados como small-group `*`.

## Reports

### `index.html`

Visão geral e seção **Configuração × resultado obtido**.

### `mobile.html` / `desktop.html`

Detalhes por contexto de dispositivo quando materializados.

### `remediation.html`

Findings agrupados e recomendações.

### `content-suggestions.html`

Sugestões textuais e JSON-LD advisory.

### `accessibility.html`

Evidência Lighthouse de acessibilidade quando disponível e causa da indisponibilidade quando não disponível.

### `web-performance.html`

PageSpeed/Lighthouse/CrUX, Core Web Vitals, tentativas externas e diagnósticos técnicos de performance.

### `apdex.html`

Synthetic Navigation Apdex.

### `ai-usage.html`

Provider/modelo, tentativas, tokens, reasoning e custo estimado quando persistidos.

### `references.html`

Metodologia e referências públicas.

### `consolidated/CONS-*/report.html`

Snapshot histórico/consolidado de indicadores já persistidos, filtrado por domínio, período, dispositivo e opcionalmente URL, com políticas explícitas de comparabilidade.

## Log operacional

```text
logs/audit.log
```

Deve permitir rastrear, sem secrets:

- início/fim de etapas;
- tentativa de provider;
- PageSpeed/CrUX;
- timeout/HTTP/quota;
- progresso Synthetic Apdex;
- falhas fail-open;
- geração de reports.

A consolidação não grava eventos em `AUD-*/logs/audit.log`; sua rastreabilidade fica no `manifest.json` do próprio `CONS-*`.

## Segurança

- API keys não devem ser persistidas no SQLite, report ou log;
- o arquivo `searchgeo-console.ini` também não armazena secrets;
- request IDs e diagnósticos devem ser sanitizados;
- custo estimado não é invoice;
- o consolidador não escreve em `AUD-*/audit.db` e não faz chamadas externas.
