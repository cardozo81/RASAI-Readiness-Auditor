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
.\.venv\Scripts\python.exe tests\report_catalog_visual_smoke.py --report-dir $candidate --output-dir $smoke
```

A rematerialização publica **somente** em `$out`; os bytes da AUD fonte devem permanecer intactos. O comando Playwright verifica o pacote autocontido, as 19 páginas, menu único com item ativo, comportamento `file://`, viewport sem overflow global, funcionamento de abrir/fechar menu mobile, modal de objetivos com contagem e foco, deep-link, navegação sem JS, e produz capturas desktop/tablet/mobile para cada página (incluindo `objective-modal-open.png` nas páginas com objetivos) e PDFs A4 de index/Análise Direcionada/CAT-07.

Para comparar **linhas de tabela, seções e quantidade de diálogos** com um relatório baseline produzido a partir **do mesmo código main e da mesma AUD** (idealmente rematerializado em cópia isolada antes do redesign), adicionar `--baseline-report-dir "C:\CAMINHO\BASELINE\report-catalog"`. A comparação estrita verifica contagens e texto de linhas de tabelas, IDs/âncoras persistidos, links locais, conteúdo textual visível e quantidade de diálogos. O smoke também calcula e reconfere hashes dos arquivos do relatório de origem e de `audit.db` antes/depois, sem escrever na AUD. A ferramenta recusa publicar capturas dentro da pasta da AUD e impede usar a mesma pasta como baseline e candidato. Comparar com o ZIP antigo sem equalizar as demais evoluções técnicas pode acusar diferenças anteriores à #633 e exige investigação, não aceite automático.

## Checklist humano consolidado

1. **Desktop:** verificar em `screenshots\desktop` todas as 19 páginas, sobriedade visual, hierarquia, legibilidade e ausência de cortes, mantendo as tabelas originais e a distinção de estados/perfis/métricas.
2. **Tablet e mobile:** verificar `screenshots\tablet` e `screenshots\mobile`; menu de uma fonte, estado ativo, botão e Escape, links válidos, tabelas densas com scroll próprio sem perda de coluna e foco de teclado.
3. **Análise Direcionada:** verificar as sete perspectivas da PoC, incluindo as sem ação, sem inferir conformidade por zero. Selecionar cada perspectiva: abrir diálogo com ação, localização identificável, justificativa, implementação, validação e links de evidência; testar Escape, botão fechar, foco restaurado e URL `#goal-*`. A mesma ação em duas perspectivas mantém identidade única; quantidades temáticas não são aditivas. Abrir CAT-09 e validar a remediação íntegra. Verificar também o fallback `<details>` com JS desligado e o relatório impresso com toda a listagem.
4. **Dashboard, metodologia e GEO:** confirmar o retrato executivo com SARI, Lighthouse/CrUX e ações **somente quando persistidos**, sem misturar escopo URL e ORIGIN, laboratório e campo. Conferir `index.html#snapshot` e a matriz `methodology.html#interpretation` de fontes/limites, sem novo índice, classificação de ranking ou resultados falsos.
5. **Impressão A4:** validar PDFs em `print` e, se necessário, imprimir os HTMLs densos para verificar diálogos, listas, roadmap, tabelas e corte de página.
6. **Rastreabilidade e integridade:** arquivo `smoke-summary.json` precisa declarar `manifest_integrity=VERIFIED`, `page_count=19`, `javascript_disabled_mobile_navigation=true` e `objective_dialog_open_close_focus_hash=true` e `objective_nojs_source_visible=true`. Não abrir dados privados em URLs públicas.
7. **Aceite:** registrar no PR #637 aprovação/reprovação objetiva com referência ao HEAD SHA da branch, dispositivos verificados, pendências e amostra. **CI verde, captura sintética e esta documentação não equivalem a aprovação humana**.

## Gate direcionado adicional - cartões de `index.html#snapshot` (15/10/2026)

A última inspeção aprovou a geometria do retrato e solicitou **acesso inequívoco ao detalhamento de cada indicador**, além de cores da paleta em contraste acessível. Na cópia isolada recém-rematerializada, validar especificamente:

1. Cada cartão apresenta um CTA **legível e focável por teclado**; acionar o CTA de **SARI** abre a composição já persistida; **Lighthouse** e **CrUX LCP p75** abrem diretamente as linhas correspondentes em `cat-04.html#results`, sem confundir laboratório e campo. **Contrato correto:** a API Lighthouse entrega 0-1, mas o banco RASAi já persiste 0-100. Se `performance_score=1.0` na AUD, o relatório deve mostrar **1/100** - nunca **100/100**. Conferir idêntica leitura no CAT-04 e no CAT-07.
2. **Ações direcionadas** abre a tabela integral de ocorrências, sem sumarizar títulos iguais como uma única ocorrência.
3. **Prioridade alta** abre `directed-analysis.html?priority=HIGH#actions` com apenas as ocorrências cujo campo persistido é exatamente `HIGH`. Na AUD de referência, o retrato anteriormente indicava **19**; a página deve exibir a mesma quantidade filtrada, informando o total **60**.
4. **Prioridade não definida** abre `?priority=UNDEFINED#actions` com somente prioridades `NULL` ou vazias. Na AUD de referência, o retrato indicava **7**; conferir sua listagem e o total **60**. Testar `Ver todas as ações` e comprovar que as demais linhas e seus modais não foram perdidos.
5. Repetir com `file://`, teclado, viewport mobile e impressão. Com JavaScript desativado, as ações seguem acessíveis **sem filtro** com aviso de fallback. Na impressão, a tabela deve incluir inclusive as linhas além da primeira página da paginação.
6. Examinar contraste e foco dos CTAs, textos dos cartões e aviso do filtro. O teste quantitativo é parcial (tokens principais, WCAG AA 4,5:1); o operador ainda precisa avaliar a apresentação real, inclusive estados hover e foco visível.

Os checks GitHub pertinentes são **somente** o workflow de apresentação `Report 633 offline visual smoke` e seus testes direcionados. Checks de motores, banco, IA ou infraestrutura não constituem gate relevante para esse ajuste visual e não devem ser disparados manualmente. **Gate humano permanece pendente.**

## Encerramento e governança

A entrega técnica é **pronta para smoke** quando o CI do HEAD da PR Draft estiver verde e seus artefatos sintéticos disponíveis. Somente após aceite explícito do usuário deve-se converter o PR Draft, efetuar merge, confirmar main e fechar #633. Caso o smoke reprove, corrigir na **mesma branch**, reexecutar os gates e submeter novamente ao humano. Quaisquer mudanças em coleta, banco, console, scoring ou providers ficam fora desta issue.

### Revalidação factual pós-feedback (15/10/2026)

Antes de liberar o retrato, comparar no pacote isolado (sem recalcular) o valor Lighthouse do dashboard com CAT-04 e CAT-07. O score baixo de laboratório **não se transforma em aprovação** por parecer `1.0` na escala 0-1: a normalização da API já ocorreu durante a persistência. Confirmar se as notas de SARI e CrUX preservam seus domínios e dispositivos/escopos, sem derivar prontidão diretamente do score Lighthouse. Inspecionar também as 19 páginas com a revisão do Design System: superfícies neutras, bordas consistentes, GEO sem faixas alternadas e CAT-07 sem fundo azul ornamental.

**Status:** alteração corretiva de apresentação implementada, smoke sintético direcionado necessário e aceite visual humano permanece pendente. Esta intervenção não constitui homologação de fatos adicionais não comparados com a AUD original.
