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
- **configuração local**: pode usar catálogo de fábrica ou arquivo TOML editável;
- **SaaS/control plane**: usa o mesmo schema lógico e fixa um snapshot por job quando essa política é materializada no worker.

Mudanças de preço, promoções, horários peak/off-peak e thresholds de contexto são representadas por dados quando já cabem nas primitivas do schema.

## 2. Fonte canônica e responsabilidades

O catálogo declarativo é a fonte canônica de valores de pricing do runtime. Não existe outro formato público de pricing que deva ser conciliado.

| Artefato | Responsabilidade |
|---|---|
| `src/rasai/config/ai-pricing-defaults.toml` | catálogo de preços de fábrica distribuído com o RASAi |
| `src/rasai/ai_pricing_catalog.py` | parser, validação, seleção de regra e carregamento local/control plane |
| `src/rasai/ai_cost_policy.py` | cálculo de custo, estimativa e API consumida pelo runtime |
| `src/rasai/ai_pricing_console.py` | configuração das opções de pricing no console e integração com reset |
| `src/rasai/config/rasai-defaults.ini` | define a origem `factory` usada no reset de fábrica |
| `ai-pricing.toml` | nome convencional do catálogo local editável pelo operador |

## 3. Variáveis de configuração

### `RASAI_AI_PRICING_SOURCE`

| Valor | Comportamento |
|---|---|
| `factory` | usa o TOML versionado no pacote; é o default e o estado de reset de fábrica |
| `file` | exige o arquivo definido em `RASAI_AI_PRICING_FILE`; ausência ou conteúdo inválido é erro fail-closed |
| `auto` | usa o arquivo quando existe; caso contrário usa o catálogo de fábrica |

### `RASAI_AI_PRICING_FILE`

Valor convencional:

```text
ai-pricing.toml
```

O caminho relativo é resolvido a partir do diretório de execução. Caminho absoluto também é aceito.

Precedência local:

```text
variável de processo/SO
    > [environment] do rasai-console.ini
    > rasai-defaults.ini / factory
```

As duas variáveis são configuração não secreta e fazem parte da superfície gerenciada pelo console.

## 4. Reset de fábrica

`src/rasai/config/rasai-defaults.ini` contém:

```ini
RASAI_AI_PRICING_SOURCE = factory
RASAI_AI_PRICING_FILE = ai-pricing.toml
```

Restaurar os padrões do RASAi deve:

1. remover overrides conhecidos da sessão;
2. no Windows, remover overrides conhecidos de Windows/User quando permitido pelo fluxo de reset;
3. preservar Windows/Machine conforme a política do produto;
4. voltar `RASAI_AI_PRICING_SOURCE` para `factory`;
5. manter o arquivo `ai-pricing.toml` fisicamente intacto, porque reset do programa não deve destruir um artefato administrativo do operador.

Com `SOURCE=factory`, um TOML customizado existente deixa de participar da decisão.

O helper `restore_factory_pricing_catalog(destination)` permite reconstruir fisicamente um TOML editável a partir do catálogo de fábrica quando uma interface oferece a ação de copiar/restaurar o catálogo.

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

A unidade usada pelo runtime é preço por 1.000.000 tokens para:

- input sem cache;
- input em cache/cache read;
- output faturável.

`currency` pode ser informado no modelo. Quando omitido, o catálogo vigente assume `USD`.

## 6. Modelos estruturais suportados

### 6.1 `TOKEN_STANDARD`

Use quando o preço é estável durante a vigência e não depende de horário ou tamanho de contexto.

Aplicações presentes no catálogo:

- Xiaomi MiMo;
- Alibaba Qwen, com região explicitada;
- Google Gemini;
- Anthropic Claude.

### 6.2 `TOKEN_CONTEXT_TIERED`

Use quando o preço muda por volume de input/contexto.

Condições disponíveis:

```text
input_tokens_gte
input_tokens_gt
input_tokens_lte
input_tokens_lt
```

Exemplo:

```toml
[[models.rules]]
rule_id = "example-long-context"
context = "LONG_CONTEXT"
priority = 100
input_tokens_gte = 200000
input_price_per_million = 4.00
cached_input_price_per_million = 1.00
output_price_per_million = 12.00
```

