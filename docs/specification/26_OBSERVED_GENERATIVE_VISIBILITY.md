# Observed Generative Visibility

**Status:** INTEGRADO E VALIDADO.
**Versão do contrato de importação:** `OGV-IMPORT-001`
**Impacto da importação em scoring:** `NONE`
**Uso posterior permitido:** `CONTROLLED_QUERY_RUNS` elegíveis podem alimentar a calibração offline do `SCORE-GEO-003`.

## 1. Objetivo

Observed Generative Visibility adiciona ao SearchGEO uma camada de **outcomes observados** de Search/AI Search.

A pergunta respondida é:

> O que foi efetivamente observado quanto a participação/citação do conteúdo em uma fonte ou protocolo explicitamente identificado?

A importação não recalcula o SGRI, não cria um novo GEO Score e não altera pesos, thresholds ou dimensões da auditoria fonte.

No `SCORE-GEO-003`, query-runs controlados podem ser usados posteriormente por um processo separado de calibração. Isso não elimina a distinção entre readiness medido e visibility observada.

## 2. Princípio normativo

```text
Readiness medido != Visibilidade observada
```

- `SGRI-001` descreve readiness técnico/semântico/evidencial.
- Web Performance, Acessibilidade e Apdex mantêm seus domínios próprios.
- Observed Generative Visibility descreve outcomes observados/importados.
- o calibrador do `SCORE-GEO-003` pode estudar associação entre as dimensões SearchGEO e `CITED/NOT_CITED`;
- associação observacional não prova causalidade nem garante citação futura.

## 3. Fontes suportadas em OGV-IMPORT-001

### 3.1 `BING_WEBMASTER_TOOLS_AI_PERFORMANCE`

Fonte observacional correspondente ao AI Performance do Bing Webmaster Tools.

A documentação pública do Bing descreve Total Citations, Average Cited Pages, grounding queries, atividade de citação por URL e tendências.

Referência primária:

- https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview

O SearchGEO não presume API oficial para AI Performance e não faz scraping do portal. O usuário normaliza uma evidência/exportação observada para `OGV-IMPORT-001`; o arquivo normalizado é preservado como artifact com SHA-256.

`total_citations` e `average_cited_pages` são persistidos como **source-reported metrics**. Não são convertidos no outcome binário do calibrador.

### 3.2 `CONTROLLED_QUERY_RUNS`

Dataset produzido por protocolo controlado externo à execução do scoring. Cada run registra no mínimo:

- engine;
- query;
- timestamp com timezone;
- status `VALID` ou `INVALID`;
- `cited=true/false` quando válido;
- URLs do origin auditado quando citado.

Opcionalmente pode registrar surface, market, language, notes e rank observado.

`rank` só é aceito com `ranking_semantics`. O SearchGEO não presume equivalência de posição entre engines.

Para calibração do `SCORE-GEO-003`, somente query-runs controlados válidos e que atendam ao promotion gate são elegíveis.

### 3.3 Método de captura/proveniência

`source.capture_method` é obrigatório:

```text
MANUAL_TRANSCRIPTION
NORMALIZED_EXPORT
CONTROLLED_PROTOCOL
EXTERNAL_AUTOMATION
```

O valor descreve proveniência declarada. Não implica que o SearchGEO autenticou ou coletou diretamente o dado no sistema externo.

## 4. Citation Presence Rate

```text
Citation Presence Rate = valid runs with cited=true / valid runs
```

Runs `INVALID` ficam fora do numerador e denominador.

Quando `n > 0`, o SearchGEO calcula Wilson 95%:

```text
p = x / n
z = 1.959963984540054
center = (p + z²/(2n)) / (1 + z²/n)
half = z * sqrt((p(1-p) + z²/(4n))/n) / (1 + z²/n)
CI95 = [center-half, center+half], limitado a [0,1]
```

A taxa e seu intervalo descrevem o dataset observado. Não são, isoladamente, previsão de citação futura.

## 5. Contrato JSON OGV-IMPORT-001

Exemplo:

