# Catálogo configurável de modelos de IA

**Estado:** contrato atual do RASAi em desenvolvimento.  
**Data de referência do catálogo de fábrica:** 14/09/2026  
**Schema do catálogo:** `1`

## 1. Objetivo

O RASAi separa a **integração técnica do provider** da **lista de modelos disponíveis**.

- autenticação, endpoint, protocolo HTTP/SDK, parsing de resposta e tratamento de erros continuam no adapter do provider;
- modelos, disponibilidade, defaults, reasoning/esforço e elegibilidade ao `AUTO` são dados configuráveis;
- preços permanecem em um catálogo separado;
- um novo modelo de um provider já integrado pode ser cadastrado sem alteração de código quando continuar compatível com o adapter existente.

Exemplo: se a OpenAI publicar um novo modelo compatível com a mesma integração já usada pelo RASAi, o operador pode cadastrá-lo no catálogo de modelos e cadastrar sua política comercial no catálogo de pricing. Um provider completamente novo, ou um modelo que exija protocolo incompatível, continua exigindo implementação de adapter.

## 2. Arquivos

| Artefato | Responsabilidade |
|---|---|
| `src/rasai/config/ai-models-defaults.toml` | catálogo de modelos de fábrica distribuído com o RASAi |
| `ai-models.toml` | catálogo local editável pelo operador |
| `src/rasai/config/ai-pricing-defaults.toml` | catálogo de preços de fábrica |
| `ai-pricing.toml` | catálogo local editável de preços |

Modelos e preços são separados de propósito. Um modelo pode existir para seleção explícita mesmo quando ainda não existe uma tarifa unitária conhecida. Nesse caso ele não entra no ranking econômico do `AUTO`.

## 3. Seleção da origem

### `RASAI_AI_MODELS_SOURCE`

| Valor | Comportamento |
|---|---|
| `factory` | usa `ai-models-defaults.toml`; é o padrão de fábrica |
| `file` | exige o arquivo definido por `RASAI_AI_MODELS_FILE`; erro de arquivo ou conteúdo é tratado de forma fail-closed |
| `auto` | usa o arquivo quando existir; caso contrário usa o catálogo de fábrica |

### `RASAI_AI_MODELS_FILE`

Valor convencional:

```text
ai-models.toml
```

Exemplo no ambiente ou em `[environment]` do `rasai-console.ini`:

```ini
RASAI_AI_MODELS_SOURCE = file
RASAI_AI_MODELS_FILE = ai-models.toml
```

O reset de fábrica volta a usar:

```ini
RASAI_AI_MODELS_SOURCE = factory
RASAI_AI_MODELS_FILE = ai-models.toml
```

O reset muda a origem efetiva; não precisa apagar o arquivo administrativo `ai-models.toml`.

## 4. Estrutura do catálogo

Metadados:

```toml
[metadata]
schema_version = 1
catalog_version = "MINHA-POLITICA-MODELOS-2026-09-14"
reference_date = "2026-09-14"
verified_on = "2026-09-14"
review_recommended_on = "2026-10-14"
```

Cada modelo é declarado com `[[models]]`:

```toml
[[models]]
provider = "OPENAI"
model = "nome-do-modelo"
enabled = true
selectable = true
adapter_default = false
public_default = false
auto_eligible = true
qualification = "PROVISIONAL"
rasai_class = "PROVISIONAL"
rank = 50
recommended_depth = "MEDIUM"
recommended_use = "uso geral"
reasoning_values = ["NONE", "LOW", "MEDIUM", "HIGH"]
default_reasoning = "LOW"
capabilities = ["STRUCTURED_OUTPUT", "REASONING"]
source_reference = "https://fonte-oficial-do-provider"
```

Campos opcionais:

```toml
context_window = 200000
max_output_tokens = 32000
effective_from = "2026-09-14T00:00:00Z"
effective_until = "2027-01-01T00:00:00Z"
```

## 5. Significado dos campos

