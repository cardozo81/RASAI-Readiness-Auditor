# Plano linear de pendências - RASAi (09/10/2026)

## Fonte de verdade e baseline

- Repositório: `cardozo81/RASAI-Readiness-Auditor`.
- Baseline validado: `main@85d8c97a90d18bab8882ddd2c94e3291e7fc1e3e`.
- PRs #312/#331/#332/#333/#335 integrados. CI do `main` 7/7 verde.
- Issue #334 fechada, com sete validações humanas OK: relatório refeito,
  integridade da AUD, colunas, responsividade, modais, alvos e impressão.
- Auditoria de referência:
  `AUD-3CDB4E407A6A40FDA5CAB5D82FA672A8`, dispositivo MOBILE, URL
  `https://loja.bradescoseguros.com.br/seguro-de-vida`.
- Épico #301 governa GEO. Issue #310 controla gates de release.
  Épico #324 governa observação de prontidão de conteúdo.
- Há um único implementador; **trabalhar apenas na branch**
  `feat/310-linear-residual-hardening-20261009` durante a estabilização.
  Não abrir N branches por issue. Não repetir funcionalidades já mescladas.

## Inventário completo das 17 issues abertas

| Ordem | Issue | Natureza | Situação e trabalho real | Ação |
| ---: | --- | --- | --- | --- |
| 0 | #301 | Épico GEO | Governar entregas #304/#306/#308/#309/#318/#310. | Reconciliar durante o ciclo; não codificar como tarefa independente. |
| 1 | #319 | Parcial, P2 | Histórico financeiro e cronologia pós-uso já existem. Previsão física *ex ante* por estágio é incompleta. | Implementar incrementalmente, sem inventar duração; iniciar agora. |
| 2 | #304 | Parcial, P1 | Taxas descritivas SERP x Perplexity, URL segura e contexto geotemporal persistidos. Falta comparabilidade comprovável de fontes e validação real. | Testes e ajustes determinísticos; abster de ranking, citações e equivalência não observados. |
| 3 | #306 | Parcial, P2 | IA GEO opt-in e integração canônica com falhas fakes. Falta aceite de operação real com proveniência/custo. | Fechar somente lacunas determinísticas; segregação do gate externo. |
| 4 | #308 | Parcial, P2 | Contexto por finding/CAT e referências estratégicas implementados. #334 cobre somente UX dirigida. | Matriz de cobertura CAT-01/03/05/08/09, index, directed e ai-integrations, com evidências. |
| 5 | #309 | Parcial, P1 | Replay e fluxo pós-AUD com sidecar e fakes implementados. | Regressão de historico/idempotência, integração read-only, sem coleta duplicada. |
| 6 | #322 | Parcial, P2 | Classificador 001/002 estrito concluído, sem Playwright same-sample. | Avaliar probe opt-in de baixo overhead e armazenamento separado; não alterar M23/M25. |
| 7 | #324 | Épico Apdex | Controla #322; não é segundo motor. | Registrar limites, testes, aprovação metodológica e fechamento condicionado. |
| 8 | #310 | Gate/release, P1 | Integração e CI verde, mas homologações residuais pendentes. | Fechar somente após reconciliar todas as dependências; registrar autorização externa não obtida. |
| 9 | #318 | Parcial + aceite comercial, P2 | UI opt-in e complemento preservando AUD selada, simulados. Falta chamada real autorizada, cobrança/idempotência operacional. | Validar UX offline; operação comercial somente mediante autorização específica. |
| 10 | #328 | Roadmap UX, P3 | #334 aprovado, restante GEO/CAT-06/07 adiado. | Após aceite de conteúdo: protótipo, correções pontuais, sem redesign geral automático. |
| 11 | #330 | Roadmap GEO, P3 | Extração real e comparação do HTML de concorrentes inexistente. | Desenho metodológico + autorização de crawling; não inferir página por snippet. |
| 12 | #311 | Roadmap GEO/CONS, P3 | Série GEO longitudinal não implementada. | Definir equivalência de query, domínio, região, data e evidência antes de código. |
| 13 | #210 | Arquitetura CONS, P3 | `same URL` homologado; modo `same domain` entre páginas distintas não. | Especificar comparação entre páginas sem fabricar série temporal única. |
| 14 | #1 | Arquitetura SaaS, P3 | Runner gerenciado, upload selado e relatório dinâmico ainda não implementados. | Apenas avaliação/ADR até autorização arquitetural. |
| 15 | #127 | P4 congelada | Política de reinício de etapa possui coberturas pontuais; refatoração global é de alto risco. | Não implementar sem defeito real reproduzível. |
| 16 | #192 | Bloqueada, Orqetia | Integração depende da paridade e do gate Integration Readiness externo. | Não iniciar migração nem mexer no orquestrador RASAi. |

A ordem acima especifica **o inventário completo**, mas distingue execução
imediata dos itens condicionados, congelados e de roadmap. Não converter
roadmap em compromisso de código sem critérios e autorização.

## Regra de execução linear

1. Em cada issue, conferir implementações e testes existentes em `main`.
   Corrigir somente lacunas comprovadas; registrar evidência na issue.
2. Implementar em **uma única branch e um PR draft**, sequencialmente.
   Nenhum agent/humano concorrente, sem forks ou merges parciais sem gate.
3. Usar testes pontuais da área alterada e CI do SHA final. Corrigir CI
   antes de avançar. Não rodar smoke amplo no meio do ciclo.
4. Preservar dados históricos, `audit.db`, snapshots, sidecars,
   manifestos, hashes, FK, proveniência e custos das chamadas anteriores.
