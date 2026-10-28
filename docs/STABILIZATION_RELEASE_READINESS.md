# Estabilização CONS/RPR/relatórios - matriz inicial de evidências

> Registro incremental da branch única. Não equivale a aceite de release.

- Baseline: `main@06dd1bfaafc981eb238e893ec1b37007c1948b27` (27/10/2026).
- Release publicada: `v0.8.0`; candidato `v0.9.0` ainda não decidido.
- Branch: `stabilization/cons-rpr-reports-release-readiness`; PR Draft obrigatória.
- Issue documental incremental: #674. #650 exclusivamente pós-v1.0.0.
- Restrições: offline/mocks, sem APIs pagas, sem sondagem externa, sem merge/tag/publicação sem aceite humano.

| Macrolote | Contrato ou evidência inicial | Estado atual | Próximo gate verificável |
| --- | --- | --- | --- |
| CONS-5 | `docs/CONSOLIDATED_REPORTING_VALIDATION.md`, `consolidated-reporting-ci.yml` | Implementado; homologação aprofundada pendente | Auditar fixtures, testes de proveniência/imutabilidade, políticas e comparabilidade |
| RPR | `docs/AUDIT_REPROCESSING.md`, `audit-reprocessing-ci.yml` | Implementado; homologação aprofundada pendente | Idempotência, recuperação seletiva, accounting incremental, SHA das AUDs |
| HTML | `report-catalog-visual-smoke.yml` | Análise transversal pendente | Smoke sintético + comparação com dados persistidos autorizados |
| IA/pricing | `ai-native-usage-pricing-targeted.yml`; AUD-01D61DBA30DD45D19F99401AB927580D | Desvio +320,69% reportado; causa não demonstrada | Reconciliação de escopo, retries, usage nativo e precificação sem API externa |
| Documentação | `docs/AUDIT_REPROCESSING.md` | Divergência v0.5.0 comprovada; correção iniciada | Revisão documental afetada + links + versão canônica |
| Release | `pyproject.toml` e `src/rasai/__init__.py` = 0.8.0 | Versão candidata ainda não aprovada | SemVer, changelog, gates Windows/Linux e decisão GO/NO-GO |

## Limites das evidências

- Nenhum cenário da matriz acima deve ser considerado reexecutado sem o SHA do workflow e resultado correspondente.
- Workflows por `paths` podem não disparar apenas por mudar este documento; gates ausentes exigem execução explícita segura ou status pendente.
- A execução física de IA da #668 e o aceite de rede #666 são referências históricas, não testes rodados neste ciclo.
- Não misturar confiança quantitativa da IA com cobertura de controles estruturais.

## Fronteiras protegidas

#127, #192, #311, #649, #650, #656 e #657 permanecem fora do escopo de implementação ou condicionadas aos seus próprios gates.

## Reconciliação econômica de IA - evidência sintética

- Teste: `tests/test_audit_cost_explain.py::test_large_point_deviation_is_not_a_calculation_defect_by_itself`.
- Contrato: não confundir diferença da estimativa pontual com precisão do intervalo, falha de cálculo ou fatura real.
- Cenários: desvio +320,69% integralmente coberto; chamada opcional não comparável; cobertura monetária incompleta.
- Evidência real da AUD-01D61DBA30DD45D19F99401AB927580D: comparação causal ainda pendente de inspeção de forecast/ledgers persistidos, sem nova API paga.
- Aceite: workflow econômico verde no SHA exato; cenário sintético não substitui exame financeiro real.

## Gate visual offline dos relatórios CAT/GEO

O workflow `report-catalog-visual-smoke.yml` executa, no mesmo gate, regressões de seções CAT-06/CAT-07, confiança de IA em percentual fracionário e rótulos/proveniência de KPMs Dynatrace, além de screenshots sintéticos de desktop, mobile e impressão. Os gatilhos passam a incluir esses testes e as camadas canônicas de apresentação afetadas. Este smoke usa fixture sintética; não atesta pertinência semântica de todos os relatórios reais nem a calibração estatística da confiança declarada pela IA. Artefatos visuais permanecem sujeitos à revisão humana.

## Evidências de CI da candidata (28/10/2026)

Commit de referência: `9ea28c20ae5a0da5154184f154fd273babf449d5`. A matriz abaixo documenta somente resultados efetivamente consultados no GitHub Actions; seu estado pertence ao SHA indicado, não automaticamente a commits posteriores.

