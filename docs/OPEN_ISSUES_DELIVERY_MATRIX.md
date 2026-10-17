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
