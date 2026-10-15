# RASAi — Contrato de redesign visual HTML (#633)

**Estado:** referência de implementação na branch exclusiva `feat/633-report-ux-unified`. **Não autoriza merge.**  
**Escopo:** somente projeção HTML da auditoria individual `<AUD>/report-catalog/`; código, testes e documentação do renderer. Nenhum motor, console, banco, provider ou fluxo alterado.

## Referência de design

A PoC aprovada na conversa tem o rótulo “Nova experiência” e utiliza uma sidebar escura, superfícies claras, cards de métricas, hierarquia hero → síntese → objetivo → intervenção → evidência, tipografia de sistema e filtros locais.

A implementação NÃO copia o `index.html` da PoC, `relatorios-originais/`, snapshots de banco, JSON contendo dados de cliente ou uma segunda árvore de relatório. Reutiliza os renderizadores e contratos canônicos no código.

### Tokens visuais propostos

| Token | Cor | Uso |
|---|---|---|
| `--ink` | `#142d3d` | texto principal |
| `--muted` | `#687c87` | texto secundário, somente onde contraste aprovado |
| `--nav` | `#0c2533` | sidebar |
| `--nav2` | `#113444` | elevação da sidebar |
| `--bg` | `#f3f6f6` | fundo do canvas |
| `--surface` | `#ffffff` | cards e tabelas |
| `--line` | `#e1e9e9` | bordas |
| `--accent` | `#087a77` | ações/links |
| `--accent2` | `#10a49e` | detalhe secundário |
| `--orange` | `#d18132` | atenção (ajustar contraste) |
| `--red` | `#be4c4c` | regressão/erro |
| `--blue` | `#3159a8` | informativo |

**Obrigatório:** validar contraste real texto/fundo e WCAG; tokens são ponto de partida e podem precisar de ajustes. Não substituir texto de estado por cores.

### Shell e navegação

- Contrato de páginas: `src/rasai/catalog_report_contract.py` — `CATALOG_REPORT_PAGES`.
- Renderização e navegação: `src/rasai/catalog_report_presentation.py` já define `_navigation(current)`; consolidar/reutilizar, não criar geradores concorrentes.
- Entrada do pacote: `src/rasai/catalog_report_site.py`, com rotinas de fingerprint, snapshot, manifest e verificação: **não alterar sem necessidade de integração estritamente visual e teste de invariantes**.
- CSS: recurso canônico `css/site.css`, referenciado pelo pacote e pela abertura via Web API. Evitar dependência de CSS/JS remoto; `file://` deve operar offline.
- Uma sidebar por página, com ativo correto, agrupamentos de Auditoria, Catálogos, Estratégia e Governança. Navegação acessível no mobile com fallback sem JS. Breadcrumbs e atalhos de seção não são um segundo menu.
- Preservar anchors do produto e links deep-link para findings/evidência. Sem novas URLs HTML redundantes.
- Manter segurança de escaping, `noopener` para links externos, detalhes técnicos opcionais e legibilidade de tabelas largas.

## Mapeamento das telas da PoC para páginas atuais

| PoC | Destino único |
|---|---|
| Visão geral | `index.html` |
| Por objetivo | seções de `directed-analysis.html` |
| Intervenções | ações estratégicas em `directed-analysis.html`; inventário e remediação completa em `cat-09.html`, por referência sem duplicação |
| Por URL/alvo | visão/filter de `cat-09.html`, com contexto de `capture-context.html` |
| Fonte e método | `methodology.html`, `execution-evidence.html`, `ai-integrations.html` |
| Catálogos, SARI, GEO | suas 19 páginas canônicas sem omissão de conteúdo |

Para cada objetivo: exibir status obtido, intervenções identificadas, limitações da fonte, alvos sustentados e links para evidências. Uma ação pode pertencer a mais de um objetivo, mas seu `action_id` permanece único; contagens por objetivo são não aditivas. Preservar estados `ACCEPTED`, `VERIFY_DECIDE`, `REJECTED`.

Novas auditorias operam com **uma única URL de entrada**. Não desenhar UI de múltiplas URLs ou TXT, e não alterar seu legado nesta issue. Histórico continua legível.

## Cobertura e revisão

A interface final deve conter exatamente as páginas públicas do contrato vigente, sem omissão de `geo.html` ou páginas de governança. A página existe mesmo quando a capacidade estiver desabilitada/sem dado. Manter todos os elementos informativos presentes no relatório original; redesenho pode reordenar, oferecer filtros e progressive disclosure acessível.

Comparar renderização antes/depois usando uma AUD real já persistida em ambiente de teste, em uma **nova pasta de rematerialização**, sem gravar na fonte nem executar auditoria, APIs ou IA. Verificar inventários de seções/tabelas/contagens, impressão A4, desktop/mobile, `file://`, sem JS, entrega via Web API e integridade `manifest.json`/SHA/snapshot.

Não modificar `CONS-*` nesta issue. Não introduzir bibliotecas de CDN obrigatórias. Remover somente CSS/JS legado efetivamente sem referências, com testes que provem ausência de regressão.

## Política de liberação

Issue #633 controla a demanda, branch `feat/633-report-ux-unified` é a ÚNICA branch de execução. PR futuro: DRAFT, sem auto-merge. Exigir evidência de CI direcionado e screenshots antes/depois; **somente aceite humano explícito** habilita merge. Uma validação automática positiva nunca equivale a aceite humano.
