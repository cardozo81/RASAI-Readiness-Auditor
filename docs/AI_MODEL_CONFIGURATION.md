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

Exemplo: se um provider publicar um novo modelo compatível com a mesma integração já usada pelo RASAi, o operador pode cadastrá-lo no catálogo de modelos e cadastrar sua política comercial no catálogo de pricing. Um provider completamente novo, ou um modelo que exija protocolo incompatível, continua exigindo implementação de adapter.

## 2. Arquivos e responsabilidade

A regra operacional é única: **arquivos que o humano administra ficam em `config/` na raiz; arquivos em `src/rasai/config/` são baselines internas do produto**.

| Artefato | Responsabilidade | Alteração humana operacional |
|---|---|---|
| `config/ai-models.toml` | catálogo operacional de modelos | **sim** |
| `config/ai-pricing.toml` | catálogo operacional de preços | **sim** |
| `config/ai-task-profiles.toml` | overrides de personas/perfis de tarefa | **sim** |
| `src/rasai/config/ai-models-defaults.toml` | catálogo de modelos de fábrica distribuído com o RASAi | não |
| `src/rasai/config/ai-pricing-defaults.toml` | catálogo de preços de fábrica | não |
| `src/rasai/config/ai-profiles-defaults.toml` | catálogo completo de personas de fábrica | não |

Modelos e preços são separados de propósito. Um modelo pode existir para seleção explícita mesmo quando ainda não existe uma tarifa unitária conhecida. Nesse caso ele não entra no ranking econômico do `AUTO`.

## 3. Seleção da origem

### `RASAI_AI_MODELS_SOURCE`

| Valor | Comportamento |
|---|---|
| `factory` | ignora o arquivo do operador e usa `src/rasai/config/ai-models-defaults.toml` |
| `file` | exige o arquivo definido por `RASAI_AI_MODELS_FILE`; ausência ou conteúdo inválido é fail-closed |
| `auto` | usa o arquivo do operador quando existir; caso contrário usa o catálogo de fábrica |

O console interativo usa como baseline:

```ini
RASAI_AI_MODELS_SOURCE = auto
RASAI_AI_MODELS_FILE = config/ai-models.toml
```

Portanto, em uso normal, o humano altera **`config/ai-models.toml`**. Não é necessário editar `src/rasai/config/ai-models-defaults.toml`.

### Vigência da alteração no console interativo

O console é um processo de longa duração, mas cada nova AUD local executa em subprocesso próprio. Imediatamente antes de iniciar uma AUD, o RASAi:

1. resolve `RASAI_AI_MODELS_SOURCE` e `RASAI_AI_MODELS_FILE`;
2. lê o arquivo atual do operador;
3. valida o catálogo;
4. cria um snapshot temporário imutável;
5. atualiza o catálogo usado pelo preflight e pela estimativa de custo do console;
6. passa o snapshot ao subprocesso da AUD.

Consequências:

- salvar uma alteração em `config/ai-models.toml` **não exige reiniciar o console**;
- a alteração passa a valer na **próxima AUD iniciada**;
- uma AUD em andamento continua usando o snapshot com que começou;
- uma alteração inválida falha no precheck antes de iniciar o subprocesso da auditoria.

Isso evita hot reload no meio da execução e preserva reprodutibilidade.

## 4. Estrutura do catálogo

Metadados:

```toml
[metadata]
schema_version = 1
catalog_version = "MINHA-POLITICA-MODELOS-2026-09-15"
reference_date = "2026-09-15"
verified_on = "2026-09-15"
review_recommended_on = "2026-10-15"
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
effective_from = "2026-09-15T00:00:00Z"
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

O catálogo define quais modelos são válidos e qual é o default. As variáveis existentes continuam selecionando o modelo efetivo por provider, por exemplo:

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

O valor precisa estar em `reasoning_values` do modelo efetivamente selecionado. Isso permite que dois modelos do mesmo provider tenham políticas de esforço diferentes sem alterar código.

Quando o provider não expõe níveis configuráveis, o catálogo usa `PROVIDER_DEFAULT`.

## 8. Exemplo: adicionar um novo modelo de um provider existente

Edite diretamente `config/ai-models.toml`, mantenha os registros necessários e acrescente o novo bloco compatível com o adapter existente. Atualize também `catalog_version`, `reference_date` e `verified_on` quando a mudança for material.

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

Depois selecione o modelo pela variável do provider, se desejar seleção explícita. Para participar do `AUTO` econômico, também deve existir uma regra de preço vigente em `config/ai-pricing.toml` para o mesmo par provider/modelo.

## 9. Desativar um modelo

Para retirar um modelo de novas seleções, prefira manter seu registro administrativo e configurar:

```toml
enabled = false
selectable = false
adapter_default = false
public_default = false
auto_eligible = false
```

Outro modelo habilitado do mesmo provider deve assumir os defaults obrigatórios. Essa abordagem preserva clareza administrativa sem fazer fallback silencioso para um modelo diferente.

## 10. AUTO e orquestração de custos

O catálogo de modelos **não cria uma nova orquestração**. Todos os consumidores de IA continuam usando o runtime central do RASAi.

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

No `AUTO`, o RASAi trabalha com um modelo efetivo por provider. Um modelo só participa quando provider/adaptador, credencial, elegibilidade, vigência, pricing e saúde operacional permitem. Ausência de preço nunca é interpretada como custo zero.

## 11. Validação cruzada modelo x pricing

O RASAi valida, entre outros pontos:

- pricing apontando para provider/modelo inexistente no catálogo de modelos;
- modelo elegível ao `AUTO` sem regra de preço aplicável;
- quantidade de modelos habilitados, elegíveis ao `AUTO` e precificados.

A validação é complementar às validações individuais dos TOMLs.

## 12. Limite da configuração sem código

### Não exige código

- novo modelo compatível com um adapter já integrado;
- alterar default, disponibilidade, reasoning e elegibilidade ao `AUTO`;
- alterar pricing usando o schema comercial existente.

### Exige código

- provider completamente novo;
- nova autenticação;
- novo protocolo ou endpoint incompatível com o adapter;
- formato de request/response incompatível;
- nova regra comercial não representável pelo schema de pricing existente.

O TOML não é uma linguagem para criar integrações HTTP arbitrárias.

## 13. SaaS / backoffice

O SaaS usa o mesmo contrato lógico, armazenado em PostgreSQL para manutenção pelo backoffice. O schema prevê `ai_providers`, `ai_model_catalogs`, `ai_models`, `ai_pricing_catalogs`, `ai_pricing_rules`, `ai_catalog_events` e `ai_job_catalog_snapshots`.

Estados administrativos de catálogo:

```text
DRAFT -> VALIDATED -> PUBLISHED -> DISABLED
```

Uma versão `PUBLISHED` é tratada como imutável quanto ao conteúdo: uma mudança comercial ou funcional deve gerar outra `catalog_version`.

## 14. Snapshot por execução

No console local, o snapshot é criado no limite de cada nova AUD. No SaaS, o control plane fixa a versão/hash por job. Em ambos os casos, a regra é a mesma:

> uma execução iniciada não muda de catálogo no meio do processamento.

Isso preserva explicabilidade do `AUTO`, cálculo de custo, histórico e reprodutibilidade. Reprocessamentos devem continuar respeitando o contrato próprio da AUD/reprocessamento, e não reinterpretar silenciosamente uma execução histórica com uma configuração diferente.