5. Não alterar coletores homologados, scoring/SARI/SCORE-GEO, M23/M25,
   seleção de provider, contratos e motor canônico de orquestração IA.
6. Não executar Perplexity, IA ou qualquer chamada comercial de teste
   sem consentimento humano explícito sobre custo/queries/limites.
7. Instrumentação experimental #322 somente se houver prova de mesmo
   sample/context/page/device, relógio monotônico comum e overhead
   comprovado. Falha de observação é `N/D`, não zero ou sucesso.
8. Evitar execução longa sem checkpoints: salvar commits e comentários
   na issue a cada mudança estabilizada; para trocar de sessão, retomar
   pelo HEAD real da branch, não por texto histórico.
9. Atualizar estados de issues apenas diante do respectivo aceite.
   Aceite de HTML não é homologação Search API real.
10. Smoke humano único após estabilização técnica: usar a AUD preservada
    para read-only quando possível; exigir AUD nova só para prova de
    observação física nova. Não alterar a origem na rematerialização.

## Gate de integração

Quando o escopo técnico seguro estiver concluído: PR não-draft,
checagens exigidas todas `COMPLETED/SUCCESS` no **SHA exato da PR**,
diff de risco limitado, nenhuma regressão ou efeito financeiro oculto,
revisão de integridade. Solicitar smoke humano somente onde indispensável.
Integrar sem perder código, nunca declarar homologados #318 live ou
#322 física real com testes apenas fakes.

## Pendências de histórico real

O histórico `console_execution_projections` fornece duração física da
AUD local. IA M18/M20 tem tentativas com intervalos que podem se
sobrepor. #319 só pode prever intervalos a partir de coorte com parâmetros
registrados e comparáveis, pelo menos cinco observações: onde não houver
medição suficiente, apresentar `N/D`. Métricas separadas por coleta,
PSI, Apdex e geração de relatório dependem de relógios específicos
persistidos, não de resíduo aritmético.


## Checkpoint de implementação incremental - 09/10/2026 - PR #336

### Entregue com testes determinísticos

- **#319:** forecast físico ex ante read-only com coorte de >=5 AUDs
  completas, mesma configuração (incluindo modo de entrada e limite
  PSI `web_max_pages`), duração real total, união de tempos ativos de IA
  e faixas descritivas P25/P75/P90. Quando o histórico permite, soma de
  tempos de **requests HTTP** PageSpeed/CrUX por serviço é mostrada em
  seção distinta, com abstenção por ausência/invalidez. Isto não é
  duração física do estágio M21, nem parcela aditiva do relógio total.
- **#304:** snapshot GEO v4 imutável; dados v1/v2/v3 não são reescritos.
  Janela descritiva entre consultas exige horários com timezone e
  diferença <=24h. Multi-query, janela não comprovada, dados/denominadores
  ausentes geram taxas N/D. A correspondência da string não comprova
  intenção nem equivalência de país, idioma e dispositivo.
- **#306:** caminho de execução de IA GEO opt-in exige provedor canônico
  efetivo; uma factory injetada explicitamente em testes não é prova de
  elegibilidade do provedor em produção. Regressão com factory fake.
- **#308:** deduplicação no HTML CAT-09 da mesma recomendação/achado,
  somente leitura; preservação de ações e evidências distintas.
- **#309:** regressão de RPR/replay com data histórica sem timezone:
  preserva proveniência e idempotência, mas não atribui taxas GEO.
- **#322:** somente classificação experimental existente; nenhuma
  coleta same-sample via Playwright foi homologada neste recorte.

### Aceites residuais e fronteiras técnicas

O trabalho incremental foi testado nos workflows existentes do GitHub.
Cada commit novo demanda nova verificação no **HEAD exato**; um CI
bem-sucedido em um SHA anterior não libera alterações posteriores.
Os gaps físicos de #319 que dependem de nova instrumentação
(captura, extração, Apdex, relatório e duração real completa de M21)
permanecem N/D. A instalação de hook #322 nos motores de browser
homologados carece de prova de overhead/identidade amostral e decisão
específica; não é aceitável degradar Apdex em nome da observabilidade.
#318 ainda requer autorização independente para uso comercial real da
Perplexity. #310 e os épicos seguem abertos; #328/#330/#311/#210,
#1/#127/#192 permanecem conforme status acima.


## Consolidado de hardening seguro para smoke - 09/10/2026

- **#318:** validação fail-closed de manifesto, reserva e vínculo do
  suplemento à AUD selada; impede reuso com hash/fingerprint divergente,
  manifesto incompleto/corrompido, symlink e caminho não permitido.
  Cobertura fake de HTTP/timeout/reuse sem consumo real. Aceite comercial
  permanece PENDENTE e **não** é pré-requisito para o smoke read-only.
- **#304:** relatório GEO v4 exibe N/D para sobreposição quando não houver
  comparabilidade temporal válida; não converte ausência de métrica em
  zero interseção. Snapshots legados permanecem explicitamente históricos.
- **#322:** adapter opt-in `playwright_primary_content_probe_322.py`
  disponível para estudo com o mesmo objeto de página e cronômetro
  monotônico fornecidos por futuro gateway, apenas com testes fake;
  **sem hook instalado em M23/M25**, sem nova amostra nem índice.
- **#310:** roteiro de smoke humano mínimo em
  `docs/SMOKE_GATE_310_20261009.md`, sem repetir a AUD completa;
  não confundir CI da branch com aceite humano do pacote e do console.