| Campo | Regra |
|---|---|
| `provider` | precisa corresponder a um provider que já tenha adapter no RASAi |
| `model` | identificador enviado ao provider |
| `enabled` | habilita o modelo no catálogo efetivo |
| `selectable` | permite seleção explícita do modelo |
| `adapter_default` | modelo usado como default técnico do adapter; exatamente um por provider habilitado |
| `public_default` | modelo sugerido pelo RASAi quando não existe override; exatamente um por provider habilitado |
| `auto_eligible` | autoriza o modelo a participar do `AUTO`, sujeito às demais regras |
| `qualification` | estado de qualificação operacional do modelo |
| `rasai_class` | classificação técnica usada na política de provider |
| `rank` | desempate determinístico quando necessário; não substitui o ranking econômico |
| `recommended_depth` | indicação de profundidade/esforço recomendada |
| `recommended_use` | descrição administrativa do uso esperado |
| `reasoning_values` | esforços aceitos para esse modelo |
| `default_reasoning` | esforço usado quando não há override e deve existir em `reasoning_values` |
| `capabilities` | capacidades declaradas do modelo |
| `effective_from` / `effective_until` | janela opcional de disponibilidade do registro |
| `source_reference` | referência oficial usada para validar o cadastro |

Um modelo desabilitado não pode ser selecionável, default ou elegível ao `AUTO`.

## 6. Seleção efetiva por provider

O catálogo define quais modelos são válidos e qual é o default. As variáveis já existentes continuam selecionando o modelo efetivo por provider, por exemplo:

```ini
RASAI_OPENAI_MODEL = gpt-5.6-luna
RASAI_GEMINI_MODEL = gemini-3.8-flash
RASAI_ANTHROPIC_MODEL = claude-sonnet-5
```

Se o valor configurado não existir no catálogo efetivo, estiver desabilitado ou estiver fora da vigência, o RASAi rejeita a configuração em vez de trocar silenciosamente de modelo.

## 7. Reasoning / esforço

O catálogo também define os esforços aceitos por **modelo**. A variável do provider continua sendo o override operacional:

```ini
RASAI_OPENAI_REASONING_EFFORT = MEDIUM
```

O valor precisa estar em `reasoning_values` do modelo OpenAI efetivamente selecionado. Isso permite que dois modelos do mesmo provider tenham políticas de esforço diferentes sem alterar código.

Quando o provider não expõe níveis configuráveis, o catálogo usa `PROVIDER_DEFAULT`.

## 8. Exemplo: adicionar um novo modelo de um provider existente

Suponha que a OpenAI publique um novo modelo e a documentação oficial confirme que ele usa o mesmo contrato técnico já suportado pelo adapter OpenAI do RASAi.

Copie o catálogo de fábrica para `ai-models.toml`, mantenha os modelos existentes e acrescente um novo bloco:

```toml
[[models]]
provider = "OPENAI"
model = "novo-modelo-openai"
enabled = true
selectable = true
adapter_default = false
public_default = false
auto_eligible = true
qualification = "PROVISIONAL"
rasai_class = "PROVISIONAL"
rank = 50
recommended_depth = "MEDIUM"
recommended_use = "avaliação inicial"
reasoning_values = ["NONE", "LOW", "MEDIUM", "HIGH"]
default_reasoning = "LOW"
capabilities = ["STRUCTURED_OUTPUT", "REASONING", "CACHED_INPUT"]
source_reference = "https://documentacao-oficial-do-modelo"
```

Depois selecione o modelo:

```ini
RASAI_OPENAI_MODEL = novo-modelo-openai
```

Para uso explícito, isso é suficiente do ponto de vista do catálogo de modelos, desde que o adapter existente seja compatível.

Para participar do `AUTO` econômico, também deve existir uma regra de preço vigente em `ai-pricing.toml` para o mesmo par provider/modelo.

Exemplo estrutural de pricing, com valores meramente ilustrativos que devem ser substituídos pela política oficial:

```toml
[[models]]
provider = "OPENAI"
model = "novo-modelo-openai"
pricing_model = "TOKEN_STANDARD"
reasoning_billing = "IN_OUTPUT"
region = "GLOBAL"
source_reference = "https://fonte-oficial-de-precos"

  [[models.rules]]
  rule_id = "openai-novo-modelo-standard"
  context = "STANDARD"
  priority = 0
  effective_from = "2026-09-14T00:00:00Z"
  input_price_per_million = 0.00
  cached_input_price_per_million = 0.00
  output_price_per_million = 0.00
```

Valores `0.00` acima são somente placeholders de formato e **não devem ser usados como tarifa real sem confirmação oficial**.

## 9. Desativar um modelo

Para retirar um modelo de novas seleções, prefira manter seu registro administrativo e configurar:

```toml
enabled = false
selectable = false
adapter_default = false
public_default = false
auto_eligible = false
```

