# Configuração de preços de IA do RASAi

**Estado:** vigente.  
**Data de referência desta configuração:** 13/09/2026  
**Versão do catálogo de fábrica:** `RASAI-PRICING-2026-09-13`  
**Schema do catálogo:** `1`  
**Revisão ordinária recomendada:** 13/10/2026

Os preços deste documento e de `src/rasai/config/ai-pricing-defaults.toml` representam a política conhecida e validada na data de referência. Eles são usados para estimativa operacional e roteamento econômico. Não substituem a fatura do fornecedor.

## 1. Objetivo

A política comercial de uma IA não deve exigir alteração de código quando a mudança puder ser expressa pelo schema de pricing vigente.

O RASAi separa:

- **motor de pricing**: interpreta regras, vigência, faixas de tokens e janelas de horário;
- **catálogo de pricing**: contém valores e condições comerciais por provider/modelo;
- **roteamento AUTO**: usa o preço resolvido para ordenar candidatos elegíveis;
- **telemetria/persistência**: registra custo e versão do pricing usados pela execução;
- **configuração local**: usa a superfície humana em `config/` ou a baseline de fábrica;
- **SaaS/control plane**: usa o mesmo schema lógico e fixa um snapshot por job.

Mudanças de preço, promoções, horários peak/off-peak e thresholds de contexto são representadas por dados quando já cabem nas primitivas do schema.

## 2. Fonte canônica e responsabilidades

A regra operacional é a mesma usada pelos demais catálogos de IA:

> `config/` na raiz é a superfície editável pelo humano. `src/rasai/config/` contém baselines internas distribuídas com o produto.

| Artefato | Responsabilidade | Alteração humana operacional |
|---|---|---|
| `config/ai-pricing.toml` | catálogo operacional de preços | **sim** |
| `config/ai-models.toml` | catálogo operacional de modelos | **sim** |
| `config/ai-task-profiles.toml` | overrides de personas/perfis | **sim** |
| `src/rasai/config/ai-pricing-defaults.toml` | preços de fábrica | não |
| `src/rasai/config/ai-models-defaults.toml` | modelos de fábrica | não |
| `src/rasai/config/ai-profiles-defaults.toml` | personas de fábrica | não |
| `src/rasai/ai_pricing_catalog.py` | parser, validação e seleção de regra | código |
| `src/rasai/ai_cost_policy.py` | cálculo de custo e API de pricing | código |

Não existe outro formato público de pricing que deva ser conciliado com o TOML.

## 3. Variáveis de configuração

### `RASAI_AI_PRICING_SOURCE`

| Valor | Comportamento |
|---|---|
| `factory` | ignora o arquivo do operador e usa a baseline empacotada |
| `file` | exige `RASAI_AI_PRICING_FILE`; ausência ou conteúdo inválido é erro fail-closed |
| `auto` | usa o arquivo configurado quando existe; caso contrário usa a baseline de fábrica |

### `RASAI_AI_PRICING_FILE`

Baseline do console interativo:

```ini
RASAI_AI_PRICING_SOURCE = auto
RASAI_AI_PRICING_FILE = config/ai-pricing.toml
```

O caminho relativo é resolvido a partir do diretório de execução. Caminho absoluto também é aceito.

Precedência local:

```text
variável de processo/SO
    > [environment] do rasai-console.ini
    > rasai-defaults.ini
```

As duas variáveis são configuração não secreta e fazem parte da superfície gerenciada pelo console.

## 4. Atualização pelo humano e snapshot da AUD

No console local, o operador altera **`config/ai-pricing.toml`**. Não deve editar `src/rasai/config/ai-pricing-defaults.toml` para ajustes operacionais.

Ao iniciar uma nova AUD, o console:

1. resolve a origem e o caminho efetivos;
2. copia o catálogo file-backed para um snapshot temporário imutável;
3. valida o catálogo antes da execução;
4. atualiza o pricing usado pela prévia/estimativa do processo pai;
5. passa o snapshot ao subprocesso que executará a AUD.

Consequências:

- não é necessário reiniciar o console após salvar o TOML;
- a alteração vale na **próxima AUD iniciada**;
- uma AUD em andamento não muda de preço no meio da execução;
- se o arquivo for alterado novamente durante a AUD, a alteração só participa de uma execução posterior;
- erro de catálogo falha no precheck antes de iniciar o subprocesso.

