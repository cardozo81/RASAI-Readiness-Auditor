# Registry de providers de IA

O `provider_registry` canônico centraliza metadados consumidos por CLI, console, preflight e orquestração para evitar listas divergentes de providers, modelos, credenciais, aliases, URLs de onboarding e elegibilidade no modo automático.

Arquivo principal:

```text
src/rasai/provider_registry.py
```

Referência operacional de cadastro/login e geração de credenciais: [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Providers concretos

| ID canônico | Provider | Aliases CLI | Credencial | URL de credencial/login | Elegível para `AUTO` |
|---|---|---|---|---|---|
| `openai` | OpenAI | - | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> | sim |
| `deepseek` | DeepSeek | - | `DEEPSEEK_API_KEY` | <https://platform.deepseek.com/api_keys> | sim |
| `mimo` | Xiaomi MiMo | - | `MIMO_API_KEY` | <https://mimo.mi.com/> | sim |
| `xai` | xAI / Grok | `grok` | `XAI_API_KEY` | <https://console.x.ai/> | sim |
| `qwen` | Alibaba Qwen | - | `DASHSCOPE_API_KEY` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | sim |
| `gemini` | Google Gemini | - | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> | sim |
| `anthropic` | Anthropic Claude | `claude` | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> | sim |
| `copilot` | GitHub Copilot | `github-copilot` | `COPILOT_GITHUB_TOKEN` | <https://github.com/settings/personal-access-tokens/new> | **não; explicit-only** |

`none` representa ausência deliberada de provider externo. `auto` representa a política de composição/orquestração e não um provider físico.

## GitHub Copilot

A integração usa o **GitHub Copilot SDK oficial** e a assinatura Copilot elegível do usuário. Não existe uma `COPILOT_API_KEY` separada de modelo.

Para o RASAi local, a autenticação deliberada é `COPILOT_GITHUB_TOKEN`. O adapter configura `use_logged_in_user=False`, evitando que uma auditoria consuma silenciosamente outra sessão GitHub autenticada na máquina.

O token recomendado é um fine-grained PAT da conta pessoal com a permissão **Copilot Requests**. Prefixos aceitos pelo contrato atual: `github_pat_`, `gho_` e `ghu_`; classic PAT `ghp_` não é compatível com esse fluxo.

O provider é `explicit_only=true` e `auto_eligible=false`. A razão é operacional: uma key configurada não deve fazer o `AI=auto` consumir automaticamente créditos/franquia de uma assinatura pessoal.

Instalação opcional:

```powershell
python -m pip install -e ".[copilot]"
```

## Modo `AUTO`

O runtime atual **não usa uma cadeia fixa limitada a OpenAI, DeepSeek e MiMo**.

`AI=auto`:

1. consulta `provider_registry`;
2. considera os registros com `auto_eligible=true`;
3. exige credencial e configuração válidas para aquela execução;
4. remove os IDs listados em `RASAI_AI_AUTO_EXCLUDE`;
5. usa round-robin compartilhado entre necessidades de IA;
6. tenta cada provider elegível no máximo uma vez por necessidade;
7. aplica estado de saúde e circuit breaker durante a execução;
8. encerra a necessidade quando recebe o primeiro resultado válido.

Providers `explicit-only`, atualmente GitHub Copilot, não entram no pool `AUTO` mesmo quando a credencial existe.

Excluir um provider de `AUTO` não apaga sua credencial/configuração e não impede seleção explícita posterior.

## Metadados do registro

Cada registro pode expor:

- identificador canônico e nome de apresentação;
- aliases;
- variável de credencial;
- URL oficial de cadastro/login/credencial;
- URL de documentação;
- nota específica de autenticação;
- variável de modelo;
- modelos suportados;
- modelo interno de referência/qualificação;
- variável e valores de reasoning quando suportados;
- endpoint override quando aplicável;
- elegibilidade `AUTO` e `explicit_only`;
- qualificação/reliability;
- restrição de prefixo/formato de credencial quando necessária.

Qualificação e elegibilidade `AUTO` são conceitos diferentes. Um provider pode manter qualificação `PROVISIONAL` e ainda estar disponível ao coordenador `AUTO` quando o registry vigente o marca como elegível e sua configuração passa no preflight. Da mesma forma, Copilot é `PROVISIONAL` mas permanece explicit-only por política de consumo.

## Valores públicos de modelo e reasoning

Os defaults públicos efetivos são definidos por `provider_runtime_policy`, não pelos defaults históricos internos usados por adapters ou políticas de qualificação.

| Provider | Default público de modelo | Modelos permitidos pelo runtime | Default de reasoning | Valores de reasoning permitidos | Recomendado |
|---|---|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | default público; elevar deliberadamente quando necessário |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | default público |
| MiMo | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | default público |
| xAI | `grok-4.6` | `grok-4.6` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | default público |
| Qwen | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` | default público |
| Gemini | `gemini-3.8-flash` | `gemini-3.8-flash` | `LOW` | `LOW`, `MEDIUM`, `HIGH` | default público |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | default público |
| GitHub Copilot | `auto` | `auto` | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` | deixar o SDK/assinatura resolver o modelo disponível; seleção explícita |

A referência operacional consolidada é [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md), complementada por [`PROVIDER_SETUP.md`](PROVIDER_SETUP.md) para onboarding de providers. Caso documentação e runtime divirjam, o código vigente deve ser tratado como fonte técnica e a documentação corrigida; não se deve alterar o runtime apenas para preservar um texto antigo.

## MiMo

O registry expõe a restrição da credencial PAYG `sk-...` para impedir que Token Plan `tp-...` seja tratado como credencial compatível pelo adapter atual.

## Fonte de verdade e compatibilidade interna

Adapters históricos podem conservar defaults, ranks e labels de qualificação usados para compatibilidade interna. Esses valores não devem ser confundidos com o default público resolvido por `provider_runtime_policy`.

Nomes internos de módulos/eventos também podem preservar identificadores históricos por compatibilidade. Consumidores públicos devem usar nomenclatura funcional e o registry canônico.