```json
{
  "format_version": "OGV-IMPORT-001",
  "source": {
    "type": "CONTROLLED_QUERY_RUNS",
    "label": "Controlled query-runs",
    "capture_method": "CONTROLLED_PROTOCOL",
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "market": "BR",
    "language": "pt-BR"
  },
  "query_runs": [
    {
      "engine": "ENGINE_A",
      "surface": "AI answer",
      "query": "example query",
      "observed_at": "2026-08-20T12:00:00-03:00",
      "status": "VALID",
      "cited": true,
      "cited_urls": ["https://example.com/page"]
    }
  ]
}
```

Arrays não aplicáveis podem ser omitidos. Deve existir ao menos uma observação ou métrica reportada.

## 6. Validação de escopo

Todas as URLs persistidas devem pertencer ao `normalized_origin` da auditoria, incluindo:

- `page_citations[].url`;
- `grounding_queries[].url`;
- `query_runs[].cited_urls`.

Importação cross-origin é rejeitada.

## 7. Proveniência e idempotência

Artifact:

```text
<AUD-ID>/artifacts/m26/observed-generative-visibility-<sha16>.json
```

Persistem-se SHA-256, caminho, fonte, `capture_method`, período, market/language, metadata e timestamp de importação.

`import_id` é determinístico pelo SHA-256. Reimportar o mesmo arquivo substitui a projeção daquele artifact sem duplicar observações.

## 8. Persistência

Tabelas:

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

A operação `visibility import` não escreve em:

- `scores`;
- `score_contributions`;
- `rule_executions`;
- `findings`;
- `recommendations`.

O comando separado `searchgeo scoring calibrate` lê dados elegíveis de múltiplos `AUD-*` e grava apenas um model artifact fora dos bancos fonte.

## 9. Report

```text
<AUD-ID>/report/ai-visibility.html
```

A página separa métricas reportadas pela fonte, atividade por URL, grounding queries, tendência, query-runs, Citation Presence Rate + n + Wilson 95% e proveniência.

Não existe agregação global que combine fontes diferentes em um único score.

## 10. CLI

Importação:

```powershell
searchgeo visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Regeneração:

```powershell
searchgeo visibility report --audit-id AUD-... --audits-root audits
```

Calibração separada:

```powershell
searchgeo scoring calibrate --dataset-version GEO-CAL-001
```

A calibração não chama engines; ela usa somente outcomes já persistidos.

## 11. Relação com SCORE-GEO-003

Promotion gate mínimo vigente:

- 40 domínios;
- 12 domínios de validação;
- 2 engines;
- 10 queries por domínio;
- 3 repetições por query/engine;
- 2400 observações válidas;
- AUC holdout >= 0,60;
- Brier melhor que baseline por prevalência de treino.

O split é por domínio para reduzir leakage.

O artifact gerado permanece `EXPERIMENTAL` até satisfazer todos os gates. Artifact experimental não consolida `OVERALL_READINESS`.

Detalhes: `../SCORE_GEO_003.md` e `../SCORING_VALIDATION.md`.

## 12. Fronteiras e linguagem proibida

Não afirmar:

- “GEO Score oficial”;
- garantia/probabilidade universal de citação;
- que Total Citations representa ranking/autoridade;
- que uma citação prova qualidade ou causalidade;
- que Bing AI Performance possui API oficial sem documentação pública;
- que um `capture_method` prova coleta autenticada;
- que resultados de uma engine são universalmente transferíveis.

## 13. Critérios de aceite

- JSON validado e same-origin;
- `source.capture_method` obrigatório;
- artifact com SHA-256;
- reimport idempotente;
- source-reported metrics não reinterpretadas;
- query-runs inválidos excluídos do Citation Presence Rate;
- Wilson 95% reproduzível;
- report dedicado com proveniência explícita;
- importação sem alteração de score do AUD fonte;
- zero chamada de rede causada pelo Observed Generative Visibility;
- query-runs controlados elegíveis disponíveis para calibração offline do `SCORE-GEO-003`;
- testes automatizados cobrindo as fronteiras acima.
