# Observed Generative Visibility

**Estado no baseline de desenvolvimento:** integrada / validada  
**Contrato de importação:** `OGV-IMPORT-001`  
**Impacto no scoring:** `NONE`

## 1. Objetivo

Observed Generative Visibility armazena outcomes observados de Search/IA sob uma fonte explicitamente identificada ou um protocolo controlado.

```text
readiness medido != visibilidade observada
```

A importação OGV não recalcula SARI nem altera a auditoria de origem. O scoring vigente é `SCORE-GEO-004`, e dados OGV não são entrada de sua fórmula.

## 2. Fontes

Formatos de origem suportados incluem evidência normalizada de Bing AI Performance e execuções controladas de queries conforme o contrato de importação.

Quando uma API direta documentada não está implementada, o RASAi permanece *import-first* e preserva artefato/proveniência da fonte.

Execuções controladas podem registrar engine, query, horário observado, validade, presença de citação e URLs citadas. São somente evidência observacional.

## 3. Limite de pesquisa

Outcomes observados podem sustentar **pesquisa de validação offline separada** que estude associação entre readiness e outcomes reais.

Essa pesquisa não deve alterar resultados persistidos de `SCORE-GEO-004`. Qualquer fórmula futura de produção derivada de trabalho empírico exige nova versão explícita de scoring.

## 4. Citation Presence Rate

```text
Citation Presence Rate = execuções válidas com citação / execuções válidas
```

Execuções inválidas ficam fora do numerador e do denominador. Tamanho amostral e intervalo de Wilson de 95% podem qualificar a taxa observada; nenhum deles é previsão universal de citações futuras.

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
report/ai-visibility.html
```

O relatório separa métricas de origem, atividade de URLs, grounding queries, tendências, execuções controladas, informações amostrais e proveniência. Fontes diferentes não são colapsadas em um score universal.

Comandos:

```powershell
rasai visibility import --audit-id AUD-... --audits-root audits --file observed-visibility.json
rasai visibility report --audit-id AUD-... --audits-root audits
```

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
