# Escopo e agregação de relatórios com múltiplas URLs

Os relatórios do RASAi devem tornar explícita a propriedade de cada valor quando uma auditoria contém mais de uma URL. O leitor deve conseguir distinguir um valor de URL, um contexto URL/dispositivo, um fato de origem, uma população sintética e um agregado da auditoria sem inferir isso apenas pela posição visual.

## Visão geral

`report-catalog/index.html` é uma superfície de síntese e não implica que um card pertença à primeira URL da auditoria.

Para múltiplas URLs:

- **SARI-001 Mobile/Desktop** é um agregado do conjunto auditado para aquele dispositivo. `SCORE-GEO-004` distribui o peso de cada scoring group entre seus escopos de página aplicáveis; adicionar URLs não multiplica o peso metodológico do grupo. O resultado não representa uma única página nem uma média aritmética de scores independentes de páginas.
- **Core Web Vitals** é apresentado como quantidade de contextos válidos aprovados sobre contextos válidos avaliados.
- **Lighthouse Performance** e **Lighthouse Accessibility** são apresentados como faixa mínimo-máximo entre contextos URL/dispositivo válidos quando existe mais de um valor. Nenhuma média sem rótulo é criada.
- **Synthetic Navigation Apdex** também é resumido como faixa entre resumos URL/dispositivo válidos. Cada resumo subjacente continua pertencendo a uma população de amostras de uma URL/dispositivo.

O relatório deve expor `Escopo e agregação` com quantidade de URLs, dispositivos disponíveis e regra de agregação usada nos cards executivos.

## Superfícies atuais por contexto

O contrato HTML da AUD usa somente `report-catalog/`.

As superfícies relevantes para escopo multi-URL incluem:

```text
report-catalog/index.html
report-catalog/sari.html
report-catalog/cat-02.html
report-catalog/cat-04.html
report-catalog/cat-06.html
report-catalog/cat-07.html
report-catalog/capture-context.html
report-catalog/metrics.html
```

As páginas CAT preservam a granularidade nativa dos dados. `capture-context.html` explica a topologia URL/dispositivo. Filtros e paginação no cliente alteram apenas o que está visível; não recalculam scores nem removem evidências do artefato HTML.

## Contrato de filtro de URL e paginação

A interface escalável do relatório indexa cada linha/card a partir de `textContent` estável do DOM antes ou independentemente do estado visual. Ela não deve usar `innerText` dependente de layout como fonte de verdade, pois linhas paginadas usam `display:none` e poderiam se tornar impossíveis de localizar após mudança de filtro ou página.

Consequências:

- alternar repetidamente entre filtros de URL deve ser idempotente;
- uma linha oculta por paginação continua elegível para filtros posteriores de URL/busca;
- voltar para `Todas as URLs` restaura a coleção filtrada correta;
- paginação sempre é aplicada **depois** dos filtros atuais;
- impressão pode expor a coleção completa.

## Layout do Synthetic User Experience Apdex

A seção de Apdex calibrado por população e dispositivo pode conter um card de população por URL. Em auditorias multi-URL, esses cards podem ser organizados em grade responsiva em vez de uma única coluna longa. A grade altera somente a apresentação: cada card continua representando uma população de uma URL e seus valores de Apdex/quantidade de amostras permanecem inalterados.

## Nenhuma agregação oculta

Uma nova superfície que combine múltiplas URLs deve escolher e identificar explicitamente uma destas semânticas:

1. valor individual de URL ou URL/dispositivo;
2. contagem ou razão de aprovação;
3. faixa mínimo-máximo;
4. agregado ponderado formalmente definido;
5. estatística aritmética identificada quando a metodologia realmente a definir.

O relatório não pode exibir um único valor sobre múltiplas URLs sem declarar a regra que o produziu.
