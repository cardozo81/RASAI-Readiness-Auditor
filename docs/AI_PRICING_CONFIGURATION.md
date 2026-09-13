# Configuração de preços de IA do RASAi

**Data de referência desta configuração: 13/09/2026**  
**Versão do catálogo de fábrica: `RASAI-PRICING-2026-09-13`**  
**Schema do catálogo: `1`**  
**Revisão ordinária recomendada: 13/10/2026**

> Os preços deste documento e de `src/rasai/config/ai-pricing-defaults.toml` representam a política conhecida e validada na data de referência acima. Não são uma promessa de preço futuro nem substituem a fatura do fornecedor.

## 1. Objetivo

O pricing de IA é configuração de negócio, não lógica específica de provider.

O RASAi separa:

- **motor de pricing**: interpreta regras, vigência, faixas de tokens e janelas de horário;
- **catálogo de pricing**: contém valores e condições comerciais por provider/modelo;
- **roteamento AUTO**: usa o preço resolvido para ordenar candidatos elegíveis;
- **telemetria/persistência**: registra o preço/custo usado pela execução;
- **configuração local**: pode usar catálogo de fábrica ou arquivo TOML editável;
- **SaaS/control plane**: usa o mesmo schema lógico e entrega o snapshot do catálogo ao worker.

Não existe mais motivo para alterar `ai_cost_policy.py` somente porque um fornecedor mudou uma tarifa, uma janela de desconto, um threshold de contexto ou uma data de vigência que caibam no schema atual.

## 2. Estado do projeto e decisão de compatibilidade

Na data desta implementação o RASAi não possui legado publicado nem instalação de produção que imponha migração de formato. Portanto:

- o catálogo declarativo passa a ser a fonte canônica de valores;
- não existe camada de compatibilidade para um catálogo externo anterior;
- não existe migração de configuração antiga de pricing porque ela não existia;
- a API Python consumida pelo runtime foi preservada para reduzir regressão interna;
- o `rasai-defaults.ini` continua sendo a baseline de reset de fábrica do produto.

## 3. Arquivos e responsabilidades

| Artefato | Responsabilidade |
|---|---|
| `src/rasai/config/ai-pricing-defaults.toml` | catálogo de preços de fábrica distribuído com a versão |
| `src/rasai/ai_pricing_catalog.py` | parser, validação do schema, seleção de regra e fonte local/SaaS |
| `src/rasai/ai_cost_policy.py` | cálculo de custo, estimativa, telemetria e API compatível com o runtime |
| `src/rasai/config/rasai-defaults.ini` | define que o reset de fábrica usa `RASAI_AI_PRICING_SOURCE=factory` |
| `ai-pricing.toml` | nome convencional do catálogo local editável pelo operador |

## 4. Fontes possíveis

A variável `RASAI_AI_PRICING_SOURCE` aceita:

| Valor | Comportamento |
|---|---|
| `factory` | usa sempre o TOML versionado dentro do pacote; é o default e o estado de reset de fábrica |
| `file` | exige o arquivo indicado por `RASAI_AI_PRICING_FILE`; arquivo ausente é erro fail-closed |
| `auto` | usa o arquivo quando existe; caso contrário usa o catálogo de fábrica |

`RASAI_AI_PRICING_FILE` tem como valor convencional:

```text
ai-pricing.toml
```

Caminho relativo é resolvido a partir do diretório de execução. Caminho absoluto também é aceito.

A precedência para descobrir essas duas opções é:

```text
variável de processo/SO
    > [environment] do rasai-console.ini
    > default interno/factory
```

## 5. Reset de fábrica

`src/rasai/config/rasai-defaults.ini` permanece a fonte oficial do reset do produto e contém:

```ini
RASAI_AI_PRICING_SOURCE = factory
RASAI_AI_PRICING_FILE = ai-pricing.toml
```

Portanto, restaurar os padrões do RASAi volta a política efetiva para o catálogo empacotado da versão instalada.

Um `ai-pricing.toml` customizado pode permanecer fisicamente no disco. Isso é intencional: resetar o programa não precisa destruir um arquivo administrativo do operador. Com `SOURCE=factory`, esse arquivo deixa de participar da decisão.

O módulo também expõe `restore_factory_pricing_catalog(destination)` para reconstruir fisicamente um TOML editável a partir do catálogo de fábrica quando uma interface local ou SaaS desejar oferecer a ação **“copiar/restaurar catálogo”**.

