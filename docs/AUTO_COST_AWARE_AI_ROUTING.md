# AUTO cost-aware AI routing

Status da referência: **12/09/2026**  
Versão do catálogo de pricing: **`RASAI-PRICING-2026-09-12`**  
Revisão ordinária recomendada: **12/10/2026**

Este documento define a política de seleção econômica de IA usada pelo RASAi **somente quando `AI=auto` está selecionado**.

A política não muda o contrato de um provider explicitamente selecionado, não habilita providers sem credencial, não insere GitHub Copilot no AUTO e não altera as regras de quarentena/circuit breaker já homologadas.

## 1. Objetivo

Para cada necessidade de IA da auditoria, o RASAi deve ordenar os providers ativos e elegíveis pelo **custo monetário estimado daquela requisição específica**, considerando:

- provider ativo;
- modelo configurado para aquele provider;
- esforço de raciocínio configurado;
- tamanho estimado do prompt efetivamente enviado;
- quantidade esperada de tokens de saída para a finalidade da chamada;
- cache observado quando existe histórico utilizável na mesma execução;
- regra de preço aplicável ao instante da chamada;
- faixas de contexto que alteram preço;
- janelas horárias oficiais quando existirem.

A seleção econômica é um critério de **ordenação dos candidatos elegíveis**, não um mecanismo para ignorar erros ou forçar uso de um provider em quarentena.

## 2. Escopo funcional

A política é aplicada ao runtime principal `AI=auto` e aos fluxos que compartilham o mesmo coordenador AUTO:

1. análise semântica;
2. remediação de conteúdo;
3. remediação técnica de crawling/discovery;
4. explicação de Source Quality quando o adapter daquele provider é compatível com esse fluxo.

Ficam fora desta política:

- provider explicitamente selecionado pelo usuário;
- GitHub Copilot, que continua `explicit_only` e `auto_eligible=false`;
- Improvement Intelligence, cujo contrato atual exige provider explícito;
- Competitive Search AI, que possui configuração própria e separada do `AI=auto` principal;
- PageSpeed, CrUX, SERP e outros serviços que não são providers de LLM do pool AUTO.

## 3. Fonte única de pricing

O catálogo canônico fica em `src/rasai/ai_cost_policy.py`.

Todos os cálculos monetários de IA que usam preços tabelados devem resolver provider, modelo, contexto tarifário e custo a partir desse mesmo catálogo. O runtime semântico, o AUTO, o console e a persistência não mantêm tabelas paralelas de preço.

Quando uma regra deixa de estar vigente e não existe uma tarifa seguinte revalidada, o custo fica **não precificado**. O RASAi não inventa tarifa futura nem reutiliza silenciosamente preço expirado.

## 4. Algoritmo de decisão

Para cada necessidade de IA:

1. obtém o conjunto de providers configurados, `auto_eligible=true` e não excluídos por `RASAI_AI_AUTO_EXCLUDE`;
2. remove qualquer provider já inelegível pela política de saúde/quarentena da execução;
3. resolve provider, modelo e reasoning efetivamente configurados;
4. estima o volume de input/output da requisição;
5. resolve o preço vigente no instante da chamada;
6. calcula o custo estimado;
7. ordena candidatos com preço conhecido do menor para o maior custo estimado;
8. em empate, usa o rank já existente do provider e depois a ordem determinística anterior;
9. providers sem preço catalogado ficam depois dos providers precificados e preservam entre si a ordem rotativa determinística do coordenador;
10. tenta cada provider no máximo uma vez naquela necessidade e usa fallback conforme a lógica existente.

A fórmula base é:

```text
estimated_cost =
  ((estimated_input_tokens - estimated_cached_tokens) * input_price
   + estimated_cached_tokens * cached_input_price
   + estimated_output_tokens * output_price)
  / 1_000_000
```

O custo de roteamento é uma **estimativa pré-chamada**. Depois da chamada, quando o provider retorna usage nativo, a telemetria de custo da tentativa é recalculada com os tokens efetivamente reportados e a tarifa vigente naquele instante.

## 5. Estimativa do prompt e da resposta

### 5.1 Input

Quando o adapter expõe `_request_payload`, o router serializa em memória o mesmo payload lógico que seria enviado e usa seu tamanho como aproximação de tokens, com razão inicial de 4 caracteres por token.

