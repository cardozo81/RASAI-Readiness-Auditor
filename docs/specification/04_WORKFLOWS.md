# WORKFLOWS.md

**Estado no baseline de desenvolvimento:** aprovado / vigente  
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

O escopo público é `mobile`, `desktop` ou `both`. Somente contextos selecionados/materializados podem disparar renderização downstream, análise ou chamadas externas.

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

## 7. Site estático de relatório

Entrada canônica:

```text
report/index.html
```

Páginas canônicas de método:

```text
report/readiness.html
report/scoring.html
```

Outras páginas de domínio são materializadas condicionalmente, incluindo Mobile/Desktop, remediation, content suggestions, crawling/discovery, accessibility, Web Performance, Search Intelligence, os dois domínios Apdex, AI visibility, Observability, Quality, AI usage e references.

Abrir HTML estático não dispara crawling, IA nem coleta de API externa. `audit.db` + artefatos permanecem a evidência de origem.

## 8. Conclusão e fluxos derivados

Uma auditoria concluída pode alimentar posteriormente workflows derivados/somente leitura:

- Monitoring (`compare`, `gate`, `impact`);
- Observability/importações;
- Quality/Fix Verification/Timeline;
- indexação na Product Platform e comparações de deployment.

Esses workflows preservam o `audit.db` de origem e não recalculam silenciosamente scoring histórico.
