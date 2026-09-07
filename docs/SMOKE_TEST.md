# SMOKE_TEST.md

Smoke mínimo após instalação/merge.

## 1. Ambiente

```powershell
.\.venv\Scripts\Activate.ps1
python --version
rasai --version
rasai audit --help
```

Help deve conter `--device-context`, `--ai-provider` e `--ai-content-remediation`.

## 2. Mobile sem IA - default

```powershell
rasai audit https://example.com --project "Smoke Mobile" --max-pages 1
```

Esperado:

```text
Contexto de dispositivo: MOBILE
Sugestões de conteúdo por IA: DESABILITADAS
```

Workspace:

```text
report/index.html                 existe
report/mobile.html                existe
report/desktop.html               não existe
report/remediation.html           existe
report/content-suggestions.html   existe
report/ai-usage.html              existe
report/references.html            existe
report/css/site.css               existe
```

Em `content-suggestions.html`, Sugestões e remediação de conteúdo por IA textual deve estar DISABLED e a revisão JSON-LD deve existir.

## 3. Desktop e Both

```powershell
rasai audit https://example.com --max-pages 1 --device-context desktop
rasai audit https://example.com --max-pages 1 --device-context both
```

Validar páginas condicionais e BR-GEO-052 somente em `both`.

## 4. JSON-LD ausente

Usar página sem JSON-LD. Confirmar proposta `WebPage` somente com valores observados/persistidos. Não aceitar autor/preço/rating/data/claim inventado.

## 5. JSON-LD existente

Confirmar preservação do graph e revisão não destrutiva de parse, duplicações, `@context`, `@type` e propriedades genéricas quando sustentadas.

## 6. Sugestões e remediação de conteúdo por IA com IA

Pré-requisito: chave de API do produto correto.

```powershell
rasai audit https://URL-DE-TESTE `
  --max-pages 1 `
  --device-context mobile `
  --ai-provider openai `
  --ai-content-remediation
```

Validar em `content-suggestions.html`: finding, objetivo, localização, texto proposto, evidence IDs, provider/model, revisão humana. Em `ai-usage.html`, validar telemetria Sugestões e remediação de conteúdo por IA.

## 7. Falha Sugestões e remediação de conteúdo por IA/provider

Sem token ou com provider indisponível, audit deve concluir; Sugestões e remediação de conteúdo por IA registra estado operacional e não altera Score/finding. JSON-LD determinístico permanece.

## 8. Segurança

Nenhuma API key/Authorization nos HTMLs/DB/artifacts. Um teste “sem token” nunca deve executar chamada real mesmo que o terminal tenha chave exportada.

## 9. CSS/Confidence/References

Validar CSS externo, ausência de `<style>` final, explicação de Coverage/Confidence e fontes oficiais em `references.html`.

## 10. Suíte

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

Nenhum merge com falha conhecida. A validação de estabilização deve passar em Windows e Linux.