Outro modelo habilitado do mesmo provider deve assumir os defaults obrigatórios.

Essa abordagem preserva clareza administrativa sem fazer fallback silencioso para um modelo diferente.

## 10. AUTO e orquestração de custos

O catálogo de modelos **não cria uma nova orquestração**. Todos os consumidores de IA continuam usando o runtime central do RASAi.

A ordem conceitual é:

```text
necessidade de IA
  -> provider integrado e credencial disponível
  -> modelo habilitado, selecionável e vigente
  -> reasoning válido para esse modelo
  -> elegibilidade ao AUTO
  -> preço vigente para o modelo efetivo
  -> ranking econômico
  -> tentativa
  -> quarentena / circuit breaker / fallback já existentes
```

No `AUTO`, o RASAi trabalha com **um modelo efetivo por provider**. O modelo efetivo vem do override `RASAI_<PROVIDER>_MODEL` ou do `public_default` do catálogo.

Um modelo só participa do `AUTO` quando:

1. o provider já possui adapter integrado;
2. o provider está habilitado para AUTO;
3. o modelo está habilitado, selecionável, vigente e `auto_eligible=true`;
4. existe credencial válida/configurada para o provider;
5. existe uma regra de pricing vigente para o modelo efetivo;
6. a saúde do provider não o colocou em quarentena/circuit breaker.

Se o modelo estiver tecnicamente disponível, mas sem pricing vigente, ele pode continuar disponível para seleção explícita. Para `AUTO`, ele é excluído com motivo equivalente a **modelo sem preço vigente para decisão econômica**. O RASAi não inventa preço nem transforma ausência de tarifa em custo zero.

## 11. Validação cruzada modelo x pricing

O RASAi possui validação cruzada entre os catálogos para identificar:

- pricing apontando para provider/modelo que não existe no catálogo de modelos;
- modelo elegível ao `AUTO` sem regra de preço aplicável;
- quantidade de modelos habilitados, elegíveis ao `AUTO` e precificados.

A validação é complementar às validações individuais de cada TOML.

## 12. Limite da configuração sem código

### Não exige código

- novo modelo de OpenAI usando o mesmo adapter OpenAI;
- novo modelo de Gemini compatível com o adapter Gemini atual;
- novo modelo de Anthropic compatível com o adapter Anthropic atual;
- equivalentes para os demais providers já integrados;
- alterar default;
- alterar disponibilidade;
- alterar reasoning aceito/default;
- alterar elegibilidade ao AUTO;
- alterar pricing usando o schema comercial existente.

### Exige código

- provider completamente novo;
- nova autenticação;
- novo protocolo ou endpoint incompatível com o adapter;
- formato de request/response incompatível;
- nova regra comercial que não possa ser expressa pelo schema de pricing existente.

O TOML não é uma linguagem para criar integrações HTTP arbitrárias.

## 13. SaaS / backoffice

O SaaS usa o mesmo contrato lógico, armazenado em PostgreSQL para futura manutenção pelo backoffice. O schema prevê:

- `ai_providers`: providers e adapters técnicos disponíveis;
- `ai_model_catalogs`: versões/publicações do catálogo de modelos;
- `ai_models`: modelos e características;
- `ai_pricing_catalogs`: versões/publicações da política comercial;
- `ai_pricing_rules`: regras de preço;
- `ai_catalog_events`: trilha administrativa das publicações;
- `ai_job_catalog_snapshots`: versões e hashes fixados por job.

Estados administrativos de catálogo:

```text
DRAFT -> VALIDATED -> PUBLISHED -> DISABLED
```

Uma versão `PUBLISHED` é tratada como imutável quanto ao conteúdo: uma mudança comercial ou funcional deve gerar outra `catalog_version`.

## 14. Snapshot por job no SaaS

O worker não deve consultar continuamente a versão corrente das tabelas enquanto executa uma auditoria.

Ao preparar o job, o control plane fixa:

```text
model_catalog_version
model_catalog_sha256
pricing_catalog_version
pricing_catalog_sha256
```

Os documentos validados podem ser materializados como snapshots TOML somente-leitura para o worker. Assim, se o backoffice publicar outra versão durante uma execução, a auditoria em andamento continua usando exatamente a versão com a qual começou.

Isso preserva explicabilidade do `AUTO`, reprocessamento e cálculo de custo.
