# Observed Generative Visibility — Observed Generative Visibility

**Status:** INTEGRADO E VALIDADO.
**Versão do contrato de importação:** `OGV-IMPORT-001`
**Impacto em scoring:** `NONE`

## 1. Objetivo

O Observed Generative Visibility adiciona ao SearchGEO uma camada de **outcomes observados** de Search/AI Search, rigorosamente separada do readiness inferido pelo `SGRI-001`/`SCORE-GEO-002`.

A pergunta respondida pelo Observed Generative Visibility é:

> O que foi efetivamente observado quanto a participação/citação do conteúdo em uma fonte ou protocolo explicitamente identificado?

O Observed Generative Visibility não afirma causalidade entre readiness e visibilidade, não cria um novo GEO Score e não altera pesos, thresholds ou dimensões SearchGEO.

## 2. Princípio normativo

```text
Readiness inferido != Visibilidade observada
```

- `SGRI-001` continua descrevendo readiness técnico/semântico/evidencial.
- Web Performance externo/Acessibilidade automatizada e diagnósticos Web/Synthetic Navigation Apdex/Synthetic User Experience Apdex continuam descrevendo seus domínios externos/sintéticos próprios.
- Observed Generative Visibility descreve somente outcomes observados/importados.
- uma correlação futura entre readiness e Observed Generative Visibility exige estudo empírico específico; não pode ser presumida pelo relatório.

## 3. Fontes suportadas em OGV-IMPORT-001

### 3.1 `BING_WEBMASTER_TOOLS_AI_PERFORMANCE`

Fonte observacional correspondente ao AI Performance do Bing Webmaster Tools.

A documentação pública do Bing descreve, entre outros:

- Total Citations;
- Average Cited Pages;
- grounding queries;
- atividade de citação por URL;
- tendências ao longo do tempo.

Referência primária:

- https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview

O SearchGEO **não possui nem presume uma API oficial para AI Performance**. O Observed Generative Visibility não faz scraping do portal. O usuário normaliza uma evidência/exportação observada para `OGV-IMPORT-001`; o arquivo original normalizado é preservado como artifact e identificado por SHA-256.

`total_citations` e `average_cited_pages` são persistidos como **source-reported metrics**. O SearchGEO não os recalcula para simular equivalência com uma fórmula de produto não publicada.

### 3.2 `CONTROLLED_QUERY_RUNS`

Dataset produzido por protocolo controlado externo ao scoring SearchGEO. Cada run registra no mínimo:

- engine;
- query;
- timestamp com timezone;
- status `VALID` ou `INVALID`;
- `cited=true/false` quando válido;
- URLs do origin auditado quando citado.

Opcionalmente pode registrar surface, market, language, notes e rank observado.

`rank` só é aceito quando `ranking_semantics` também é informado. O Observed Generative Visibility não presume que ordem visual, ordem de referências ou posição de citação sejam equivalentes entre engines.

### 3.3 Método de captura/proveniência

`source.capture_method` é obrigatório para qualquer fonte. Valores suportados em `OGV-IMPORT-001`:

```text
MANUAL_TRANSCRIPTION
NORMALIZED_EXPORT
CONTROLLED_PROTOCOL
EXTERNAL_AUTOMATION
```

Semântica:

- `MANUAL_TRANSCRIPTION`: transcrição humana de uma fonte observada;
- `NORMALIZED_EXPORT`: exportação/arquivo obtido externamente e normalizado para o contrato Observed Generative Visibility;
- `CONTROLLED_PROTOCOL`: dataset produzido por protocolo de query-runs controlados;
- `EXTERNAL_AUTOMATION`: coleta realizada por automação externa ao SearchGEO.

O valor é **proveniência declarada do dataset**. Ele não significa, por si só, que o SearchGEO autenticou, consultou ou coletou diretamente o dado no sistema externo. O report deve deixar essa fronteira explícita.

## 4. Citation Presence Rate

Para query-runs controlados:

```text
Citation Presence Rate = valid runs with cited=true / valid runs
```

Runs `INVALID` são excluídos do numerador e do denominador.

O relatório deve sempre apresentar o tamanho amostral. Quando `n > 0`, o SearchGEO calcula também intervalo de confiança binomial de Wilson de 95%:

```text
p = x / n
z = 1.959963984540054
center = (p + z²/(2n)) / (1 + z²/n)
half = z * sqrt((p(1-p) + z²/(4n))/n) / (1 + z²/n)
CI95 = [center-half, center+half], limitado a [0,1]
```

A escolha de 95% é convenção estatística de apresentação do Observed Generative Visibility. O intervalo mede incerteza amostral do protocolo informado; não é previsão de citação futura nem validação causal do SGRI.

