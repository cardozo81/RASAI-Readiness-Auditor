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

## Reconciliação incremental — 17/10/2026

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
| #604 | EPIC DEPENDENTE | Reconciliação de relatórios SARI/FAQ/SEO/claims | Aceites integrais de #600–#603 | Não |
| #639 | VALIDAÇÃO PENDENTE | Compatibilidade dos imports/paths históricos quando houver defeito demonstrado | Prova dos consumidores externos e main pós-merge | Não |
| #646 | DECISÃO METODOLÓGICA PENDENTE | Guardrails/ADR F3 e testes negativos adicionais | Matriz F3 de consumidores autorizada | Não |

**Categorias não exclusivas:** um item com bloqueio humano também pode conter tarefa técnica independente. Não transformar bloqueio de metodologia em autorização implícita para alterar scoring, coleta, IA, Apdex ou histórico. **Nenhuma destas 16 issues está comprovadamente pronta para fechamento.** Não há testes físicos nem chamadas a provedores externos novos neste ciclo.

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