Essa aproximação existe apenas para ordenar providers antes da chamada. O provider continua sendo a fonte de verdade para usage real após a resposta.

Quando a finalidade não permite construir o payload completo antes da seleção, utiliza-se um envelope conservador por escopo e o valor é refinado durante a execução usando usage nativo observado.

### 5.2 Output por finalidade

O output esperado é específico da finalidade:

| Escopo | Baseline inicial |
|---|---:|
| análise semântica | 4.000 tokens, ajustados pela quantidade de evidências |
| remediação de conteúdo | 900 + 650 tokens por finding, limitado a 16.000 antes do multiplicador de reasoning |
| remediação técnica de crawling/discovery | 3.200 tokens |
| Source Quality | 1.800 tokens |

Os números acima são **heurísticas de roteamento**, não preços oficiais nem limites de API.

### 5.3 Reasoning

O esforço configurado é incorporado como multiplicador conservador sobre o envelope esperado de saída:

| Reasoning | Multiplicador de roteamento |
|---|---:|
| `NONE` | 1,00 |
| `LOW` | 1,10 |
| `MEDIUM` | 1,35 |
| `HIGH` | 1,70 |
| `XHIGH` | 2,20 |
| `MAX` | 2,80 |
| `ADAPTIVE` | 1,50 |
| `PROVIDER_DEFAULT` | 1,20 |
| `THINKING_ENABLED` | 1,70 |

Esses fatores não pretendem reproduzir a implementação interna de reasoning de cada fornecedor. Eles evitam comparar um modelo configurado em baixo esforço com outro em esforço elevado como se ambos tivessem a mesma expectativa de geração.

## 6. Aprendizado durante a própria execução

O coordenador mantém uma janela curta de usage por `(escopo, provider)` durante a auditoria.

Quando já existem chamadas anteriores comparáveis, o próximo cálculo combina:

- tamanho estimado do request atual;
- mediana de input observado;
- mediana de output observado;
- proporção de cache observada.

Isso permite que uma auditoria com várias páginas converja progressivamente para uma previsão mais aderente ao comportamento real do conteúdo e dos providers ativos.

Esse histórico é usado apenas para roteamento daquela execução; não substitui a telemetria persistida nem altera scoring.

## 7. Quarentena e fallback: sem mudança de contrato

A lógica de saúde permanece a mesma.

### Exclusão imediata

Continuam terminais:

- `AUTH_ERROR`;
- `CREDIT_ERROR`;
- `QUOTA_ERROR`;
- `MODEL_ERROR`;
- `PERMISSION_ERROR`;
- HTTP 401, 403, 404 e 410.

### Circuit breaker temporário

Continua abrindo com **3 falhas nas últimas 5 observações** do provider.

O custo não reativa provider em quarentena, não reduz contadores, não ignora falhas e não muda a classificação de erro. A única alteração de comportamento do AUTO é a ordem em que candidatos ainda elegíveis são tentados.

## 8. Preços considerados em 12/09/2026

Todos os valores abaixo são em **USD por 1 milhão de tokens**, no modo síncrono/standard compatível com o runtime atual do RASAi.

