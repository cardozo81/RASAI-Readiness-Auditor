# Troubleshooting

## `rasai` não é reconhecido

Ative a `.venv` e reinstale o projeto em modo editável:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
rasai --version
```

## Chromium/Playwright

```powershell
python -m playwright install chromium
```

Se `RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE` estiver configurado, o caminho precisa existir.

## Provider de IA indisponível

Use o console em **4. IA** ou **E. Variáveis de ambiente / credenciais**. O status deve distinguir `DESABILITADA`, `CONFIGURAR`, `APTO` e `INDISPONÍVEL`; ausência de credencial não é finding do website.

Para verificar presença sem exibir o segredo:

```powershell
Test-Path Env:OPENAI_API_KEY
Test-Path Env:DEEPSEEK_API_KEY
Test-Path Env:MIMO_API_KEY
Test-Path Env:XAI_API_KEY
Test-Path Env:DASHSCOPE_API_KEY
Test-Path Env:GEMINI_API_KEY
Test-Path Env:ANTHROPIC_API_KEY
Test-Path Env:COPILOT_GITHUB_TOKEN
```

A lista canônica, aliases, variável de credencial e URL oficial de cadastro/login ficam em [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md). Não mantenha uma lista paralela como fonte de verdade.

Também verifique:

- produto/plano correto;
- saldo/quota;
- modelo permitido;
- endpoint compatível;
- esforço/reasoning aceito;
- bloqueio/quarantine depois de erro operacional.

MiMo PAYG exige chave `sk-...` no adapter atual; `tp-...` não é equivalente.

GitHub Copilot exige o extra Python `copilot`, `COPILOT_GITHUB_TOKEN` compatível e assinatura Copilot elegível. No fluxo manual, instale com:

```powershell
python -m pip install -e ".[copilot]"
```

Copilot é `explicit-only`: estar configurado não o coloca em `AI=auto`.

## Search Intelligence/SERP sem dados

Em modo `live`, confirme o provider e sua variável de credencial:

```text
serpapi / serpapi-bing -> RASAI_SERPAPI_API_KEY
zenserp               -> RASAI_ZENSERP_API_KEY
scrapingdog            -> RASAI_SCRAPINGDOG_API_KEY
```

O console mostra a URL oficial de cadastro/login e o preflight deve diferenciar provider não configurado de tentativa que falhou. `RASAI_SERP_MAX_REQUESTS` limita tentativas HTTP do RASAi; não equivale necessariamente a créditos comerciais do fornecedor.

Consulte [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Remediação textual indisponível

A opção depende de uma IA configurada e apta. Configure primeiro a opção 4 do console.

## PageSpeed/Lighthouse sem dados

Consulte:

```text
audit.db → web_performance_attempts
logs/audit.log
report/web-performance.html
report/accessibility.html
```

Se aparecer `TIMEOUTERROR`, a chamada PageSpeed excedeu o timeout do cliente. O default público atual é 120 s e pode ser alterado na opção 6 ou em `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS`.

PageSpeed executa Lighthouse remotamente. O RASAi não possui, nesse endpoint, um parâmetro separado para aumentar o timeout interno de carregamento da página dentro do Lighthouse.

## Acessibilidade sem dados

Acessibilidade automatizada reutiliza a categoria `accessibility` do artifact Lighthouse. Se PageSpeed falhou ou não produziu artifact/categoria, o resultado não pode ser materializado. Isso deve aparecer como limitação de coleta, não como score zero ou aprovação.

## CrUX funciona e Lighthouse não

É um estado válido de coleta parcial. CrUX direto pode retornar dados de campo mesmo se PageSpeed/Lighthouse falhar. O report deve mostrar ambas as tentativas separadamente.

## `content-suggestions.html` existe com IA textual OFF

É esperado: revisão/proposta determinística de JSON-LD pode ser materializada sem chamada de IA textual.

## Synthetic Apdex `PARTIAL`

Grupos com menos de 100 amostras válidas são deliberadamente small-group e recebem `*`. Um smoke de 3-5 amostras pode estar operacionalmente correto e ainda ser `PARTIAL` por não ser grupo final.

## INI não salva credenciais

Comportamento intencional. `rasai-console.ini` persiste somente parâmetros não sensíveis. O console pode alterar a credencial na sessão e, no Windows, persistir/remover explicitamente o valor no escopo `User`; nunca grava secrets no INI e não altera `Windows/Machine`.

## Configuração não salva

O menu mostra `ALTERAÇÕES NÃO SALVAS`. Use:

```text
S. Salvar configuração INI [SEM CHAVES]
```

Ao sair, o console deve oferecer salvar, descartar ou cancelar.
