# Relatório HTML por catálogos — validação paralela

## Objetivo

O RASAi mantém temporariamente duas projeções HTML independentes para a mesma AUD. A
finalidade é validar a nova arquitetura CAT-01…CAT-09 sem alterar, remover ou reinterpretar
o conjunto de relatórios que já era gerado.

| Árvore física | Responsável | Situação |
|---|---|---|
| `report/` | geradores HTML atuais/canônicos | permanece inalterada e continua sendo gerada |
| `report-catalog/` | `catalog_report_site.py` | proposta nova em validação |

Não existe cópia de arquivos entre as árvores. Cada gerador possui contrato, navegação,
CSS e materialização próprios. Quando a validação terminar, uma das implementações poderá
ser removida sem exigir que a outra absorva templates ou regras de navegação da descartada.

## Fonte de verdade da proposta

`report-catalog/` é uma projeção **read-only**. O gerador lê:

- `audit.db` da própria AUD;
- `audit_execution_configurations`, incluindo o bloco `audit_catalog` congelado no início
  da execução;
- scores, métricas, work-items e resultados já persistidos.

O gerador não consulta a configuração atual da máquina para reconstruir o plano, não faz
chamadas externas, não chama IA, não executa coletores, não recalcula SARI/SCORE, não cria
evidências e não altera fulfillment.

## Contrato de páginas

A fonte única da navegação é `src/rasai/catalog_report_contract.py`. Todas as páginas usam
o mesmo menu, na mesma ordem, alterando apenas o item ativo.

### Auditoria

- `index.html` — Visão geral;
- `sari.html` — SARI, com score persistido, coverage, confidence, dimensões, limitações e
  versão metodológica.

### Catálogos

- `cat-01.html` — Fundamentos técnicos e descoberta;
- `cat-02.html` — Acessibilidade;
- `cat-03.html` — Conteúdo, semântica e dados estruturados;
- `cat-04.html` — Web Performance;
- `cat-05.html` — Search & AI Intelligence;
- `cat-06.html` — Apdex de navegação;
- `cat-07.html` — Apdex de experiência;
- `cat-08.html` — Análise profunda e melhorias;
- `cat-09.html` — Remediações.

Cada página CAT utiliza a gramática comum:

1. Resumo;
2. Escopo solicitado;
3. Configuração efetiva;
4. Execução;
5. Resultados;
6. Evidências;
7. Análise e interpretação;
8. Remediações;
9. Detalhes técnicos.

Catálogos ausentes do plano congelado continuam tendo página estável, mas aparecem como
`NÃO SOLICITADO`; ausência de dado não é convertida artificialmente em falha do website.

### Governança

- `execution-evidence.html` — matriz plano × execução e integridade do snapshot;
- `ai-integrations.html` — IA e integrações, usando somente telemetria segura persistida;
- `methodology.html` — distinção entre índice, métrica, classificação e contagem, além do
  contrato de scoring persistido;
- `metrics.html` — inventário transversal de índices/métricas e dicionário de leitura.

## Índices e contexto

Todo score persistido na tabela `scores` é projetado. `OVERALL_READINESS` é exibido como
SARI em página específica; as demais dimensões permanecem visíveis com device/contexto,
valor, coverage, confidence, status de consolidação e versão de scoring.

Métricas de Web Performance, SERP e Apdex são exibidas nos CATs que as produzem e também
no inventário transversal. O relatório mantém a distinção metodológica entre, por
exemplo, posição observada em SERP e posição média do Google Search Console.

O HTML não cria classificação nova para um valor quando essa classificação não está
persistida no contrato que produziu o dado.

## IA e segurança

A proposta não envia dados para IA. Quando a AUD registra uso de IA, a página apenas
informa essa política e telemetria segura já persistida. Prompt, resposta bruta, segredo,
API key, access token, refresh token, client secret e senha não são projetados.

Nomes técnicos e tabelas físicas aparecem apenas em blocos de detalhes/proveniência. O
conteúdo principal usa conceitos funcionais.

## Integração com o finalizador

`report_completion.finalize_audit_report_site()` executa o gerador novo após finalizar a
árvore `report/`. A inspeção de completude canônica continua verificando somente
`report/`; portanto, a proposta não redefine silenciosamente o contrato legado durante o
período de avaliação.

Uma falha do gerador experimental é registrada como `catalog-report:<erro>` em
`renderer_errors`, permitindo diagnóstico sem confundir a lista canônica de páginas da
árvore atual.

## Critério para remoção futura

Após o smoke e a comparação funcional, decidir explicitamente qual árvore se torna o
contrato único. Somente então remover:

- o gerador descartado;
- seu contrato de páginas/menu;
- seus testes específicos;
- a chamada correspondente no finalizador.

Até essa decisão, não mover arquivos entre `report/` e `report-catalog/` e não criar uma
terceira árvore de relatórios.
