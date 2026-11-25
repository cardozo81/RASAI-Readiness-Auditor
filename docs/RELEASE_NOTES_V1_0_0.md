# RASAi 1.0.0 - notas de versão

Primeiro marco 1.x do RASAi - Readiness Assessment for Search & AI, autorizado pelo responsável do projeto em 25/11/2026. Consolida a evolução acumulada após v0.10.0. O incremento identifica a maturidade pretendida do produto; não constitui alegação de ruptura metodológica nem certificação universal de integrações externas.

A base funcional deste preparo é `47cedb9cb2656484a753ccb7605ec0e304309dec` (main, 343 commits à frente de v0.10.0 na comparação do GitHub). A [GitHub Release v1.0.0](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v1.0.0) foi publicada em 25/11/2026 08:18:29 (America/Sao_Paulo), com imutabilidade habilitada, tag anotada `24b0e2751204f303f8949641060e38adc3294d23` e commit `e55717b2a2c924cdc9f81e39565353d063f47892`.

## Principais evoluções desde v0.10.0

- **Apresentação executiva:** refinamentos de cobertura, paridade, linguagem, evidências e anexos, sínteses de busca e GEO, contexto arquitetural e temporal, projeções analíticas e visualização de rede; rematerialização offline a partir de evidências persistidas.
- **Rede:** evolução de diagnóstico de origem da conexão, sondagens sob política explícita, topologia lógica, IPv4/IPv6 e projeções de evidência de rede e mapa.
- **Console e execução:** ajustes de persistência de configurações e integrações, parametrização de busca, composição dos comandos externos e registro operacional.
- **Custos e integração de IA:** refinamentos da previsão e da reconciliação de custos, comunicação de limites e tratamento de estados de execução.
- **Operação e relatórios:** ajustes de publicação, reprocessamento, Apdex e rastreabilidade; preservação da distinção entre evidência observada, inferência e ausência de dados.

## Identidade e compatibilidade

- Pacote e CLI: 1.0.0. Índice público SARI-001; SCORE-GEO-005 vigente e SCORE-GEO-004 histórico.
- Python 3.13, plataformas e distribuição conforme README e documentação de instalação.
- O catálogo técnico permanece referência de evidências; a apresentação não executa coleta nem recalcula scoring. Uma auditoria parcial não se torna completa por rematerialização.
- Não se promete ranking, tráfego, conversões, citações generativas ou disponibilidade de serviços externos.
- O preparo altera apenas identidade do pacote e documentação de versão. Não modifica motores, coletores, contratos metodológicos, configuração privada ou AUDs históricas.

## Gate e distribuição

O procedimento abaixo registra os requisitos do ciclo de preparação concluído. Não constitui nova autorização de publicação. A distribuição efetiva contém os arquivos-fonte automáticos do GitHub, sem anexos adicionais.

Verificar a consistência do pacote/CLI, a regressão aplicável e o smoke de instalação/compatibilidade offline; conferir os checks do SHA integrado antes de publicar. Os recibos anteriores não equivalem a certificação do novo SHA. Não são autorizadas novas chamadas pagas, auditorias físicas ou distribuição por PyPI/registry Docker neste ciclo.

Distribuição prevista: arquivos-fonte automáticos do GitHub, sem anexos adicionais. A tag v1.0.0 deve identificar exclusivamente o commit aprovado; preservar tags e releases anteriores. Publicar com Immutable Releases habilitado, conforme VERSIONING.md.

[Comparação funcional desde v0.10.0](https://github.com/cardozo81/RASAI-Readiness-Auditor/compare/v0.10.0...47cedb9cb2656484a753ccb7605ec0e304309dec)
