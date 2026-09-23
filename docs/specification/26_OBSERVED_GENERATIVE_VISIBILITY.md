# Visibilidade generativa observada

**Estado:** vigente  
**Contrato de importação:** `OGV-IMPORT-001`  
**Impacto no scoring:** `NONE`

## 1. Objetivo

Observed Generative Visibility armazena resultados observados de Search/IA sob uma fonte explicitamente identificada ou um protocolo controlado.

```text
readiness medido != visibilidade observada
```

A importação OGV não recalcula SARI nem altera a auditoria de origem. O scoring vigente é `SCORE-GEO-004`, e dados OGV não são entrada de sua fórmula.

## 2. Fontes

Formatos de origem suportados incluem evidência normalizada de Bing AI Performance e execuções controladas de queries conforme o contrato de importação.

Quando uma API direta documentada não está disponível no contrato do RASAi, a operação permanece *import-first* e preserva artefato/proveniência da fonte.

Execuções controladas podem registrar engine, query, horário observado, validade, presença de citação e URLs citadas. São somente evidência observacional.

## 3. Limite de pesquisa

Resultados observados podem sustentar **pesquisa de validação offline separada** que estude associação entre readiness e resultados reais.

Essa pesquisa não altera resultados persistidos de `SCORE-GEO-004` nem cria contribuição de scoring. O único scoring de produção aplicável é o contrato explícito vigente.

## 4. Citation Presence Rate

```text
Citation Presence Rate = execuções válidas com citação / execuções válidas
```

Execuções inválidas ficam fora do numerador e do denominador. Tamanho amostral e intervalo de Wilson de 95% podem qualificar a taxa observada; nenhum deles é previsão universal de citações.

## 5. Escopo, proveniência e persistência

URLs sujeitas à validação de mesma origem devem pertencer a um `normalized_origin` auditado.

Artefatos são preservados no workspace da auditoria dentro da área interna de Observed Generative Visibility, com SHA-256 e metadados declarados de captura/origem. O nome físico do subdiretório é detalhe de implementação e não integra o contrato público. Reimportação é idempotente sob a identidade determinística de importação.

Tabelas incluem:

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

A importação não grava em scores, contribuições de score, RuleExecutions, findings ou recommendations.

## 6. Relatório e CLI

```text
report-catalog/cat-05.html
report-catalog/metrics.html
```

CAT-05 projeta a leitura point-in-time de Search & AI Intelligence e a visibilidade generativa observada quando houver dados; `metrics.html` mantém o inventário transversal das métricas persistidas. Fontes diferentes não são colapsadas em um score universal.

Comandos:

```powershell
rasai visibility import --audit-id AUD-... --audits-root audits --file observed-visibility.json
```

A projeção HTML é materializada pelo fluxo canônico de `report-catalog/`; o contrato atual não define subcomando `rasai visibility report`.

A inspeção do scoring atual é:

```powershell
rasai scoring inspect
```

## 7. Limites de interpretação

OGV não estabelece scoring GEO oficial, citação garantida, autoridade de ranking, causalidade ou transferibilidade universal entre engines. Métricas reportadas pela fonte permanecem métricas reportadas pela fonte.

## 8. Critérios de aceitação

- validação da importação e aplicação de escopo;
- proveniência explícita da captura;
- SHA-256 preservado;
- reimportação idempotente;
- métricas da fonte não reinterpretadas;
- execuções inválidas excluídas de Citation Presence Rate;
- relatório com amostra/proveniência explícitas;
- nenhuma mutação do scoring do `AUD-*` de origem;
- pesquisa offline separada do scoring de runtime.
