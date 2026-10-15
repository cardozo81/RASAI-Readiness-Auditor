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


## Implementação PoC por evidência (15/10/2026; ainda sem aceite)

**Motivação vinculante:** o operador solicitou reestruturação dos dados da apresentação com a gramática das cinco páginas PoC, e não apenas restyling. O RASAi não está em produção. A PoC fornecida contempla `index.html`, `objetivos.html`, `intervencoes.html`, `urls.html` e `fontes-e-metodo.html`. CSS/JS originais da PoC não foram fornecidos: a comparação estrutural é possível, uma afirmação de fidelidade pixel-perfect não é.

**Modelo de informação:** medição → interpretação/limite → objetivo → ação → alvo/ocorrência → como implementar → como validar → proveniência. Valores, prioridades, escopos e ações continuam vindo de dados persistidos; não há pontuação derivada ou ação adicionada.

| Referência PoC | Destino canônico | Implementação na branch | Limitação transparente |
|---|---|---|---|
| Retrato executivo, métricas diferentes e direcionamento | `index.html#snapshot` | Resumo independente de SARI, Lighthouse/CrUX e ações persistidas quando as fontes estão presentes; caminho para objetivos, intervenções e método | Sem tabela ou amostra não se apresenta zero ou aprovação; não forma score composto |
| Objetivos de melhoria | `directed-analysis.html#objectives` | Sete perspectivas temáticas fixas; contagem de `action_id` distintos **dentro** de cada objetivo; vazios explícitos; grupo extra de não classificados quando necessário | Perspectivas sobrepostas não são somáveis; ausência de ação não equivale a domínio conforme |
| Detalhamento contextual por objetivo | `directed-analysis.html#goal-*` | Um nó HTML de detalhe por objetivo, transformado com JS em `<dialog>` nativo modal; com JS desligado mantém `<details>`; hash histórico da dimensão preservado por âncora alias; na impressão renderiza a fonte HTML | Nenhum dado é carregado por `fetch` ou clonagem JS; modais individuais de ação continuam sendo fonte integral na seção Ações |
| Intervenções com o que/onde/como/validar/evidência | `directed-analysis.html#objectives` e `#actions`, origem `cat-09.html` | Cada referência no detalhamento do objetivo traz justificativa, localização identificável, instruções e validação persistidas, prioridade/esforço/confiança, dimensão e links de origem/evidência/remediação | Quando um campo não existe, diz “não consolidado”; decisões de governança não são inventadas |
| Agrupamento e localização do alvo | `directed-analysis.html`, `cat-09.html`, `capture-context.html` | Consulta somente leitura de `target_location` do CONTENT_AI e `selector` da análise profunda, além do CAT-10 já existente; alvos indeterminados permanecem explicitamente indeterminados | Não geolocaliza, não deduplica por texto, não atribui responsabilidade ao site para recurso externo |
| Fonte, método, separação e limites | `methodology.html`, `execution-evidence.html`, `ai-integrations.html` | Matriz de famílias (SARI, Lighthouse/CrUX, Apdex, acessibilidade, GEO, governança, IA, alvos), percurso observação → índice → análise → remediação, links canônicos | Não altera contrato de scoring, método de aquisição, IA ou avaliação |
| As 19 páginas | CSS compartilhado, menu e shell existentes | Tokens centralizados; estilos obsoletos de cards antigos e redefinições de objetivo removidos; escala de leitura operacional e metodologia adicionada | Páginas CAT/GEO/SARI não perdem resultados, seções, IDs, tabelas ou arquivos canônicos |

### Checklist transversal das 19 páginas