| Provider / modelo | Input sem cache | Cache hit/read | Output | Contexto relevante |
|---|---:|---:|---:|---|
| OpenAI `gpt-5.6-luna` | 0,20 | 0,02 | 1,20 | >272k input: 2x input e 1,5x output |
| OpenAI `gpt-5.6-terra` | 2,00 | 0,20 | 12,00 | >272k input: 2x input e 1,5x output |
| OpenAI `gpt-5.6-sol` | 4,00 | 0,40 | 20,00 | >272k input: 2x input e 1,5x output; promoção vigente na data desta revisão |
| DeepSeek `deepseek-v4-pro` off-peak | 0,66 | 0,022 | 1,98 | janela UTC descrita abaixo |
| DeepSeek `deepseek-v4-pro` peak | 1,32 | 0,044 | 3,96 | janela UTC descrita abaixo |
| DeepSeek `deepseek-v4-flash` off-peak | 0,15 | 0,003 | 0,60 | preço vigente desde 10/09/2026 04:00 UTC |
| DeepSeek `deepseek-v4-flash` peak | 0,30 | 0,006 | 1,20 | preço vigente desde 10/09/2026 04:00 UTC |
| MiMo `mimo-v2.5` | 0,14 | 0,0028 | 0,28 | PAYG, sem janela horária |
| MiMo `mimo-v2.5-pro` | 0,435 | 0,0036 | 0,87 | PAYG, sem janela horária |
| xAI `grok-4.6`, <200k input | 2,00 | 0,50 | 6,00 | tarifa curta |
| xAI `grok-4.6`, >=200k input | 4,00 | 1,00 | 12,00 | tarifa longa |
| Qwen `qwen3.8-flash` US/Virginia | 0,113 | 0,014 | 0,382 | cache implícito/read |
| Qwen `qwen3.8-max` US/Virginia | 1,65 | 0,206 | 4,951 | cache implícito/read |
| Gemini `gemini-3.8-flash` standard | 0,75 | 0,075 | 3,75 | promoção vigente até 31/12/2026; output inclui thinking |
| Anthropic `claude-sonnet-5` standard | 2,00 | 0,20 | 10,00 | 0,20 representa cache read; cache write possui tarifa própria |

### 8.1 Por que Batch/Flex não entram automaticamente

OpenAI Batch, Anthropic Batch e Gemini Batch/Flex podem reduzir custo, mas alteram latência e/ou contrato de execução. O router **não troca silenciosamente o service tier** para economizar preço.

A política atual compara apenas modos síncronos já compatíveis com a expectativa operacional do RASAi. Batch/Flex devem ser tratados futuramente como estratégia de execução assíncrona explicitamente configurável.

### 8.2 MiMo Token Plan

O Token Plan possui regras próprias e coeficiente por horário, mas não é usado pelo adapter PAYG atual e possui restrições de cenário de uso. O AUTO não utiliza esse desconto.

## 9. DeepSeek: timezone oficial e conversão GMT-3

A DeepSeek define peak/off-peak em **UTC**, não pelo timezone visual da conta do consumidor.

Peak oficial:

```text
segunda a sexta em UTC
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

Todo o restante é off-peak.

O weekday também deve ser avaliado em UTC. Essa regra é necessária porque, em GMT-3, a primeira janela de segunda-feira começa ainda no domingo local.

### Conversão para GMT-3

| Dia local GMT-3 | Peak |
|---|---|
| domingo | 22:00-24:00 |
| segunda a quinta | 00:00-01:00, 03:00-07:00, 22:00-24:00 |
| sexta | 00:00-01:00, 03:00-07:00 |
| sábado | nenhum |

A maior janela contínua off-peak em GMT-3 é:

```text
sexta 07:00 -> domingo 22:00
```

Total: **63 horas**.

O banner da conta DeepSeek observado em 12/09/2026 informa todos os horários do dashboard em GMT-3, mas o anúncio de alteração do Flash especifica `12:00 Beijing Time on September 10, 2026`. Essa vigência corresponde a:

```text
10/09/2026 12:00 Beijing (UTC+8)
= 10/09/2026 04:00 UTC
= 10/09/2026 01:00 GMT-3
```

O catálogo considera somente a tarifa vigente para o contrato atual do RASAi. Como o produto ainda não foi publicado, não existe contrato histórico de pricing a preservar.

## 10. Regras não horárias que alteram preço

### OpenAI

Para a família GPT-5.6 usada pelo RASAi, prompts acima de 272k tokens de input usam a tarifa longa informada pelo fornecedor: o request completo passa a 2x input e 1,5x output. O router resolve isso por request.

### xAI

`grok-4.6` muda de tarifa em 200k tokens de contexto. O router usa a estimativa de input para selecionar a faixa antes da chamada e o usage nativo para normalizar o custo observado depois.

### Gemini

A tarifa promocional vigente foi catalogada somente até **31/12/2026**. Se o catálogo não tiver sido revisado antes de 01/01/2027, Gemini passa a ficar sem preço resolvido para roteamento econômico em vez de o RASAi presumir uma tarifa futura não revalidada.

## 11. Cache e limitações de telemetria

Antes da primeira chamada comparável, o router assume cache miss. Isso evita escolher um provider com base em um desconto de cache que talvez não ocorra.

Depois que usage nativo reporta cache, a proporção observada pode influenciar as próximas estimativas da mesma execução.

Limitações conhecidas:

- tokenização real varia entre providers; tamanho de JSON/4 é apenas aproximação pré-chamada;
- Anthropic diferencia cache creation de 5 min/1 h e cache read, mas o modelo de usage canônico atual do RASAi não preserva separadamente todos os tokens de cache write; por isso o router não presume desconto de write;
- Qwen possui modalidades adicionais de cache explícito; o runtime atual utiliza a tarifa de input/cache observável pelo adapter corrente;
- remediação técnica de crawling/discovery e Source Quality usam baseline na primeira seleção porque seu payload completo é construído depois da enumeração do candidato; usage real da própria execução passa a refinar chamadas seguintes;
- uma resposta rejeitada pelo contrato local pode ainda gerar cobrança externa e deve continuar aparecendo na telemetria quando usage estiver disponível.

## 12. Fontes oficiais

- OpenAI GPT-5.6: `https://developers.openai.com/api/docs/models/`
- DeepSeek pricing: `https://api-docs.deepseek.com/quick_start/pricing/`
- DeepSeek usage/account banner usado para a alteração Flash de 10/09/2026: `https://platform.deepseek.com/usage`
- Xiaomi MiMo PAYG: `https://mimo.mi.com/docs/en-US/price/pay-as-you-go`
- xAI pricing: `https://docs.x.ai/developers/pricing`
- Alibaba Qwen/Model Studio: `https://www.alibabacloud.com/help/en/model-studio/`
- Gemini API pricing: `https://ai.google.dev/gemini-api/docs/pricing`
- Anthropic pricing: `https://platform.claude.com/docs/en/about-claude/pricing`
- GitHub Copilot SDK billing: `https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing`

