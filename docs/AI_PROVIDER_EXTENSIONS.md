# Providers de IA adicionais

Guia operacional dos providers semânticos adicionais integrados ao RASAi por meio do `provider_registry` canônico.

## Estado atual

Os providers adicionais abaixo estão implementados e mantêm sua qualificação própria no registry. A qualificação (`QUALIFIED`, `PROVISIONAL` etc.) continua sendo informação de governança; a participação em `--ai-provider auto` é controlada explicitamente por `auto_eligible` e pela aptidão da configuração da execução.

| CLI | Provider | Modelo default público | Transporte | Estado RASAi | AUTO |
|---|---|---|---|---|---|
| `xai` / `grok` | xAI / Grok | `grok-4.6` | Responses API | `PROVISIONAL` | elegível se apto |
| `qwen` | Alibaba Cloud Model Studio / Qwen | `qwen3.8-flash` | OpenAI-compatible Chat Completions | `PROVISIONAL` | elegível se apto |
| `gemini` | Google Gemini | `gemini-3.8-flash` | Gemini Interactions API | `PROVISIONAL` | elegível se apto |
| `anthropic` / `claude` | Anthropic Claude | `claude-sonnet-5` | Messages API | `PROVISIONAL` | elegível se apto |
| `copilot` / `github-copilot` | GitHub Copilot | `auto` | GitHub Copilot SDK oficial | `PROVISIONAL` | **não; explicit-only** |

O contrato semântico exige o conjunto de regras previsto pela implementação, validação local de schema, proibição de `evidence_id` inventado e fail-closed em saída incompleta ou inválida.

