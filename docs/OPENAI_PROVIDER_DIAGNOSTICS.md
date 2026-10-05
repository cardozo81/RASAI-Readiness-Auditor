# OPENAI_PROVIDER_DIAGNOSTICS.md

## Onde diagnosticar

A telemetria final fica em:

```text
<audits-root>/<AUD-ID>/report-catalog/ai-integrations.html
```

No banco:

```text
ai_audit_sessions
ai_provider_attempts
```

## Credencial

Valide presença sem imprimir a chave:

```powershell
Test-Path Env:OPENAI_API_KEY
```

Com `--ai-provider openai`, chaves ausentes de DeepSeek/MiMo não interferem.

## Provider sem chave

Estado esperado:

```text
NOT_CONFIGURED
```

Nenhuma chamada externa ocorre.

## Timeout

`TIMEOUT_ERROR` não significa, por si só, falta de crédito ou erro de autenticação.

Default CLI:

```text
180 s
```

Override:

```powershell
$env:RASAI_AI_TIMEOUT_SECONDS = "240"
```

Não existe retry automático após timeout.

## Saldo disponível e timeout

Ter saldo/crédito disponível elimina apenas algumas hipóteses. Uma chamada ainda pode falhar por:

- timeout local;
- rede;
- rate limit;
- indisponibilidade de servidor;
- model/permission;
- contrato/resposta inválida.

Use a classe de erro persistida, não inferência pelo saldo.

## Dispositivo

Default da CLI:

```text
mobile
```

Para economizar chamadas, mantenha Mobile quando Desktop não for necessário:

```powershell
rasai audit https://example.com `
  --device-context mobile `
  --ai-provider openai
```

Para comparar Mobile e Desktop, execute AUDs separadas; uma nova AUD não combina os dois contexts.

## Primeiro resultado válido

No AUTO, o primeiro provider com resultado válido encerra a cadeia naquele contexto. Não existe chamada posterior para sobrescrever a resposta aceita.

## URL lock

Em novas AUDs, cada URL possui um único contexto de device. A política de provider/URL continua vinculada à evidência daquele contexto e não mistura respostas de outra AUD ou de outro device.

## Custo

`ESTIMATED_COST` em `ai-integrations.html` é estimativa local. Não substitui billing/invoice da OpenAI.

## Segurança

A página de telemetria não deve conter:

- API key;
- Authorization;
- body integral sensível;
- mensagem não sanitizada que possa carregar segredo.
