# AUTO cost-aware AI routing

**Data de referência da política/catálogo: 13/09/2026**  
**Versão do catálogo: `RASAI-PRICING-2026-09-13`**  
**Revisão ordinária recomendada: 13/10/2026**

Este documento define a seleção econômica usada pelo RASAi quando `AI=auto` está selecionado. O detalhamento cadastral, schema, preços vigentes, atualização local, reset de fábrica e equivalência SaaS estão em [`AI_PRICING_CONFIGURATION.md`](AI_PRICING_CONFIGURATION.md).

## 1. Princípios

A política econômica:

- somente ordena providers já configurados, elegíveis e saudáveis;
- não habilita credenciais;
- não altera quarantine/circuit breaker;
- não torna GitHub Copilot elegível ao AUTO;
- não troca silenciosamente service tier para Batch/Flex/Priority;
- trata preço como estimativa operacional, não como fatura do fornecedor.

## 2. Fonte única de pricing

Os **dados comerciais canônicos** estão em:

```text
src/rasai/config/ai-pricing-defaults.toml
```

O motor/contrato está em:

```text
src/rasai/ai_pricing_catalog.py
src/rasai/ai_cost_policy.py
```

`ai_cost_policy.py` não contém mais tabelas de preço específicas por provider. Ele preserva a API consumida por AUTO, console, telemetria e persistência.

O operador pode usar um catálogo local editável através de:

```text
RASAI_AI_PRICING_SOURCE=file
RASAI_AI_PRICING_FILE=ai-pricing.toml
```

O reset de fábrica mantém `RASAI_AI_PRICING_SOURCE=factory` em `rasai-defaults.ini`.

## 3. Algoritmo AUTO

Para cada necessidade de IA:

1. obtém providers configurados, `auto_eligible=true` e não excluídos;
2. remove candidatos inelegíveis pela política de saúde/quarentena;
3. resolve modelo e reasoning efetivos;
4. estima input/output da chamada;
5. resolve a regra de preço vigente no catálogo para provider/modelo, instante e quantidade de input tokens;
6. calcula custo estimado;
7. ordena providers precificados pelo menor custo;
8. em empate preserva rank/ordem determinística;
9. candidatos sem preço ficam depois dos precificados;
10. fallback e circuit breaker continuam com suas regras próprias.

Fórmula atual:

```text
estimated_cost =
  ((estimated_input_tokens - estimated_cached_tokens) * input_price
   + estimated_cached_tokens * cached_input_price
   + estimated_output_tokens * output_price)
  / 1_000_000
```

Após a chamada, quando usage nativo é suficiente, o custo observado é calculado usando a regra vigente e os tokens reportados.

## 4. Estruturas comerciais interpretadas pelo motor

O schema `1` suporta as estruturas necessárias às políticas conhecidas em 13/09/2026:

| Estrutura | Uso |
|---|---|
| `TOKEN_STANDARD` | preço por input/cache/output sem condição adicional além de vigência |
| `TOKEN_CONTEXT_TIERED` | preço muda por faixa de `input_tokens` |
| `TOKEN_TIME_WINDOW` | preço muda por weekday/janela UTC |

Reasoning pode ser declarado como:

- `IN_OUTPUT`;
- `ADD_REASONING_TO_OUTPUT`.

Toda regra possui `effective_from`; `effective_until` é opcional. Sem regra vigente, o modelo é não precificado.

## 5. Estado atual por provider — referência 13/09/2026

Valores em USD por 1 milhão de tokens.

