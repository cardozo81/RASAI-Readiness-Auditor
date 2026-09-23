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
| `openai` | OpenAI | - | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> | permitido quando o modelo efetivo é elegível e precificado |
| `deepseek` | DeepSeek | - | `DEEPSEEK_API_KEY` | <https://platform.deepseek.com/api_keys> | permitido quando o modelo efetivo é elegível e precificado |
| `mimo` | Xiaomi MiMo | - | `MIMO_API_KEY` | <https://mimo.mi.com/> | permitido quando o modelo efetivo é elegível e precificado |
| `xai` | xAI / Grok | `grok` | `XAI_API_KEY` | <https://console.x.ai/> | permitido quando o modelo efetivo é elegível e precificado |
| `qwen` | Alibaba Qwen | - | `DASHSCOPE_API_KEY` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | permitido quando o modelo efetivo é elegível e precificado |
| `gemini` | Google Gemini | - | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> | permitido quando o modelo efetivo é elegível e precificado |
| `anthropic` | Anthropic Claude | `claude` | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> | permitido quando o modelo efetivo é elegível e precificado |
| `copilot` | GitHub Copilot | `github-copilot` | `COPILOT_GITHUB_TOKEN` | <https://github.com/settings/personal-access-tokens/new> | **não; explicit-only** |

`none` representa ausência deliberada de provider externo. `auto` representa a política de composição/orquestração e não um provider físico.

## Separação provider x modelo

O provider registry responde **como** o RASAi integra uma IA:

- credencial;
- aliases;
- endpoint configurável quando aplicável;
- documentação/onboarding;
- adapter/protocolo;
- política explicit-only do provider quando necessária.

O catálogo de modelos responde **qual modelo daquele provider pode ser usado**:

- modelo habilitado/selecionável;
- default técnico e default público;
- reasoning aceito/default;
- qualification/classificação;
- rank determinístico;
- elegibilidade ao `AUTO`;
- capacidades e vigência.

Por isso, adicionar `[[models]]` para um provider já integrado pode disponibilizar um novo modelo sem alterar código, desde que o novo modelo continue compatível com o adapter existente. Um `provider` inexistente no conjunto de adapters é rejeitado pelo runtime.

## GitHub Copilot

A integração usa o **GitHub Copilot SDK oficial** e a assinatura Copilot elegível do usuário. Não existe uma `COPILOT_API_KEY` separada de modelo.

Para o RASAi local, a autenticação deliberada é `COPILOT_GITHUB_TOKEN`. O adapter configura `use_logged_in_user=False`, evitando que uma auditoria consuma silenciosamente outra sessão GitHub autenticada na máquina.

O token recomendado é um fine-grained PAT da conta pessoal com a permissão **Copilot Requests**. Prefixos aceitos pelo contrato atual: `github_pat_`, `gho_` e `ghu_`; classic PAT `ghp_` não é compatível com esse fluxo.

O provider é `explicit_only=true`; o catálogo de fábrica mantém seu modelo `auto` com `auto_eligible=false`. Assim, a presença de uma credencial não autoriza consumo automático da assinatura pessoal.

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
5. exige uma regra de pricing **vigente** para o modelo efetivo;
6. remove candidatos inelegíveis pela saúde/quarentena da execução;
7. estima o custo da necessidade atual usando provider/modelo/reasoning, tokens esperados, cache observado e tarifa vigente;
8. ordena os candidatos elegíveis pelo menor custo estimado;
9. tenta cada provider elegível no máximo uma vez por necessidade;
10. aplica o mesmo circuit breaker/quarentena/fallback central durante a execução.

Um modelo habilitado para seleção explícita, mas sem pricing vigente, continua tecnicamente selecionável quando permitido pelo catálogo. Ele **não participa do `AUTO` econômico**. O RASAi não inventa tarifa e não interpreta ausência de preço como custo zero.

Providers explicit-only, atualmente GitHub Copilot, não entram no pool `AUTO` mesmo quando a credencial existe.

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

Qualificação e elegibilidade ao `AUTO` são conceitos diferentes. O modelo efetivo ainda precisa cumprir pricing e saúde operacional antes de entrar na decisão econômica.

## Catálogo de fábrica em 14/09/2026

A tabela abaixo é apenas a fotografia do catálogo distribuído com o produto. Um catálogo `file` pode modificar a lista sem alterar o adapter.

| Provider | Default público | Modelos de fábrica | Reasoning default do modelo público |
|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `NONE` |
| xAI | `grok-4.6` | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `PROVIDER_DEFAULT` |
| Gemini | `gemini-3.8-flash` | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | `LOW` |
| GitHub Copilot | `auto` | `auto` | `PROVIDER_DEFAULT` |

A fonte de verdade para a execução é o catálogo efetivamente carregado, não esta fotografia documental.

## MiMo

O registry expõe a restrição da credencial PAYG `sk-...` para impedir que Token Plan `tp-...` seja tratado como credencial compatível pelo adapter atual.

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