## 6. Modelo declarativo

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

A unidade atualmente suportada pelo runtime é **USD por 1.000.000 tokens** para:

- input sem cache;
- input em cache/cache read;
- output faturável.

`currency` pode ser declarado no modelo e, quando omitido, assume `USD`.

## 7. Modelos estruturais suportados

### 7.1 `TOKEN_STANDARD`

Use quando o preço é estável para o período de vigência e não depende de horário ou tamanho de contexto.

Aplicações atuais:

- Xiaomi MiMo;
- Alibaba Qwen, observando a região configurada;
- Google Gemini na regra atual;
- Anthropic Claude na regra atual.

### 7.2 `TOKEN_CONTEXT_TIERED`

Use quando o preço muda a partir de um volume de input/contexto.

Condições disponíveis:

```text
input_tokens_gte
input_tokens_gt
input_tokens_lte
input_tokens_lt
```

A regra mais específica deve receber prioridade maior.

Aplicações atuais:

- OpenAI GPT-5.6: faixa acima de 272.000 tokens de input;
- xAI Grok 4.6: faixa a partir de 200.000 tokens de input.

Exemplo:

```toml
[[models.rules]]
rule_id = "example-long"
context = "LONG_CONTEXT"
priority = 100
input_tokens_gte = 200000
...
```

### 7.3 `TOKEN_TIME_WINDOW`

Use quando o preço depende de dia/horário.

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

As janelas são sempre declaradas explicitamente em UTC no catálogo atual. O motor converte o instante da execução para UTC antes de resolver a regra.

Aplicação atual:

- DeepSeek V4 Pro/Flash peak e off-peak.

## 8. Reasoning faturável

`reasoning_billing` separa o formato de usage do provider da regra de preço.

Valores atuais:

| Valor | Significado |
|---|---|
| `IN_OUTPUT` | `output_tokens` já representa o volume faturável de output |
| `ADD_REASONING_TO_OUTPUT` | `reasoning_tokens`, quando reportado separadamente, é somado ao output faturável |

O Gemini atual usa `ADD_REASONING_TO_OUTPUT`.

Isso elimina a antiga necessidade de `if provider == GEMINI` no cálculo de billing.

## 9. Vigência

Toda regra exige:

```toml
effective_from = "..."
```

Opcionalmente:

```toml
effective_until = "..."
```

Sem regra vigente, o provider/modelo é tratado como **não precificado** para aquela decisão.

O RASAi não:

- inventa preço;
- mantém silenciosamente preço expirado;
- extrapola promoção vencida;
- assume que a tarifa de uma região vale em outra.

## 10. Prioridade de regras

Mais de uma regra pode estar válida no mesmo instante. O motor escolhe pela ordem:

1. maior `priority`;
2. vigência (`effective_from`) mais recente;
3. `rule_id` como desempate determinístico.

Isso permite manter uma regra base com `priority=0` e sobrepor uma faixa específica com `priority=100`.

## 11. Política atual por IA — referência 13/09/2026

Valores em USD por 1 milhão de tokens.

| IA / modelo | Estrutura | Input | Cache/read | Output | Regra adicional atual |
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
| Gemini `gemini-3.8-flash` | `TOKEN_STANDARD` | 0,75 | 0,075 | 3,75 | thinking/reasoning soma no output; vigente no catálogo até 01/01/2027 UTC |
| Anthropic `claude-sonnet-5` | `TOKEN_STANDARD` | 2,00 | 0,20 | 10,00 | 0,20 representa cache read no modelo atual |
| GitHub Copilot `auto` | **não precificado** | — | — | — | explicit-only, `auto_eligible=false`; não participa do ranking econômico AUTO |

### 11.1 DeepSeek

Na referência atual, peak ocorre de segunda a sexta em UTC:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

A regra peak tem prioridade maior e condições de weekday/janela. A regra off-peak é o fallback vigente.

### 11.2 OpenAI

A faixa longa é uma regra declarativa independente com `input_tokens_gt=272000`. Os valores finais já estão registrados na regra longa; o motor não multiplica preços por provider.

### 11.3 xAI

A regra longa usa `input_tokens_gte=200000`.

### 11.4 Qwen

O catálogo atual registra `region="US_VIRGINIA"`, coerente com o endpoint US usado pela configuração padrão analisada. Trocar região exige regra apropriada no catálogo.

### 11.5 Gemini

