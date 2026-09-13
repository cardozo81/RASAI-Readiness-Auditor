# Configuração de preços de IA do RASAi

**Data de referência desta configuração: 13/09/2026**  
**Versão do catálogo de fábrica: `RASAI-PRICING-2026-09-13`**  
**Schema do catálogo: `1`**  
**Revisão ordinária recomendada: 13/10/2026**

Os preços deste documento e de `src/rasai/config/ai-pricing-defaults.toml` representam a política conhecida e validada na data de referência acima. Eles são usados para estimativa operacional e roteamento econômico. Não substituem a fatura do fornecedor.

## 1. Objetivo

A política comercial de uma IA não deve exigir alteração de código quando a mudança puder ser expressa pelo schema de pricing.

O RASAi separa:

- **motor de pricing**: interpreta regras, vigência, faixas de tokens e janelas de horário;
- **catálogo de pricing**: contém valores e condições comerciais por provider/modelo;
- **roteamento AUTO**: usa o preço resolvido para ordenar candidatos elegíveis;
- **telemetria/persistência**: registra custo e versão do pricing usados pela execução;
- **configuração local**: pode usar catálogo de fábrica ou arquivo TOML editável;
- **SaaS/control plane**: usa o mesmo schema lógico e fixa um snapshot por job.

O resultado é que mudanças de preço, promoções, horários peak/off-peak e thresholds de contexto deixam de exigir `if provider == ...` no runtime quando já forem representáveis pelo schema.

## 2. Estado do projeto e compatibilidade

Na data desta implementação o RASAi não possui aplicação publicada nem legado de configuração de pricing em produção. Portanto:

- o catálogo declarativo passa diretamente a ser a fonte canônica de valores;
- não existe migração de arquivo de pricing anterior;
- não existe necessidade de manter formato antigo para instalações publicadas;
- a API Python interna de `ai_cost_policy` foi preservada para reduzir regressão funcional;
- `rasai-defaults.ini` permanece como baseline de reset de fábrica.

A decisão prioriza um contrato limpo agora, antes de existir legado externo.

## 3. Arquivos e responsabilidades

| Artefato | Responsabilidade |
|---|---|
| `src/rasai/config/ai-pricing-defaults.toml` | catálogo de preços de fábrica distribuído com a versão |
| `src/rasai/ai_pricing_catalog.py` | parser, validação, seleção de regra e carregamento local/SaaS |
| `src/rasai/ai_cost_policy.py` | cálculo de custo, estimativa e API consumida pelo runtime |
| `src/rasai/ai_pricing_console.py` | cadastro das opções de pricing no console e integração com reset |
| `src/rasai/config/rasai-defaults.ini` | define a origem `factory` usada no reset de fábrica |
| `ai-pricing.toml` | nome convencional do catálogo local editável pelo operador |

## 4. Fontes de pricing

A variável `RASAI_AI_PRICING_SOURCE` aceita:

| Valor | Comportamento |
|---|---|
| `factory` | usa sempre o TOML versionado no pacote; é o default e o estado de reset de fábrica |
| `file` | exige o arquivo definido em `RASAI_AI_PRICING_FILE`; ausência ou conteúdo inválido é erro fail-closed |
| `auto` | usa o arquivo quando existe; caso contrário usa o catálogo de fábrica |

`RASAI_AI_PRICING_FILE` tem como valor convencional:

```text
ai-pricing.toml
```

Caminho relativo é resolvido a partir do diretório de execução. Caminho absoluto também é aceito.

A precedência local é:

```text
variável de processo/SO
    > [environment] do rasai-console.ini
    > rasai-defaults.ini / factory
```

As duas variáveis fazem parte do catálogo gerenciado pelo console. Isso significa que podem ser persistidas como configuração não secreta e também são conhecidas pelo fluxo de Restore Defaults.

## 5. Reset de fábrica

`src/rasai/config/rasai-defaults.ini` contém:

```ini
RASAI_AI_PRICING_SOURCE = factory
RASAI_AI_PRICING_FILE = ai-pricing.toml
```

Restaurar os padrões do RASAi deve:

