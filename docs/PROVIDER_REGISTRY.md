# Registry de providers de IA

O `provider_registry` centraliza os providers tecnicamente integrados ao RASAi. O adapter de cada provider continua em código; a lista de modelos, defaults, reasoning e elegibilidade por modelo vem do catálogo declarativo descrito em [AI_MODEL_CONFIGURATION.md](AI_MODEL_CONFIGURATION.md).

Arquivos principais:

```text
src/rasai/provider_registry.py
src/rasai/ai_model_catalog.py
src/rasai/config/ai-models-defaults.toml
```

Referência operacional de cadastro/login e geração de credenciais: [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Providers concretos

| ID canônico | Provider | Aliases CLI | Credencial | URL de credencial/login | Política do provider no `AUTO` |
|---|---|---|---|---|---|
| `openai` | OpenAI | - | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `deepseek` | DeepSeek | - | `DEEPSEEK_API_KEY` | <https://platform.deepseek.com/api_keys> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `mimo` | Xiaomi MiMo | - | `MIMO_API_KEY` | <https://mimo.mi.com/> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `xai` | xAI / Grok | `grok` | `XAI_API_KEY` | <https://console.x.ai/> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `qwen` | Alibaba Qwen | - | `DASHSCOPE_API_KEY` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `gemini` | Google Gemini | - | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `anthropic` | Anthropic Claude | `claude` | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> | sim, quando configurado/modelo elegível e saudável; pricing conhecido só altera a ordem econômica |
| `mistral` | Mistral AI | - | `MISTRAL_API_KEY` | <https://console.mistral.ai/api-keys/> | sim, quando configurado/modelo elegível e saudável |
| `cohere` | Cohere | - | `COHERE_API_KEY` | <https://dashboard.cohere.com/api-keys> | sim, quando configurado/modelo elegível e saudável |
| `kimi` | Kimi / Moonshot | `moonshot` | `MOONSHOT_API_KEY` | <https://platform.kimi.ai/console/api-keys> | sim, quando configurado/modelo elegível e saudável |
| `copilot` | GitHub Copilot | `github-copilot` | `COPILOT_GITHUB_TOKEN` | <https://github.com/settings/personal-access-tokens/new> | sim, quando configurado/modelo elegível e saudável |

`none` representa ausência deliberada de provider externo. `auto` representa a política de composição/orquestração e não um provider físico.

Na **seleção explícita** de um provider, pricing nunca é requisito para permitir a chamada. Credencial, modelo/configuração e saúde operacional continuam válidos; se o custo não puder ser resolvido, a tentativa é executável e registrada como `UNPRICED`. Pricing é telemetria e, no `AUTO`, critério de ordenação; não é autorização de execução.

## Regra de escopo de capabilities externas

O registry descreve capacidades efetivamente conectadas ao RASAi. Uma capability presente na documentação do fornecedor não deve ser adicionada ao registry, à documentação operacional ou ao console apenas porque existe externamente. Novos métodos de autenticação, planos, tiers, endpoints, tools, search, agents ou connectors exigem decisão própria, adapter/contrato verificável e teste. Variantes já identificadas estão rastreadas na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

## Separação provider x modelo

O provider registry responde **como** o RASAi integra uma IA:

- credencial;
- aliases;
- endpoint configurável quando aplicável;
- documentação/onboarding;
- adapter/protocolo;
- elegibilidade do provider no AUTO e sua configuração efetiva.

O catálogo de modelos responde **qual modelo daquele provider pode ser usado**:

- modelo habilitado/selecionável;
- default técnico e default público;
- reasoning aceito/default;
- qualification/classificação;
- rank determinístico;
- elegibilidade ao `AUTO`;
- capacidades e vigência.

Por isso, adicionar `[[models]]` para um provider já integrado pode disponibilizar um novo modelo sem alterar código, desde que o novo modelo continue compatível com o adapter existente. Um `provider` inexistente no conjunto de adapters é rejeitado pelo runtime.

## Mistral AI

A integração inicial usa `POST https://api.mistral.ai/v1/chat/completions` com `MISTRAL_API_KEY`, Structured Outputs por JSON Schema e validação local integral pelo contrato já existente do RASAi.

O provider não expõe `RASAI_MISTRAL_ENDPOINT` nesta etapa. O adapter fixa o endpoint global e `service_tier=standard_only` para manter o contexto comercial coerente com o pricing catalogado. O único modelo de fábrica inicialmente habilitado é `mistral-small-2603`.

Mistral está integrado e `auto_eligible=true`; quando `MISTRAL_API_KEY` e o modelo vigente estão configurados, participa de `AI=auto`, sujeito a exclusão explícita e saúde operacional.

## Cohere

A integração inicial usa `POST https://api.cohere.com/v2/chat` com `COHERE_API_KEY` e o modelo `command-a-03-2025`. Structured Outputs são enviados em `response_format`; constraints que o wire Cohere não aceita são removidas apenas da projeção externa e continuam obrigatórias na validação local do RASAi.

Não há `RASAI_COHERE_ENDPOINT` nem controle de reasoning nesta fase. Tools, documents, RAG e Rerank não fazem parte do adapter. Cohere está `auto_eligible=true`; `RASAI_COHERE_COMMERCIAL_MODE=UNKNOWN` pode deixá-lo UNPRICED, sem removê-lo do AUTO.

## Kimi / Moonshot

A integração inicial usa `POST https://api.moonshot.ai/v1/chat/completions` com `MOONSHOT_API_KEY`, somente na plataforma internacional, e o modelo `kimi-k3`. O alias `moonshot` resolve para o mesmo provider.

K3 usa Structured Output por `response_format.type=json_schema` com `strict=true`; o RASAi envia uma projeção wire conservadora e mantém a validação canônica/local integral. Reasoning aceita `LOW|HIGH|MAX`, com default público `LOW`. Não há `RASAI_KIMI_ENDPOINT`: endpoint China/regional alternativo, tools, web search, Formula, Responses API, multimodalidade e cache TTL 1h não fazem parte desta entrega.

Kimi está `auto_eligible=true`; quando `MOONSHOT_API_KEY` e o modelo vigente estão configurados, participa do AUTO. Falhas futuras de quota/crédito/provider são tratadas como limitações/bugs funcionais sem reclassificar o provider como não homologado.

## GitHub Copilot

A integração usa o **GitHub Copilot SDK oficial** e a assinatura Copilot elegível do usuário. Não existe uma `COPILOT_API_KEY` separada de modelo.

Para o RASAi local, a autenticação deliberada é `COPILOT_GITHUB_TOKEN`. O adapter configura `use_logged_in_user=False`, evitando que uma auditoria consuma silenciosamente outra sessão GitHub autenticada na máquina.

O token recomendado é um fine-grained PAT da conta pessoal com a permissão **Copilot Requests**. Prefixos aceitos pelo contrato atual: `github_pat_`, `gho_` e `ghu_`; classic PAT `ghp_` não é compatível com esse fluxo.

O provider está `explicit_only=false` e o modelo `auto` está `auto_eligible=true`. Portanto, `COPILOT_GITHUB_TOKEN` configurado autoriza sua participação no AUTO; use `RASAI_AI_AUTO_EXCLUDE=copilot` quando o operador quiser manter a credencial sem consumir a assinatura no roteamento automático.

Instalação opcional:

```powershell
python -m pip install -e ".[copilot]"
```

## Modo `AUTO`

O runtime não usa uma cadeia fixa de providers.

Para cada provider tecnicamente integrado, `AI=auto`:

1. resolve o modelo efetivo a partir de `RASAI_<PROVIDER>_MODEL` ou `public_default` do catálogo;
2. exige que provider e modelo estejam habilitados para o `AUTO`;
3. exige credencial/configuração válida;
4. remove os IDs listados em `RASAI_AI_AUTO_EXCLUDE`;
5. resolve a regra de pricing vigente quando disponível; ausência de preço mantém o candidato como `UNPRICED` e **não o remove** do pool;
6. remove candidatos inelegíveis pela saúde/quarentena da execução;
7. estima o custo da necessidade atual usando provider/modelo/reasoning, tokens esperados, cache observado e tarifa vigente;
8. ordena os candidatos elegíveis pelo menor custo estimado;
9. tenta cada provider elegível no máximo uma vez por necessidade;
10. aplica o mesmo circuit breaker/quarentena/fallback central durante a execução.

Um modelo habilitado e `auto_eligible=true` pode participar do AUTO mesmo sem pricing vigente. Nesse caso fica **UNPRICED**, é ordenado depois dos candidatos precificados e nunca é interpretado como custo zero.

Todos os providers de IA integrados no registry atual podem entrar no pool `AUTO` quando configurados, com modelo elegível e saudáveis. Esta é também uma **regra para novas integrações**: um provider que for homologado/mergeado no registry canônico deve entrar AUTO-eligible no mesmo merge. `RASAI_AI_AUTO_EXCLUDE` continua sendo a exclusão operacional explícita.

Integrações domain-specific fora do registry não são providers do AUTO. A Perplexity Search API implementada em Search Intelligence é o caso atual: ela permanece separada de evidence-bound e do registry. Consulte [PERPLEXITY_SEARCH_INTELLIGENCE.md](PERPLEXITY_SEARCH_INTELLIGENCE.md).

A política de custo está em [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md) e o schema de preços em [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md).

## Metadados do registro

Cada registro público deriva do adapter e do catálogo efetivo e expõe:

- identificador canônico e nome de apresentação;
- aliases;
- variável de credencial;
- URL oficial de cadastro/login/credencial;
- URL de documentação;
- variável de modelo;
- modelos habilitados/selecionáveis no catálogo efetivo;
- default técnico e default público;
- valores de reasoning aceitos pelos modelos disponíveis;
- endpoint override quando aplicável;
- elegibilidade do provider ao `AUTO`;
- qualificação pública;
- restrição de prefixo/formato de credencial quando necessária.

Qualificação e elegibilidade ao `AUTO` são conceitos diferentes. Saúde/configuração podem retirar o provider da execução; pricing não é gate de admissão. Quando não houver preço resolvível, o provider permanece `UNPRICED` e participa depois dos candidatos precificados.

## Catálogo de fábrica em 02/10/2026

A tabela abaixo é apenas a fotografia do catálogo distribuído com o produto. Um catálogo `file` pode modificar a lista sem alterar o adapter.

| Provider | Default público | Modelos de fábrica | Reasoning default do modelo público |
|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.6-flash` | `mimo-v2.6-pro`, `mimo-v2.6-flash`; v2.5/pro mantidos temporariamente por compatibilidade até 21/10/2026 02:00 UTC | `NONE` |
| xAI | `grok-4.6` | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `NONE` |
| Gemini | `gemini-3.8-flash` | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | `LOW` |
| Mistral | `mistral-small-2603` | `mistral-small-2603` | `PROVIDER_DEFAULT` |
| Cohere | `command-a-03-2025` | `command-a-03-2025` | `PROVIDER_DEFAULT` |
| Kimi / Moonshot | `kimi-k3` | `kimi-k3` | `LOW` |
| GitHub Copilot | `auto` | `auto` | `PROVIDER_DEFAULT` |

A fonte de verdade para a execução é o catálogo efetivamente carregado, não esta fotografia documental.

## MiMo

O contrato atual usa PAYG `sk-...` e o mesmo endpoint Responses `https://api.xiaomimimo.com/v1/responses`. Em 02/10/2026 os defaults foram migrados para `mimo-v2.6-pro` (adapter) e `mimo-v2.6-flash` (público/eficiente). `mimo-v2.5` e `mimo-v2.5-pro` permanecem somente como modelos mantidos temporariamente por compatibilidade selecionáveis até **21/10/2026 02:00 UTC**, horário oficial de retirada; depois disso deixam de ser efetivos pelo catálogo.

O reasoning default RASAi é `NONE`, o menor valor aceito pela Responses API MiMo. Outros valores permitidos ativam thinking, mas a documentação atual informa que a intensidade não é diferenciada no backend. Token Plan `tp-...`, Batch, UltraSpeed, web search, tools e capacidades multimodais não são herdados por essa migração. Modalidades externas continuam na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180); a migração v2.6 é rastreada na [issue #183](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/183).

## Fonte de verdade

A composição vigente é:

```text
adapter técnico do provider
    + catálogo efetivo de modelos
    + catálogo efetivo de pricing
    -> provider registry/runtime
    -> orquestração central
```

Consumidores públicos devem usar o registry canônico e não manter listas próprias de modelos. Configuração detalhada: [AI_MODEL_CONFIGURATION.md](AI_MODEL_CONFIGURATION.md).
