# RASAi - Gate de entrega tecnica para smoke humano

Status: procedimento controlado pre-smoke, read-only quando possivel.
Este documento nao declara homologadas as issues em que faltam dados reais
de provedores, comparabilidade amostral ou decisao metodologica.

## Gate B consolidado da PR #645 — adendo operacional (16/10/2026)

Este roteiro substitui orientacoes historicas de `main` no pre-merge. Fonte de
gates independentes: [SMOKE_READINESS_GATE.md](SMOKE_READINESS_GATE.md).
Uma leitura do GitHub em 16/10/2026 identificou
`c5af57d9a97eeb2dd4b6966a72cfcc08d5d8b23c`, PR DRAFT e
79 workflow runs SUCCESS (API de PR, primeira pagina). Isso nao e
resultado de Windows no mesmo HEAD ou aceite visual.

**Execucao autonomica antes de apresentar ao operador:**
1. Fixar HEAD, conferir PR DRAFT, arvore limpa e required checks.
2. Registrar por criterio: modulo/commit, teste e SHA, evidencia fisica,
   classe de prova, risco residual, decisao KEEP_OPEN/CLOSE.
3. Executar testes focais somente se nao cobertos por CI vigente ou se
   houver alteracao funcional real; nao reexecutar 79 workflows apenas por
   documentacao.
4. Em Windows, conferir INI temporario (sem save/restauracao reais),
   caminhos de navegacao/cancelamento e integridade de AUD existente.
5. Rematerializar somente em destino novo, comparar 19 relatorios e
   hashes da fonte antes/depois. Integridade estrutural sintetica sem
   baseline completo nao equivale a aceite visual.
6. Sem fontes autorizadas, registrar N/D para SERP/Perplexity, FAQ
   pos-clique, claims oficiais, Dynatrace e longitudinal.
7. Gate B final depende de aceite humano consolidado. Nao executar merge
   enquanto DRAFT e enquanto gates obrigatorios nao comprovados.

**Matriz das 16 issues abertas elegiveis, no checkpoint acima:**

| Issue | Situacao de evidencia | Residual / proxima prova |
| --- | --- | --- |
| #301 | EPIC / OPEN | Aceites das filhas GEO e provas reais |
| #304 | PARTIAL / OPEN | Equivalencia fisica SERP x Perplexity ou N/D |
| #311 | PARTIAL / OPEN | Coortes fisicas comparaveis e metodo CONS |
| #319 | PARTIAL / OPEN | Cronometros fisicos por etapa e custos reconciliados |
| #322 | EXPERIMENTAL / OPEN | Mesmo sample, overhead e contrato sem M23/M25 |
| #330 | PARTIAL / OPEN | Autorizacao, HTML concorrente real e SPA |
| #355 | PARTIAL / OPEN | RUM tenant/populacao Load/XHR/Custom autorizados |
| #357 | EPIC / OPEN | Aceites arquiteturais/Dynatrace relacionados |
| #523 | PARTIAL / OPEN | Inventario completo e round-trip Windows INI |
| #600 | PARTIAL / OPEN | Leitura SARI/ORIGIN e aceite visual em AUD real |
| #601 | PARTIAL / OPEN | DOM FAQ pre/pos autorizado e contrato |
| #602 | NEEDS_DECISION / OPEN | ADR/versionamento/golden antes de recalibrar |
| #603 | BLOCKED_EXTERNAL / OPEN | Fonte primaria e recibo versionado por claim |
| #604 | EPIC / OPEN | Filhas P1/P2, integridade e aceite decisorio |
| #639 | PARTIAL / OPEN | Paths/imports/contratos em Linux e Windows |
| #646 | NEEDS_DECISION / OPEN | Descoberta separada de declaracao e propagacao |

**Criterio de classificacao:** CI verde demonstra exclusivamente o escopo
do workflow. O estado PARTIAL nao significa falha funcional. Nao fechar
issues por presuncao de completude nem exigir fonte paga para validar
apresentacao N/D. Conservar bytes e hashes das AUDs originais.

**Pacote unico de evidencia Windows:** salvar externamente ao repositorio
(a) HEAD e status Git; (b) manifests de checks e hashes antes/depois;
(c) log de `compileall`/imports/pytest apenas quando executados;
(d) matriz de 16 criterios com resultado PASS/FAIL/N/D e razao;
(e) capturas das 19 paginas, identificador do baseline homologado
e divergencias; (f) testes de cancelamento e INI temporario
sem restauracao efetiva; (g) aprovacoes humanas por escopo.
Nao expor credenciais, banco original ou payload de terceiros.

---

## 1. Invariantes antes do smoke