O RASAi não usa file-watcher nem hot reload por chamada de IA. A unidade de consistência é a execução/AUD.

`Restore Defaults` restaura as variáveis gerenciadas ao baseline desta versão. Os arquivos administrativos em `config/` não são apagados. Para ignorar explicitamente o catálogo do operador, use `RASAI_AI_PRICING_SOURCE=factory`.

## 5. Estrutura do catálogo

Metadados obrigatórios:

```toml
[metadata]
schema_version = 1
catalog_version = "RASAI-PRICING-2026-09-13"
reference_date = "2026-09-13"
verified_on = "2026-09-13"
review_recommended_on = "2026-10-13"
```

Cada provider/modelo declara:

```toml
[[models]]
provider = "PROVIDER"
model = "model-name"
pricing_model = "TOKEN_STANDARD"
reasoning_billing = "IN_OUTPUT"
region = "GLOBAL"
source_reference = "https://fonte-oficial"
```

Depois declara uma ou mais regras:

```toml
[[models.rules]]
rule_id = "provider-model-standard"
context = "STANDARD"
priority = 0
effective_from = "2026-09-13T00:00:00Z"
input_price_per_million = 0.50
cached_input_price_per_million = 0.05
output_price_per_million = 2.00
```

A unidade usada pelo runtime é preço por 1.000.000 tokens para input sem cache, input em cache/cache read e output faturável. `currency` pode ser informado no modelo; quando omitido, assume `USD`.

## 6. Modelos estruturais suportados

### 6.1 `TOKEN_STANDARD`

Use quando o preço é estável durante a vigência e não depende de horário ou tamanho de contexto. Aplicações atuais incluem MiMo, Qwen, Gemini e Anthropic.

### 6.2 `TOKEN_CONTEXT_TIERED`

Use quando o preço muda por volume de input/contexto. Condições suportadas:

```text
input_tokens_gte
input_tokens_gt
input_tokens_lte
input_tokens_lt
```

Aplicações atuais incluem OpenAI GPT-5.6 acima de 272.000 tokens e xAI Grok 4.6 a partir de 200.000 tokens.

### 6.3 `TOKEN_TIME_WINDOW`

Use quando o preço depende de dia e horário. Campos:

```text
weekdays_utc
time_windows_utc
```

As janelas são declaradas em UTC. O motor converte o instante da chamada para UTC antes da resolução. A aplicação atual é DeepSeek V4 Pro/Flash peak e off-peak.

## 7. Reasoning faturável

| Valor | Significado |
|---|---|
| `IN_OUTPUT` | `output_tokens` já representa o volume faturável de output |
| `ADD_REASONING_TO_OUTPUT` | `reasoning_tokens`, quando reportado separadamente, é somado ao output faturável |

O Gemini vigente usa `ADD_REASONING_TO_OUTPUT`. Essa interpretação pertence ao catálogo e não deve virar condição hardcoded por provider quando o schema já representa a regra.

## 8. Vigência

Toda regra exige `effective_from` e pode ter `effective_until`. Sem regra vigente, o provider/modelo é **UNPRICED**.

O RASAi não deve inventar preço, manter silenciosamente preço expirado, extrapolar promoção vencida, assumir preço de outra região ou usar valor fora da vigência apenas para evitar UNPRICED.

## 9. Prioridade de regras

Quando mais de uma regra é válida, a seleção é:

1. maior `priority`;
2. `effective_from` mais recente;
3. `rule_id` como desempate determinístico.

## 10. Política por IA - referência 13/09/2026

Valores em USD por 1 milhão de tokens.

