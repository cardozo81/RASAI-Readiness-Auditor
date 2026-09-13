# AUTO cost-aware AI routing

Status da referência: **13/09/2026**  
Versão do catálogo de pricing: **`RASAI-PRICING-2026-09-13`**  
Revisão ordinária recomendada: **13/10/2026**

Este documento define a política de seleção econômica de IA usada pelo RASAi **somente quando `AI=auto` está selecionado**.

A política não muda o contrato de um provider explicitamente selecionado, não habilita providers sem credencial, não insere GitHub Copilot no AUTO e não altera as regras de quarentena/circuit breaker.

## 1. Objetivo

Para cada necessidade de IA, o RASAi ordena os providers ativos e elegíveis pelo **custo monetário estimado daquela requisição específica**, considerando:

- provider e modelo efetivos;
- esforço de raciocínio;
- tamanho estimado do prompt e da resposta;
- cache observado na própria execução, quando disponível;
- tarifa vigente no instante da chamada;
- janela horária oficial e weekday em UTC quando aplicável;
- faixas de contexto que alteram preço.

A seleção econômica apenas ordena candidatos já elegíveis. Ela não ignora falha, não reativa provider em quarentena e não reduz contadores do circuit breaker.

## 2. Escopo funcional

A política vale para o runtime principal `AI=auto` e para os fluxos que reutilizam o mesmo coordenador:

1. análise semântica;
2. remediação de conteúdo;
3. remediação técnica de crawling/discovery;
4. Source Quality quando o adapter é compatível.

Ficam fora:

- provider explicitamente selecionado;
- GitHub Copilot (`explicit_only`);
- Improvement Intelligence quando configurada com provider próprio;
- Competitive Search AI com configuração própria;
- PageSpeed, CrUX, SERP e demais serviços que não pertencem ao pool LLM AUTO.

## 3. Fonte única de pricing

O catálogo canônico é `src/rasai/ai_cost_policy.py`.

AUTO, telemetria, console e persistência devem usar essa mesma fonte. Quando uma regra deixa de estar vigente e não existe tarifa seguinte revalidada, o provider/modelo fica **não precificado** para aquela decisão. O RASAi não inventa tarifa futura nem reutiliza silenciosamente preço expirado.

Pricing é estimativa operacional, não substitui a fatura do fornecedor.

## 4. Algoritmo de decisão

Para cada necessidade de IA:

1. obtém providers configurados, `auto_eligible=true` e não excluídos;
2. remove candidatos inelegíveis pela política de saúde/quarentena;
3. resolve modelo e reasoning efetivos;
4. estima input/output;
5. resolve a tarifa vigente para o instante e contexto;
6. calcula custo estimado;
7. ordena providers precificados pelo menor custo;
8. em empate, preserva rank e ordem determinística;
9. candidatos sem preço ficam depois dos precificados;
10. cada provider é tentado no máximo uma vez naquela necessidade, seguindo fallback e circuit breaker existentes.

Fórmula base:

```text
estimated_cost =
  ((estimated_input_tokens - estimated_cached_tokens) * input_price
   + estimated_cached_tokens * cached_input_price
   + estimated_output_tokens * output_price)
  / 1_000_000
```

Após a chamada, quando usage nativo é fornecido, o custo observado é recalculado com os tokens reportados e a tarifa vigente naquele instante.

## 5. Estimativas por finalidade

Quando o adapter expõe o payload lógico, o router usa o tamanho serializado como aproximação de tokens. Na ausência disso, usa envelope conservador por escopo e o refina com usage observado na mesma execução.

| Escopo | Baseline inicial de output |
|---|---:|
| análise semântica | 4.000 tokens, ajustados pela evidência |
| remediação de conteúdo | 900 + 650 por finding, limitado a 16.000 antes do reasoning |
| remediação técnica | 3.200 |
| Source Quality | 1.800 |
| especialista consolidado | 3.500 |

Multiplicadores de roteamento para reasoning:

| Reasoning | Multiplicador |
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

Esses valores são heurísticas de roteamento, não preços oficiais nem limites de API.

## 6. Aprendizado dentro da execução

O coordenador mantém uma janela curta de usage por `(escopo, provider)`. Chamadas posteriores combinam a estimativa atual com mediana de input/output e proporção de cache observadas. Esse histórico vale apenas para a execução corrente e não altera scoring.

