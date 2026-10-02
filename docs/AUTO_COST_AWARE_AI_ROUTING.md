# AUTO cost-aware AI routing

**Data de referência da política de preços: 02/10/2026**  
**Versão do catálogo de pricing de fábrica: `RASAI-PRICING-2026-10-02.2`**  
**Data de referência do catálogo de modelos: 02/10/2026**

Este documento define a seleção econômica usada pelo RASAi quando `AI=auto` está selecionado. O cadastro de modelos está em [`AI_MODEL_CONFIGURATION.md`](AI_MODEL_CONFIGURATION.md) e o schema comercial em [`AI_PRICING_CONFIGURATION.md`](AI_PRICING_CONFIGURATION.md).

## 1. Princípios

A política econômica:

- somente ordena providers/modelos já configurados, elegíveis, precificados e saudáveis;
- não habilita credenciais;
- não altera quarantine/circuit breaker;
- não torna Mistral durante sua homologação inicial nem GitHub Copilot elegíveis ao AUTO;
- não troca silenciosamente service tier para Batch/Flex/Priority;
- não interpreta ausência de preço como preço zero;
- trata preço como estimativa operacional, não como fatura do fornecedor.

## 2. Duas fontes declarativas e duas camadas de responsabilidade

Modelos e preços têm responsabilidades separadas. O RASAi também separa baseline do produto de configuração administrativa.

Baselines internas:

```text
src/rasai/config/ai-models-defaults.toml
src/rasai/config/ai-pricing-defaults.toml
```

Arquivos humanos:

```text
config/ai-models.toml
config/ai-pricing.toml
```

O catálogo de modelos determina:

- modelos habilitados/selecionáveis;
- default público e default técnico;
- reasoning aceito/default;
- elegibilidade do modelo ao `AUTO`;
- qualification, rank, capabilities e vigência.

O catálogo de pricing determina:

- preço de input/cache/output;
- condições runtime obrigatórias da tarifa, como tier, modalidade, operação e região;
- vigência;
- região;
- faixas de contexto;
- janelas horárias;
- interpretação de reasoning faturável.

Os motores estão em:

```text
src/rasai/ai_model_catalog.py
src/rasai/ai_model_runtime.py
src/rasai/ai_pricing_catalog.py
src/rasai/ai_cost_policy.py
```

Baseline do console interativo:

```ini
RASAI_AI_MODELS_SOURCE = auto
RASAI_AI_MODELS_FILE = config/ai-models.toml
RASAI_AI_PRICING_SOURCE = auto
RASAI_AI_PRICING_FILE = config/ai-pricing.toml
```

`auto` usa o arquivo humano quando presente e a baseline empacotada quando ausente. `factory` ignora o arquivo humano. `file` exige o arquivo configurado.

Antes de cada nova AUD, o console resolve, valida e snapshotará os catálogos efetivos. Assim, alterações salvas em `config/` valem na próxima AUD sem reiniciar o console, mas não alteram uma execução já iniciada. `Restore Defaults` não apaga os arquivos administrativos; para ignorá-los explicitamente, selecione `SOURCE=factory`.

## 3. Algoritmo AUTO

Para cada necessidade de IA:

1. consulta o registry dos providers tecnicamente integrados;
2. resolve **um modelo efetivo por provider** a partir de `RASAI_<PROVIDER>_MODEL` ou do `public_default` do catálogo;
3. exige modelo habilitado, selecionável, vigente e `auto_eligible=true`;
4. exige credencial/configuração válida e aplica `RASAI_AI_AUTO_EXCLUDE`;
5. deriva do adapter as condições efetivas de pricing (tier/modalidade/região/operação) e exige uma regra vigente que corresponda integralmente;
6. remove candidatos inelegíveis pela política de saúde/quarentena;
7. resolve reasoning efetivo e estima input/output da necessidade;
8. calcula o custo estimado da chamada atual;
9. ordena os candidatos elegíveis do menor para o maior custo estimado, preservando desempate determinístico;
10. fallback e circuit breaker continuam com suas regras próprias.

Um modelo sem pricing vigente pode continuar disponível para **seleção explícita**, se permitido pelo catálogo. Ele é excluído do `AUTO` econômico e o motivo é registrado como modelo sem preço vigente para AUTO.

Fórmula atual:

```text
estimated_cost =
  ((estimated_input_tokens - estimated_cached_input_tokens) * input_price
   + estimated_cached_input_tokens * cached_input_price
   + estimated_output_tokens * output_price)
  / 1_000_000
```

