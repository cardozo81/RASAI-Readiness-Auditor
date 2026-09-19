# Fluxos de execução

**Estado:** vigente  
**Scoring:** `SCORE-GEO-004`

## 1. Fluxo principal da auditoria

```text
Inicializar
→ Resolver contexto de dispositivo
→ Descobrir
→ Adquirir/renderizar contextos selecionados
→ Análise técnica
→ Extrair evidência/conteúdo
→ Análise semântica ou fallback
→ Comparar Desktop × Mobile quando aplicável
→ Findings
→ Scores por dimensão
→ Overall SCORE-GEO-004
→ Prioridade / remediação
→ Site estático de relatório
→ Concluir
```

Os princípios centrais são Evidence First, isolamento de falhas, escopo explícito de dispositivo, IA opcional e separação entre readiness, outcomes observados, Web Performance, acessibilidade e Apdex.

## 2. Contexto de dispositivo

O escopo público é `mobile`, `desktop` ou `both`. Somente contextos selecionados/materializados podem disparar renderização posterior, análise ou chamadas externas.

A comparação Desktop × Mobile só é aplicável quando ambos os contextos existem. Uma auditoria de contexto único não trata a ausência do outro contexto como falha de renderização.

## 3. Descoberta, aquisição e evidência

A descoberta normaliza e remove duplicatas de URLs de entrada/descobertas, aplica política de origem/escopo e `max_pages`, e persiste proveniência suficiente para explicar o universo auditado.

Cada contexto selecionado de página/dispositivo preserva a evidência exigida pelo pipeline, incluindo estado HTTP, conteúdo RAW/renderizado e fatos técnicos/semânticos extraídos conforme aplicabilidade.

Falha de extractor, browser, provider ou serviço opcional é distinguida de falha do website.

## 4. Análise semântica

IA é opcional. Quando disponível, saída semântica só é aceita após validação local de contrato/schema/evidência. Quando indisponível ou insuficiente, regras exclusivamente semânticas podem permanecer `UNKNOWN`, em vez de se tornarem `FAIL`.

Falha de provider é estado operacional, não finding do website. Business Rules permanecem independentes de provider.

## 5. Findings e scoring

O fluxo de scoring:

- valida integridade de evidência/finding;
- calcula contribuições determinísticas das dimensões;
- calcula Score e Coverage por dimensão;
- deriva Confidence e Consolidation;
- calcula Overall segundo `SCORE-GEO-004`;
- valida a reprodutibilidade de BR-GEO-054.

Contrato Overall:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Regras:

- pesos de dimensão e grupos de scoring são fixos/versionados pelo contrato de scoring;
- dimensões legitimamente `NOT_APPLICABLE` saem do denominador;
- o valor Overall é `sum(Dimension Weight × measured Dimension Score) / sum(measured applicable Dimension Weight)`;
- uma dimensão aplicável sem valor não é imputada como zero; a medição ausente reduz Overall Coverage/Confidence e pode limitar Consolidation;
- Overall Coverage é a Coverage ponderada pelo peso das dimensões no universo aplicável;
- dimensões críticas (`DISCOVERY_ACCESS`, `INDEXABILITY`, `CONTENT_EXTRACTABILITY`) mantêm gates mais rígidos de Confidence/Consolidation;
- Overall consolidado exige Coverage >= 80%, Confidence `HIGH`/`MEDIUM` e nenhum bloqueador crítico de medição;
- um resultado calculável pode ser `PARTIAL` quando Coverage >= 50% e Confidence está disponível;
- evidência insuficiente nunca vira zero.

## 6. Recomendações e remediação

Recomendações derivam de findings/evidências persistidos e receitas aprovadas de remediação. Exemplos propostos não são evidência observada. Remediação não altera score por si só.

## 7. Projeção HTML da auditoria

Entrada canônica:

```text
report-catalog/index.html
```

O runtime não gera mais `report/`, `report.html` ou `remediation.html` para uma AUD. A retirada é somente de projeção HTML: recomendações, findings, evidências, causa raiz, precisão, scoring, integrações, IA e telemetria continuam sendo materializados/persistidos conforme seus contratos.

`report-catalog/` é gerado após a produção dos dados e não pode disparar coleta, provider, API externa ou IA apenas para preencher o HTML. `audit.db` + artifacts permanecem a evidência de origem.

## 8. Conclusão e fluxos derivados

Uma auditoria concluída pode alimentar fluxos derivados e somente leitura:

- Monitoring (`compare`, `gate`, `impact`);
- Observability/importações;
- Quality/Fix Verification/Timeline;
- indexação na Product Platform e comparações de deployment.

Esses fluxos preservam o `audit.db` de origem e não recalculam silenciosamente o scoring persistido da auditoria.
