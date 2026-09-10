# Providers de IA adicionais

Guia operacional dos providers semânticos adicionais integrados ao RASAi por meio do `provider_registry` canônico.

## Estado atual

Os providers adicionais abaixo estão implementados e mantêm sua qualificação própria no registry. A qualificação (`QUALIFIED`, `PROVISIONAL` etc.) continua sendo informação de governança; a participação em `--ai-provider auto` é controlada explicitamente pelo atributo `auto_eligible` do registry e pela aptidão de configuração da execução.

| CLI | Provider | Modelo default público | API usada | Estado RASAi |
|---|---|---|---|---|
| `xai` / `grok` | xAI / Grok | `grok-4.6` | Responses API | `PROVISIONAL` |
| `qwen` | Alibaba Cloud Model Studio / Qwen | `qwen3.8-flash` | OpenAI-compatible Chat Completions | `PROVISIONAL` |
| `gemini` | Google Gemini | `gemini-3.8-flash` | Gemini Interactions API | `PROVISIONAL` |
| `anthropic` / `claude` | Anthropic Claude | `claude-sonnet-5` | Messages API | `PROVISIONAL` |

O contrato semântico exige o conjunto de regras previsto pela implementação, validação local de schema, proibição de `evidence_id` inventado e fail-closed em saída incompleta ou inválida.

## AUTO

AUTO não usa mais uma cadeia fixa limitada aos providers históricos. O runtime consulta o registry e inclui todos os providers com `auto_eligible=true` que estejam aptos naquela execução.

Aptidão exige credencial configurada, modelo aceito e demais parâmetros válidos. Providers sem configuração suficiente são excluídos antes de chamadas externas.

A seleção usa round-robin compartilhado entre necessidades de IA. Em uma mesma necessidade, cada provider é tentado no máximo uma vez. Falha temporária avança para o próximo e pode manter o provider elegível para necessidades futuras; falha terminal o remove do restante da auditoria. O circuit breaker abre com três falhas nas últimas cinco observações daquele provider.

Contrato completo: [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## Defaults de esforço

Sem override explícito, a política pública usa o menor esforço suportado pela integração:

```text
xAI       LOW
Qwen      PROVIDER_DEFAULT
Gemini    LOW
Anthropic LOW
```

Qwen permanece `PROVIDER_DEFAULT` porque o adapter atual não expõe controle de reasoning validado.

## Evidência de smoke e qualificação

A existência de adapter e testes fail-closed não equivale a homologação comercial irrestrita do provider. O runtime pode considerar um provider elegível para AUTO quando o registry assim determinar, mas a classificação de qualificação continua visível e deve ser levada em conta em governança/observabilidade.

Sem chave, o provider permanece `NOT_CONFIGURED`, com zero chamada externa. Com chave válida, uma chamada HTTP prova comunicação com o serviço; não prova que o request foi aceito pelo contrato do provider ou pelo contrato local do RASAi.

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
RASAI_XAI_MODEL
RASAI_XAI_ENDPOINT
RASAI_XAI_REASONING_EFFORT
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
RASAI_QWEN_MODEL
RASAI_QWEN_ENDPOINT
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
RASAI_GEMINI_MODEL
RASAI_GEMINI_ENDPOINT
RASAI_GEMINI_REASONING_EFFORT
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
RASAI_ANTHROPIC_MODEL
RASAI_ANTHROPIC_ENDPOINT
RASAI_ANTHROPIC_REASONING_EFFORT
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

Em AUTO, ausência de credencial apenas impede a entrada daquele provider no pool; os demais aptos continuam elegíveis.

## Structured output e diferenças de wire

A validação local completa do RASAi continua sendo a fonte de verdade. Schemas podem ser projetados no limite do transport quando uma API aceita apenas um subconjunto do JSON Schema.

Gemini mantém sua projeção específica. OpenAI também recebe projeção de constraints incompatíveis nos payloads estruturados, sem remover a validação local mais estrita. Esse comportamento abrange as finalidades que reutilizam o transport do provider, inclusive remediações compatíveis.

Falha `invalid_json_schema`/`invalid_request` é erro técnico de integração, não finding do website.

## Diagnóstico e telemetria

Uma chave configurada e uma tentativa HTTP registrada provam que o provider foi chamado; não provam que o request foi aceito. O runtime registra tentativas, diagnósticos, consumo/custo quando disponíveis e exchanges sanitizados de request/response em `ai_exchange_log`.

No AUTO, uma quarentena interna legada do adapter após falha temporária não é suficiente para retirar definitivamente o provider: o coordenador da execução decide elegibilidade e pode reativá-lo até o limiar do circuit breaker. Condições terminais continuam removendo-o imediatamente.

## Segurança

Credenciais podem ser alteradas pelo console, mas não são gravadas em `rasai-console.ini`. A presença da chave não garante saldo, quota ou acesso ao modelo.

Headers de autenticação e secrets são excluídos da telemetria de exchanges. Consulte [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md).
