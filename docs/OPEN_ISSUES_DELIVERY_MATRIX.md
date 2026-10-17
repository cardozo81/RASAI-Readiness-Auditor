# Matriz de pendências - issues abertas

**Data de triagem:** 17/10/2026. **Repositório:**
`cardozo81/RASAI-Readiness-Auditor`. **Intervalo:**
issues abertas com IDs de 301 a 646 (inclusive). Não foram incluídas
issues fechadas, nem PRs. **Branch única:** `feat/acceptance-and-architecture-governance`.
**HEAD inicial desta triagem:** `98c73e95f46fe68670ace6016979532e9a91404e`,
com **18/18 workflows SUCCESS** antes das novas alterações.

Esta matriz diferencia prova de contrato em CI, implementação funcional,
coleta física externa, homologação, decisão metodológica e roadmap.
`CI verde` ou `issue parcialmente implementada` não certifica
conclusão dos critérios de aceitação.

| Issue aberta | Situação / implementação já existente | Residual técnico ou impedimento | Por que não foi concluída |
| --- | --- | --- | --- |
| #301 - Épico GEO | Contratos observacionais, persistência e relatório GEO já implementados parcialmente | Concluir #304 e dependências de equivalência/cobertura das amostras | Busca SERP não equivale à presença em resposta gerativa; universo, região e denominadores não estão certificados |
| #304 - Métricas SERP × Perplexity | Overlap por URL/host seguro, abstenção para multi-query sem proveniência | Comparabilidade query/intent/mercado/tempo, denominadores e amostra externa admissível | Sem observações pareadas equivalentes, uma taxa agregada seria fictícia |
| #311 - GEO longitudinal CONS | Preview consultivo por snapshots e proteção de manifesto | Ligação nativa e método de tendências calibrado; aprovação específica | Não há prova de equivalência longitudinal; integração invasiva do CONS não autorizada |
| #319 - Tempo e custos por estágio | Ledger IA unificado, proteção de duplicidade e métricas read-only | Exibição completa por fase no console/preview/relatório e estimativa probabilística honesta | Duração observada de tarefas concorrentes não constitui wall-time aditivo; previsão ex ante não dispõe dos tokens futuros |
| #322 - Prontidão pós-load | Sidecar experimental selado e validações de integridade | Sensor real no **mesmo navegador/amostra** de navegação e autorização de instrumentação | Prova de tempo no mesmo sample e não regressão do Apdex não obtida; não modificar coletor homologado sem aceite |
| #330 - Conteúdo concorrente | Comparação apenas de HTML já capturado, com URL/HTTP/proveniência rígidos | Coleta opcional, autorizada e delimitada por URL concorrente; amostras heterogêneas | Robots, privacidade, custos e evidência de permissão; snippets não comprovam conteúdo completo |
| #355 - Dynatrace RUM | Validação fail-closed de ações Load/XHR/Custom, KPM, timeout, headers e thresholds | Snapshot real de tenant, ação, dispositivo e janela compatíveis; aceite de acesso | Ambiente Dynatrace/credenciais e consentimento externo não disponibilizados; não presumir equivalência a Synthetic |
| #357 - Épico Apdex arquitetura | Presets e orientação CAT-07 consultiva; contratos de arquitetura sem alterar índices | Aceites de #322 e #355 e comparabilidade por arquitetura | Uma classe SPA observada não autoriza trocar thresholds ou recalcular Apdex |
| #523 - Configuração/persistência | INI completo em processo novo, segurança de origem/rollback, Windows/User HKCU descartável, SERP/APDEX consumer tests | Vincular e testar cada variável pública com seu consumidor de efeito real; integrações externas isoladas | Round-trip de registro não é prova universal de operação; consentimento/segredos do operador não podem ser simulados |
| #600 - Segurança SARI | Cobertura, escopo ORIGIN/URL, gates e avisos de confiança em apresentação | Aceite decisório com dados reais, resolver dependências #601/#602 | Alto score contratual não certifica UX real; itens opcionais e FAQ ainda têm método pendente |
| #601 - FAQ SPA/interação | Estados de DOM/painel, recibos offline e proteção SQLite sem escrita | Teste físico **opt-in** de clique FAQ seguro e revisão da semântica de scoring | Falta de resposta sem clicar não prova inexistência editorial; interação não está autorizada indiscriminadamente |
| #602 - SEO opcional | Abstenção em erros para robots/canonical/sitemap | ADR com versão SCORE-GEO, golden antes/depois e aprovação de pesos | Ausência isolada desses sinais não prova prejuízo real; alteração muda histórico de comparação |
| #603 - Alegações reguladas | Tipos de claims e recibos assinados/versões/datas parcialmente implementados | Fonte oficial versionada e validação de escopo/produto, integração completa no relatório | Sem documento primário vigente e revisão competente não é correto afirmar verdade ou não conformidade legal |
| #604 - Épico confiança | Linguagem de SARI/FAQ/SEO/claims e correções filhas já implementadas parcialmente | Aceites integrados de #600/#601/#602/#603 | Gate semântico depende de evidências heterogêneas e decisão normativa, não apenas teste estático |
| #639 - Nomes versionados | 1.509 arquivos varridos via Git Trees API com zero padrões numéricos legados; gate incremental existente | Novo gate total da árvore + conferir compatibilidade e `main` após merge | Zero tokens numéricos não comprova nomes opacos ou consumidores externos não versionados |
| #646 - Governança arquitetural | F1/F2 e matriz read-only de proveniência, registro selado e relatório consultivo | ADR de F3 + autorização da matriz de consumidores e golden/performance | AUTO/DECLARED não pode alterar índice, coletor, Apdex ou IA por autoautorização |