Aplicações presentes no catálogo:

- OpenAI GPT-5.6 acima de 272.000 tokens de input;
- xAI Grok 4.6 a partir de 200.000 tokens de input.

### 6.3 `TOKEN_TIME_WINDOW`

Use quando o preço depende de dia e horário.

Campos:

```text
weekdays_utc
time_windows_utc
```

Exemplo:

```toml
weekdays_utc = ["MON", "TUE", "WED", "THU", "FRI"]
time_windows_utc = ["01:00-04:00", "06:00-10:00"]
```

As janelas são declaradas em UTC. O motor converte o instante da chamada para UTC antes da resolução.

Aplicação presente no catálogo:

- DeepSeek V4 Pro e Flash com peak/off-peak.

## 7. Reasoning faturável

`reasoning_billing` informa como o usage do provider deve ser interpretado.

| Valor | Significado |
|---|---|
| `IN_OUTPUT` | `output_tokens` já representa o volume faturável de output |
| `ADD_REASONING_TO_OUTPUT` | `reasoning_tokens`, quando reportado separadamente, é somado ao output faturável |

O Gemini vigente usa `ADD_REASONING_TO_OUTPUT`.

A interpretação pertence ao catálogo e não deve depender de condição hardcoded por provider quando o schema já representa a regra.

## 8. Vigência

Toda regra exige:

```toml
effective_from = "..."
```

Opcionalmente:

```toml
effective_until = "..."
```

Sem regra vigente, o provider/modelo é tratado como **UNPRICED** para aquela decisão.

O RASAi não deve:

- inventar preço;
- manter silenciosamente preço expirado;
- extrapolar promoção vencida;
- assumir que preço de uma região vale em outra;
- usar um valor fora da vigência apenas para evitar estado UNPRICED.

## 9. Prioridade de regras

Quando mais de uma regra é válida, o motor seleciona pela ordem:

1. maior `priority`;
2. `effective_from` mais recente;
3. `rule_id` como desempate determinístico.

Isso permite uma regra base com `priority=0` e uma faixa especial com prioridade maior.

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

A tabela é uma fotografia operacional da data de referência. O TOML efetivamente carregado pelo processo é a autoridade de cálculo da execução.

### 10.1 DeepSeek

Peak em UTC, segunda a sexta, conforme o catálogo de referência:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

A regra peak possui prioridade superior e condições de weekday/janela. A regra off-peak é o fallback vigente.

### 10.2 OpenAI

A faixa longa é declarada com `input_tokens_gt=272000`. Os valores finais já estão na regra. O motor não aplica multiplicadores específicos de OpenAI.

### 10.3 xAI

A faixa longa usa `input_tokens_gte=200000`.

### 10.4 Qwen

O catálogo registra `region="US_VIRGINIA"`, coerente com o endpoint US configurado no runtime. Se endpoint ou região mudar, a regra de preço precisa corresponder à nova região antes de participar do ranking econômico.

### 10.5 Gemini

A regra possui:

```toml
effective_until = "2027-01-01T00:00:00Z"
```

Sem uma regra vigente a partir desse instante, o modelo fica UNPRICED em vez de herdar tarifa presumida.

### 10.6 GitHub Copilot

Na referência de 13/09/2026 não existe tarifa unitária de API cadastrada no catálogo do RASAi. O provider é explicit-only e não é elegível ao AUTO. Sua ausência de pricing não interfere no ranking econômico automático.

## 11. Como atualizar um preço localmente

Fluxo operacional:

1. copie `src/rasai/config/ai-pricing-defaults.toml` para um local administrativo, normalmente `ai-pricing.toml`;
2. altere valores, vigências ou condições necessárias;
3. atualize `catalog_version`;
4. atualize `reference_date` para a data efetiva da revisão;
5. atualize `verified_on`;
6. ajuste `review_recommended_on`;
7. configure:

```ini
RASAI_AI_PRICING_SOURCE = file
RASAI_AI_PRICING_FILE = ai-pricing.toml
```

8. reinicie o processo/worker para fixar o novo snapshot.

Para voltar ao catálogo distribuído com o RASAi:

```ini
RASAI_AI_PRICING_SOURCE = factory
```

ou use Restore Defaults no console.

## 12. Regra com vigência posterior

