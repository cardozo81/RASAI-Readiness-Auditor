# Troubleshooting

## `searchgeo` não é reconhecido

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

Se `PLAYWRIGHT_CHROMIUM_EXECUTABLE` estiver configurado, o caminho precisa existir.

## Provider de IA indisponível

Verifique sem exibir a chave:

```powershell
Test-Path Env:OPENAI_API_KEY
Test-Path Env:DEEPSEEK_API_KEY
Test-Path Env:MIMO_API_KEY
```

No console use `E. Variáveis de ambiente`. Secrets aparecem somente como `[SET]`.

Também verifique:

- produto/plano correto;
- saldo/quota;
- modelo permitido;
- endpoint compatível;
- esforço/reasoning aceito;
- bloqueio/quarantine depois de erro operacional.

MiMo PAYG exige chave `sk-...` no adapter atual; `tp-...` não é equivalente.

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

Se aparecer `TIMEOUTERROR`, a chamada PageSpeed excedeu o timeout do cliente. O default público atual é 120 s e pode ser alterado na opção 6 ou em `SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS`.

PageSpeed executa Lighthouse remotamente. O RASAI não possui, nesse endpoint, um parâmetro separado para aumentar o timeout interno de carregamento da página dentro do Lighthouse.

## Acessibilidade sem dados

Acessibilidade automatizada reutiliza a categoria `accessibility` do artifact Lighthouse. Se PageSpeed falhou ou não produziu artifact/categoria, o resultado não pode ser materializado. Isso deve aparecer como limitação de coleta, não como score zero ou aprovação.

## CrUX funciona e Lighthouse não

É um estado válido de coleta parcial. CrUX direto pode retornar dados de campo mesmo se PageSpeed/Lighthouse falhar. O report deve mostrar ambas as tentativas separadamente.

## `content-suggestions.html` existe com IA textual OFF

É esperado: revisão/proposta determinística de JSON-LD pode ser materializada sem chamada de IA textual.

## Synthetic Apdex `PARTIAL`

Grupos com menos de 100 amostras válidas são deliberadamente small-group e recebem `*`. Um smoke de 3–5 amostras pode estar operacionalmente correto e ainda ser `PARTIAL` por não ser grupo final.

## INI não salva credenciais

Comportamento intencional. `rasai-console.ini` persiste somente parâmetros não sensíveis. Chaves alteradas no console são voláteis ao processo se o usuário não as configurar externamente.

## Configuração não salva

O menu mostra `ALTERAÇÕES NÃO SALVAS`. Use:

```text
S. Salvar configuração INI [SEM CHAVES]
```

Ao sair, o console deve oferecer salvar, descartar ou cancelar.
