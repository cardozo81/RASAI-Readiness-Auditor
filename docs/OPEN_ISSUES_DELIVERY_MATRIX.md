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