- Antes do merge, validar a branch `chore/acceptance-evidence-reconciliation` (PR #645) em SHA fixado, sem modificacoes locais.
  A `main` e validada separadamente somente depois de merge aprovado.
- Escopo de reconciliacao: issues abertas >= #301; #322 admite apenas instrumentacao experimental isolada, sem hook em M23/M25 nem alteracao de indices.
- #1, #127, #192 e #210 permanecem fora do escopo de implementacao.
- Nenhum teste automatizado pre-smoke deve executar provedores comerciais,
  disparar nova AUD nem modificar bancos e artefatos originais.
- As ferramentas consultivas de #210, #304, #311, #319, #330 e #355 nao
  integram automaticamente seus resultados a scores ou CONS canonico.
- `COMPLETE` e `PARTIAL_RETRYABLE` representam estados logicos distintos;
  progresso fisico 100% nao prova satisfacao de todos os requisitos.

## 2. Atualizacao local Windows

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git fetch origin --prune
git switch chore/acceptance-evidence-reconciliation
git pull --ff-only origin chore/acceptance-evidence-reconciliation
git status --short
git rev-parse HEAD
```

A saida de `git status --short` deve ser vazia, ressalvando arquivos locais
de evidencias nao rastreados que nunca devem ser apagados por este gate.
Confirmar o SHA do HEAD com o SHA registrado na entrega da implementacao.

## 3. Smoke sem nova coleta comercial

Selecione uma AUD existente, com `audit.db` e artefatos originais
disponiveis, e execute uma unica rematerializacao em pasta de saida
nova. Nao usar este comando para corrigir a origem.

```powershell
$auditRoot = Join-Path (Get-Location) "audits"
Get-ChildItem -LiteralPath $auditRoot -Directory -Filter "AUD-*" |
    Select-Object Name, FullName
$auditId = Read-Host "Informe o Audit ID existente na lista acima (AUD-...)"
$aud = Join-Path $auditRoot $auditId
if (-not (Test-Path -LiteralPath (Join-Path $aud "audit.db") -PathType Leaf)) {
    throw "audit.db nao encontrado na pasta AUD selecionada: $aud"
}
$db = Join-Path $aud "audit.db"
$before = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash
$out = Join-Path $env:TEMP ("RASAI-REPORTS-SMOKE-" + (Get-Date -Format "yyyyMMddHHmmss"))
.\.venv\Scripts\rasai.exe rematerialize-report --audit-dir $aud --output-root $out
if ($LASTEXITCODE -ne 0) {
    throw "Rematerializacao recusada: nenhum relatorio publicado. Conservar a AUD original."
}
$report = Join-Path (Join-Path $out $auditId) "report-catalog\index.html"
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "Manifestacao de sucesso sem HTML publicado: $report"
}
$after = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash
if ($before -ne $after) {
    throw "Integridade violada: SHA-256 do audit.db original mudou"
}
.\.venv\Scripts\rasai.exe audit-attempts $aud
if ($LASTEXITCODE -ne 0) {
    throw "Inspecao de tentativas indisponivel: nao declarar smoke verde"
}
Write-Host "Relatorio confirmado:" $report
```

A pasta informada deve ser a subpasta fisica da AUD dentro de
C:\IA-PROJETOS\github\RASAI-Readiness-Auditor\audits (ou do
auditRoot configurado localmente), nunca C:\CAMINHO\PARA\...
nem o diretorio audits desacompanhado de Audit ID. Se a AUD nao
aparecer na lista ou nao contiver audit.db, nao execute o smoke:
localize primeiro a origem real, sem copiar, mover, recriar ou apagar
os artefatos existentes. O comando audit-attempts retorna agora
erro de uso legivel (exit code 2) quando nao encontra a base.

**Falha nao equivale a entrega:** criar `$out` ou imprimir manualmente
`Relatorios gerados em: $out` apos o erro nao comprova que algum
HTML foi publicado. A verificacao requer **exit code 0**, arquivo real
`report-catalog/index.html` e SHA do audit.db de origem identico.
Uma AUD `COMPLETE_WITH_LIMITATIONS` pode gerar relatorio `PRELIMINARY`;
nao atribuir `COMPLETE` a esse estado logico nem usar sua cronologia
como janela fisica completa para a issue #319.

Ambos os comandos sao publicos e somente leitura de origem. O primeiro
recria os HTMLs em copia, sem executar novos coletores. O segundo
exibe cronologia IA, escopo temporal e duracoes de tentativas realmente
persistidas. A entrada do relatorio original continua
`report-catalog/index.html` e a copia deve manter o estado logico
`COMPLETE` ou `PRELIMINARY` conforme a AUD.

Validar, nos HTMLs gerados, os pontos abaixo:
- `ai-integrations.html`: soma de tentativas IA e Content Remediation,
  custo de cada moeda, classificacao de desvio pontual distinta da faixa,
  conciliacao com total persistido, e tratamento N/D de custo invalido,
  moeda mista ou analise direcionada sem escopo previsto comprovado.
- `metrics.html`: duracoes IA somadas versus uniao de intervalos,
  concorrencia, continuacao apos AUD e tempos HTTP sem inventar wall-time
  fisico de fase; custo de provider observado nao e invoice.
- `cat-05.html`: fontes externas e GEO limitados a evidencia efetiva,
  ausencia de Perplexity sinalizada sem invalidar indevidamente o
  catalogo; regiao/idioma/device/intent nao inferidos.
- `cat-06.html` e `cat-07.html`: Apdex sintetico separado de
  configuracao/acoes Dynatrace RUM, sem troca automatica de thresholds.
  Conferir no CAT-07 a tabela consultiva de KPMs Load/XHR/Custom
  por arquitetura: arquitetura UNKNOWN -> N/D; nao confundir opcoes
  suportadas pelo vendor com configuracao efetiva, populacao RUM,
  recomendacao numerica ou atualizacao automatica do tenant.
- `cat-08.html`, `cat-09.html` e `directed-analysis.html`:
  conteudo de IA associado a achados reais, limites de evidencia claros,
  estados de indisponibilidade explicitos e elementos responsivos.
- `report-catalog/index.html`: navegacao, links, impressao e acesso
  aos catalogos completos.

Critério de aceite: nenhuma mudanca em SHA/bytes do `audit.db` fonte,
nenhuma escrita nos artefatos da AUD e nenhum resultado completo
fabricado a partir de um processamento parcial.

## 4. Um smoke humano ponta a ponta somente se autorizado

Caso o reprocessamento offline nao cubra o caminho que se deseja homologar,
o operador pode iniciar, via `abrir-rasai-console.cmd`, UMA auditoria
controlada de uma URL explicitamente autorizada, no device pretendido.
Escolher conscientemente se IA, Web Performance, SERP/Perplexity ou
integracoes live devem ser ativadas; chaves configuradas nao comprovam
quota, acesso ao modelo ou uso efetivo. Registrar Inicio/Fim, Audit ID,
estado logico, exigencias faltantes, contagem de chamadas e custos
tecnicos efetivamente persistidos, sem expor tokens.

Nao executar repetidas auditorias para superar `PARTIAL_RETRYABLE`.
Quando houver falha, preservar a AUD e o diagnostico/reprocessamento
para analise causal dirigida.

## 5. Aceites em aberto que nao sao simulaveis por CI

| Issue | Evidencia e criterio de aceite humano ou metodologico |
| --- | --- |
| #210 | Aprovar semantica de comparacao entre URLs distintas do mesmo dominio. Nao publicar CONS produtivo comparando scores de universos nao equivalentes. |
| #304 | Demonstrar queries, fontes, denominadores, locale/regiao/device/intent e janela de amostragem SERP versus Perplexity com proveniencia real por query; caso contrario, N/D. |
| #311 | Validar a politica de GEO longitudinal e elegibilidade de fontes fisicas antes de introduzir seus resultados ao CONS produtivo. Trends sem amostra comparavel continuam N/D. |
| #319 | Observar duracoes exclusivas de fases com relogios proprios, backtest historico e separacao do custo de execucao principal versus continuacoes direcionadas. Nao inferir wall-time da soma de tentativas. |
| #330 | Autorizar coletar conteudo primario concorrente e comprovar politica robots/consentimento, DOM/SPA, idioma, dispositivo e comparabilidade de URL. Snippets nao sao prova de HTML integral. |
| #355 | Com autorizacao e credenciais separadas de leitura, conferir tenant, APPLICATION-ID, URL, device e janela RUM; distinguir Load/XHR/Custom e Synthetic M23/M25. Nao aplicar limites numericos genericos a SPA. |
| #301, #357 | Epicos de acompanhamento. Fechar somente apos aceitar integralmente os criterios das issues relacionadas. |

O codigo consultivo e sua CI nao substituem esses dados. As issues
continuam abertas ate verificacao dos criterios faltantes.

## 6. Evidencias de retorno

Registrar o SHA exato da branch PR #645, Audit ID, URL/dispositivo sem dados pessoais,
estado logico e os checks efetivamente realizados. Anexar somente
capturas redigidas de `report-catalog/`, mensagens do console e,
quando aplicavel, hashes/contagem de arquivos. Nunca publicar banco
`audit.db`, credenciais, conteudo privado nem dumps de payload de IA
sem tratamento de sigilo.

Se a AUD atingir `COMPLETE` e os checks visuais/funcionais passarem,
o resultado e aprovacao do smoke desse escopo, nao fechamento automatico
das pesquisas RUM, GEO longitudinal ou comparacao concorrencial.
