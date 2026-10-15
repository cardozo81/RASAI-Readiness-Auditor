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


## Emenda de reconciliação — 14/10/2026

Esta seção prevalece sobre a proibição absoluta anterior de recursos remotos. **CDN é permitido, não obrigatório**, somente quando agrega melhoria demonstrável e com mitigação explícita: versões fixas, licença verificada, avaliação de CSP/SRI (quando aplicáveis), fallback funcional e visual, ausência de exfiltração de dados, e navegação/conteúdo essenciais disponíveis sem dependência de rede. Abertura em `file://`, apresentação via endpoints atuais e impressão seguem obrigatórias. Não introduzir SPA ou alterações no SaaS/console.

### Sequência operacional e gates

1. Conciliar o HEAD de `main` e `feat/633-report-ux-unified`: no diagnóstico inicial, `main` = `290a1db105d07f49168ebde33998c1fefea4e61b` e a branch = `e05f1f3703824b0193a31f3016b5ef7055c4977c` (um commit à frente e quatro atrás). Verificar novamente no momento da integração. Não copiar código de subsistemas externos para esta demanda.
2. Congelar baseline real de 19 páginas, inventariando por página e seção: conteúdos, métricas, tabelas, gráficos, estados, identificadores, links, âncoras, evidências, modais e resultados governados. A ausência de um artefato PoC não autoriza inventar dados.
3. Gerar o menu de `CATALOG_REPORT_PAGES` por um único helper compartilhado; preservar grupo, ordenação, página ativa e destinos, com fallback sem JavaScript.
4. Construir design system e aplicar a todas as páginas canônicas, mantendo associação entre observação, regra, interpretação, recomendação, ação e validação sem inferir causalidade ou novos números.
5. Documentar proveniência das projeções por objetivo, intervenção e alvo. Uma intervenção pode aparecer vinculada a objetivos distintos, mas sua identidade e contagem global continuam únicas.
6. Comparar o baseline com rematerialização em pasta separada e inspeções de desktop, tablet, mobile, teclado, contrastes e A4; validar os fluxos `file://` e HTTP, integridade de snapshot/manifest/hash e ausência de escrita no banco.
7. Exigir testes direcionados e revisão do diff para demonstrar que somente projeção HTML, CSS, JS, seus testes e documentação foram tocados.
8. Apresentar evidências e único PR DRAFT para aceite humano explícito. **Sem auto-merge, merge ou fechamento antecipado.**

**Nota metodológica:** WCAG 2.2 AA constitui referência para verificações automatizadas e humanas; CI verde, screenshots ou auditoria automatizada não certificam conformidade integral.

**Restrição de revisão:** a remoção de estilos ou scripts exige prova de que estão órfãos em todas as 19 páginas e não afetam impressão, navegação, links diretos ou modos suportados.
