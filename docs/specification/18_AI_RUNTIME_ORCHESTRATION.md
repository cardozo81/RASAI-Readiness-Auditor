# 18 - Orquestração do runtime de IA

**Estado:** vigente para o runtime multi-provider de IA.

Este contrato complementa a análise semântica e as remediações assistidas por IA sem alterar os contratos metodológicos de `SARI-001` e `SCORE-GEO-004`.

## 1. AUTO

`AI=auto` considera todos os providers registrados como `auto_eligible` que possuam credencial e configuração válidas no início da execução e que não estejam excluídos por `RASAI_AI_AUTO_EXCLUDE`.

A seleção usa round-robin compartilhado entre necessidades de IA da auditoria. Depois de uma tentativa, o cursor avança para o provider seguinte. Em uma mesma necessidade, cada provider elegível pode ser tentado no máximo uma vez; esgotar os candidatos encerra a necessidade como indisponível, sem loop.

`RASAI_AI_AUTO_EXCLUDE` tem default vazio. Os valores permitidos são IDs/aliases válidos de providers elegíveis, em lista CSV ou separada por `;`. O recomendado é manter vazio e usar a exclusão somente quando um provider deve permanecer configurado para seleção explícita, mas fora do pool AUTO.

## 2. Saúde por provider

Falhas terminais retiram o provider do pool até o fim da auditoria. Incluem, conforme a classificação vigente, autenticação, crédito/quota terminal, permissão, modelo inválido/inexistente e códigos HTTP terminais associados.

Falhas não terminais permanecem recuperáveis. O circuit breaker abre quando três falhas aparecem entre as últimas cinco observações do provider. Sucessos participam da mesma janela.

A exclusão vale somente para a execução corrente e não modifica configuração global.

## 3. Telemetria de comunicação

Cada chamada externa deve poder ser rastreada em `ai_exchange_log` com request/response sanitizados, provider/modelo, finalidade, contexto, duração, resultado e hashes/truncamento.

Credenciais e raciocínio privado do provider não podem ser persistidos. O log é telemetria de integração e não evidência de scoring.

A apresentação canônica dessa telemetria é `report/ai-usage.html`.

O limite de captura é configurado por `RASAI_AI_EXCHANGE_LOG_MAX_BYTES`: default efetivo `524288`, valores permitidos de `4096` a `4194304` bytes e recomendação de manter o default salvo necessidade de diagnóstico controlado.

## 4. Saída estruturada por provider

Schemas locais continuam normativos para validação. Quando o formato de transporte de um provider aceitar apenas um subconjunto de JSON Schema, o adapter deve projetar o schema imediatamente antes do transport e manter a validação local mais estrita depois da resposta.

Erros de schema/request são falhas técnicas de integração; não são defeitos do website auditado.

## 5. Contexto editorial AUTO

Para campos editoriais configurados como `auto`, a IA pode produzir interpretação contextual baseada exclusivamente no conteúdo/evidências enviados. A configuração persistida permanece `AUTO`.

A interpretação:

- é apresentada separadamente no HTML;
- não sobrescreve `content_analysis_contexts`;
- não é persistida como classificação canônica;
- não altera SARI/SCORE-GEO-004 por si só;
- deve usar `Não determinável` quando não houver suporte suficiente.

A classificação transitória é removida antes da normalização/persistência semântica. O HTML final pode materializar a interpretação daquela execução para comparação humana sem promovê-la a verdade persistida do contexto.

## 6. Web Performance relacionado

O transporte PageSpeed Insights vigente aceita e solicita, por default, as cinco categorias usadas pelo RASAi:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

Configuração:

| Item | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | combinação CSV sem duplicatas dessas cinco categorias | manter as cinco categorias no uso normal; reduzir somente por necessidade explícita de coleta |

`agentic-browsing` é solicitado na **mesma chamada** PageSpeed por contexto e não cria uma chamada adicional. A categoria permanece experimental no Lighthouse. Se a resposta do serviço não materializar esse resultado, `agentic_browsing_score` permanece indisponível/`NULL`; a ausência não é convertida em zero e não invalida Performance, Accessibility, Best Practices ou SEO recebidos na mesma coleta.

Web Performance permanece evidência externa/contextual e não entra automaticamente em `SARI-001`/`SCORE-GEO-004`.

Detalhamento operacional e de segurança: [`../AI_RUNTIME_ORCHESTRATION.md`](../AI_RUNTIME_ORCHESTRATION.md). Contrato do transporte PageSpeed: [`../LIGHTHOUSE_PAGESPEED_TRANSPORT.md`](../LIGHTHOUSE_PAGESPEED_TRANSPORT.md).