| Gate | Execução | Evidência consultada | Interpretação |
| --- | --- | --- | --- |
| Relatórios CAT/GEO: smoke visual offline | [40645430058](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430058) | Job `synthetic-visual-report` concluído com sucesso; artefato `rasai-catalog-report-smoke`, ID `12797755212`, 22.346.624 bytes | Regressão sintética e geração de imagens aprovadas; inspeção visual humana pendente |
| Telemetria econômica | [40645430025](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430025) | SUCCESS | Comparação e apresentação econômicas cobertas pelos testes do workflow; discrepância da AUD física não reconciliada |
| Contrato público | [40645430105](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430105) | SUCCESS | Contrato público automatizado aprovado |
| RPR: contadores direcionados | [40645430029](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430029) | SUCCESS | Cobertura isolada dos contadores; não substitui RPR integral |
| CONS-5: pipeline completo | [40645430031](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430031) | Em execução na consulta | Sem aceite conclusivo nesta observação |
| RPR: pipeline completo | [40645430027](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430027) | Em execução na consulta | Sem aceite conclusivo nesta observação |

### Critérios de inspeção humana dos screenshots

Ao revisar o artefato publicado, conferir correspondência de cada seção ao relatório (CAT-06, CAT-07 e GEO), integridade de textos em pt-BR, leitura e hierarquia em mobile/desktop/impressão, duplicidades e coerência dos blocos, apresentação percentual de confiança **somente quando o dado permitir conversão válida**, proveniência e códigos das métricas Dynatrace, separação entre gravidade da regra e confiança declarada pela IA, e ausência de extrapolação causal. Divergências devem ser reproduzidas em fixtures ou relatórios de AUD com evidência rastreável antes de alterar os motores.

**Limite de aceite:** não considerar o pacote de 22 MB revisado apenas porque foi publicado. Para a release, ficam pendentes inspeção dos artefatos, análise comparativa de uma AUD real e aprovação humana explícita; não há GO automático por CI verde.

## Plano de encerramento dos itens parciais sem intervenção humana

Este quadro determina o executor e a evidência mínima sem antecipar aceite humano nem iniciar novos motores. Referência automatizada de 28/10/2026: SHA `6f5a1c567f71663b0926ab2d2445ae2afd4d60af`. Nesse SHA, CONS-5 e smoke visual estavam verdes; workflow integral RPR seguia executando o job Windows após sucesso do job Linux.

| Pendência parcial | Pode ser realizada sem humano? | Ação e condição de encerramento |
| --- | --- | --- |
| CONS-5: regressão de integridade, seleção e IA simulada | Sim | CI CONS verde no SHA; encerramento apenas **do gate sintético**, não da homologação de AUD real |
| RPR: regressão Linux/Windows completa | Sim | Aguardar conclusão do mesmo workflow no SHA, analisar logs e corrigir falhas comprovadas |
| Contadores RPR e ausência de chamadas tarifadas | Sim | Testes determinísticos, ledger por `reprocess_id`; nunca declarar precisão financeira do provedor a partir desses contadores |
| Relatórios CAT/GEO: smoke visual | Sim | CI gera screenshots e HTML sintéticos; revisão de presença, erros técnicos e conteúdo verificável por fixtures |
| Relatórios CAT/GEO: julgamento final de UX/CX e pertinência em AUD real | Parcialmente | Agente faz pré-revisão; aceite visual humano permanece pendente quando exigido |
| Desvio financeiro da AUD física #668 | Condicional | Reconciliar forecast e tentativas/tokens usando arquivos persistidos acessíveis. Na ausência do ledger real, não substituir por fixture nem atribuir causa |
| Documentação incremental | Sim | Conferir links, contratos, nomes/versão e consistência com HEAD; preservar história de versões |
| Publicação de v0.9.0, merge e exclusão da branch | Não | Exigem autorização humana explícita, CI final verde e verificações pré-release |

### Critérios anti-falso-positivo

- Cada resultado verde pertence a um SHA e a um workflow; testes não disparados ou ainda em andamento permanecem pendentes.
- Artefato visual gerado não é revisão visual concluída.
- Um desvio econômico sintético não substitui inspeção dos dados persistidos da AUD real.
- Não criar novo `AUD-*`, não reexecutar IA paga e não modificar `main` neste ciclo.
- O encerramento técnico automatizado nunca concede, por si só, autorização de merge ou release.

