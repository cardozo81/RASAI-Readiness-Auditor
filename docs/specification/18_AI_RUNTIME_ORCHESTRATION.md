# 18 — AI Runtime Orchestration

Status: **vigente** para o runtime multi-provider de IA.

Este contrato complementa a análise semântica e as remediações assistidas por IA sem alterar os contratos metodológicos de `SARI-001` e `SCORE-GEO-004`.

## 1. AUTO

`AI=auto` considera todos os providers registrados como `auto_eligible` que possuam credencial e configuração válidas no início da execução.

A seleção usa round-robin compartilhado entre necessidades de IA da auditoria. Depois de uma tentativa, o cursor avança para o provider seguinte. Em uma mesma necessidade, cada provider elegível pode ser tentado no máximo uma vez; esgotar os candidatos encerra a necessidade como indisponível, sem loop.

## 2. Saúde por provider

Falhas terminais retiram o provider do pool até o fim da auditoria. Incluem autenticação, crédito, quota terminal, permissão, modelo inválido/inexistente e HTTP 401/403/404/410.

Falhas não terminais permanecem recuperáveis. O circuit breaker abre quando três falhas aparecem entre as últimas cinco observações do provider. Sucessos participam da mesma janela.

A exclusão vale somente para a execução corrente e não modifica configuração global.

## 3. Telemetria de comunicação

Cada chamada externa deve poder ser rastreada em `ai_exchange_log` com request/response sanitizados, provider/modelo, finalidade, contexto, duração, resultado e hashes/truncamento.

Credenciais e raciocínio privado do provider não podem ser persistidos. O log é telemetria de integração e não evidência de scoring.

A apresentação canônica dessa telemetria é `report/ai-usage.html`.

## 4. Structured output por provider

Schemas locais continuam normativos para validação. Quando o wire format de um provider aceitar apenas um subconjunto de JSON Schema, o adapter deve projetar o schema imediatamente antes do transport e manter a validação local mais estrita depois da resposta.

Erros de schema/request são falhas técnicas de integração; não são defeitos do website auditado.

## 5. Contexto editorial AUTO

Para campos editoriais configurados como `auto`, a IA pode produzir interpretação contextual baseada exclusivamente no conteúdo/evidências enviados. A configuração persistida permanece `AUTO`.

A interpretação:

- é apresentada separadamente no HTML;
- não sobrescreve `content_analysis_contexts`;
- não é persistida como classificação canônica;
- não altera SARI/SCORE-GEO-004 por si só;
- deve usar `Não determinável` quando não houver suporte suficiente.

A classificação transitória é removida antes da normalização/persistência semântica. O HTML final pode materializar a interpretação daquela execução para comparação humana.

## 6. Web Performance relacionado

O transporte PageSpeed Insights vigente aceita somente as categorias usadas pelo RASAi `performance`, `accessibility`, `best-practices` e `seo`. `agentic-browsing` exige fonte Lighthouse separada e não integra o request PageSpeed.

Detalhamento operacional e de segurança: [`../AI_RUNTIME_ORCHESTRATION.md`](../AI_RUNTIME_ORCHESTRATION.md).