A regra atualmente catalogada possui `effective_until="2027-01-01T00:00:00Z"`. Se não existir regra seguinte, após esse instante o modelo fica não precificado em vez de herdar uma tarifa presumida.

### 11.6 GitHub Copilot

Não existe tarifa unitária de API cadastrada no catálogo desta referência. Além disso, o provider é explicit-only no registry do RASAi. Portanto a ausência de pricing não interfere no `AI=auto`.

## 12. Como atualizar um preço localmente

1. copie `src/rasai/config/ai-pricing-defaults.toml` para um local administrativo, normalmente `ai-pricing.toml`;
2. altere os valores/regras necessários;
3. atualize obrigatoriamente `catalog_version`, `reference_date`, `verified_on` e, quando aplicável, `review_recommended_on`;
4. configure:

```ini
RASAI_AI_PRICING_SOURCE = file
RASAI_AI_PRICING_FILE = ai-pricing.toml
```

5. reinicie o processo/worker para que a execução passe a usar o novo snapshot.

Para voltar ao produto sem customização:

```ini
RASAI_AI_PRICING_SOURCE = factory
```

ou use o reset de fábrica do console.

## 13. Mudança de preço com vigência futura

Não substitua uma regra ainda necessária historicamente. Adicione uma regra de maior vigência/prioridade ou encerre a atual.

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

A partir da vigência, o motor resolve a nova regra sem mudança de código.

## 14. IA hoje sem preço e tarifada no futuro

A ausência de provider/modelo/regra válida equivale a **UNPRICED**.

Se um provider que hoje não possui política unitária passar a cobrar, basta incluí-lo no mesmo schema, por exemplo:

```toml
[[models]]
provider = "FUTUREAI"
model = "future-1"
pricing_model = "TOKEN_STANDARD"
reasoning_billing = "IN_OUTPUT"
region = "GLOBAL"
source_reference = "https://provider.example/pricing"

  [[models.rules]]
  rule_id = "futureai-future-1-standard"
  context = "STANDARD"
  priority = 0
  effective_from = "2027-03-01T00:00:00Z"
  input_price_per_million = 0.15
  cached_input_price_per_million = 0.03
  output_price_per_million = 0.60
```

Desde que o provider já exista no registry/runtime e a nova política caiba em uma estrutura suportada, nenhuma alteração do motor de pricing é necessária.

## 15. Quando alteração de código ainda seria necessária

O schema atual cobre as políticas comerciais conhecidas em 13/09/2026 para o escopo usado pelo RASAi. Ele não tenta executar código arbitrário vindo de configuração.

Uma evolução do schema será necessária se surgir uma modalidade de cobrança materialmente diferente, por exemplo:

- preço por requisição em vez de token;
- preço por tool call;
- preço por imagem, segundo de áudio/vídeo ou compute-time;
- cache-write cobrado como meter independente quando necessário ao cálculo do RASAi;
- fórmula dependente de variável ainda inexistente no contrato.

Nesse caso deve-se adicionar uma nova primitiva de billing ao schema e ao motor **uma vez**. Não se deve criar `if provider == X` para cada fornecedor.

Nunca permitir Python/JavaScript arbitrário dentro do catálogo.

## 16. SaaS / control plane

O SaaS deve usar exatamente o mesmo contrato lógico. A diferença é somente a origem do documento.

Fluxo recomendado:

```text
Admin SaaS
  -> edita/publica catálogo
  -> control plane valida schema_version=1
  -> persiste versão imutável do catálogo
  -> Execution Job referencia pricing_catalog_version
  -> worker recebe snapshot normalizado
  -> load_pricing_catalog(document=...)
  -> mesmo resolve_catalog_rule()/resolve_price()
```

### 16.1 Escopos recomendados no SaaS

Preparar o cadastro para:

```text
FACTORY/GLOBAL
    -> catálogo oficial da versão RASAi

DEPLOYMENT
    -> política administrativa do ambiente hospedado

ORGANIZATION
    -> preços contratuais/BYOK negociados pelo cliente
```

Precedência conceitual recomendada:

```text
ORGANIZATION
  > DEPLOYMENT
  > FACTORY
  > UNPRICED
```

A implementação atual já aceita o documento como `Mapping` através de `pricing_catalog_from_mapping()` / `load_pricing_catalog(document=...)`, portanto local e SaaS compartilham parser e validação. A persistência/UI/API do cadastro SaaS deve armazenar o mesmo documento normalizado em vez de criar um segundo motor de pricing.