Após a chamada, quando usage nativo é suficiente, o custo observado é calculado usando a mesma regra compatível com as condições efetivas e os tokens reportados. Se o adapter estiver em endpoint/tier/modalidade não reconhecido pelo catálogo, a tentativa permanece UNPRICED; não é custo zero.

## 4. Estruturas comerciais interpretadas pelo motor

O schema `1` suporta as estruturas necessárias às políticas conhecidas em 02/10/2026:

| Estrutura | Uso |
|---|---|
| `TOKEN_STANDARD` | preço por input/cache/output sem condição adicional além de vigência |
| `TOKEN_CONTEXT_TIERED` | preço muda por faixa de `input_tokens` |
| `TOKEN_TIME_WINDOW` | preço muda por weekday/janela UTC |

Reasoning pode ser declarado como:

- `IN_OUTPUT`;
- `ADD_REASONING_TO_OUTPUT`.

Toda regra possui `effective_from`; `effective_until` é opcional. Sem regra vigente, o modelo é não precificado e fica fora do AUTO econômico.

## 5. Estado de pricing de fábrica - referência 02/10/2026

Valores em USD por 1 milhão de tokens.

| Provider / modelo | Input | Cache | Output | Contexto |
|---|---:|---:|---:|---|
| OpenAI `gpt-5.6-luna` | 0,20 | 0,02 | 1,20 | >272k: 0,40 / 0,04 / 1,80 |
| OpenAI `gpt-5.6-terra` | 2,00 | 0,20 | 12,00 | >272k: 4,00 / 0,40 / 18,00 |
| OpenAI `gpt-5.6-sol` | 4,00 | 0,40 | 20,00 | >272k: 8,00 / 0,80 / 30,00 |
| DeepSeek `deepseek-v4-flash` off-peak | 0,22 | 0,007 | 0,66 | peak: 0,44 / 0,014 / 1,32 |
| DeepSeek `deepseek-v4-pro` off-peak | 0,66 | 0,022 | 1,98 | peak: 1,32 / 0,044 / 3,96 |
| MiMo `mimo-v2.6-flash` | 0,14 | 0,0028 | 0,28 | PAYG real-time; default público |
| MiMo `mimo-v2.6-pro` | 0,435 | 0,0036 | 0,87 | PAYG real-time; default adapter |
| MiMo `mimo-v2.5` | 0,14 | 0,0028 | 0,28 | compatibilidade temporária até 21/10/2026 02:00 UTC |
| MiMo `mimo-v2.5-pro` | 0,435 | 0,0036 | 0,87 | compatibilidade temporária até 21/10/2026 02:00 UTC |
| xAI `grok-4.6` global <200k | 2,00 | 0,50 | 6,00 | >=200k: 4,00 / 1,00 / 12,00; US regional usa regras próprias |
| Qwen `qwen3.8-flash` | 0,113 | 0,014 | 0,382 | US/Virginia |
| Qwen `qwen3.8-max` | 1,65 | 0,206 | 4,951 | US/Virginia |
| Gemini `gemini-3.8-flash` | 0,75 | 0,075 | 3,75 | reasoning soma no output; regra até 01/01/2027 UTC |
| Anthropic `claude-sonnet-5` | 2,00 | 0,20 | 10,00 | standard/cache read |
| Mistral `mistral-small-2603` | 0,15 | 0,015 | 0,60 | Standard global; precificado, porém explicit-only nesta entrega |
| GitHub Copilot | - | - | - | explicit-only; não precificado e fora do AUTO |

### DeepSeek

Peak atual em UTC, segunda a sexta:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

Essa lógica é declarada em `weekdays_utc` e `time_windows_utc` no TOML.

## 5.1 Condições runtime obrigatórias

O custo econômico é resolvido com o contexto efetivo do adapter, não apenas por provider/modelo. Regras condicionadas exigem correspondência em `service_tier`, `commercial_mode`, `region` e/ou `operation_mode`, conforme o TOML. Contexto ausente, `UNKNOWN` ou divergente torna o candidato **UNPRICED**; ele permanece depois dos candidatos precificados e nunca recebe custo zero.

O AUTO não muda endpoint, tier, modalidade comercial ou modo de operação para obter uma tarifa menor. Essas escolhas pertencem à configuração/adapter já autorizado.

### OpenAI

A faixa >272k é uma regra de maior prioridade com `input_tokens_gt=272000`. Os preços finais estão no catálogo; não há multiplicador hardcoded por provider.

### xAI

A faixa longa é uma regra de maior prioridade com `input_tokens_gte=200000`. O endpoint global usa `region=GLOBAL`; o endpoint `us.api.x.ai` usa `region=US` e a tarifa regional 10% maior. Endpoint não reconhecido fica UNPRICED.