| Páginas | Contrato informacional prioritário | Validação |
|---|---|---|
| `index.html` | Medições independentes, decisão e navegação editorial | KPI sem score novo, vínculos diretos e fontes |
| `sari.html` | Prontidão/limites sem misturar índices | Valores e dimensões preservados |
| `cat-01.html`, `cat-02.html`, `cat-03.html` | Escopo, achados, acessibilidade, semântica, dados estruturados | Seções, ocorrências, tabelas e fonte técnica |
| `cat-04.html` | Lighthouse, CrUX, URL versus origem | Unidades, contexto e escopo medido |
| `cat-05.html` | Search / SERP observacional | Ausência de estimativa não medida |
| `cat-06.html`, `cat-07.html` | Amostras Apdex distintas por arquitetura/perfil | Amostras, estados, índices e mensagens de limitação |
| `cat-08.html`, `cat-09.html` | Origem dos achados, instruções e validação | Remediações e vínculos integrais |
| `cat-10.html` | Segurança passiva e alvo/ocorrência técnico | Sem inferência de titularidade/cookie |
| `geo.html` | GEO observacional, inferência delimitada | Evidência sem promessa de citação |
| `directed-analysis.html` | Objetivo → intervenção → alvo → validação → fonte | Ações distintas, aliases, modais, roadmap, impressão |
| `capture-context.html` | URL, dispositivo, snapshots, recursos | Identificadores longos sem overflow global |
| `execution-evidence.html` | Proveniência de execução | IDs, snapshots e tabelas inalterados |
| `ai-integrations.html` | Modelos/provedores como registros reais | Sem reexecução/sem secrets |
| `methodology.html` | Método e limites por família | Sem recálculo ou alegação de conformidade |
| `metrics.html` | Indicadores na fonte apropriada | Preservação de unidades/limitações |

### Higiene e isolamento do diff

- CSS com uma única definição da paleta `:root`; removidas as regras históricas `report-experience-grid/card` sem renderizador correspondente e o primeiro bloco redundante de objetivos. Padrões reutilizáveis de `directed-operational-*` e `report-evidence-chain` substituem decorativismo por hierarquia e informação.
- Não foram modificados esquema, histórico, motor de IA, pipeline de captura, console, pontuação ou API. Mudanças restritas a renderizadores da árvore `report-catalog`, CSS/JS, testes específicos e documentos.
- A mesma identidade de navegação e CSS continua aplicada a todas as páginas por `CATALOG_REPORT_PAGES` e `_shell`. Não se cria novo `index`, URL ou página de “originais”.
- O baseline equivalente de paridade textual/data_row ainda não foi fornecido. CI sintético pode verificar integridade e contratos, não certificação integral com AUD real.
- **Status de release:** implementação técnica em verificação até 19 checks obrigatórios verdes no HEAD final e smoke físico da AUD isolada. Qualquer regressão corrige-se na mesma branch. **PR #637 permanece DRAFT; #633 OPEN; sem merge.**

### Mapa por URL / alvo

A seção `directed-analysis.html#targets` indexa cada ação uma única vez pelo alvo disponível na fonte: local editorial, seletor, ocorrência técnica CAT-10 ou explicitamente indeterminado. Informa contagens e decisões de governança comprovadas, até quatro títulos por agrupamento e o número de títulos adicionais no inventário integral `#actions`. Não cria uma página HTML nova nem atribui recursos externos ao site sem evidência. Uma mesma ação pode constar de mais de um objetivo, mas somente de um grupo de alvo.

## Revisão de UX após inspeção do retrato (15/10/2026)

**Achado humano:** a disposição visual do retrato foi aceita, mas cada indicador precisava identificar imediatamente **quais evidências ou ações sustentam o valor**. A paleta e os contrastes também exigiam verificação. A observação não equivale a aceite final das 19 páginas.

