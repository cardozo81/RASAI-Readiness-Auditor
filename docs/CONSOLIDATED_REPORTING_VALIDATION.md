# Validação e reversibilidade - relatórios consolidados

**Estado:** vigente.

## Formato e contratos

Formato materializado vigente:

```text
CONS-4
```

Contratos derivados associados:

```text
TEMPORAL-APDEX-001
CONSOLIDATED-EVOLUTION-001
CONSOLIDATED-SPECIALIST-001
```

O runtime utiliza uma camada interna de renderização base identificada no código como `CONS-3`. Essa identificação é detalhe de implementação e não representa versão pública anterior nem compromisso de compatibilidade externa. A materialização `CONS-4` deve manter identidade própria e não alterar em lugar um snapshot base reutilizado.

## Fonte de verdade e escrita

As fontes são os `AUD-*/audit.db`, abertas em modo somente leitura (`SQLite mode=ro` e `PRAGMA query_only=ON`). A consolidação não recalcula auditorias, não migra schema e não grava nos bancos fonte.

Artefatos derivados:

```text
.rasai/consolidated-index.db
consolidated/CONS-*/report.html
consolidated/CONS-*/manifest.json
consolidated/CONS-*/specialist-analysis.json
```

O índice e os snapshots consolidados são reconstruíveis. O artefato especialista não contém secrets.

## Contrato comportamental CONS-4

- SARI mostra pontuação, Coverage, Confidence e estado de Consolidation persistidos;
- score parcial não é apresentado como SARI consolidado;
- séries de readiness exigem `scoring_version` e universo de URLs comparáveis;
- filtro parcial de URL não reutiliza score calculado sobre páginas excluídas;
- Lighthouse/lab e Core Web Vitals/field continuam separados;
- Navigation e User Experience Apdex continuam domínios separados;
- Apdex do período usa soma de Satisfied/Tolerating/Frustrated sobre amostras válidas comparáveis;
- p50/p75/p90/p95/p99, média, desvio-padrão e CV do período usam o pool bruto por URL/contexto, nunca média de percentis individuais;
- findings permanecem contextualizados pelo universo auditado;
- dado ausente não vira zero;
- extremos não são eliminados automaticamente;
- diferenças materiais de método criam fronteiras de comparabilidade;
- evolução factual é calculada por Monitoring/Fix Verification, não pela IA;
- IA especialista é opcional, advisory e non-scoring;
- ausência, recusa ou falha da IA não impede o relatório base;
- a camada `CONS-4` não altera em lugar snapshots do renderizador base.

## Comparação de evolução

A análise longitudinal pode usar:

```text
FIRST_LAST
LATEST_PREVIOUS
MANUAL
```

A comparação preserva escopo de URL/dispositivo e limites metodológicos. Em filtro parcial de URL, sinais agregados calculados para universo maior não podem ser reutilizados como se fossem específicos do subconjunto.

Estados determinísticos são derivados de Monitoring. Fix Verification mantém `FIXED`, `PARTIALLY_FIXED`, `NOT_FIXED` e `NOT_VERIFIABLE` separados de mera narrativa de melhora.

A validação deve garantir que o HTML não confunda:

```text
melhora observada
correção verificada
associação temporal
causalidade
```

## IA especialista e custo

Quando a IA estiver ativa no console, a análise consolidada deve ser explicitamente opt-in.

Antes da chamada externa:

1. construir o pacote de evidências persistidas;
2. estimar tokens de input/output;
3. usar o catálogo canônico `ai_cost_policy`;
4. quando a seleção for `AUTO`, usar a mesma ordenação cost-aware do runtime;
5. apresentar provider/model/reasoning/contexto tarifário/custo estimado;
6. solicitar confirmação explícita.

Sem confirmação não ocorre chamada de IA.

Quando `ai_provider=none`, quando a seleção não estiver apta ou quando a estimativa/provider não puder ser preparado, o consolidado continua sem a seção de especialista por IA.

A resposta de IA deve ser structured output e só pode citar `evidence_ids` enviados no request. Não pode alterar findings, scores, SARI ou SCORE-GEO.

## Comparabilidade do Apdex

### Synthetic Navigation Apdex

A série deve preservar, no mínimo:

```text
URL
+ device
+ task
+ profile
+ T / 4T
+ pacing relevante
```

### Synthetic User Experience Apdex

A série deve preservar, no mínimo:

```text
URL
+ device/POPULATION
+ task
+ profile
+ KPM
+ Satisfied/Frustrated thresholds
+ session mode
+ errors_affect_apdex/error scope
+ pacing/settle
+ device mix para POPULATION
```

