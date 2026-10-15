# #633 - Redesenho unificado: baseline e contrato da primeira etapa

**Status:** implementação em revisão após reprovação visual da AUD real; aceite humano pendente. Este documento acompanha iterações e não constitui homologação. Este arquivo **não** constitui aceite de release ou substituto de smoke.

## Escopo imutável

Fonte de verdade: `CATALOG_REPORT_PAGES` / `CATALOG_REPORT_FILENAMES` em `catalog_report_contract.py`. As 19 páginas existentes são: `index.html`, `sari.html`, `cat-01.html` a `cat-10.html`, `geo.html`, `directed-analysis.html`, `capture-context.html`, `execution-evidence.html`, `ai-integrations.html`, `methodology.html`, `metrics.html`.

A primeira etapa altera apenas **apresentação** nos helpers compartilhados: `_shell`, CSS e JavaScript da camada `report-catalog`, mais fixtures e esta documentação. Mantém as tabelas, métricas, evidências, ações, estados, seções e deep-links existentes. O gerador continua `materialize_catalog_report_site`, com CSS local no pacote e JS mínimo inline. Nenhuma nova rota ou página HTML, nenhum relatório paralelo, nenhum `fetch` de dados.

## Alterações visuais da primeira etapa

- Paleta sóbria inspirada nos tokens da PoC: fundo esverdeado pálido, navegação azul-petróleo, texto principal azul escuro, acentos teal; nomes de CSS existentes preservados quando representam outra semântica, como `--nav` (largura) versus `--nav-bg` (cor).
- Uma navegação canônica gerada por `_navigation` a partir do contrato: a mesma sidebar em todas as páginas. Apenas **um** link recebe `aria-current='page'`, sem árvore adicional.
- Link de pular ao conteúdo, `main` focalizável e breadcrumbs que não duplicam o estado de navegação primário.
- Em mobile há um botão de abrir/fechar a sidebar com `aria-controls`, `aria-expanded` e Escape. A navegação só é ocultada em viewport estreita após JS instalar explicitamente a classe de aprimoramento; com JS desligado a lista continua visível.
- Foco de teclado explícito, cores contrastantes para estados da navegação e exceção de impressão para controles transitórios.

## Provas automatizadas previstas

Teste físico local de materialização com 19 páginas, links na ordem do contrato, somente uma sidebar e somente uma ação de menu móvel por página; CSS empacotado localmente; rotas e dados existentes testados por `test_catalog_report_site.py` e demais suites de apresentação. Demais requisitos ainda não são declarados concluídos: inventário detalhado/diff de conteúdo frente ao ZIP real, visões por objetivo/intervenção/alvo, verificações quantitativas de contraste, testes de desktop/tablet/mobile/impressão, screenshots e aceite visual.

## Gate de merge

**Nunca integrar na `main` nem fechar a issue #633** antes do aceite humano explícito exigido pela própria issue. CI verde valida apenas regressões programáticas, não suficiência visual. Manter um único PR em estado **DRAFT** com esta branch exclusiva. Não modificar motores, console, web portal, banco, score, providers ou contratos da AUD.

## Iteração pós-smoke real (15/10/2026)

O smoke físico automatizado da AUD de referência verificou 19 páginas, mobile/tablet/desktop e imutabilidade da AUD após correção de identificador técnico longo. **O usuário reprovou a qualidade visual e a organização informacional**: cartões de acesso rápido não equivalem à arquitetura da PoC “Nova experiência”.

Nesta revisão, `index.html#experience` deixa de ser uma grade de atalhos e passa a oferecer um **percurso de leitura em seis etapas**, com objetivo de leitura, contextualização e vínculos para os relatórios existentes: diagnóstico → objetivos → intervenções → evidências → Search/IA → metodologia. Esta estrutura é somente projeção de navegação: não produz métricas, achados ou avaliações adicionais. O CSS compartilha geometria mais contida e remove destaque lateral decorativo dos cartões gerais. Todos os dados originais devem permanecer nas páginas canônicas.

**Limitação:** não houve acesso aos arquivos completos da PoC visual nesta sessão; portanto, não se declara paridade visual ou estrutural integral com ela. A página de ações por objetivo mantém grupos e detalhamento existentes, que requerem apreciação humana comparativa. O baseline de conteúdo equivalente não foi fornecido: `data_row_parity` e `all_visible_content_parity` devem permanecer sem certificação até comparação válida.

### Gates obrigatórios após alterações

- Confirmar CI do **novo HEAD**; falha ou execução pendente impede novo handoff.
- Reexecutar rematerialização isolada e `tests/report_smoke_633.py` na AUD real, sem coletar dados.
- Inspecionar as 19 páginas, em especial intervenções, objetivos, navegação de dados densos, mobile e A4.
- Obter **novo aceite explícito** do responsável sobre o HEAD revisado; PR #637 fica DRAFT até então.