## Revisão do artefato visual publicado - evidência do agente

Origem: [workflow 40645919644](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645919644), SHA `062765052cf89001831c5531ce7522b3b4b5667e`, artefato `rasai-catalog-report-smoke` (ID `12797263282`). O ZIP foi aberto em leitura, sem alteração da fixture.

- Inventário verificado: 92 entradas no ZIP; HTMLs das dez páginas `cat-01.html` a `cat-10.html`, `geo.html`, `network.html`, `sari.html`, `metrics.html`, `ai-integrations.html`, `directed-analysis.html` e demais páginas de suporte.
- Imagens presentes para desktop, mobile e tablet, além de três PDFs de impressão (`cat-07`, índice e análise direcionada).
- Inspeção por folha de contato das 20 capturas desktop: navegação lateral, título contextual e blocos em cartões/tabelas aparentam seguir uma família visual consistente. **Essa inspeção reduzida não certifica legibilidade de cada texto em resolução nativa nem a ausência de overflow no mobile/impressão.**
- Hierarquia textual inspecionada no HTML: cada CAT apresenta título próprio, resumo, escopo solicitado, configuração efetiva e execução; GEO, rede, métricas e SARI têm títulos e seções temáticas diferenciados.
- A fixture de `network.html` contém seção `Mapa e caminho de rede` e indica dados indisponíveis. **Não é evidência de rota geográfica completa**; a ausência de dados na fixture não constitui defeito demonstrado do motor.
- As capturas exibem uma fixture sintética, portanto não demonstram cobertura de findings, recomendações ou níveis de confiança de uma AUD física. Não marcar validação semântica real como concluída.
- Versão atual verificada em `pyproject.toml` e `src/rasai/__init__.py`: `0.8.0`. A versão candidata `0.9.0` ainda não foi aplicada; não alterar versão antes de decisão de release.

### Estado técnico verificado no GitHub Actions

No SHA `062765052cf89001831c5531ce7522b3b4b5667e`, todos os **12 workflows** estavam `completed/success`, incluindo `Audit Fulfillment and Reprocessing` Windows/Linux, `Consolidated reporting safety`, `AI Economic Telemetry 195 Targeted` e `Report catalog offline visual smoke`. Esse é o baseline de CI integral verde **antes** deste registro documental.

### Itens restantes para GO

1. Conferir os HTMLs e screenshots na resolução original e confrontá-los com AUD física representativa, incluindo completude das recomendações e proveniência das avaliações de IA.
2. Reconciliar o custo da AUD #668 com forecast e tentativas persistidas, caso o pacote da auditoria esteja disponível; não inferir causa apenas do desvio numérico.
3. Fechar revisão do changelog/versão e obter decisão humana sobre aceite visual e publicação. Nenhuma dessas pendências implica autorização automática para merge.

## Inspeção visual ampliada - resolução original e impressão (28/10/2026)

Fonte inalterada: ZIP do artefato `rasai-catalog-report-smoke` (ID `12797263282`), do workflow [40645919644](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645919644), fixture `TEST_SYNTHETIC`. Este registro é uma inspeção de evidência, não uma autorização de release.

**Abrangência observada:**
- 20 capturas desktop (1440 px), 20 tablet (820 px), 21 mobile (390 px, incluindo menu aberto). Revisão visual de painéis comparativos e capturas em tamanho de origem para CAT-01, CAT-06, CAT-07, GEO, rede, SARI, IA, análise direcionada e métricas, além do índice.
- HTMLs do catálogo: 20 arquivos examinados quanto à estrutura. Cada página possui um único `h1`; CAT-01 a CAT-10 possuem blocos temáticos e tabelas de resultados; páginas auxiliares mantêm assuntos específicos.
- PDF de impressão: `cat-07.pdf` (6 páginas), `index.pdf` (10 páginas) e `directed-analysis.pdf` (2 páginas), com extração de texto página a página. Nenhuma página sem texto foi identificada.
- Na captura mobile, cabeçalho com botão Menu e cartões em coluna; na desktop, navegação lateral e área principal. Nenhum corte generalizado de cartões foi demonstrado na amostra examinada.
- **Observação de paginação**: a primeira página de impressão do CAT-07 contém apenas 374 caracteres extraíveis e grande área vazia após o cabeçalho; as páginas seguintes concentram conteúdo (até 2.227 caracteres). Possível quebra de impressão subótima; exige comparação com contrato de impressão e reprodução direcionada antes de classificar como defeito funcional.
- `smoke-summary.json` declara `manifest_integrity=VERIFIED`, `source_files_unchanged=true`, `source_audit_writes=0`, `collector_or_provider_requests=0`, `manual_visual_acceptance=PENDING`, `data_row_parity=BASELINE_NOT_PROVIDED` e `all_visible_content_parity=BASELINE_NOT_PROVIDED`. Não inferir paridade com uma AUD real.