Contextos incompatíveis não podem entrar no mesmo denominador nem no mesmo pool de durações/KPM.

## Estatística

### Apdex do período

```text
Apdex = (sum Satisfied + 0,5 x sum Tolerating) / sum Valid
```

Se as contagens S/T/F persistidas não fecharem com `valid_samples`, o denominador persistido é preservado e a limitação deve aparecer no output.

### Distribuição temporal

Amostras válidas com duração/KPM numérica formam o pool usado para média, mediana/p50, p75/p90/p95/p99, mínimo/máximo, desvio-padrão populacional e coeficiente de variação.

Amostra válida sem valor temporal continua no Apdex, mas fica fora da distribuição; a diferença deve ser declarada.

### Demais métricas

Readiness, Web Performance, findings, estados categóricos e dados externos mantêm suas políticas específicas. O consolidado não aplica uma média universal a todos os tipos de indicador.

## Integridade do snapshot e dedupe

O fingerprint `CONS-4` depende dos filtros canônicos, que incluem seleção do par de comparação e configuração não secreta da análise especialista.

Comportamento esperado:

- mesma requisição + mesmas fontes + mesmos contratos: reutiliza o mesmo `CONS-4`;
- novo AUD/filtro/par/opção de IA: novo fingerprint;
- consolidado com IA não é reutilizado por solicitação sem IA e vice-versa;
- hashes/bytes dos `AUD-*` permanecem iguais;
- `request_fingerprint`, `report_format_version`, `cons_id` e `generated_at` permanecem coerentes;
- o manifest não duplica amostras brutas nem persiste credentials.

## Gates automatizados e sistema operacional

Workflow específico:

```text
.github/workflows/consolidated-reporting-ci.yml
```

Esta superfície é local/console; portanto o workflow específico roda em **Windows**, conforme a convenção do projeto.

O control plane/SaaS é validado em **Linux** quando houver mudança pertinente ao SaaS. O contrato atual de consolidação não adiciona endpoint SaaS nem migração de schema.

O gate do consolidado deve cobrir:

- compile da superfície de consolidação;
- geração read-only e hash dos `audit.db` inalterado;
- dedupe e invalidação por novo AUD/filtro/contrato/configuração de IA;
- seleção `FIRST_LAST`, `LATEST_PREVIOUS` e `MANUAL`;
- Fix Verification e estados de evolução;
- preview de custo canônico;
- fallback sem IA;
- segregação de método/universo de URLs;
- Snapshot com N=1 sem falsa tendência;
- Apdex calculado pelas contagens persistidas;
- percentis recalculados do pool bruto;
- HTML/manifest/artefato especialista coerentes;
- regressões do console Windows.

## Testes pontuais mínimos

1. dois AUDs com `FAIL` na referência e `PASS` no comparado, confirmando `FIXED`;
2. confirmar que hashes dos dois `audit.db` não mudaram;
3. confirmar seções determinísticas no HTML sem IA configurada;
4. comparar fingerprints com `specialist_ai=false` e `specialist_ai=true`;
5. validar preview de custo com hints de tokens e catálogo canônico;
6. validar que `AUTO` usa candidatos ordenados pela política dinâmica existente;
7. negar autorização e confirmar geração sem IA;
8. usar apenas um AUD e confirmar relatório válido sem falsa comparação;
9. dois AUDs Navigation com durações conhecidas e quantidades diferentes de S/T/F;
10. alterar `T` em um AUD e confirmar séries separadas;
11. repetir para Experience/`POPULATION`;
12. abrir o HTML com o console fechado e confirmar funcionamento estático.

## SaaS/control plane

Não existe endpoint SaaS de consolidação `CONS-*` no contrato atual. A geração permanece uma superfície local e não exige migração de schema do control plane.

Qualquer exposição Web/API dessa capacidade deve reutilizar a mesma lógica canônica de comparação, autorização de custo e roteamento, sem recriar scoring, pricing ou análise longitudinal em outro serviço.

## Reversibilidade

O consolidado é derivado. Remover cache e `CONS-*` não exige migração dos `AUD-*`; os artefatos derivados podem ser reconstruídos a partir das fontes persistidas.

Veja também [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md), [`CONSOLIDATED_REPORTING_TEMPORAL.md`](CONSOLIDATED_REPORTING_TEMPORAL.md), [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md), [`REPORT_GUIDE.md`](REPORT_GUIDE.md) e [`SCORING_GUIDE.md`](SCORING_GUIDE.md).
