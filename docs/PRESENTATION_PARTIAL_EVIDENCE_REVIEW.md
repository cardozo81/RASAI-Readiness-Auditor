# Revisão de apresentação da PR #718 - gerador 0.4.16

> **Contexto histórico de engenharia.** Revisão do gerador 0.4.16 na PR #718. As decisões e testes descritos preservam o contexto histórico de uma auditoria parcial; não são um gate aberto de merge. Para uso atual, consulte o [guia de leitura](REPORT_GUIDE.md), o [contrato de apresentação](REPORT_PRESENTATION_CONTRACT.md) e a [rematerialização](REPORT_REMATERIALIZATION.md). O [registro da versão 1.0.0](https://github.com/cardozo81/RASAI-Readiness-Auditor/blob/e55717b2a2c924cdc9f81e39565353d063f47892/docs/PRESENTATION_PARTIAL_EVIDENCE_REVIEW.md) permanece acessível.

Na auditoria parcial, dois achados de descoberta não constituem um plano aprovado,
uma previsão financeira não representa consumo de IA e uma captura passiva não
comprova sondas ativas. A revisão mantém essas distinções visíveis nas páginas
Plano, IA e custos e Rede, com os componentes e o design existentes.

- Plano: estado de ausência do plano no início da página, sem a sequência de
  classes vazias. Achados informativos mostram título registrado, categoria
  tipada em português, estado, origem, evidências e vínculo ao registro completo.
  As classes de propostas, aprovações e exclusões continuam disponíveis quando
  existem registros; os contratos de governança permanecem intactos.
- IA e custos: previsão, faixa histórica e origem em destaque; zero tentativas
  registradas não vira zero tokens nem custo final. Pesquisa SERP e Perplexity
  têm natureza própria. Tentativas existentes conservam provedor, modelo,
  custos e moedas separadas para valores estimados e observados.
- Rede: conexões e cronologia antes dos painéis de cobertura; matriz por método
  com valores, disponibilidade, fonte e vínculo local. Instante de captura não
  vira latência. Sondas e saltos persistidos conservam tempos e métodos. A falta
  de fonte de ping é explícita; ICMP de traceroute não equivale a ping independente.
  O mapa continua sem pontos quando faltam coordenadas verificáveis.
- Demais páginas: apenas rótulos tipados e cabeçalhos comprovadamente técnicos
  foram humanizados. Categorias, disponibilidade de funcionalidades, integração,
  relação dos recursos com o site e qualidade da captura recebem texto legível.
  Seletores, IDs, mensagens, títulos e evidências livres preservam o texto da fonte.
- CSS: as duas regras de `main` usam teto de 1980px; responsividade e impressão
  conservam suas regras. A largura é máxima, não fixa.

Os recibos mantêm `state` por compatibilidade e acrescentam
`representation_level`, distinguindo síntese, projeção analítica, detalhe técnico
e processamento não executado. `certifies_editorial_completeness` continua falso.

## Verificação delimitada

`tests/report_presentation/test_final_presentation_review.py` cobre plano ausente
com dois achados, rótulos tipados, previsão com execução parcial e zero tentativas,
moedas distintas, captura passiva, sonda sintética persistida com checksum válido,
compatibilidade do recibo e largura CSS calculada no Chromium. A fixture de sonda
é escrita pelo teste; nenhuma sonda é executada.

Executar os testes de `tests/report_presentation` e o kit de aceitação existente
somente em cópia isolada da auditoria. Comparar a versão anterior com a nova,
preservando registros, anexos, inventário da origem, manifesto e idempotência.
Validar as onze páginas no Chromium offline em 1440/390 e em viewport amplo.
O catálogo serve de referência humana para a comparação funcional; seu HTML não
é consumido como fonte de geração. A geração sem o pacote do catálogo também
precisa funcionar.

Os caminhos, dados, screenshots, matriz por campo e ZIP da auditoria permanecem
no dossiê privado local. Registrar separadamente o resultado dos workflows no
SHA publicado e qualquer verificação não concluída. O aceite editorial e visual
humano permanece pendente. Esta revisão não autoriza merge.
