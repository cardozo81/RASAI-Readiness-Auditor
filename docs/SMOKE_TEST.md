# SMOKE_TEST.md

Smoke mínimo após instalação/merge.

## Política de plataforma

O smoke deve ser executado no ambiente que corresponde à superfície alterada.

- **Windows/PowerShell** é obrigatório para console interativo, CLI/runtime local, SQLite local, persistência de configuração/credenciais, filesystem/paths, multiprocessing/subprocessos, Chromium/Playwright local e abertura de relatórios/artifacts.
- **Linux** é obrigatório para Web/API, PostgreSQL hospedado, workers, scheduler/queue, containers e demais componentes do runtime SaaS.
- Mudanças puramente determinísticas e agnósticas de SO não exigem smoke duplicado.
- Executar Windows + Linux somente quando o mesmo componente roda nos dois ambientes ou quando existir risco técnico concreto de divergência entre sistemas operacionais.

Portanto, Windows não é gate para uma alteração exclusivamente SaaS/Linux, e Linux não é gate para uma alteração exclusivamente do console/runtime local Windows.

## 1. Ambiente local Windows

Aplicável quando o escopo envolver o produto local:

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
report/                           não existe
report.html                       não existe
remediation.html                  não existe
report-catalog/index.html         existe
report-catalog/manifest.json      existe
report-catalog/css/site.css       existe
```

Validar no `report-catalog/` os CATs selecionados e suas páginas de governança. A ausência de HTML não-catalog não pode reduzir findings, recomendações, causa raiz, precisão ou telemetria persistida.

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

## 10. Suíte local Windows

Executar quando a mudança atingir o runtime local ou uma fronteira compartilhada sensível ao SO:

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

## 11. Smoke SaaS Linux

Quando a mudança for de SaaS, validar em Linux somente os componentes atingidos, priorizando Web/API, PostgreSQL, worker, execução desacoplada, scheduling/queue e contratos tenant-scoped. Não é necessário repetir o smoke do console Windows quando a alteração não toca o runtime local.

Para componentes compartilhados, adicionar o segundo SO apenas quando houver dependência de filesystem, processo, browser, rede de baixo nível ou outro comportamento específico de plataforma.

Nenhum merge pode seguir com falha conhecida no gate pertinente ao escopo alterado.

## JSON-LD observado na tela e linguagem pública

Em uma auditoria que possua Structured Data/JSON-LD coletado:

1. abrir `content-suggestions.html`;
2. localizar a URL/dispositivo com JSON-LD existente;
3. abrir **Visualizar JSON-LD observado nesta auditoria**;
4. confirmar que o conteúdo persistido aparece no HTML e que o link para o artifact completo funciona;
5. confirmar que status operacionais aparecem em linguagem humana (por exemplo, **Execução com limitações**) e não como enums como `DEGRADED`;
6. confirmar que identificadores técnicos necessários, como `BR-GEO-*`, IDs de perfil e valores em blocos `code`/`pre`, permanecem inalterados.
