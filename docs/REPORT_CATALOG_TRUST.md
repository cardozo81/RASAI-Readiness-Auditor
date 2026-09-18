# Contrato de confiança do `report-catalog`

## Objetivo

O `report-catalog` deve ser uma projeção auditável do estado persistido da AUD. Ele não pode transformar ausência de dados em sucesso, inferir execução a partir de configuração nem reconstruir payload/evidência inexistentes.

## Invariantes de estado

As superfícies de relatório distinguem, quando aplicável:

- configurado;
- solicitado;
- habilitado;
- executado;
- estado da execução;
- dados disponíveis;
- estado dos dados;
- freshness/proveniência;
- erro/limitação;
- resultado efetivamente persistido.

`configurado != solicitado != executado != dados disponíveis`.

## CAT-05 / `SOURCE-STATE-001`

Search & AI Intelligence mantém estados independentes para:

- SERP;
- AI Overview;
- Competitive Intelligence;
- Google Search Console;
- Microsoft Clarity;
- Common Crawl.

Uma fonte configurada mas não solicitada não aparece como executada. Uma fonte executada sem linhas/resultados não é apresentada como “incluída com sucesso”.

## Freshness e reuso

SERP observada durante a própria AUD usa `LIVE_RECOLLECTION`.

Evidência anterior só pode ser reutilizada quando persistida como `REUSED_EVIDENCE` com origem e motivo. Uma observação temporalmente anterior à AUD apresentada como live invalida a publicação final do `report-catalog`.

## Estado dos demais catálogos

A camada de confiança impede alguns casos de falso sucesso:

- CAT-02 só considera evidência própria quando `accessibility_score`/medição de acessibilidade foi materializada; outra métrica Lighthouse não substitui acessibilidade;
- CAT-04 não é `CONCLUÍDO` somente porque a etapa terminou se nenhuma medição de desempenho utilizável foi persistida;
- CAT-06 não é `CONCLUÍDO` sem amostra/resumo Apdex persistido;
- CAT-07 não é `CONCLUÍDO` sem amostra/resumo de experiência persistido.

CAT-01 pode concluir com evidência técnica persistida mesmo sem work item exclusivo, porque captura/descoberta são parte do próprio pipeline-base.

## CAT-03

CAT-03 separa:

1. contexto declarado;
2. observação determinística;
3. inferência/assessments de IA.

Interpretações AUTO são persistidas como inferência da execução, não como configuração canônica, e podem ser reconstruídas posteriormente.

## CAT-08

Quando CAT-08 é solicitado, `Improvement Intelligence` participa do fulfillment. `COMPLETE_WITH_LIMITATIONS` não é promovido silenciosamente a auditoria completa: o work item permanece em estado retryable/limitado conforme o contrato de fulfillment.

## CAT-09

CAT-09 usa [RECOMMENDATION_GOVERNANCE.md](RECOMMENDATION_GOVERNANCE.md). O plano do cliente contém apenas recomendações aceitas pelo contrato de governança.

## Integridade do pacote

O pacote inclui:

```text
report-catalog/
  manifest.json
  integrity/audit-snapshot.db
  ... páginas e assets
```

`audit-snapshot.db` é criado com SQLite backup, incorporando estado committed que poderia estar em WAL. Portanto, o pacote entregue não depende do `audit.db-wal` original para reconstrução posterior.

O manifest registra:

- hash SHA-256 do snapshot SQLite;
- SHA-256/tamanho de cada arquivo entregue, exceto o próprio manifest;
- fingerprint do estado live utilizado durante materialização;
- versão do contrato;
- AUD de origem;
- data/hora de geração;
- invariantes de confiança habilitadas.

A promoção do diretório temporário para `report-catalog/` é recusada se:

- o estado fonte mudar durante a geração;
- a verificação dos hashes falhar;
- o snapshot não for materializado;
- freshness SERP for inválida.

## Regra de projeção

A geração de relatório não realiza nova análise por IA. Ela lê estado persistido. A única derivação adicional permitida antes do fingerprint final é governança determinística explicitamente persistida, como as decisões CAT-09.

## Verificação offline

`verify_catalog_report_package()` valida o conteúdo usando somente os arquivos entregues no pacote. Alteração ou remoção de arquivo após materialização invalida o manifest.


## Gate de encerramento estrutural

O `report-catalog` materializa `integrity/catalog-assurance.json` e projeta a mesma matriz na visão geral e em cada catálogo.

Os percentuais são **cobertura determinística de controles estruturais**. Eles não são probabilidade estatística de uma observação externa estar correta e não transformam indisponibilidade de provider em erro do site.

Eixos avaliados:

- configurabilidade: parâmetros aplicáveis congelados, origem e exposição;
- governança: estado, limitações, evidências, detalhes técnicos e remediação;
- exposição: dados materiais persistidos permanecem acessíveis à decisão humana;
- confiabilidade: estado/resultados/análise derivam do estado persistido sem fallback inventado;
- integridade: hash da configuração, inventário de fontes, artefatos verificáveis e boundary read-only;
- segurança: snapshot secret-free, saída sem credenciais, links externos endurecidos e ausência de URLs/handlers executáveis injetados pela projeção.

Critérios de encerramento definidos para a estruturação/exposição:

- cada catálogo selecionado: maturidade estrutural >= 95,00%;
- cada catálogo selecionado: confiabilidade >= 99,50%;
- cada catálogo selecionado: integridade >= 99,50%;
- cada catálogo selecionado: segurança >= 99,50%;
- nenhuma média global pode compensar um catálogo individual abaixo desses gates.

Como os checks são discretos, um catálogo normalmente atinge 100% quando todos os controles aplicáveis passam. A meta de 99,50% funciona como limite mínimo, não como estimativa probabilística.

Falhas externas legítimas, `NO_DATA`, `PARTIAL`, indisponibilidade de API ou limitação amostral não reduzem automaticamente o assurance estrutural. O que reduz o assurance é ocultar, classificar incorretamente, perder provenance, quebrar integridade, omitir configuração aplicável ou não tornar a limitação auditável.

`manifest.json` referencia `integrity/catalog-assurance.json`. A verificação offline recusa divergência entre os thresholds, scores globais ou `closure_eligible` registrados nos dois arquivos.

A estruturação/exposição de dados dos catálogos só pode ser declarada encerrada após um smoke CLEAN cujo pacote materializado resulte em `closure_eligible=true`.