## 5. Contrato JSON OGV-IMPORT-001

Exemplo:

```json
{
  "format_version": "OGV-IMPORT-001",
  "source": {
    "type": "BING_WEBMASTER_TOOLS_AI_PERFORMANCE",
    "label": "Bing Webmaster Tools AI Performance",
    "capture_method": "NORMALIZED_EXPORT",
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "market": "BR",
    "language": "pt-BR",
    "reported_metrics": {
      "total_citations": 120,
      "average_cited_pages": 1.8
    },
    "metadata": {
      "capture": "normalized-manual-export"
    }
  },
  "page_citations": [
    {"url": "https://example.com/page", "citations": 12}
  ],
  "grounding_queries": [
    {"query": "example query", "citations": 4, "url": "https://example.com/page"}
  ],
  "trend": [
    {"date": "2026-08-01", "citations": 2}
  ],
  "query_runs": [
    {
      "engine": "BING_COPILOT",
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

Todas as URLs persistidas pelo Observed Generative Visibility devem pertencer ao `normalized_origin` da auditoria.

Isso inclui:

- `page_citations[].url`;
- `grounding_queries[].url`, quando informado;
- `query_runs[].cited_urls`.

O Observed Generative Visibility rejeita importação cross-origin em vez de misturar outcomes de propriedades diferentes.

## 7. Proveniência e idempotência

O arquivo JSON é preservado em:

```text
<AUD-ID>/artifacts/m26/observed-generative-visibility-<sha16>.json
```

Persistem-se:

- SHA-256 completo;
- caminho relativo do artifact;
- source type/label;
- `capture_method`;
- período;
- market/language;
- metadata fornecida;
- timestamp de importação.

`import_id` é determinístico pelo SHA-256. Reimportar o mesmo arquivo para a mesma auditoria substitui a projeção anterior daquele artifact sem duplicar observações.

## 8. Persistência

Tabelas aditivas:

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

O Observed Generative Visibility não escreve em:

- `scores`;
- `score_contributions`;
- `rule_executions`;
- `findings`;
- `recommendations`.

## 9. Report

Arquivo dedicado:

```text
<AUD-ID>/report/ai-visibility.html
```

A página deve separar visualmente, por dataset/período:

- métricas reportadas pela fonte;
- atividade por URL;
- grounding queries;
- tendência importada;
- query-runs controlados;
- Citation Presence Rate + n + Wilson 95%, quando calculável;
- artifact, SHA-256, período, fonte e método de captura.

O report deve distinguir **fonte declarada** de **método de captura** e não pode sugerir coleta autenticada pelo SearchGEO quando o dataset foi transcrito, exportado ou produzido externamente.

Não existe agregação global que combine fontes diferentes em um único score.

## 10. CLI

Importação:

```powershell
searchgeo visibility import `
  --audit-id AUD-... `
  --audits-root audits `
  --file observed-visibility.json
```

Regeneração do report a partir do `audit.db`:

```powershell
searchgeo visibility report --audit-id AUD-... --audits-root audits
```

O entrypoint `searchgeo` roteia somente o comando `visibility` ao Observed Generative Visibility. Demais comandos continuam delegados ao pipeline `cli_extensions` existente.

## 11. Fronteiras e linguagem proibida

O Observed Generative Visibility não deve afirmar:

- “GEO Score oficial”;
- “probabilidade de citação” a partir de uma taxa histórica simples;
- que Total Citations representa ranking/autoridade;
- que uma citação prova qualidade, causalidade ou preferência do engine;
- que Bing AI Performance possui API oficial enquanto isso não estiver documentado publicamente;
- que um `capture_method` prova coleta autenticada pelo SearchGEO;
- que resultados de uma engine são universalmente transferíveis para outra.

## 12. Evolução futura

A versão seguinte pode adicionar adapters oficiais somente quando houver contrato público/documentado da fonte.

Uma futura calibração do readiness contra outcomes Observed Generative Visibility deve usar dataset longitudinal, separação por domínio entre treino/calibração/teste, múltiplas queries/runs/engines, análise de estabilidade e validação fora da amostra antes de qualquer alegação preditiva.

## 13. Critérios de aceite

- import JSON validado e same-origin;
- `source.capture_method` obrigatório e validado;
- artifact preservado com SHA-256;
- reimport idempotente;
- source-reported metrics não reinterpretadas;
- query-runs inválidos excluídos do Citation Presence Rate;
- Wilson 95% reproduzível;
- report dedicado gerado com proveniência explícita;
- zero alteração em SGRI/SCORE-GEO;
- zero chamada de rede causada pelo Observed Generative Visibility;
- `searchgeo audit` preserva comportamento anterior;
- testes automatizados cobrindo fronteiras acima.
