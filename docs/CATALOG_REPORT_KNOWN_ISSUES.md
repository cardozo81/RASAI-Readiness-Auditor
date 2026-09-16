# Report-catalog - estado de validação e pendências conhecidas

Data de referência: 2026-09-16.

Este documento acompanha a validação incremental de `report-catalog/`. A estrutura visual
atual deve ser preservada; os ajustes serão feitos por contrato de dados e, depois, por
página, sem redesenhar a navegação ou o layout já aprovado.

## Correções estruturais aplicadas

- A seleção `CAT-*` é congelada no snapshot secret-free da execução e deve chegar ao
  subprocesso mesmo quando a configuração de modelos/preços de IA foi congelada antes.
- O snapshot de IA deixa de congelar uma cópia completa e antiga do ambiente do processo.
  Somente os parâmetros dos catálogos de modelo/preço/task-profile permanecem imutáveis;
  overlays posteriores da execução continuam visíveis ao subprocesso.
- CAT-08 não selecionado passa a suprimir também `RASAI_IMPROVEMENT_INTELLIGENCE` durante
  a projeção do plano. Uma configuração persistida antiga não pode reativar análise
  profunda fora do plano escolhido pelo operador.
- Itens do snapshot do catálogo passam a persistir `id` e `catalog_id` com o mesmo
  `CAT-*`, permitindo que o gerador HTML relacione o item congelado ao catálogo exibido.

Essas correções são de contrato/execução. Não alteram scoring, regras determinísticas,
layout HTML, roteamento AUTO de providers, quarentena ou política de retry.

## Pendências conhecidas do relatório por catálogos

### Captura e contexto da página

Os dados de captura (`page_snapshots`, URL solicitada/final, device, viewport, navegador,
renderização e artefatos HTTP/DOM/visual) já podem existir no `audit.db`/workspace, mas a
nova árvore ainda não possui uma página sistêmica dedicada para projetá-los. A página deve
ser adicionada em Governança sem alterar a organização visual existente.

### IA: plano versus uso efetivo

A página `IA e integrações` já consegue ler tentativas persistidas, porém cada página CAT
ainda precisa reconciliar explicitamente três estados distintos:

- política de IA declarada pelo catálogo (`NONE`, `OPTIONAL`, `REQUIRED`);
- IA autorizada para aquela subcapacidade no plano congelado;
- tentativa/resultado de IA efetivamente persistido na AUD.

O ajuste deve ser feito página a página. A presença de custo/tentativa persistida nunca
deve ser descrita como "IA não utilizada".

### AUDs anteriores sem `audit_catalog`

Uma AUD criada antes da persistência correta do bloco `audit_catalog` pode possuir dados e
work-items válidos sem possuir o plano CAT congelado. Dados produzidos não devem ser usados
para inferir retroativamente que o operador solicitou um catálogo. O relatório deve tratar
o plano como **indeterminado/ausente**, e não como prova de `NÃO SOLICITADO`.

### CAT-02 - Acessibilidade

A página precisa separar coleta automatizada Lighthouse/PageSpeed de evidências
determinísticas de acessibilidade obtidas por outras rotinas. Falha de Lighthouse não
significa ausência de toda evidência de acessibilidade, mas também não pode ser apresentada
como fulfillment completo da coleta que falhou.

### Mapeamento catálogo x work-item

O relatório deve evoluir para uma tabela declarativa de ownership entre `CAT-*` e
work-items internos. Componentes de suporte como aquisição HTTP, renderização e extração
podem servir a mais de um catálogo e não devem ser confundidos com seleção independente.
A contagem global de work-items deve sempre refletir todas as linhas persistidas da AUD.

## Invariantes para os próximos ajustes

- A seleção do usuário vem do plano congelado; nunca é inferida pela existência de dados.
- Um CAT desmarcado não pode iniciar chamada paga nem work-item funcional próprio.
- IA não altera scoring determinístico por opinião do modelo.
- `report-catalog/` permanece read-only e não executa collectors/providers/IA.
- Ausência de snapshot de plano é estado de proveniência desconhecida, não `NÃO SOLICITADO`.
- Os relatórios serão refinados incrementalmente sem alterar a estrutura visual já
  validada, salvo necessidade funcional explícita.