A lista canônica de providers, aliases, credenciais e onboarding está em [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## AUTO

AUTO não usa uma cadeia fixa limitada aos providers históricos. O runtime consulta o registry e inclui todos os providers com `auto_eligible=true` que estejam aptos naquela execução.

Aptidão exige credencial configurada, modelo aceito e demais parâmetros válidos. Providers sem configuração suficiente são excluídos antes de chamadas externas.

A seleção usa round-robin compartilhado entre necessidades de IA. Em uma mesma necessidade, cada provider é tentado no máximo uma vez. Falha temporária avança para o próximo e pode manter o provider elegível para necessidades futuras; falha terminal o remove do restante da auditoria. O circuit breaker abre com três falhas nas últimas cinco observações daquele provider.

GitHub Copilot é deliberadamente `explicit-only` e nunca entra no pool AUTO, mesmo quando seu token está configurado. Isso evita consumo involuntário da assinatura pessoal.

Contrato completo: [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## Defaults de esforço

Sem override explícito, a política pública usa o menor esforço suportado pela integração:

```text
xAI       LOW
Qwen      PROVIDER_DEFAULT
Gemini    LOW
Anthropic LOW
Copilot   PROVIDER_DEFAULT
```

Qwen e Copilot permanecem `PROVIDER_DEFAULT` porque suas integrações atuais não expõem um controle de reasoning público equivalente aos demais adapters.

## Evidência de smoke e qualificação

A existência de adapter e testes fail-closed não equivale a homologação comercial irrestrita do provider. O runtime pode considerar um provider elegível para AUTO quando o registry assim determinar, mas a classificação de qualificação continua visível e deve ser levada em conta em governança/observabilidade.

Sem chave/token, o provider permanece `NOT_CONFIGURED`, com zero chamada externa. Com credencial válida, uma tentativa registrada prova que houve comunicação com o serviço; não prova que a resposta foi aceita pelo contrato do provider ou pelo contrato local do RASAi.

## xAI / Grok

```powershell
$env:XAI_API_KEY = "<xai-api-key>"
rasai audit https://example.com --ai-provider xai
```

Alias: `grok`.

Modelo: `grok-4.6`.

Variáveis:

```text
XAI_API_KEY
RASAI_XAI_MODEL
RASAI_XAI_ENDPOINT
RASAI_XAI_REASONING_EFFORT
```

Endpoint default: `https://api.x.ai/v1/responses`.

Referências oficiais de onboarding e documentação ficam consolidadas em [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Alibaba Qwen

```powershell
$env:DASHSCOPE_API_KEY = "<model-studio-api-key>"
rasai audit https://example.com --ai-provider qwen
```

Modelos:

```text
qwen3.8-max
qwen3.8-flash
```

Default público: `qwen3.8-flash`.

Variáveis:

```text
DASHSCOPE_API_KEY
RASAI_QWEN_MODEL
RASAI_QWEN_ENDPOINT
```

Endpoint default: `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions`.

A API key precisa pertencer à região/workspace do endpoint usado.

## Google Gemini

```powershell
$env:GEMINI_API_KEY = "<gemini-api-key>"
rasai audit https://example.com --ai-provider gemini
```

Modelo: `gemini-3.8-flash`.

Variáveis:

```text
GEMINI_API_KEY
RASAI_GEMINI_MODEL
RASAI_GEMINI_ENDPOINT
RASAI_GEMINI_REASONING_EFFORT
```

Endpoint default: `https://generativelanguage.googleapis.com/v1beta/interactions`.

A key é enviada em header e não deve ser persistida em URL, SQLite, HTML, log ou INI.

## Anthropic Claude

```powershell
$env:ANTHROPIC_API_KEY = "<anthropic-api-key>"
rasai audit https://example.com --ai-provider anthropic
```

Alias: `claude`.

Modelo: `claude-sonnet-5`.

Variáveis:

```text
ANTHROPIC_API_KEY
RASAI_ANTHROPIC_MODEL
RASAI_ANTHROPIC_ENDPOINT
RASAI_ANTHROPIC_REASONING_EFFORT
```

Endpoint default: `https://api.anthropic.com/v1/messages`.

`stop_reason=refusal` em HTTP 200 representa indisponibilidade/rejeição da tentativa, não avaliação negativa do website.

## GitHub Copilot

O adapter usa o **GitHub Copilot SDK oficial** e a assinatura Copilot elegível do usuário.

```powershell
python -m pip install -e ".[copilot]"
$env:COPILOT_GITHUB_TOKEN = "<fine-grained-token>"
rasai audit https://example.com --ai-provider copilot
```

Alias: `github-copilot`.

Configuração pública:

```text
COPILOT_GITHUB_TOKEN
RASAI_COPILOT_MODEL=auto
```

O RASAi configura `use_logged_in_user=False`; portanto não usa silenciosamente uma sessão local do GitHub/Copilot CLI. O token recomendado é um fine-grained PAT da conta pessoal com a permissão **Copilot Requests**. O contrato atual aceita prefixos `github_pat_`, `gho_` e `ghu_`; classic PAT `ghp_` não é aceito nesse fluxo.

A sessão do SDK é criada sem tools e com política deny-by-default de permissões. O RASAi usa Copilot apenas para inferência evidence-bound, não para shell, edição de arquivos ou browser agentic.

Copilot é `explicit_only=true` e `auto_eligible=false`. Selecionar `AI=auto` nunca deve consumir a assinatura Copilot.

## Ausência de credencial

Selecionar explicitamente um provider sem sua key/token resulta em `NOT_CONFIGURED`, zero chamada externa e zero custo daquela integração. Não existe fallback para credencial de outro provider.

Em AUTO, ausência de credencial apenas impede a entrada daquele provider elegível no pool; os demais aptos continuam disponíveis. Copilot continua fora do AUTO independentemente da presença da credencial.

## Structured output e diferenças de wire

A validação local completa do RASAi continua sendo a fonte de verdade. Schemas podem ser projetados no limite do transport quando uma API aceita apenas um subconjunto do JSON Schema.

Gemini mantém sua projeção específica. OpenAI também recebe projeção de constraints incompatíveis nos payloads estruturados, sem remover a validação local mais estrita. Copilot encapsula o contrato provider-neutral no prompt do SDK e a resposta continua submetida à validação local integral.

Falha `invalid_json_schema`/`invalid_request` é erro técnico de integração, não finding do website.

## Diagnóstico e telemetria

Uma credencial configurada e uma tentativa registrada provam que o provider foi chamado; não provam que o request foi aceito. O runtime registra tentativas, diagnósticos, consumo/custo quando disponíveis e exchanges sanitizados em `ai_exchange_log`.

No AUTO, uma quarentena interna legada do adapter após falha temporária não é suficiente para retirar definitivamente o provider: o coordenador da execução decide elegibilidade e pode reativá-lo até o limiar do circuit breaker. Condições terminais continuam removendo-o imediatamente.

## Segurança

Credenciais podem ser alteradas pelo console, mas não são gravadas em `rasai-console.ini`. No Windows, persistência no escopo `User` exige ação explícita; `Windows/Machine` é somente observado. A presença da chave/token não garante saldo, quota, plano ou acesso ao modelo.

Headers de autenticação e secrets são excluídos da telemetria de exchanges. Consulte [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md).