## 7. Quarentena e fallback

Continuam terminais, entre outros, `AUTH_ERROR`, `CREDIT_ERROR`, `QUOTA_ERROR`, `MODEL_ERROR`, `PERMISSION_ERROR` e HTTP 401/403/404/410.

O circuit breaker continua abrindo com **3 falhas nas últimas 5 observações** do provider.

O custo não reativa provider, não apaga falhas e não altera os limiares de quarentena.

## 8. Preços considerados em 13/09/2026

Valores em **USD por 1 milhão de tokens**, usando o modo síncrono compatível com o runtime atual.

| Provider / modelo | Input sem cache | Cache hit/read | Output | Contexto relevante |
|---|---:|---:|---:|---|
| OpenAI `gpt-5.6-luna` | 0,20 | 0,02 | 1,20 | >272k input: 2x input e 1,5x output |
| OpenAI `gpt-5.6-terra` | 2,00 | 0,20 | 12,00 | >272k input: 2x input e 1,5x output |
| OpenAI `gpt-5.6-sol` | 4,00 | 0,40 | 20,00 | >272k input: 2x input e 1,5x output |
| DeepSeek `deepseek-v4-pro` off-peak | 0,66 | 0,022 | 1,98 | janela UTC abaixo |
| DeepSeek `deepseek-v4-pro` peak | 1,32 | 0,044 | 3,96 | janela UTC abaixo |
| DeepSeek `deepseek-v4-flash` off-peak | 0,22 | 0,007 | 0,66 | vigente desde 16/08/2026 16:00 UTC |
| DeepSeek `deepseek-v4-flash` peak | 0,44 | 0,014 | 1,32 | vigente desde 16/08/2026 16:00 UTC |
| MiMo `mimo-v2.5` | 0,14 | 0,0028 | 0,28 | PAYG |
| MiMo `mimo-v2.5-pro` | 0,435 | 0,0036 | 0,87 | PAYG |
| xAI `grok-4.6`, <200k input | 2,00 | 0,50 | 6,00 | tarifa curta |
| xAI `grok-4.6`, >=200k input | 4,00 | 1,00 | 12,00 | tarifa longa |
| Qwen `qwen3.8-flash` US/Virginia | 0,113 | 0,014 | 0,382 | região do endpoint US usado pelo catálogo atual |
| Qwen `qwen3.8-max` US/Virginia | 1,65 | 0,206 | 4,951 | região do endpoint US usado pelo catálogo atual |
| Gemini `gemini-3.8-flash` standard | 0,75 | 0,075 | 3,75 | regra catalogada até 31/12/2026; output inclui thinking |
| Anthropic `claude-sonnet-5` standard | 2,00 | 0,20 | 10,00 | 0,20 representa cache read |

### 8.1 DeepSeek: timezone oficial

A DeepSeek define a janela pelo **UTC e weekday UTC**:

```text
segunda a sexta UTC
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

Todo o restante é off-peak.

Para GMT-3, a conversão é:

| Dia local GMT-3 | Peak |
|---|---|
| domingo | 22:00-24:00 |
| segunda a quinta | 00:00-01:00, 03:00-07:00, 22:00-24:00 |
| sexta | 00:00-01:00, 03:00-07:00 |
| sábado | nenhum |

A mudança de pricing da família V4 considerada pelo catálogo entra em vigor em **16/08/2026 16:00 UTC**. O runtime não deve usar a data/hora exibida em timezone local da conta como substituta da vigência oficial.

### 8.2 Qwen e região

O Model Studio possui preços regionais. O catálogo atual registra a tarifa **US/Virginia**, coerente com o endpoint `dashscope-us.aliyuncs.com` usado pela configuração padrão analisada. Uma mudança de região/endpoint exige revisão do catálogo antes de tratar o custo como comparável.

Enquanto o runtime não carregar região como dimensão explícita do preço observado, uma configuração Qwen em outra região deve ser tratada como caso que exige revisão de pricing, não como prova de que a tarifa US se aplica universalmente.

### 8.3 Batch/Flex

Batch/Flex podem reduzir preço, mas alteram latência e/ou contrato. O AUTO não muda silenciosamente service tier para economizar. Essas modalidades exigem estratégia de execução explicitamente configurável.

## 9. Regras não horárias

### OpenAI

Prompts acima de 272k tokens de input usam o multiplicador de tarifa longa catalogado para a família GPT-5.6.

### xAI

`grok-4.6` muda de tarifa em 200k tokens de input/contexto. O router seleciona a faixa pela estimativa pré-chamada e normaliza o custo observado com usage quando disponível.

### Gemini

A regra promocional atual está catalogada somente até **31/12/2026**. Sem revisão antes da expiração, o modelo fica sem preço resolvido em vez de herdar tarifa presumida.

## 10. Cache e limitações

Antes da primeira chamada comparável, o router assume cache miss. Depois, cache nativo observado pode influenciar a estimativa da mesma execução.

Limitações conhecidas:

- tokenização real varia por provider; JSON/4 é aproximação pré-chamada;
- Anthropic diferencia cache creation e cache read; o modelo canônico atual não presume descontos não observados;
- Qwen possui preços regionais e modalidades adicionais de cache;
- algumas finalidades montam o payload completo somente depois da enumeração inicial do candidato;
- uma resposta rejeitada pelo contrato local pode ter sido cobrada externamente e continua sendo tentativa de custo quando usage está disponível.

## 11. Contrato de remediação técnica e prevenção de fallback artificial

A remediação técnica continua evidence-bound. `actions` podem usar apenas o universo global de evidências fornecido. `resource_assessments` possuem universo mais estrito por recurso:

```text
ROBOTS -> somente evidence_ids autorizados para ROBOTS
SITEMAP -> somente evidence_ids autorizados para SITEMAP
```

O prompt deve expor esse mapa ao provider antes da chamada. O validator continua fail-closed e rejeita referência cruzada ou inventada. Isso evita pagar fallback adicional apenas porque o modelo não recebeu uma restrição que o runtime já aplicava localmente.

## 12. Fontes oficiais

- OpenAI GPT-5.6: `https://developers.openai.com/api/docs/models/`
- DeepSeek pricing: `https://api-docs.deepseek.com/quick_start/pricing/`
- DeepSeek changelog: `https://api-docs.deepseek.com/news/`
- Xiaomi MiMo PAYG: `https://mimo.mi.com/docs/en-US/price/pay-as-you-go`
- xAI pricing: `https://docs.x.ai/developers/pricing`
- Alibaba Qwen/Model Studio: `https://www.alibabacloud.com/help/en/model-studio/model-pricing`
- Gemini API pricing: `https://ai.google.dev/gemini-api/docs/pricing`
- Anthropic pricing: `https://platform.claude.com/docs/en/about-claude/pricing`

## 13. Política de revisão

Revisão ordinária: **mensal**, próxima em **13/10/2026**.

Revisar imediatamente se ocorrer:

- aviso de preço no dashboard/provider;
- lançamento/troca do modelo default;
- mudança de endpoint ou região do Qwen;
- mudança de cache;
- alteração de janela peak/off-peak;
- mudança de limite de contexto que altera tarifa;
- expiração de promoção;
- divergência material entre `estimated_cost` e cobrança observada.

Revisões antecipadas conhecidas:

- antes do encerramento de qualquer promoção OpenAI explicitamente catalogada;
- antes de **31/12/2026** para Gemini 3.8 Flash.

## 14. Observabilidade

O snapshot do AUTO deve expor estratégia, versão do catálogo, data recomendada para revisão e ranking de custo mais recente, incluindo provider/modelo/reasoning, volume estimado, contexto tarifário e custo estimado.

Tentativas persistem usage e custo observado quando o provider fornece informação suficiente.

## 15. Critérios de regressão

A suíte deve cobrir, no mínimo:

- DeepSeek peak/off-peak com weekday UTC;
- domingo 22:xx GMT-3 como segunda-feira UTC peak;
- sábado dentro das mesmas horas de relógio como off-peak;
- vigência do V4 Flash desde 16/08/2026 16:00 UTC;
- ausência de regra antes da vigência atual;
- preço disponível para todos os modelos default do pool AUTO;
- uma única fonte de pricing;
- thresholds OpenAI/xAI;
- expiração fail-closed do Gemini;
- efeito do reasoning;
- thinking tokens Gemini quando separados;
- escolha do menor custo estimado;
- ordem determinística de candidatos sem pricing;
- quarentena/circuit breaker inalterados;
- no máximo uma tentativa por provider por necessidade;
- contrato de remediação técnica com evidence IDs por recurso e rejeição de referências cruzadas.