## Reconciliação incremental - 17/10/2026

**HEAD validado:** `02d7cc92df267380b9fa98444e32f7ebc5faf270`; GitHub Actions **19/19 SUCCESS**, incluindo `Console configuration controls targeted`, `Windows Console Navigation`, `Audit Fulfillment and Reprocessing` e `Public Contract Consistency`. A PR #647 permanece **DRAFT/OPEN**, sem merge. Esta comprovação cobre exclusivamente o código presente no HEAD; não é aceite funcional integral das issues.

**Implementação adicional comprovada neste ciclo:** #523 ganhou testes parametrizados de restauração de INI e consumo por `ImprovementConfig.from_environment` (enabled, máximo de recomendações, timeout, idioma) e `configured_presentation_timezone` (três fusos). A suíte de configuração passou no CI. O catálogo completo de consumidores ainda não foi exaurido; não concluir #523 por esses ensaios.

### Matriz de decisão e entregas residuais

| Issue | Classificação ativa | Residual de código independente | Evidência/decisão humana faltante | Pode fechar? |
| --- | --- | --- | --- | --- |
| #301 | EPIC DEPENDENTE | Conciliar critérios de #304 com apresentação GEO | Coorte SERP e Search API comparável | Não |
| #304 | IMPLEMENTAÇÃO/EVIDÊNCIA PENDENTE | Testar proveniência e abstenção em agregações restantes | Query, intenção, mercado, janela e denominadores pareados reais | Não |
| #311 | ROADMAP NÃO AUTORIZADO | Apenas contrato read-only permitido; não integrar CONS operacional | Aprovação de metodologia longitudinal e escopo P3 | Não |
| #319 | IMPLEMENTAÇÃO PENDENTE | Projeção por fase em console/prévia/relatório, com campos não medidos explícitos | Avaliação de UX com AUD real depois do código | Não |
| #322 | EVIDÊNCIA/VALIDAÇÃO PENDENTE | Fixture e isolamento opt-in podem ser ampliados sem coletor principal | Mesmo snapshot/navegador e segurança de medição física | Não |
| #330 | ROADMAP NÃO AUTORIZADO | Apenas evidências já capturadas; não ativar coleta concorrente | Permissão de escopo, privacidade e protocolo de amostras | Não |
| #355 | ACESSO EXTERNO PENDENTE | Negativos offline e matriz de equivalência são possíveis | Tenant Dynatrace e ações RUM reais da mesma janela | Não |
| #357 | EPIC DEPENDENTE | Contratos consultivos e integração documental | Aceites de #322/#355 e perfil por arquitetura aprovado | Não |
| #523 | IMPLEMENTAÇÃO PENDENTE | Catalogar e provar efeito dos demais adaptadores registrados; parte Improvement/fuso validada no HEAD | Integrações pagas/credenciais somente onde indispensáveis | Não |
| #600 | IMPLEMENTAÇÃO/VALIDAÇÃO PENDENTE | Provar consistência transversal de confiança e avisos | Coorte de auditorias reais e dependência #601/#602 | Não |
| #601 | EVIDÊNCIA/MÉTODO PENDENTE | Fixture offline de clique FAQ sem tráfego externo | Smoke same-snapshot e política de penalização aprovada | Não |
| #602 | DECISÃO METODOLÓGICA PENDENTE | ADR e golden diferencial sem ativar pesos | Aprovação de SCORE-GEO e comparabilidade histórica | Não |
| #603 | EVIDÊNCIA REGULATÓRIA PENDENTE | Schema e estado de abstenção/proveniência podem ser reforçados | Documento oficial vigente e revisão especializada | Não |
| #604 | EPIC DEPENDENTE | Reconciliação de relatórios SARI/FAQ/SEO/claims | Aceites integrais de #600-#603 | Não |
| #639 | VALIDAÇÃO PENDENTE | Compatibilidade dos imports/paths históricos quando houver defeito demonstrado | Prova dos consumidores externos e main pós-merge | Não |
| #646 | DECISÃO METODOLÓGICA PENDENTE | Guardrails/ADR F3 e testes negativos adicionais | Matriz F3 de consumidores autorizada | Não |