- Os seis indicadores disponíveis no caso de referência apresentam **CTA textual dentro do próprio cartão**, sem aumentar a quantidade de métricas ou criar uma página paralela: SARI → `sari.html#composition`; Lighthouse de laboratório → linha original de CAT-04 (`#metric-lighthouse-performance`); LCP p75 de campo → linha original de CAT-04 (`#metric-field-lcp-p75`); ações totais → inventário integral; prioridade `HIGH` → subconjunto exato; prioridade `NULL`/vazia → subconjunto exato. Os links de catálogo apontam a linhas originais, não a valores reproduzidos numa segunda tabela.
- Os links de prioridade usam `directed-analysis.html?priority=HIGH#actions` ou `?priority=UNDEFINED#actions` e selecionam as linhas **já persistidas** da tabela de ações. A indicação no topo mostra a quantidade selecionada e o total, com `Ver todas as ações` para reverter o filtro. A definição é estrita: `HIGH` é alta; somente `NULL` ou string vazia representam não definida. **Não incluir `CRITICAL` como `HIGH` nem reinterpretar outras prioridades.**
- A tabela canônica conserva as linhas completas, prioridades e botões de estratégia; com JavaScript desligado, todas as linhas continuam disponíveis e um aviso declara que o filtro exige JS. Na impressão, a apresentação força a inclusão das linhas que a paginação ocultaria na tela. Nenhum dado é carregado via rede ou gravado novamente.
- **Errata validada após novo feedback humano:** a documentação e o código anteriores confundiram a escala da API Lighthouse (0–1) com a escala **já persistida** no banco RASAi (0–100). Segundo o contrato M21 (`docs/LIGHTHOUSE_WEB_QUALITY.md` e `m21_web_performance._parse_lighthouse`), `performance_score=1.0` no `audit.db` significa **1/100**, e não 100/100. O retrato e os indicadores originais CAT-04 passam a projetar diretamente os valores persistidos, sem multiplicação adicional. A versão anterior (HEAD `d9fa940...`) tinha uma representação indevidamente otimista, rejeitada e corrigida na mesma branch. Nenhum valor persistido, motor, fórmula ou medição foi alterado; SARI, Lighthouse e CrUX mantêm contratos distintos.
- O CSS usa os tokens `--ink`, `--secondary-ink`, `--blue`, `--line` e `--card`; links têm texto explícito e sublinhado, foco de teclado, estado de hover sem depender exclusivamente de cor. Testes pontuais verificam contraste mínimo **WCAG AA 4,5:1** para os principais textos do cartão sobre branco. Não se afirma auditoria WCAG integral de todo o relatório.

**Gate específico desta iteração:** executar **somente** `tests/test_catalog_report_site.py`, `tests/test_report_section_readability_328.py` e `tests/report_smoke_633.py` (fluxo `Report 633 offline visual smoke`); não reexecutar suites de coleta/IA/scoring ou todos os workflows do repositório por alterações confinadas à apresentação. A verificação automatizada é complementar ao smoke humano com a AUD real.

## Revisão visual de superfícies e bordas (15/10/2026)

A inspeção humana aprovou a **estrutura de dados**, mas identificou excesso de bordas coloridas em seções GEO sem diferença de significado, fundos azuis em notas meramente explicativas, fundo especial em CAT-07 e numerosos chips azuis na rastreabilidade das ações. As mudanças desta iteração concentram-se nas folhas de estilo de apresentação:

- **Superfícies neutras**: branco como superfície primária; cinza-azulado discreto (`--surface-subtle`) como apoio; borda neutra (`--line`) em cards, blocos de leitura e tabelas. Cartões não recebem faixas de cor por posição ou índice.
- **Ênfase por semântica**, não ornamentação: warning laranja apenas quando o estado requer atenção, erro vermelho, sucesso verde; links de ação/filtro ativos em azul. A nota informativa genérica é neutra. A regra metodológica de limitação pode ter leve destaque azul contextual sem aparentar reprovação.
- **GEO**: as bordas esquerdas alternando turquesa/azul foram eliminadas; sombras decorativas removidas e dimensões tipográficas, preenchimentos, cabeçalhos de tabela e cores ligados ao Design System compartilhado. Nenhum relatório GEO, evidência ou texto alterado.
- **CAT-06/07**: seção de arquitetura e amostras harmonizada, com fundo discreto neutro e sem realce azul arbitrário.
- **Análise Direcionada**: referências de evidência e origem deixam de parecer botões preenchidos idênticos às ações; seguem como links legíveis, sem ocultação ou remoção. Estados persistidos continuam textualmente identificáveis.

**Regressões automatizadas pertinentes:** apresentação dos 19 HTMLs sintéticos no smoke visual #633; asserts de CSS design tokens e tipografia, mais teste da escala Lighthouse persistida. Nenhum workflow de motor/IA/banco deverá ser reexecutado manualmente. Isso não constitui aceite humano final.
