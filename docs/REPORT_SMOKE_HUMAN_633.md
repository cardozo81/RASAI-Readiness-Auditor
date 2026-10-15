# #633 - Execução do smoke humano no relatório canônico

Este procedimento aplica-se **somente à branch de redesenho do PR #637** e a uma **cópia isolada** de uma AUD existente. Não executar uma nova auditoria, não sobrescrever a pasta original, não iniciar integração paga e não fazer merge antes do aceite humano.

## Baseline físico disponibilizado para análise

O pacote da AUD `AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF` examinado neste projeto contém exatamente **19 páginas HTML** no `report-catalog`, o CSS local `css/site.css` e um `manifest.json`. As páginas densas a verificar com prioridade incluem `ai-integrations.html` (883.098 bytes), `directed-analysis.html` (375.898 bytes), `cat-09.html` (358.369 bytes), `cat-10.html` (282.010 bytes), `cat-08.html` (217.944 bytes) e `cat-07.html` (93.077 bytes). Esses tamanhos são **do ZIP original**, apenas marcos de inventário: o tamanho HTML não precisa permanecer idêntico após a mudança de layout.

Não adicionar esse ZIP ou seus HTMLs a git/PR/Actions: somente capturas sintéticas podem ser publicadas como artefatos CI.

## Antes de iniciar

É necessário que o operador tenha Python no ambiente local, Chromium utilizável pelo Playwright, um checkout da branch `feat/633-report-design-unified-20261014` e a AUD original extraída do ZIP. Faça a atualização local apenas para o smoke consolidado, sem tocar em `audits/` ou outras auditorias existentes.

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git fetch origin
git switch feat/633-report-design-unified-20261014
git pull --ff-only origin feat/633-report-design-unified-20261014

$aud = "C:\CAMINHO\EXTRAIDO\AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF"
$out = Join-Path $env:TEMP "rasai-633-preview"
$smoke = Join-Path $env:TEMP "rasai-633-smoke"
.\.venv\Scripts\python.exe -m rasai rematerialize-report --audit-dir $aud --output-root $out

$candidate = Join-Path $out "AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF\report-catalog"
.\.venv\Scripts\python.exe tests\report_smoke_633.py --report-dir $candidate --output-dir $smoke
```

A rematerialização publica **somente** em `$out`; os bytes da AUD fonte devem permanecer intactos. O comando Playwright verifica o pacote autocontido, as 19 páginas, menu único com item ativo, comportamento `file://`, viewport sem overflow global, funcionamento de abrir/fechar menu mobile, navegação sem JS, e produz capturas desktop/tablet/mobile para cada página e PDFs A4 de index/Análise Direcionada/CAT-07.

Para comparar **linhas de tabela, seções e quantidade de diálogos** com um relatório baseline produzido a partir **do mesmo código main e da mesma AUD** (idealmente rematerializado em cópia isolada antes do redesign), adicionar `--baseline-report-dir "C:\CAMINHO\BASELINE\report-catalog"`. A comparação estrita é um gate de regressão; comparar com o ZIP antigo sem equalizar as demais evoluções técnicas pode acusar diferenças anteriores à #633 e exige investigação, não aceite automático.

## Checklist humano consolidado

1. **Desktop:** verificar em `screenshots\desktop` todas as 19 páginas, sobriedade visual, hierarquia, legibilidade e ausência de cortes, mantendo as tabelas originais e a distinção de estados/perfis/métricas.
2. **Tablet e mobile:** verificar `screenshots\tablet` e `screenshots\mobile`; menu de uma fonte, estado ativo, botão e Escape, links válidos, tabelas densas com scroll próprio sem perda de coluna e foco de teclado.
3. **Análise Direcionada:** conferir cartões de objetivos como índices navegáveis e **não aditivos**; cruzar ação, ocorrência, alvo, roadmap, modal, fontes e referências CAT-09. Verificar ausência de ações inventadas em AUD sem síntese.
4. **Dashboard e GEO:** os atalhos da nova experiência apontam às páginas existentes e não criam um segundo resultado. Não confundir SARI com Lighthouse, Web Vitals, Apdex ou SERP/IA.
5. **Impressão A4:** validar PDFs em `print` e, se necessário, imprimir os HTMLs densos para verificar diálogos, listas, roadmap, tabelas e corte de página.
6. **Rastreabilidade e integridade:** arquivo `smoke-summary.json` precisa declarar `manifest_integrity=VERIFIED`, `page_count=19`, `javascript_disabled_mobile_navigation=true`. Não abrir dados privados em URLs públicas.
7. **Aceite:** registrar no PR #637 aprovação/reprovação objetiva com referência ao HEAD SHA da branch, dispositivos verificados, pendências e amostra. **CI verde, captura sintética e esta documentação não equivalem a aprovação humana**.

## Encerramento e governança

A entrega técnica é **pronta para smoke** quando o CI do HEAD da PR Draft estiver verde e seus artefatos sintéticos disponíveis. Somente após aceite explícito do usuário deve-se converter o PR Draft, efetuar merge, confirmar main e fechar #633. Caso o smoke reprove, corrigir na **mesma branch**, reexecutar os gates e submeter novamente ao humano. Quaisquer mudanças em coleta, banco, console, scoring ou providers ficam fora desta issue.
