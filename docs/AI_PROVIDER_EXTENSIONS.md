# Providers de IA adicionais

Guia operacional dos providers semânticos adicionais integrados ao RASAi por meio do `provider_registry` canônico.

## Estado atual

Os providers abaixo estão implementados, mas permanecem **PROVISIONAL** e **explicit-only**. Eles não participam de `--ai-provider auto` enquanto não houver qualificação humana com credenciais reais de cada provider.

| CLI | Provider | Modelo default público | API usada | Estado RASAi |
|---|---|---|---|---|
| `xai` / `grok` | xAI / Grok | `grok-4.6` | Responses API | `PROVISIONAL` |
| `qwen` | Alibaba Cloud Model Studio / Qwen | `qwen3.8-flash` | OpenAI-compatible Chat Completions | `PROVISIONAL` |
| `gemini` | Google Gemini | `gemini-3.8-flash` | Gemini Interactions API | `PROVISIONAL` |
| `anthropic` / `claude` | Anthropic Claude | `claude-sonnet-5` | Messages API | `PROVISIONAL` |

O contrato semântico exige exatamente as regras BR-GEO-028..049 previstas pela implementação, validação local de schema, proibição de `evidence_id` inventado e fail-closed em saída incompleta ou inválida.

## AUTO

A cadeia homologada não foi ampliada:

```text
OpenAI -> DeepSeek -> MiMo
```

Mesmo com credenciais dos providers adicionais configuradas, eles não entram em AUTO enquanto permanecerem provisórios.

## Defaults de esforço

Sem override explícito, a política pública usa o menor esforço suportado pela integração:

```text
xAI       LOW
Qwen      PROVIDER_DEFAULT
Gemini    LOW
Anthropic LOW
```

Qwen permanece `PROVIDER_DEFAULT` porque o adapter atual não expõe controle de reasoning validado.

## Evidência de smoke disponível

- `none`: aprovado;
- OpenAI explícito: aprovado com chamada real;
- DeepSeek explícito: aprovado com chamada real;
- `auto`: aprovado com chamada real e parada no primeiro sucesso;
- xAI/Qwen/Gemini/Anthropic: fail-closed sem key aprovado;
- aliases `grok -> xai` e `claude -> anthropic`: aprovados sem key, zero chamada;
- MiMo: não qualificado nesta máquina por ausência de credencial PAYG compatível.

O caminho de sucesso real dos providers adicionais permanece dependente de credencial externa válida e não deve ser presumido a partir do teste fail-closed.

## xAI / Grok

```powershell
$env:XAI_API_KEY = "<xai-api-key>"
rasai audit https://example.com --ai-provider xai
```

Alias:

```powershell
rasai audit https://example.com --ai-provider grok
```

Modelo:

```text
grok-4.6
```

Variáveis:

```text
XAI_API_KEY
SEARCHGEO_XAI_MODEL
SEARCHGEO_XAI_ENDPOINT
SEARCHGEO_XAI_REASONING_EFFORT
```

Endpoint default:

```text
https://api.x.ai/v1/responses
```

Referências oficiais:

- Structured Outputs: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
- modelo: https://docs.x.ai/developers/models/grok-4.6
- pricing: https://docs.x.ai/developers/pricing

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
SEARCHGEO_QWEN_MODEL
SEARCHGEO_QWEN_ENDPOINT
```

Endpoint default:

```text
https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions
```

A API key precisa pertencer à região/workspace do endpoint usado.

Referências oficiais:

- https://www.alibabacloud.com/help/en/model-studio/qwen-api-reference
- https://www.alibabacloud.com/help/en/model-studio/compatibility-with-openai-responses-api
- https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output

## Google Gemini

```powershell
$env:GEMINI_API_KEY = "<gemini-api-key>"
rasai audit https://example.com --ai-provider gemini
```

Modelo:

```text
gemini-3.8-flash
```

Variáveis:

```text
GEMINI_API_KEY
SEARCHGEO_GEMINI_MODEL
SEARCHGEO_GEMINI_ENDPOINT
SEARCHGEO_GEMINI_REASONING_EFFORT
```

Endpoint default:

```text
https://generativelanguage.googleapis.com/v1beta/interactions
```

A key é enviada em header e não deve ser persistida em URL, SQLite, HTML, log ou INI.

Referências oficiais:

- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/pricing

## Anthropic Claude

```powershell
$env:ANTHROPIC_API_KEY = "<anthropic-api-key>"
rasai audit https://example.com --ai-provider anthropic
```

Alias:

```powershell
rasai audit https://example.com --ai-provider claude
```

Modelo:

```text
claude-sonnet-5
```

Variáveis:

```text
ANTHROPIC_API_KEY
SEARCHGEO_ANTHROPIC_MODEL
SEARCHGEO_ANTHROPIC_ENDPOINT
SEARCHGEO_ANTHROPIC_REASONING_EFFORT
```

Endpoint default:

```text
https://api.anthropic.com/v1/messages
```

`stop_reason=refusal` em HTTP 200 representa indisponibilidade da tentativa, não avaliação negativa do website.

Referências oficiais:

- https://platform.claude.com/docs/en/api/messages/create
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/about-claude/pricing

## Ausência de credencial

Selecionar explicitamente um provider sem sua key resulta em `NOT_CONFIGURED`, zero chamada externa e zero custo. Não existe fallback para credencial de outro provider.

## Segurança

Credenciais podem ser alteradas pelo console, mas não são gravadas em `rasai-console.ini`. A presença da chave não garante saldo, quota ou acesso ao modelo.
