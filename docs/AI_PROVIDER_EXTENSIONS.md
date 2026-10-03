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
| `mistral` | Mistral AI | `mistral-small-2603` | Chat Completions | `PROVISIONAL` | **não; explicit-only durante homologação** |
| `kimi` / `moonshot` | Kimi / Moonshot | `kimi-k3` | Chat Completions | `PROVISIONAL` | **não; explicit-only durante homologação** |
| `copilot` / `github-copilot` | GitHub Copilot | `auto` | GitHub Copilot SDK oficial | `PROVISIONAL` | **não; explicit-only** |

O contrato semântico exige o conjunto de regras previsto pela implementação, validação local de schema, proibição de `evidence_id` inventado e fail-closed em saída incompleta ou inválida.

A lista canônica de providers, aliases, credenciais e onboarding está em [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Limite de escopo dos providers externos

Este documento descreve apenas o wire contract e as capabilities realmente implementadas pelos adapters RASAi. Capacidades adicionais oferecidas pelos fabricantes não são herdadas automaticamente. Planos, formatos de credencial, autenticações, endpoints, tiers, tools, search, agents ou connectors não implementados/homologados permanecem fora do contrato e são avaliados separadamente na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

## AUTO

AUTO não usa uma cadeia fixa limitada a um subconjunto de providers. O runtime consulta o registry e inclui todos os providers com `auto_eligible=true` que estejam aptos naquela execução.

Aptidão exige credencial configurada, modelo aceito e demais parâmetros válidos. Providers sem configuração suficiente são excluídos antes de chamadas externas.

A seleção é recalculada por necessidade de IA. Entre os candidatos ainda elegíveis, o runtime estima o custo da requisição atual usando provider, modelo, reasoning, volume esperado de input/output, cache observado quando disponível e a tarifa aplicável naquele instante. Providers com pricing conhecido são ordenados do menor para o maior custo estimado; providers sem pricing conhecido permanecem depois dos precificados e preservam entre si a ordem rotativa determinística do coordenador. Em uma mesma necessidade, cada provider é tentado no máximo uma vez. Falha temporária avança para o próximo e pode manter o provider elegível para necessidades futuras; falha terminal o remove do restante da auditoria. O circuit breaker abre com três falhas nas últimas cinco observações daquele provider.

A política econômica não troca silenciosamente para Batch/Flex/assíncrono e não altera quarentena, classificação de erro ou limiares de circuit breaker.

Mistral, Kimi e GitHub Copilot são `explicit-only` nesta entrega e não entram no pool AUTO mesmo quando suas credenciais estão configuradas. Para Mistral, a restrição permanece até homologação humana posterior; para Copilot, evita consumo involuntário da assinatura pessoal.

Contratos completos: [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md) e [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md).

## Defaults de esforço

Sem override explícito, a política pública usa o menor esforço suportado pela integração:

```text
xAI       LOW
Qwen      NONE
Gemini    LOW
Anthropic LOW
Mistral   PROVIDER_DEFAULT
Kimi      LOW
Copilot   PROVIDER_DEFAULT
```

Qwen expõe `reasoning_effort` no contrato OpenAI-compatible e o RASAi usa `NONE` como menor valor válido. Kimi K3 aceita `LOW|HIGH|MAX` e o RASAi usa `LOW`. Mistral e Copilot permanecem `PROVIDER_DEFAULT` porque suas integrações atuais não expõem um controle de reasoning determinístico homologado pelo RASAi.

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
RASAI_QWEN_REASONING_EFFORT
```

Endpoint default: `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions`.

A API key precisa pertencer à região/workspace do endpoint usado. O default de reasoning do RASAi é `NONE`; overrides válidos são `NONE`, `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH` e `MAX`, mapeados pelo contrato OpenAI-compatible do Qwen.

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

## Mistral AI

```powershell
$env:MISTRAL_API_KEY = "<mistral-api-key>"
rasai audit https://example.com --ai-provider mistral --ai-model mistral-small-2603
```

Modelo inicial:

```text
mistral-small-2603
```

Configuração pública:

```text
MISTRAL_API_KEY
RASAI_MISTRAL_MODEL
```

O adapter fixa `https://api.mistral.ai/v1/chat/completions` e `service_tier=standard_only`. Não existe `RASAI_MISTRAL_ENDPOINT` no contrato inicial. Structured Outputs usam JSON Schema no wire e continuam sujeitos à validação local integral do RASAi. Tools/search da Mistral não são habilitados nesta entrega.

Mistral é `explicit_only=true` e `auto_eligible=false` até a homologação humana prevista para provider atual, Mistral e `AI=none`.

## Cohere

```powershell
$env:COHERE_API_KEY = "<cohere-api-key>"
$env:RASAI_COHERE_COMMERCIAL_MODE = "<TRIAL-ou-PRODUCTION>"
rasai audit https://example.com --ai-provider cohere --ai-model command-a-03-2025
```

Modelo inicial:

```text
command-a-03-2025
```

Configuração pública:

```text
COHERE_API_KEY
RASAI_COHERE_MODEL
RASAI_COHERE_COMMERCIAL_MODE=UNKNOWN|TRIAL|PRODUCTION
```

O adapter usa `https://api.cohere.com/v2/chat` e `response_format.type=json_object` com JSON Schema. `minItems`, `maxItems`, `uniqueItems`, `allOf`, `oneOf`, `not` e demais constraints incompatíveis são removidos somente da projeção enviada ao fornecedor; a validação canônica local continua integral.

O contrato atual não envia `tools` nem `documents`, não ativa RAG/Rerank, não expõe endpoint override e não controla reasoning. Pricing exige modalidade comercial explícita: `UNKNOWN` é fail-closed, `TRIAL` usa custo monetário zero segundo a política oficial de trial e `PRODUCTION` usa a tarifa token-based pública. O adapter não infere o tipo da chave. Cohere é `explicit_only=true` e `auto_eligible=false`.

## Kimi / Moonshot

```powershell
$env:MOONSHOT_API_KEY = "<kimi-api-key>"
$env:RASAI_KIMI_REASONING_EFFORT = "LOW"
rasai audit https://example.com --ai-provider kimi --ai-model kimi-k3
```

Modelo inicial:

```text
kimi-k3
```

Configuração:

```text
MOONSHOT_API_KEY
RASAI_KIMI_MODEL
RASAI_KIMI_REASONING_EFFORT=LOW|HIGH|MAX
```

O adapter usa somente a plataforma internacional, `https://api.moonshot.ai/v1/chat/completions`. K3 sempre raciocina; o default RASAi é `LOW`. Structured Output usa `response_format.type=json_schema` com `strict=true`; a projeção no wire não substitui a validação local canônica.

O contrato evidence-bound não envia tools, Formula, web search, documents nem `prompt_cache_options`. O cache implícito permanece no TTL 5m padrão; 1h não é exposto. Usage usa `prompt_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens` e `total_tokens`; cache-write permanece dentro de `prompt_tokens` e não é somado novamente. Kimi é `explicit_only=true` e `auto_eligible=false`.

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

Em AUTO, ausência de credencial apenas impede a entrada daquele provider elegível no pool; os demais aptos continuam disponíveis. Mistral, Cohere, Kimi e Copilot continuam fora do AUTO nesta entrega independentemente da presença da credencial.

## Structured output e diferenças de wire

A validação local completa do RASAi continua sendo a fonte de verdade. Schemas podem ser projetados no limite do transport quando uma API aceita apenas um subconjunto do JSON Schema.

Gemini mantém sua projeção específica. OpenAI também recebe projeção de constraints incompatíveis nos payloads estruturados, sem remover a validação local mais estrita. Mistral reutiliza o contrato Chat Completions estruturado e fixa o tier Standard. Kimi reutiliza Chat Completions com Structured Output estrito, reasoning explícito e validação local integral. Cohere usa Chat V2 e projeção própria do schema wire, preservando a validação local; nenhuma tool/document é adicionada ao request. Copilot encapsula o contrato provider-neutral no prompt do SDK e a resposta continua submetida à validação local integral.

Falha `invalid_json_schema`/`invalid_request` é erro técnico de integração, não finding do website.

## Diagnóstico e telemetria

Uma credencial configurada e uma tentativa registrada provam que o provider foi chamado; não provam que o request foi aceito. O runtime registra tentativas, diagnósticos, consumo/custo quando disponíveis e exchanges sanitizados em `ai_exchange_log`.

No AUTO, uma quarentena interna do adapter após falha temporária não é suficiente para retirar definitivamente o provider: o coordenador da execução decide elegibilidade e pode reativá-lo até o limiar do circuit breaker. Condições terminais continuam removendo-o imediatamente.

## Segurança

Credenciais podem ser alteradas pelo console, mas não são gravadas em `rasai-console.ini`. No Windows, persistência no escopo `User` exige ação explícita; `Windows/Machine` é somente observado. A presença da chave/token não garante saldo, quota, plano ou acesso ao modelo.

Headers de autenticação e secrets são excluídos da telemetria de exchanges. Consulte [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md).