| IA / modelo | Estrutura | Input | Cache/read | Output | Regra adicional |
|---|---|---:|---:|---:|---|
| OpenAI `gpt-5.6-luna` | `TOKEN_CONTEXT_TIERED` | 0,20 | 0,02 | 1,20 | >272k input: 0,40 / 0,04 / 1,80 |
| OpenAI `gpt-5.6-terra` | `TOKEN_CONTEXT_TIERED` | 2,00 | 0,20 | 12,00 | >272k input: 4,00 / 0,40 / 18,00 |
| OpenAI `gpt-5.6-sol` | `TOKEN_CONTEXT_TIERED` | 4,00 | 0,40 | 20,00 | >272k input: 8,00 / 0,80 / 30,00 |
| DeepSeek `deepseek-v4-flash` off-peak | `TOKEN_TIME_WINDOW` | 0,22 | 0,007 | 0,66 | peak: 0,44 / 0,014 / 1,32 |
| DeepSeek `deepseek-v4-pro` off-peak | `TOKEN_TIME_WINDOW` | 0,66 | 0,022 | 1,98 | peak: 1,32 / 0,044 / 3,96 |
| Xiaomi MiMo `mimo-v2.5` | `TOKEN_STANDARD` | 0,14 | 0,0028 | 0,28 | PAYG |
| Xiaomi MiMo `mimo-v2.5-pro` | `TOKEN_STANDARD` | 0,435 | 0,0036 | 0,87 | PAYG |
| xAI `grok-4.6` <200k | `TOKEN_CONTEXT_TIERED` | 2,00 | 0,50 | 6,00 | >=200k: 4,00 / 1,00 / 12,00 |
| Qwen `qwen3.8-flash` | `TOKEN_STANDARD` | 0,113 | 0,014 | 0,382 | região US/Virginia |
| Qwen `qwen3.8-max` | `TOKEN_STANDARD` | 1,65 | 0,206 | 4,951 | região US/Virginia |
| Gemini `gemini-3.8-flash` | `TOKEN_STANDARD` | 0,75 | 0,075 | 3,75 | thinking/reasoning soma no output; regra até 01/01/2027 UTC |
| Anthropic `claude-sonnet-5` | `TOKEN_STANDARD` | 2,00 | 0,20 | 10,00 | 0,20 representa cache read no modelo vigente |
| GitHub Copilot `auto` | **UNPRICED** | - | - | - | explicit-only e `auto_eligible=false`; não participa do ranking AUTO |

A tabela é uma fotografia operacional da data de referência. O TOML efetivamente snapshotado para a execução é a autoridade de cálculo daquela AUD.

### 10.1 DeepSeek

Peak em UTC, segunda a sexta:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

### 10.2 OpenAI

A faixa longa usa `input_tokens_gt=272000`; os valores finais já estão na regra.

### 10.3 xAI

A faixa longa usa `input_tokens_gte=200000`.

### 10.4 Qwen

O catálogo registra `region="US_VIRGINIA"`. Endpoint/região e pricing precisam continuar coerentes.

### 10.5 Gemini

A regra atual possui `effective_until = "2027-01-01T00:00:00Z"`. Sem regra vigente após esse instante, o modelo fica UNPRICED.

### 10.6 GitHub Copilot

Na referência de 13/09/2026 não existe tarifa unitária de API cadastrada no RASAi. O provider é explicit-only e não é elegível ao AUTO.

## 11. Como atualizar um preço localmente

Fluxo operacional:

1. edite `config/ai-pricing.toml`;
2. altere somente valores, vigências ou condições suportadas pelo schema;
3. atualize `catalog_version`;
4. atualize `reference_date` e `verified_on`;
5. ajuste `review_recommended_on`;
6. salve o arquivo;
7. inicie a próxima AUD.

Com o baseline do console:

```ini
RASAI_AI_PRICING_SOURCE = auto
RASAI_AI_PRICING_FILE = config/ai-pricing.toml
```

não é necessário reiniciar o console. O próximo precheck cria novo snapshot. Para ignorar o catálogo do operador e usar a baseline empacotada:

```ini
RASAI_AI_PRICING_SOURCE = factory
```

## 12. Regra com vigência posterior

Uma política futura pode ser cadastrada com `effective_from` posterior sem substituir antecipadamente a regra ainda vigente. Quando a vigência começar, o motor passa a selecionar a regra aplicável.

## 13. Provider sem preço com regra adicionada posteriormente

Ausência de provider/modelo/regra válida equivale a UNPRICED. Se um provider já suportado pelo runtime passar a ter cobrança unitária compatível com o schema, o catálogo pode receber a regra sem alteração do motor. Pricing não cria adapter nem credencial.

## 14. Limites do schema atual

Alteração de código é necessária para unidade de cobrança materialmente nova não representada pelo schema, por exemplo preço por requisição, tool call, imagem, segundo de áudio/vídeo, compute-time ou cache-write independente. O catálogo nunca deve aceitar Python, JavaScript ou outra execução arbitrária como regra comercial.