Quando uma política comercial já é conhecida, mas começa em outra data, registre uma nova regra com `effective_from` correspondente. Não é necessário substituir antecipadamente a regra ainda vigente.

Exemplo:

```toml
[[models.rules]]
rule_id = "provider-model-2026-10"
context = "STANDARD"
priority = 10
effective_from = "2026-10-01T00:00:00Z"
input_price_per_million = 0.40
cached_input_price_per_million = 0.04
output_price_per_million = 1.60
```

Quando a vigência começar, o motor passa a resolver a regra aplicável.

## 13. Provider sem preço com regra adicionada posteriormente

Ausência de provider/modelo/regra válida equivale a UNPRICED.

Se um provider já suportado pelo runtime passar a ter cobrança unitária compatível com o schema, o catálogo pode receber uma regra sem alteração do motor.

Exemplo estrutural:

```toml
[[models]]
provider = "EXAMPLE"
model = "example-1"
pricing_model = "TOKEN_STANDARD"
reasoning_billing = "IN_OUTPUT"
region = "GLOBAL"
source_reference = "https://provider.example/pricing"

  [[models.rules]]
  rule_id = "example-example-1-standard"
  context = "STANDARD"
  priority = 0
  effective_from = "2027-03-01T00:00:00Z"
  input_price_per_million = 0.15
  cached_input_price_per_million = 0.03
  output_price_per_million = 0.60
```

O exemplo demonstra o schema, não anuncia provider ou preço real.

Importante: cadastro de pricing não cria adapter nem credencial. O provider precisa existir no registry/runtime para ser executável.

## 14. Limites do schema atual

O schema `1` cobre as políticas comerciais representadas pelo runtime na data de referência. Alteração de código é necessária para uma unidade de cobrança materialmente nova que o schema não represente, por exemplo:

- preço por requisição em vez de token;
- preço por tool call;
- preço por imagem;
- preço por segundo de áudio ou vídeo;
- preço por compute-time;
- cache-write como meter independente quando necessário ao cálculo real;
- fórmula dependente de variável que o contrato não conhece.

Nesses casos deve-se adicionar uma nova primitiva ao schema e ao motor. Não deve ser criada lógica arbitrária por fornecedor se a política puder ser representada de forma genérica.

O catálogo nunca deve aceitar Python, JavaScript ou outra execução arbitrária como regra de preço.

## 15. SaaS / control plane

O control plane usa o mesmo schema lógico; não deve existir um segundo motor de pricing no backend Web.

### 15.1 Cadastro e validação

O documento normalizado pode ser validado com as superfícies de runtime:

```text
pricing_catalog_from_mapping(...)
load_pricing_catalog(document=...)
```

Essas funções permitem validar o cadastro antes de disponibilizá-lo ao processo que executará o job.

### 15.2 Execução job-scoped

O runtime de custo carrega o catálogo efetivo no bootstrap do processo. O contrato de execução é **job-scoped**:

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

Isso produz comportamento equivalente ao local e evita que uma alteração administrativa durante uma auditoria mude chamadas posteriores do mesmo job.

Não usar hot reload global de catálogo em um processo que execute organizações diferentes concorrentemente. O catálogo deve fazer parte do contexto imutável do job ou de um processo worker dedicado.

Escopos administrativos como preço específico por organização ou deployment **não fazem parte do schema de resolução de pricing documentado aqui**. Não devem ser apresentados como capacidade do produto enquanto não houver contrato executável correspondente.

## 16. Reprodutibilidade de pricing

Preço corrente não deve reinterpretar o custo persistido de uma execução já concluída.

Cada execução deve manter, no mínimo:

- `pricing_version` ou `catalog_version`;
- provider/modelo efetivos;
- pricing context resolvido;
- preço efetivo usado;
- instante da chamada;
- usage observado quando disponível.

Para jobs centralizados, o identificador ou hash do snapshot de catálogo deve permitir reconstruir qual política foi aplicada.

Uma nova versão do catálogo vale para execuções que a carregarem explicitamente.

## 17. AUTO e modelos sem preço

A ordem permanece:

1. candidatos configurados e elegíveis;
2. candidatos saudáveis segundo quarentena/circuit breaker;
3. candidatos com preço vigente ordenados pelo menor custo estimado;
4. empates resolvidos de forma determinística;
5. candidatos UNPRICED depois dos precificados.