1. remover overrides conhecidos da sessão;
2. no Windows, remover overrides conhecidos de Windows/User quando permitido pelo fluxo de reset;
3. preservar Windows/Machine, conforme a política já existente do produto;
4. voltar `RASAI_AI_PRICING_SOURCE` para `factory`;
5. manter o arquivo `ai-pricing.toml` fisicamente intacto, porque reset de programa não deve destruir um artefato administrativo do operador.

Com `SOURCE=factory`, um TOML customizado existente deixa de participar da decisão.

O helper `restore_factory_pricing_catalog(destination)` permite reconstruir fisicamente um TOML editável a partir do catálogo de fábrica quando uma interface quiser oferecer a ação de copiar/restaurar o catálogo.

## 6. Estrutura do catálogo

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

A unidade atualmente usada pelo runtime é preço por 1.000.000 tokens para:

- input sem cache;
- input em cache/cache read;
- output faturável.

`currency` pode ser informado no modelo. Quando omitido, o catálogo atual assume `USD`.

## 7. Modelos estruturais suportados

### 7.1 `TOKEN_STANDARD`

Use quando o preço é estável durante a vigência e não depende de horário ou tamanho de contexto.

Uso atual:

- Xiaomi MiMo;
- Alibaba Qwen, com região explicitada;
- Google Gemini na regra atual;
- Anthropic Claude na regra atual.

### 7.2 `TOKEN_CONTEXT_TIERED`

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

Uso atual:

- OpenAI GPT-5.6 acima de 272.000 tokens de input;
- xAI Grok 4.6 a partir de 200.000 tokens de input.

### 7.3 `TOKEN_TIME_WINDOW`

Use quando o preço depende de dia e horário.

Campos atuais:

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

Uso atual:

- DeepSeek V4 Pro e Flash com peak/off-peak.

## 8. Reasoning faturável

`reasoning_billing` informa como o usage do provider deve ser interpretado.

| Valor | Significado |
|---|---|
| `IN_OUTPUT` | `output_tokens` já representa o volume faturável de output |
| `ADD_REASONING_TO_OUTPUT` | `reasoning_tokens`, quando reportado separadamente, é somado ao output faturável |

O Gemini atual usa `ADD_REASONING_TO_OUTPUT`.

Assim, o cálculo não precisa mais de exceção hardcoded `if provider == GEMINI`.

## 9. Vigência

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
- usar um valor antigo somente para evitar que o provider fique sem preço.

## 10. Prioridade de regras

Quando mais de uma regra é válida, o motor seleciona pela ordem:

1. maior `priority`;
2. `effective_from` mais recente;
3. `rule_id` como desempate determinístico.

Isso permite uma regra base com `priority=0` e uma faixa especial com prioridade maior.

## 11. Política atual por IA - referência 13/09/2026

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
| Gemini `gemini-3.8-flash` | `TOKEN_STANDARD` | 0,75 | 0,075 | 3,75 | thinking/reasoning soma no output; regra até 01/01/2027 UTC |
| Anthropic `claude-sonnet-5` | `TOKEN_STANDARD` | 2,00 | 0,20 | 10,00 | 0,20 representa cache read no modelo atual |
| GitHub Copilot `auto` | **UNPRICED** | - | - | - | explicit-only e `auto_eligible=false`; não participa do ranking AUTO |

### 11.1 DeepSeek

Peak atual em UTC, segunda a sexta:

```text
01:00 <= UTC < 04:00
06:00 <= UTC < 10:00
```

A regra peak possui prioridade superior e condições de weekday/janela. A regra off-peak é o fallback vigente.

### 11.2 OpenAI

A faixa longa é declarada com `input_tokens_gt=272000`. Os valores finais já estão na regra. O motor não aplica multiplicadores específicos de OpenAI.

### 11.3 xAI

A faixa longa usa `input_tokens_gte=200000`.

### 11.4 Qwen

O catálogo atual registra `region="US_VIRGINIA"`, coerente com o endpoint US usado na configuração padrão analisada. Se o endpoint/região mudar, o preço deve ser revisto antes de ser usado no ranking econômico.