## 15. SaaS / control plane

O control plane usa o mesmo schema lógico. O contrato de execução é job-scoped:

```text
catálogo validado
        |
        v
versão/snapshot imutável associado ao job
        |
        v
worker materializa o snapshot TOML
        |
        v
RASAI_AI_PRICING_SOURCE=file
RASAI_AI_PRICING_FILE=<snapshot-do-job>
        |
        v
processo RASAi inicia e fixa o catálogo
```

Não usar hot reload global em processo que execute organizações diferentes concorrentemente.

## 16. Reprodutibilidade de pricing

Preço corrente não deve reinterpretar o custo persistido de execução concluída. Cada execução deve manter provider/modelo, versão do pricing, contexto resolvido, preço efetivo, instante e usage observado quando disponível. Para jobs centralizados, versão/hash do snapshot deve permitir reconstruir a política aplicada.

## 17. AUTO e modelos sem preço

A ordem permanece:

1. candidatos configurados e elegíveis;
2. candidatos saudáveis segundo quarentena/circuit breaker;
3. candidatos com preço vigente ordenados pelo menor custo estimado;
4. empates determinísticos;
5. candidatos UNPRICED depois dos precificados.

Pricing não habilita provider sem credencial, ignora falhas, remove quarentena, reduz circuit breaker nem torna Copilot elegível ao AUTO.

## 18. Batch, Flex, Priority e service tiers

O catálogo de referência representa modalidades síncronas compatíveis com o runtime atual. O AUTO não troca silenciosamente modalidade apenas para reduzir preço quando isso altera latência, SLA, quota, semântica ou disponibilidade.

## 19. Validação fail-closed

O loader rejeita, entre outros:

- `schema_version` incompatível;
- provider/modelo duplicado;
- `rule_id` duplicado;
- preço negativo;
- data ISO inválida;
- `effective_until <= effective_from`;
- janela horária ou weekday inválido;
- `pricing_model` ou `reasoning_billing` desconhecido;
- `SOURCE=file` sem arquivo existente.

Erro de catálogo não é convertido silenciosamente em preço presumido.

## 20. Política de revisão

Data de referência desta versão: **13/09/2026**. Revisão ordinária recomendada: **13/10/2026**.

Revisar antes disso em caso de aviso de preço, troca de modelo default, mudança de endpoint/região, cache, peak/off-peak, threshold de contexto, promoção, nova modalidade de cobrança ou divergência material entre estimativa e cobrança observada. Toda revisão efetiva deve atualizar `reference_date` e `verified_on`.

## 21. Fontes oficiais de pricing

| Provider | Fonte oficial | O que verificar |
|---|---|---|
| OpenAI | <https://openai.com/api/> e <https://developers.openai.com/api/docs/models/> | input/output/cache, faixas de contexto e modelo efetivo |
| DeepSeek | <https://api-docs.deepseek.com/quick_start/pricing/> | preços, peak/off-peak, horários UTC e vigência |
| Xiaomi MiMo | <https://mimo.mi.com/docs/en-US/price/pay-as-you-go> | preço PAYG e cache |
| xAI | <https://docs.x.ai/developers/pricing> | preço, cache e contexto longo |
| Alibaba Qwen / Model Studio | <https://www.alibabacloud.com/help/en/model-studio/model-pricing> | região, modelo, contexto e cache |
| Google Gemini | <https://ai.google.dev/gemini-api/docs/pricing> | input, cached input, output/thinking e vigência |
| Anthropic Claude | <https://platform.claude.com/docs/en/about-claude/pricing> | input, output e cache |

Cada entrada do TOML mantém `source_reference` próprio.

## 22. Critérios de validação

A suíte deve cobrir, no mínimo:

- DeepSeek peak/off-peak por weekday UTC e conversões de fuso pertinentes;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- reasoning do Gemini incluído no output faturável;
- defaults elegíveis do pool AUTO com preço vigente;
- arquivo configurado inexistente falhando fechado;
- `config/ai-pricing.toml` como superfície humana padrão do console;
- nova AUD recarregando alteração salva sem restart;
- snapshot mantendo a AUD corrente imutável mesmo se o arquivo original mudar;
- variáveis de pricing presentes no catálogo gerenciado do console.