**Categorias não exclusivas:** um item com bloqueio humano também pode conter tarefa técnica independente. Não transformar bloqueio de metodologia em autorização implícita para alterar scoring, coleta, IA, Apdex ou histórico. **Nenhuma destas 16 issues está comprovadamente pronta para fechamento.** Não há testes físicos nem chamadas a provedores externos novos neste ciclo.

## Autorização adicional - 17/10/2026

O operador autorizou o avanço dos roadmaps (#311/#330) e da frente
metodológica (#602/#646). Isso retira a classificação de **ausência de
autorização de planejamento/implementação segura**, mas **não fornece**
parâmetros normativos para recalibração de score, nem concede credenciais,
consentimento de terceiros ou datasets físicos. A política concretamente
aplicável e os gates estão registrados em
[ARCHITECTURE_AND_SCORING_DECISION.md](ARCHITECTURE_AND_SCORING_DECISION.md).
Não reclassificar essas issues como completas. A versão do contrato
consultivo continua fail-closed.

### Prova técnica incrementada

- #523: teste parametrizado de restore INI para os consumidores reais de
  ativação e timeout de `passive_security`, sem feed remoto; além dos
  cenários anteriores de Improvement Intelligence, timezone, SERP, GSC e Apdex.
- #311/#330: autorização de roadmap recebida; implementação operacional
  e coleta externa continuam por provar; estes itens deixam de ser
  simplesmente "roadmap não autorizado".
- #602/#646: autorização metodológica genérica recebida; **não** equivale
  a valores de ponderação, thresholds, matriz de consumidores F3 aprovada
  individualmente ou evidência de comparabilidade.
- Demais issues: matriz anterior permanece válida, até prova adicional.

## Regras de execução

- Uma única branch e PR; sem merge enquanto critérios de escopos distintos estiverem pendentes.
- Executar apenas suites relacionadas, em GitHub Actions com runners existentes;
  zero chamadas pagas ou novas consultas a provedores externos não autorizadas.
- Não fabricar confiança, conformidade, comparação de mercado, fonte oficial,
  dados de navegador ou observação RUM ausentes.
- O conjunto de consumidores arquiteturais descritivos é fixo; chamadores
  só podem **restringir** permissões. Propagação operacional exige ADR aprovado.
- Após cada implementação validada, atualizar o status das issues pertinentes
  distinguindo evidência CI, teste físico, pendência metodológica e impedimento.

## Resumo de bloqueios

As issues #311/#330 são **roadmap explícito**, não defeitos a serem
forçados nos coletores atuais; #322/#355 dependem de mensuração física
ou fonte Dynatrace real; #602/#646 dependem de ADR normativa; #603
depende de documento externo com prova de versão e escopo; #304/#301
exigem comparabilidade observacional; #639 depende de compatibilidade
externa e gate pós-merge; #523 depende de prova individual dos
consumidores. A implementação conservadora já existente será mantida
enquanto não houver o aceite competente.

**Sem inferência de fechamento:** todas as 16 issues identificadas
permanecem abertas nesta triagem. Este registro não concede aceite
humano nem altera dados históricos.


## Reconciliacao tecnica complementar

No ciclo corrente a PR #647 incorporou reforcos offline em quatro issues,
sem alterar AUD, scoring ou integracoes comerciais:

- #319: integridade fisica do audit.db durante leitura de telemetria;
  SHA 3f2c19f, 22/22 checks aprovados.
- #523: inventario de entradas de seguranca passiva e Improvement,
  alem de teste real de configuracao restaurada nos loaders de modelo,
  pricing e perfis de IA; SHAs 9d84eeb e 0e04703, 22/22 cada.
- #330: digest de origem concorrente com protecao contra alteracao
  de mesmo tamanho; correcoes nos SHAs 1368596 e 4db42c5.
- #603: recibo documental com rejeicao de escopo de produto em branco
  ou com espacos perifericos; SHA 7f4933d.

Essas entregas nao satisfazem sozinhas os aceites integrais. #319
ainda requer apresentacao completa e prova de estimativas; #523
requer cobertura de todos os consumidores; #330 depende de coortes e
consentimento para dados reais; #603 requer fonte primaria vigente
e revisao independente. Nenhuma issue foi encerrada neste ciclo.


### Verificacoes de persistencia e FAQ - 17/10/2026

- #523: o carregamento de INI tambem recusa JSON Dynatrace contendo
  campos de credenciais aninhados, tanto em ambiente quanto em estado
  tipado; fixture de arquivo adulterado comprova recusa e preservacao
  dos bytes de origem. Implementacao na PR #647.
- #601: a validacao de recibos de interacao FAQ exige identificadores
  nao vazios de coletor e recibo, sem aceitar apenas espacos em uma
  allowlist equivocada; caso negativo offline, sem navegador/rede.
- Nenhuma das duas protecoes certifica coleta real, mesmo snapshot ou
  cobertura integral. Issues permanecem abertas ate aceite correspondente.


### Piloto fisico FAQ e inventario de catalogos de IA

- #601: novo piloto isolado `faq_existing_page_pilot` exercita botao
  FAQ no mesmo objeto Playwright com opt-in e bloqueio temporario
  de novos HTTPs. Teste em Chrome offline usa pagina fixture;
  nao atesta a mesma amostra da experiencia sintetica, descoberta por crawler, fonte externa nem pontuacao.
- #523: inventario de configuracao agora declara seletor e arquivo
  dos catalogos de modelos, precificacao e perfis de tarefas de IA.
  Metadados continuam `NOT_PROVEN_BY_REGISTRY`, e nao inferem
  chamadas comerciais nem cobranca.
- Todos os criterios dependentes de observacao real ou de fontes
  externas permanecem abertos. A aprovacao da metodologia nao
  autoriza alteracao silenciosa de indices canonicos.


### Read-only sensitivity replay integrity (current batch)

- #602: `optional_seo_audit_replay._read_hash` verifies the physical
  source descriptor, inode identity, size and last-modified timestamp
  before/after SHA-256 of `audit.db`. A same-byte-count mutation during
  reading fails closed; a targeted offline regression ensures it.
  The check remains read-only and does not alter SCORE-GEO-004,
  published SARI, historical scores, or optional-signal weights.
- `report-catalog-targeted.yml` now includes the negative regression
  and activates when the replay reader changes.
- This is partial proof; a new versioned normative score contract,
  accepted weighting table and real comparative evidence are not
  inferred from general roadmap approval. #602 stays open.


### GEO source attribution hardening

- #304: the independent per-result query metadata parser rejects padded
  query values and control characters, rather than silently assigning
  physical results to an ambiguous market/query cohort. An offline
  adversarial test covers LF, TAB, NUL and surrounding whitespace, with
  one accepted positive example. No change to scoring, stored AUD data
  or provider calls.
- #301 remains dependent on physically comparable SERP/Perplexity
  observations. A successful parser test cannot establish external
  market, freshness, language or search intent equivalence.


### Censura explicita de cobertura economica por estagio

- #319: o relatorio metodologico agora apresenta valores monetarios da
  telemetria de IA com denominadores de tentativas. Montantes observados
  pelo provedor e estimativas posteriores ao uso sao expostos
  separadamente com contagem e denominador; zero observado e permitido.
  Ausencia de informacao ou contagem impossivel devolve N/D em vez
  de apresentar somatoria parcial como cobertura integral.
- A suite `tests/test_audit_cost_explain.py` cobre soma parcial,
  zero observado, ausencia e censo impossivel. Nenhuma fatura e inferida
  nem o forecast original e sobrescrito.
- Permanecem pendentes paridade de duracoes ativas em AUD real,
  forecast de fase com cronometro comparavel e aceite completo da
  interface console/previsao/HTML.


### Proveniencia do CONS consultivo no HTML longitudinal

- #311: o HTML independente apresentado pelo companion CONS-3 agora
  explicita o ID do consolidado e o fingerprint do manifesto a partir
  do bloco `cons_reference`, sem ocultar o limite de atestado.
  A regressao comprava que report.html e manifest.json existentes
  permanecem intactos e os campos de referencia aparecem na pagina.
- A exposicao e apenas do inventario de AUDs listado pelo CONS,
  nao constitui verificacao independente da assinatura de origem,
  calibracao longitudinal ou publicacao nativa no CONS.


### Leitura executiva e mapeamento de timezone no registry

- #600: os cards SARI mantem todos os numeros e enums brutos, mas
  explicam em portugues Cobertura, Confianca contratual, Consolidacao
  e Gates criticos. E somente melhoria de interpretabilidade e
  nao altera score, pesos, evidencia ou HTMLs de outros catalogos.
- #523: o registro de configuracao identifica o consumidor declarado
  da zona IANA de apresentacao; o mapeamento nao reivindica alteracao
  de timestamps historicos nem execucao real do consumidor.
- #639: a varredura da arvore Git integral no SHA b7d1021
  verificou 1513 blobs, resposta Git nao truncada e zero nomes em
  violacao dos tres padroes versionados em
  `tests/test_repository_filename_policy.py`. Ainda faltam
  contratos externos e verificacao de main apos merge autorizado.
- Gates de aceite de #600, #523 e #639 permanecem abertos ate
  evidencia fisica/externa correspondente. O CI valida os contratos
  automatizados; ele nao substitui o aceite do operador.


### Validação monetária adicional do relatório de IA

- #319: a projeção HTML por etapa agora recusa montantes monetários
  inválidos (NaN, Infinity, negativo, bool, string ou ausência) mesmo
  quando o denominador de tentativas aparenta estar completo. O
  resultado é N/D explícito em vez de renderizar valores financeiros
  incorretos. Tipos booleanos em contagens também não são aceitos.
- Regressão dirigida em `tests/test_audit_cost_explain.py`,
  preservando zero monetário legítimo e as frações de cobertura.
- Não muda contabilização, preço dos fornecedores ou estimativas.
  Persistem as provas físicas e de cobertura total previstas na #319.


### Guardas adversariais de contadores de IA e snapshots de arquitetura

- #319: `ai_economic_telemetry.canonical_total_tokens` recusa
  contagens negativas, fracionarias, booleanas ou nao-finitas,
  sem truncar para inteiro nem transformar negativos em zero.
  Zero fisico e representacoes decimais inteiras sao mantidos.
  Regressoes offline cobrem totals, input e output.
- #646: `architecture_context.resolve_architecture` agora ignora
  linhas de evidencia com tipo estranho junto a snapshots validos.
  Linhas malformadas isoladas levam a abstencao, nunca crash
  nem promocao de contexto alheio ao audit/page/device/snapshot.
  A matriz de elegibilidade continua estritamente consultiva.
- Nenhum desses guards autoriza alteracao de scoring, KPM, Apdex,
  formula longitudinal ou aplicacao de arquitetura descoberta
  retroativamente a um coletor.


### Protecoes de integridade da telemetria economica

- #319: contadores de tokens agora aceitam somente inteiros exatos
  nao-negativos ou strings decimais ASCII limitadas a dezoito digitos.
  Dados fracionarios, negativos, flags, infinitos e inteiros textuais
  gigantes resultam em N/D, em vez de truncamento, coerção ou falha.
- #319: denominacoes monetarias de custos persistidos devem ser
  rotulos alfabeticos ASCII de tres letras; valores malformados nao
  integram o somatorio. Nao sao introduzidas taxas de cambio.
- #646: entradas de origem de arquitetura com tipos inesperados sao
  ignoradas pelo contrato consultivo puro; sem uma observacao valida,
  o contexto falha fechado, sem alterar parametros de coleta e scores.
- Fixtures adversariais estao em `tests/test_ai_economic_telemetry.py`
  e `tests/test_architecture_context_policy_matrix.py`. Os gates de
  aceite operacional dos dois tickets permanecem abertos.


### Escopo de deducao de total de tokens

- #319: quando `total_tokens` nao esta disponivel, o total so pode
  ser derivado de `input_tokens + output_tokens` se todos os campos
  explicitamente presentes forem validos. Valor negativo, fracionario,
  ou texto decimal acima do limite provoca abstencao; nao se reinterpreta
  a metade valida como total do provedor.
- O caminho preferencial `total_tokens` explicito e validado continua
  prioritario, sem dupla contagem de tokens de raciocinio.
- O contrato permanece sem alteracao de faturamento, scores ou AUD
  historica; CI do novo HEAD exige nova verificacao integral.


### Integridade de consumidores de IA e projeção dinâmica da configuração

- #319: o total de tokens informado explicitamente pelo provedor
  agora prevalece se válido. Quando presente e corrompido, a execução
  abstém; não usa silenciosamente a soma de campos secundários.
  Casos negativos adicionais distinguem total ausente de inválido.
- #523: a projeção viva de estado do console para variáveis de
  ambiente valida JSON Dynatrace antes de aplicar qualquer variável.
  Campos de credenciais aninhados são rejeitados antes de mutação do
  ambiente, em paridade com o save/load de INI. Prova negativa e
  positiva em `tests/test_console_persistence_matrix.py`.
- A aprovação do CI e o aceite operacional ainda dependem da validação
  completa do HEAD; nenhuma API de provedor foi acionada nesses ensaios.


### Rejeicao tipada de valores arquiteturais malformados

- #646: o resolvedor puramente consultivo retorna UNKNOWN/N/D
  quando uma observacao tipada contem classe invalida ou nao-hashable
  (lista, dicionario etc.). Modos e declaracoes do operador com
  tipos inadequados geram erro de contrato controlado em vez de
  `TypeError` nao tratado. Testes dirigidos cobrem cada entrada.
- Nao ha elevacao de evidencias a score, nova AUD, alteracao de Apdex
  ou habilitacao de consumidores F3 sem matriz normativa.