| Provider / modelo | Input | Cache | Output | Contexto |
|---|---:|---:|---:|---|
| OpenAI `gpt-5.6-luna` | 0,20 | 0,02 | 1,20 | >272k: 0,40 / 0,04 / 1,80 |
| OpenAI `gpt-5.6-terra` | 2,00 | 0,20 | 12,00 | >272k: 4,00 / 0,40 / 18,00 |
| OpenAI `gpt-5.6-sol` | 4,00 | 0,40 | 20,00 | >272k: 8,00 / 0,80 / 30,00 |
| DeepSeek `deepseek-v4-flash` off-peak | 0,22 | 0,007 | 0,66 | peak: 0,44 / 0,014 / 1,32 |
| DeepSeek `deepseek-v4-pro` off-peak | 0,66 | 0,022 | 1,98 | peak: 1,32 / 0,044 / 3,96 |
| MiMo `mimo-v2.5` | 0,14 | 0,0028 | 0,28 | standard |
| MiMo `mimo-v2.5-pro` | 0,435 | 0,0036 | 0,87 | standard |
| xAI `grok-4.6` <200k | 2,00 | 0,50 | 6,00 | >=200k: 4,00 / 1,00 / 12,00 |
| Qwen `qwen3.8-flash` | 0,113 | 0,014 | 0,382 | US/Virginia |
| Qwen `qwen3.8-max` | 1,65 | 0,206 | 4,951 | US/Virginia |
| Gemini `gemini-3.8-flash` | 0,75 | 0,075 | 3,75 | reasoning soma no output; regra até 01/01/2027 UTC |
| Anthropic `claude-sonnet-5` | 2,00 | 0,20 | 10,00 | standard/cache read |
| GitHub Copilot | — | — | — | explicit-only; não precificado e fora do AUTO |

### DeepSeek

Peak atual em UTC, segunda a sexta:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

Essa lógica agora é declarada em `weekdays_utc` e `time_windows_utc` no TOML.

### OpenAI

A faixa >272k é uma regra de maior prioridade com `input_tokens_gt=272000`. Os preços finais estão no catálogo; não há multiplicador hardcoded por provider.

### xAI

A faixa longa é uma regra de maior prioridade com `input_tokens_gte=200000`.

### Qwen

As regras atuais são associadas à região `US_VIRGINIA`. Uma mudança de endpoint/região exige regra apropriada antes de considerar custos comparáveis.

### Gemini

A regra atual expira em `2027-01-01T00:00:00Z`. Sem regra posterior, o modelo fica não precificado. O campo `reasoning_billing=ADD_REASONING_TO_OUTPUT` substitui a antiga exceção hardcoded no cálculo.

## 6. Estimativas por finalidade

Quando o adapter expõe payload lógico, o router usa o tamanho serializado como aproximação de tokens. Na ausência, aplica baselines conservadores e refina com usage observado dentro da execução.

| Escopo | Baseline inicial de output |
|---|---:|
| análise semântica | 4.000 tokens, ajustados pela evidência |
| remediação de conteúdo | 900 + 650 por finding, limitado a 16.000 antes do reasoning |
| remediação técnica | 3.200 |
| Source Quality | 1.800 |
| especialista consolidado | 3.500 |

Multiplicadores de estimativa para reasoning:

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

Esses multiplicadores são heurísticas de roteamento, não preços oficiais.

## 7. Cache e aprendizado dentro da execução

Antes da primeira chamada comparável o router assume cache miss. Usage observado pode ajustar input/output/cache de chamadas posteriores da mesma execução.

A política de preço continua independente da política de saúde do provider.

## 8. SaaS

O control plane deve persistir/publicar o mesmo documento lógico do catálogo e entregar um snapshot imutável ao execution job/worker. O parser aceita `Mapping` via `load_pricing_catalog(document=...)`, evitando um segundo motor de pricing para SaaS.

Escopos futuros recomendados:

```text
ORGANIZATION > DEPLOYMENT > FACTORY > UNPRICED
```

Isso permite preços contratuais/BYOK por organização sem alterar adapters.

## 9. Política de revisão

A data de referência desta configuração é **13/09/2026**. Próxima revisão ordinária: **13/10/2026**.

Revisar imediatamente se houver mudança de preço, modelo default, região, endpoint, cache, janela horária, threshold de contexto, promoção, service tier ou divergência material entre estimativa e cobrança.

## 10. Regressão obrigatória

A suíte deve preservar:

- DeepSeek peak/off-peak e weekday UTC;
- domingo 22:xx GMT-3 convertido para segunda UTC peak;
- sábado off-peak;
- vigência do V4;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- billing de reasoning do Gemini;
- preço para todos os defaults do pool AUTO;
- candidato sem preço posterior aos precificados;
- quarantine/circuit breaker inalterados;
- configuração futura de provider/preço sem hardcode quando o modelo comercial couber no schema.