## 13. Política de revisão do catálogo

Revisão ordinária recomendada: **mensal**, com próxima revisão em **12/10/2026**.

Além da revisão mensal, o catálogo deve ser revisado imediatamente quando ocorrer qualquer um destes eventos:

- aviso de preço exibido no console/dashboard do provider;
- lançamento ou troca do modelo default de um provider;
- alteração de endpoint/região do Qwen;
- mudança em política de cache;
- nova janela peak/off-peak;
- alteração de limite de contexto que muda tarifa;
- antes do encerramento conhecido de promoção;
- divergência material entre `estimated_cost` do RASAi e cobrança observada.

Datas que merecem revisão antecipada já conhecidas em 12/09/2026:

- **até 21/11/2026**: revalidar promoção/preço do GPT-5.6 Sol;
- **antes de 31/12/2026**: revalidar Gemini 3.8 Flash antes da expiração da regra catalogada.

## 14. Observabilidade

O `session_snapshot()` do AUTO expõe:

- `strategy=COST_AWARE_WITH_CIRCUIT_BREAKER`;
- versão do catálogo de preço;
- data de revisão recomendada;
- indicador `pricing_review_due`;
- último ranking de custo calculado, incluindo provider, modelo, reasoning, input/output estimados, contexto tarifário e custo estimado.

A telemetria de tentativas continua persistindo usage e custo observado quando disponíveis.

## 15. Critérios de regressão

A suíte deve cobrir pelo menos:

- DeepSeek peak/off-peak com weekday em UTC;
- domingo 22:xx GMT-3 corretamente reconhecido como segunda-feira peak em UTC;
- sábado em horário `01:00-04:00 UTC` corretamente tratado como off-peak;
- vigência do preço Flash desde 10/09/2026 04:00 UTC;
- ausência de regra anterior ao início do contrato atual de pricing;
- preço disponível para todos os modelos default do pool AUTO;
- uma única fonte de pricing compartilhada entre AUTO, runtime semântico, console e persistência;
- thresholds de contexto OpenAI/xAI;
- expiração fail-closed do preço promocional Gemini até nova revisão;
- efeito de reasoning no envelope de custo;
- contabilização dos thinking tokens Gemini quando reportados separadamente;
- escolha do candidato precificado de menor custo;
- preservação da ordem rotativa determinística para candidatos sem pricing;
- quarentena imediata e circuit breaker sem mudança de limiares;
- no máximo uma tentativa por provider por necessidade.
