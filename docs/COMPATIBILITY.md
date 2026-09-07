# Compatibilidade

## Ambiente suportado

| Componente | Contrato |
|---|---|
| Python | CPython `>=3.13,<3.14` |
| Windows/PowerShell | alvo operacional principal |
| Playwright | `>=1.57,<2` |
| Chromium | necessário para rendering e Synthetic Apdex |
| SQLite | local/embarcado |

## Dispositivos

```text
mobile
desktop
both
```

Default: `mobile`. Somente contextos materializados participam das análises dependentes de snapshot e das integrações opcionais.

## IA

A auditoria funciona com IA desligada. Providers suportados pelo registry:

```text
OpenAI
DeepSeek
MiMo
xAI/Grok
Qwen
Gemini
Anthropic/Claude
```

AUTO permanece restrito a OpenAI → DeepSeek → MiMo. Providers adicionais são explicit-only.

Cada provider pode ter diferenças de plano, modelo, endpoint, structured output, reasoning e cobrança. Uma chave válida para um produto não deve ser presumida válida para outro endpoint/plano.

## MiMo

O adapter PAYG atual exige chave compatível `sk-...`. Token Plan `tp-...` não é intercambiável com o endpoint PAYG.

## Web Performance

PageSpeed/Lighthouse e CrUX são opcionais e independentes de IA. O default público de timeout externo é 120 s e pode ser alterado.

Acessibilidade automatizada depende do artifact Lighthouse; se PageSpeed falhar, a página de Acessibilidade deve registrar a limitação em vez de inferir resultado.

## Synthetic Apdex

Synthetic Apdex usa Chromium local e tráfego HTTP real contra o alvo. Não depende de IA, PageSpeed ou CrUX. O timeout por navegação é independente do timeout das APIs externas.

## Persistência do console

`rasai-console.ini` armazena somente parâmetros não sensíveis. Credenciais permanecem em ambiente/sessão e não são persistidas pelo console.