### 11.5 Gemini

A regra atual possui:

```toml
effective_until = "2027-01-01T00:00:00Z"
```

Sem uma regra seguinte, a partir desse instante o modelo fica UNPRICED em vez de herdar uma tarifa presumida.

### 11.6 GitHub Copilot

Na referência de 13/09/2026 não existe uma tarifa unitária de API cadastrada no catálogo do RASAi. Além disso, o provider é explicit-only e não é elegível ao AUTO. Portanto sua ausência de pricing não interfere no ranking econômico automático.

## 12. Como atualizar um preço localmente

Fluxo recomendado:

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

## 13. Mudança com vigência futura

Não é necessário editar código nem substituir uma regra ainda vigente. Registre a nova política com data futura.

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

Quando a vigência começar, o motor passará a resolver a nova regra.

## 14. IA hoje sem preço e tarifada no futuro

Ausência de provider/modelo/regra válida equivale a UNPRICED.

Se um provider já suportado pelo runtime passar a ter cobrança unitária compatível com o schema, basta cadastrá-lo.

Exemplo:

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

A partir da vigência, o modelo passa a ser precificável sem alteração no motor.

Importante: cadastro de pricing não cria adapter nem credencial. O provider precisa existir no registry/runtime para ser executável.

## 15. Limites do schema atual

O schema `1` cobre as políticas comerciais conhecidas e utilizadas pelo RASAi na data de referência. Alteração de código será necessária se surgir uma unidade de cobrança materialmente nova, por exemplo:

- preço por requisição em vez de token;
- preço por tool call;
- preço por imagem;
- preço por segundo de áudio ou vídeo;
- preço por compute-time;
- cache-write como meter independente, quando necessário ao cálculo real;
- fórmula dependente de variável que o contrato ainda não conhece.

Nesses casos deve-se adicionar uma nova primitiva ao schema e ao motor uma única vez. Não deve ser criada lógica específica por fornecedor.

O catálogo nunca deve aceitar Python, JavaScript ou outra execução arbitrária como regra de preço.

## 16. SaaS / control plane

O SaaS deve usar o mesmo schema lógico. Não deve existir um segundo motor de pricing no backend web.

### 16.1 Cadastro e validação

O control plane pode armazenar o documento normalizado e validá-lo com:

```text
pricing_catalog_from_mapping(...)
load_pricing_catalog(document=...)
```

Esse caminho é apropriado para UI/API administrativa e validação antes da publicação.

### 16.2 Execução equivalente ao local

O runtime de custo atual carrega o catálogo efetivo no bootstrap do processo. Por isso o fluxo SaaS seguro é **job-scoped**:

```text
Admin publica catálogo
        |
        v
Control plane valida schema
        |
        v
Control plane cria versão imutável
        |
        v
ExecutionJob referencia catalog_version/hash
        |
        v
Worker recebe/materializa snapshot TOML do job
        |
        v
RASAI_AI_PRICING_SOURCE=file
RASAI_AI_PRICING_FILE=<snapshot-do-job>
        |
        v
Processo RASAi inicia e fixa o catálogo
```

Isso produz comportamento equivalente ao local e evita que uma mudança administrativa durante a auditoria altere chamadas posteriores do mesmo job.

Não usar hot reload global de catálogo em um processo que execute organizações diferentes concorrentemente. O catálogo deve ser parte do contexto imutável do job ou do processo worker dedicado àquele job.

### 16.3 Escopos recomendados no SaaS

Estrutura futura recomendada:

```text
ORGANIZATION
    > DEPLOYMENT
    > FACTORY
    > UNPRICED
```

Uso:

- `FACTORY`: política pública distribuída com o RASAi;
- `DEPLOYMENT`: override administrativo do ambiente SaaS;
- `ORGANIZATION`: preço contratual/BYOK específico de um cliente enterprise.

A resolução final deve gerar um snapshot completo antes da execução. O worker não deve combinar regras mutáveis em tempo real.

### 16.4 Preço contratual enterprise

Exemplo conceitual:

```text
Preço público do provider:     USD 2,00 / MTok
Contrato da organização:       USD 1,40 / MTok
```