Pricing não:

- habilita provider sem credencial;
- ignora falhas;
- remove quarantine;
- reduz contadores do circuit breaker;
- torna Copilot elegível ao AUTO.

## 18. Batch, Flex, Priority e service tiers

O catálogo de referência representa modalidades síncronas compatíveis com o runtime atual.

O AUTO não deve trocar silenciosamente para Batch, Flex, Priority ou outra modalidade apenas para reduzir preço, porque isso pode alterar:

- latência;
- SLA;
- quota;
- semântica da chamada;
- disponibilidade do resultado.

Modalidades que não estejam representadas explicitamente no schema e no adapter não são capacidades configuráveis do contrato vigente.

## 19. Validação fail-closed

O loader rejeita, entre outros:

- `schema_version` incompatível;
- provider/modelo duplicado;
- `rule_id` duplicado;
- preço negativo;
- data ISO inválida;
- `effective_until <= effective_from`;
- janela horária inválida;
- weekday inválido;
- `pricing_model` desconhecido;
- `reasoning_billing` desconhecido;
- `SOURCE=file` sem arquivo existente.

Erro de catálogo não deve ser convertido silenciosamente em preço presumido.

## 20. Política de revisão

Data de referência desta versão: **13/09/2026**.

Revisão ordinária recomendada: **13/10/2026**.

Revisar antes disso se ocorrer:

- aviso de preço do fornecedor;
- lançamento ou troca de modelo default;
- mudança de endpoint/região;
- alteração de cache;
- mudança de peak/off-peak;
- mudança de threshold de contexto;
- promoção com data de término;
- nova modalidade de cobrança;
- divergência material entre custo estimado e cobrança observada.

Toda revisão efetiva deve atualizar `reference_date` e `verified_on`.

## 21. Fontes oficiais de pricing

As referências externas servem para validar a política comercial do provider. O valor efetivamente usado por uma execução continua sendo o catálogo carregado pelo RASAi.

| Provider | Fonte oficial | O que verificar |
|---|---|---|
| OpenAI | <https://openai.com/api/> e <https://developers.openai.com/api/docs/models/> | preços de input/output/cache, faixas de contexto, promoções e modelo efetivamente chamado |
| DeepSeek | <https://api-docs.deepseek.com/quick_start/pricing/> | preços vigentes, regras peak/off-peak, horários em UTC e vigência |
| Xiaomi MiMo | <https://mimo.mi.com/docs/en-US/price/pay-as-you-go> | preço PAYG por modelo e tratamento de cache |
| xAI | <https://docs.x.ai/developers/pricing> | preço por milhão de tokens, cache e faixa de contexto longa |
| Alibaba Qwen / Model Studio | <https://www.alibabacloud.com/help/en/model-studio/model-pricing> | região, modelo, tier de contexto e regras de context cache |
| Google Gemini | <https://ai.google.dev/gemini-api/docs/pricing> | input, cached input, output/thinking e datas de vigência quando houver |
| Anthropic Claude | <https://platform.claude.com/docs/en/about-claude/pricing> | input, output, cache read/write e eventuais diferenças de modalidade |

Cada entrada do TOML mantém também `source_reference` próprio. Ao revisar preços, compare a fonte oficial com o modelo, região, modalidade e vigência da regra; não copie uma tarifa de outro produto ou região apenas pelo nome comercial semelhante.

## 22. Critérios de validação

A suíte de validação deve cobrir, no mínimo:

- DeepSeek peak/off-peak por weekday UTC;
- domingo 22:xx GMT-3 convertido para segunda-feira UTC peak;
- sábado off-peak;
- vigência das regras DeepSeek configuradas;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- reasoning do Gemini incluído no output faturável;
- todos os defaults elegíveis do pool AUTO com preço vigente;
- provider/modelo suportado tornando-se precificável apenas por configuração quando compatível com o schema;
- arquivo configurado inexistente falhando fechado;
- reset de fábrica mantendo `SOURCE=factory`;
- variáveis de pricing presentes no catálogo gerenciado do console;
- documentação pública sem caracteres incompatíveis com o contrato do repositório.