**Conclusão da inspeção automatizada ampliada:** PASS com ressalva de impressão. Não se observou um defeito visual sistêmico comprovado na fixture; revisão de semântica/proveniência real e aceite humano permanecem fora desse PASS. Não modificar CSS nem motores sem reproduzir a quebra de impressão e avaliar seu efeito.


## Fechamento da baseline CI e matriz pré-release - 28/10/2026

**HEAD conferido:** `55e7a956e8a9879aa3dd3c71042ca1be897f9e67` (PR #675 Draft). A consulta aos GitHub Actions vinculados ao commit retornou **12 workflows concluídos com sucesso**; nenhum dos doze estava em andamento ou falhou. Esta constatação substitui, para o SHA indicado, os estados provisórios registrados acima para SHAs anteriores.

| Workflow | Run | Estado no HEAD |
| --- | --- | --- |
| Consolidated reporting safety | [40678468323](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468323) | PASS |
| Audit Fulfillment and Reprocessing | [40678468402](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468402) | PASS |
| RPR contadores e fechamento - testes isolados | [40678468307](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468307) | PASS |
| AI Economic Telemetry 195 Targeted | [40678468464](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468464) | PASS |
| Report catalog offline visual smoke | [40678468330](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468330) | PASS |
| Public Contract Consistency | [40678468291](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468291) | PASS |
| Secret and Configuration Safety | [40678468232](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468232) | PASS |
| Interrupted stage restart 127 (targeted) | [40678468189](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468189) | PASS |
| SCORE-GEO-005 validation | [40678468397](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468397) | PASS |
| GEO focused hardening 308-309-306-304 | [40678468373](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468373) | PASS |
| Console generative vs Search usage 319 | [40678468381](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468381) | PASS |
| Public UX language 377 isolated | [40678468288](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40678468288) | PASS |

**Alcance:** baseline automatizada aprovada para os workflows efetivamente listados no SHA consultado; sem inferir que todo workflow existente no repositório foi disparado, nem promover o aceite de auditorias reais. Um novo commit documental exige nova verificação de CI no novo HEAD antes de GO.

### Matriz de aceite separada por tipo de evidência

| Entregável | Estado | Evidência e limitação |
| --- | --- | --- |
| CONS-5 - regressões offline | PASS | Workflow integral verde no SHA indicado; cobre contratos exercitados pelos testes, não substitui teste físico longitudinal |
| CONS-5 - AUDs físicas e imutabilidade de origem | NOT_VERIFIABLE | Sem inventário físico de fontes com hashes antes/depois nesta execução; manter aceite real pendente |
| RPR - regressões offline e contadores | PASS | Pipelines integral e direcionado verdes; não equivale a confirmação de retomada em AUD física |
| RPR - reprocessamento real seletivo | NOT_VERIFIABLE | Não foi produzida comparação física antes/depois por `reprocess_id` nesta execução |
| IA - regressão de custo e moedas | PASS | Workflow econômico verde; cenário +320,69% é sintético e não demonstra causa do desvio histórico |
| IA - desvio da AUD-01D61DBA30DD45D19F99401AB927580D | NOT_VERIFIABLE | Forecast e ledger físicos não inspecionados aqui; nenhuma fatura inferida, nenhum provider chamado |
| HTML - smoke responsivo e impressão | PASS_WITH_LIMITATION | Inspeção anterior da fixture sintética, com ressalva de paginação inicial no PDF CAT-07 |
| HTML - paridade e pertinência com AUD real | NOT_VERIFIABLE | Baseline física de dados não confrontada; `data_row_parity=BASELINE_NOT_PROVIDED` |
| Documentação incremental #674 | PARTIAL | Esta matriz reconcilia CI; revisão de links, contratos e documentação operacional ainda deve ser concluída |
| Instalação limpa Windows/Linux | NOT_VERIFIABLE | Sucesso dos jobs Windows/Linux não certifica instalação limpa externa ao runner |
| Publicação candidata v0.9.0 | NO_GO | Gate técnico sintético verde, porém aceites físico, financeiro, documental e autorização humana não concluídos |

### Reconciliação financeira histórica - sem especulação causal

| Campo | Previsto | Observado | Diferença | Fonte | Conclusão |
| --- | --- | --- | --- | --- | --- |
| Custo total da AUD histórica | Indisponível nesta inspeção | Indisponível nesta inspeção | +320,69% reportado anteriormente, não recalculado | Referência #668; sem ledger/forecast físico aqui | NOT_VERIFIABLE |
| Chamadas, provider/modelo, tokens, retries, fallback | Não aferido | Não aferido | Não calculável | Ledger físico necessário | NOT_VERIFIABLE |
| Moeda, vigência e regra de pricing | Não aferido | Não aferido | Não calculável | Snapshot de pricing e tentativas necessários | NOT_VERIFIABLE |
| Chamadas opcionais posteriores à conclusão | Não aferido | Não aferido | Não calculável | Timeline da AUD e operações M18/M20 necessárias | NOT_VERIFIABLE |

**Regra de aceite:** não atribuir o desvio ao motor de forecast sem confrontar escopo, eventos, tentativas e pricing na mesma moeda. A falta de dados físicos não transforma a regressão sintética em falha, mas impede o aceite econômico histórico.

### Prévia GO/NO-GO e procedimento de promoção

- **GO técnico restrito:** regressões e CI dos 12 workflows consultados no SHA `55e7a956`.
- **NO-GO para merge/publicação neste momento:** PR permanece Draft; #674 aberta; evidências físicas CONS/RPR e reconciliação da AUD financeira não certificadas; aceite humano não concedido.
- **SemVer:** `v0.9.0` é candidato coerente para incremento funcional pré-1.0, sujeito à conferência do diff desde `v0.8.0`; não antecipar bump do código apenas com base nesta matriz.
- **Compatibilidade:** preservar leitura de `AUD-*` antigos, schemas, manifests e contratos; testar instalação Windows e Linux antes do aceite final.
- **Atualização local após autorização e integração:** salvar configuração operacional e evidências; atualizar `main` com `git pull --ff-only`; reinstalar dependências segundo README vigente; executar smoke local sem custo externo. Não executar atualização antes do merge autorizado.
- **Rollback:** manter tag/commit da `v0.8.0` e backup de configuração e auditorias; retornar o checkout à versão anterior sem reescrever `audit.db` histórico. Validar compatibilidade de artefatos novos antes de reabri-los com runtime antigo.
- **Publicação:** somente após nova CI verde no SHA final, revisão documental, julgamento das ressalvas e autorização humana explícita; PR Draft não é sinal de GO.


## Atualização da baseline de CI e documentação - 28/10/2026

- Commit validado: `104d6e85eb5805abb126ba23ca15e70df4845555` na PR #675 (Draft).
- GitHub Actions: **13 de 13 workflows efetivamente disparados no SHA acima com conclusão success**, inclusive CONS-5, RPR Windows/Linux, telemetria econômica, smoke visual, Public Contract Consistency e M24 crawling discovery safety.
- A validação pertence exclusivamente ao SHA registrado. Um commit posterior exige nova conferência, e testes sintéticos não são homologação física.
- Correção documental incremental: `README.md` e `docs/README.md` agora reconhecem a release pública `v0.8.0`, sem alterar exemplos históricos nem a versão de pacote em `pyproject.toml`.
- O pacote preliminar da candidata está em [RELEASE_CANDIDATE_0_9_0.md](RELEASE_CANDIDATE_0_9_0.md). Esse documento não é publicação de release nem autoriza merge, tag ou fechamento da issue #674.
- Lacunas restantes: paridade CONS/RPR com AUD física, ledger financeiro da AUD histórica, ressalva de impressão CAT-07, instalação limpa e aceite humano, conforme matriz anterior.