O override da organização pode substituir a regra pública para aquela organização, mantendo a fonte e a versão contratual registradas.

Esse desenho é relevante para médias e grandes empresas porque o menor preço público nem sempre representa o custo real do cliente.

## 17. Histórico e reprodutibilidade

Preço atual não deve recalcular retrospectivamente auditorias antigas.

Cada execução deve manter, no mínimo:

- `pricing_version` ou `catalog_version`;
- provider/modelo efetivos;
- pricing context resolvido;
- preço efetivo usado;
- instante da chamada;
- usage observado quando disponível.

No SaaS, recomenda-se também persistir hash/snapshot da versão publicada referenciada pelo job.

Uma alteração feita amanhã só vale para novas execuções ou para um novo job explicitamente criado com a nova versão.

## 18. AUTO e modelos sem preço

A ordem continua:

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

## 19. Batch, Flex, Priority e service tiers

O catálogo de referência representa modalidades síncronas compatíveis com o runtime atual.

O AUTO não deve trocar silenciosamente para Batch, Flex, Priority ou outra modalidade somente para reduzir preço, porque isso pode alterar:

- latência;
- SLA;
- quota;
- semântica da chamada;
- disponibilidade do resultado.

Se uma modalidade adicional for suportada futuramente, ela deve ser configuração explícita e uma dimensão declarada no catálogo.

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

Erro de catálogo não deve ser convertido silenciosamente em preço presumido.

## 21. Política de revisão

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

## 22. Fontes oficiais registradas na referência de 13/09/2026

- OpenAI: `https://developers.openai.com/api/docs/models/`
- DeepSeek: `https://api-docs.deepseek.com/quick_start/pricing/`
- Xiaomi MiMo: `https://mimo.mi.com/docs/en-US/price/pay-as-you-go`
- xAI: `https://docs.x.ai/developers/pricing`
- Alibaba Qwen: `https://www.alibabacloud.com/help/en/model-studio/model-pricing`
- Google Gemini: `https://ai.google.dev/gemini-api/docs/pricing`
- Anthropic: `https://platform.claude.com/docs/en/about-claude/pricing`

Cada modelo mantém também `source_reference` específico no TOML.

## 23. Impacto funcional da refatoração

Classificação final: **baixo impacto funcional e moderado impacto estrutural interno**.

Razões para baixo impacto funcional:

- `resolve_price()` foi preservado;
- `estimate_candidate_cost()` foi preservado;
- `PRICING_CATALOG` continua exposto para persistência;
- a fórmula de custo não mudou;
- os preços da referência de 13/09/2026 foram reproduzidos no catálogo de fábrica;
- ranking AUTO continua usando a mesma semântica;
- quarentena, fallback e eligibility não foram alterados;
- o console ganhou configuração de origem/caminho sem alterar provider selection;
- o reset de fábrica continua baseado em `rasai-defaults.ini`.

Mudanças estruturais deliberadas:

- preços saíram do Python;
- DeepSeek peak/off-peak saiu de condição específica no código;
- OpenAI/xAI context tier saiu de condição específica no código;
- billing de reasoning do Gemini virou metadado;
- TOML passou a ser package data;
- origem de pricing passou a ser configuração gerenciada;
- SaaS passa a usar o mesmo schema e snapshot por job.

## 24. Critérios de regressão

A suíte deve manter verde, no mínimo:

- DeepSeek peak/off-peak por weekday UTC;
- domingo 22:xx GMT-3 convertido para segunda-feira UTC peak;
- sábado off-peak;
- vigência do DeepSeek V4;
- OpenAI >272k;
- xAI >=200k;
- expiração fail-closed do Gemini;
- reasoning do Gemini incluído no output faturável;
- todos os defaults elegíveis do pool AUTO com preço atual;
- provider/modelo futuro precificável somente por configuração quando compatível com o schema;
- arquivo configurado inexistente falhando fechado;
- reset de fábrica mantendo `SOURCE=factory`;
- variáveis de pricing presentes no catálogo gerenciado do console;
- documentação pública sem caracteres incompatíveis com o contrato do repositório.