### Qwen

As regras atuais são associadas à região `US_VIRGINIA`. O adapter deriva essa região apenas do endpoint conhecido `dashscope-us.aliyuncs.com`; endpoint alternativo/desconhecido produz `UNKNOWN` e fica UNPRICED até existir regra explicitamente qualificada.

### Gemini

A regra atual expira em `2027-01-01T00:00:00Z`. Sem regra posterior, o modelo fica não precificado e sai do AUTO econômico. `reasoning_billing=ADD_REASONING_TO_OUTPUT` informa ao motor como compor o output faturável.

### Condicionamento runtime

O custo só participa do ranking quando o adapter expõe condições compatíveis com uma regra do catálogo. O AUTO usa o mesmo mecanismo de matching empregado na telemetria observada. Exemplos: OpenAI fixa `service_tier=default`; MiMo declara PAYG real-time; Qwen só usa a tarifa US/Virginia no endpoint correspondente; Mistral declara `standard_only`. Endpoint/tier não reconhecido => candidato UNPRICED, preservado depois dos candidatos precificados quando ainda for elegível.

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

Esses multiplicadores são heurísticas de roteamento, não preços oficiais. O catálogo de modelos define quais esforços são válidos para o modelo efetivo; o catálogo de pricing define a tarifa.

## 7. Cache e aprendizado dentro da execução

Antes da primeira chamada comparável o router assume cache miss. Usage observado pode ajustar input/output/cache de chamadas posteriores da mesma execução.

A política de preço continua independente da política de saúde do provider.

## 8. SaaS

O control plane armazena separadamente provider/modelo e pricing em tabelas administrativas e publica versões identificáveis. O schema atual prevê:

```text
ai_providers
ai_model_catalogs
ai_models
ai_pricing_catalogs
ai_pricing_rules
ai_catalog_events
ai_job_catalog_snapshots
```

O worker recebe snapshots imutáveis por job. O snapshot de modelos é materializado com:

```ini
RASAI_AI_MODELS_SOURCE = file
RASAI_AI_MODELS_FILE = <snapshot-do-job>
```

e o pricing com:

```ini
RASAI_AI_PRICING_SOURCE = file
RASAI_AI_PRICING_FILE = <snapshot-do-job>
```

O control plane registra as versões e hashes de ambos em `ai_job_catalog_snapshots`. Uma publicação do backoffice depois do início do job vale somente para jobs posteriores.

Não existe hot reload global de catálogos dentro de um worker que execute organizações diferentes de forma concorrente.

## 9. Política de revisão

O pricing e o catálogo de modelos de fábrica têm data de referência **02/10/2026**. A revisão ordinária de pricing é recomendada em **02/11/2026**.

Revisar imediatamente se houver mudança de preço, modelo default, disponibilidade de modelo, reasoning, região, endpoint, cache, janela horária, threshold de contexto, promoção, service tier ou divergência material entre estimativa e cobrança.

## 10. Regressão obrigatória

A suíte deve preservar:

- catálogo de modelos carregável por `factory`, `file` e `auto`;
- `config/ai-models.toml` e `config/ai-pricing.toml` como superfícies humanas padrão do console;
- nova AUD recarregando alterações salvas sem restart;
- AUD em andamento usando snapshots imutáveis mesmo após nova edição dos arquivos;
- novo modelo de provider existente projetado no mesmo adapter sem código específico do modelo;
- provider desconhecido rejeitado pelo catálogo de modelos;
- reasoning validado por modelo;
- modelo `auto_eligible` sem pricing vigente excluído do AUTO econômico;
- DeepSeek peak/off-peak e weekday UTC;
- domingo 22:xx GMT-3 convertido para segunda UTC peak;
- sábado off-peak;
- vigência do DeepSeek;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- billing de reasoning do Gemini;
- quarantine/circuit breaker inalterados;
- snapshots SaaS imutáveis para modelo e pricing.


### MiMo V2.6

A família V2.6 substitui os defaults v2.5 sem alterar o protocolo PAYG Responses do RASAi. O AUTO usa `mimo-v2.6-flash` como default econômico e só o considera quando modelo e pricing estão vigentes. Os modelos v2.5 deixam de ser efetivos no instante oficial de retirada.

A eventual seleção de Token Plan, Batch ou UltraSpeed não é permitida pelo AUTO atual. Essas modalidades possuem contrato/custo distinto e não podem ser escolhidas silenciosamente para reduzir preço. Issue de migração: #183; condicionamento runtime de pricing: #181.