### 16.2 Snapshot por execução

O job deve carregar uma versão imutável do catálogo no início. Mudança administrativa feita durante uma auditoria não deve alterar o custo/ranking de chamadas já iniciadas.

O identificador `catalog_version` deve acompanhar a execução e a telemetria de custo.

## 17. Histórico e reprodutibilidade

Preço atual não deve recalcular retrospectivamente auditorias antigas.

Uma execução deve conservar a versão de pricing que utilizou. O RASAi já persiste `pricing_version` junto ao catálogo/tentativas; a evolução SaaS deve preservar essa propriedade e, quando o control plane passar a gerenciar overrides contratuais, manter snapshot/hash da versão publicada.

## 18. AUTO e providers sem preço

A política de roteamento continua:

1. candidatos configurados, elegíveis e saudáveis;
2. candidatos com preço vigente ordenados pelo menor custo estimado;
3. empate preserva ordem determinística/rank;
4. candidatos sem preço ficam depois dos precificados;
5. quarentena/circuit breaker não são alterados pelo custo.

Pricing não habilita credencial, não retira quarantine e não torna Copilot elegível ao AUTO.

## 19. Batch, Flex, Priority e outros service tiers

O catálogo de referência representa modalidades síncronas compatíveis com o runtime atual. O AUTO não deve trocar silenciosamente o service tier somente para reduzir custo.

Se uma modalidade futura alterar latência, SLA, quota ou contrato de execução, ela deve ser explicitamente configurável antes de ser considerada pelo ranking econômico.

## 20. Validação fail-closed

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

Erro de catálogo não deve ser silenciosamente convertido em preço presumido.

## 21. Política de revisão

Revisão ordinária da configuração desta versão: **13/10/2026**.

Revisar antes disso se ocorrer:

- aviso do fornecedor sobre preço;
- lançamento ou troca de modelo default;
- mudança de região/endpoint;
- alteração de cache;
- mudança de peak/off-peak;
- mudança de threshold de contexto;
- promoção com data de término;
- nova modalidade de cobrança;
- diferença material entre custo estimado e cobrança observada.

A data `reference_date` deve ser atualizada em toda revisão efetiva de preços.

## 22. Fontes oficiais registradas no catálogo de 13/09/2026

- OpenAI: `https://developers.openai.com/api/docs/models/`
- DeepSeek: `https://api-docs.deepseek.com/quick_start/pricing/`
- Xiaomi MiMo: `https://mimo.mi.com/docs/en-US/price/pay-as-you-go`
- xAI: `https://docs.x.ai/developers/pricing`
- Alibaba Qwen: `https://www.alibabacloud.com/help/en/model-studio/model-pricing`
- Google Gemini: `https://ai.google.dev/gemini-api/docs/pricing`
- Anthropic: `https://platform.claude.com/docs/en/about-claude/pricing`

Cada modelo também mantém `source_reference` próprio no TOML.

## 23. Impacto funcional desta refatoração

Classificação: **baixo impacto funcional / moderado impacto estrutural interno**.

Motivos para baixo impacto funcional:

- a API de `ai_cost_policy` usada pelo runtime foi preservada;
- `resolve_price()` continua retornando o mesmo contrato;
- `estimate_candidate_cost()` mantém a mesma fórmula;
- `PRICING_CATALOG` continua disponível para persistência;
- o ranking AUTO continua recebendo os mesmos preços da referência anterior;
- quarentena, fallback e eligibility não mudaram;
- o catálogo de fábrica reproduz as regras existentes em 13/09/2026.

Mudanças estruturais deliberadas:

- preços saíram do Python;
- DeepSeek peak/off-peak saiu do `if` de provider;
- OpenAI/xAI context tier saiu do `if` de provider;
- billing de reasoning do Gemini virou metadado declarativo;
- TOML passou a ser package data;
- reset de fábrica agora explicita a origem `factory`.

## 24. Critérios de regressão

A suíte deve manter verde, no mínimo:

- DeepSeek peak/off-peak em UTC;
- conversão de domingo 22:xx GMT-3 para segunda UTC peak;
- sábado off-peak;
- vigência do DeepSeek V4;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- reasoning do Gemini somado ao output faturável;
- defaults do pool AUTO com preço válido;
- provider/modelo futuro precificável somente por configuração;
- arquivo configurado inexistente falhando fechado;
- restauração física do catálogo de fábrica;
- `rasai-defaults.ini` mantendo `SOURCE=factory`.
