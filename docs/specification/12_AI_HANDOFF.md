# AI_HANDOFF.md

## 1. Objetivo do produto

Construir um auditor local de Search & AI Readiness baseado em evidence, regras reproduzíveis, análise semântica opcional e evidências externas complementares explicitamente isoladas do scoring quando aplicável.

## 2. Fonte de verdade

Leia primeiro:

`00_SPEC_INDEX.md`

Depois siga a ordem obrigatória indicada nele.

Não derive requisitos do histórico de chats quando houver definição normativa nestes arquivos.

## 3. Estado atual

A especificação funcional, Domain Model, Business Rules, Workflows, Scoring, Prioritization, Technical Architecture e especificações evolutivas constituem baseline aprovada conforme seus respectivos documentos.

O estado real de implementação não deve ser inferido de texto histórico deste handoff.

Antes de qualquer novo trabalho:

1. confirme o HEAD corrente de `main`;
2. confirme os marcos efetivamente integrados em `main` por commits e PRs merged;
3. confirme que não existe branch ou PR de marco anterior com conteúdo exclusivo pendente;
4. leia também todas as especificações evolutivas registradas em `00_SPEC_INDEX.md`;
5. derive o próximo marco do estado confirmado de `main` + baseline normativa vigente.

`main` é a referência operacional para determinar o que está efetivamente integrado.

## 4. Execução dos marcos

Cada marco continua sendo unidade independente de implementação, validação, branch, PR, merge e confirmação pós-merge.

Nenhum marco pode ser considerado concluído apenas para permitir avanço. Bloqueio real interrompe a cascata antes de iniciar o marco seguinte.

## 5. Restrições principais

- Windows;
- aplicação local, não web;
- CLI/console interativo;
- uma máquina e um operador;
- SQLite embarcado + filesystem;
- sem database server;
- sem Docker obrigatório;
- Git/GitHub usados para desenvolvimento, sem dependência de runtime;
- Desktop/Mobile independentes;
- RAW + RENDERED;
- Playwright + Chromium;
- SPA/non-SPA no mesmo pipeline;
- Evidence First;
- Deterministic First;
- IA opcional;
- NoneProvider obrigatório;
- providers de IA isolados por provider/registry;
- `SARI-001` é o índice público de readiness;
- `SCORE-GEO-003` é o scoring runtime vigente para novas auditorias;
- Sugestões/remediação textual por IA são opcionais/advisory e não alteram scoring por si só;
- Search Console, URL Inspection, CrUX, PageSpeed, Apdex e demais outcomes observados permanecem metodologias separadas salvo contrato versionado explícito;
- relatório HTML estático em português;
- testes mínimos orientados a risco.

## 6. Web Performance e observability externos - regra de continuidade

Ao trabalhar com Core Web Vitals, Lighthouse ou Search/AI Observability:

1. mantenha Lighthouse lab e CrUX field semanticamente separados;
2. não converta Lighthouse score, LCP, INP, CLS, Search Performance, URL Inspection ou outros outcomes externos em `SARI-001/SCORE-GEO-003` sem nova decisão metodológica versionada e validação correspondente;
3. ausência/erro de API externa é limitação de coleta, não finding automático do website;
4. preserve opt-in, limites, timeout e escopo de coleta quando houver chamada externa;
5. nunca reutilize automaticamente credencial de IA como chave/token de outro serviço;
6. não acrescente análise LLM implícita de métricas externas;
7. preserve raw artifacts/telemetria sem secrets;
8. mantenha páginas de Web Performance, Observability, Apdex, AI Visibility e AI Usage semanticamente separadas do score RASAi;
9. monitoramento/observability não migra `audit.db` nem altera a evidência original;
10. associação temporal entre regressão e outcome observado não autoriza linguagem causal.

## 7. SCORE-GEO-003

As dimensões permanecem evidence-bound; o Overall depende do contrato/model artifact calibrado e dos gates definidos em `SCORE_GEO_003.md`.

`READY_FOR_MODEL_FIT` não significa `VALIDATED`. Validação/promoção continua dependente dos gates pós-fit, inclusive AUC e Brier.

## 8. Não reabrir decisões

Não solicitar decisão humana para:

- nomes internos de classes;
- estrutura interna simples;
- pequenas bibliotecas compatíveis;
- refactors sem impacto funcional;
- organização de arquivos sem alteração de contrato;
- fixtures e ajustes de testes orientados a risco;
- erros de programação ordinários e solucionáveis.

Escolha a solução técnica mais simples compatível com a baseline, corrija falhas solucionáveis, revalide e continue.

## 9. Interromper somente diante de blocker real

A execução deve interromper quando houver condição que dependa necessariamente de decisão ou ação humana, incluindo:

1. conflito normativo real não solucionável pela precedência documental;
2. impossibilidade técnica material após investigação;
3. alteração necessária de escopo ou comportamento funcional aprovado;
4. mudança material em scoring, priorização ou interpretação oficial - inclusive incorporar sinais externos ao `SARI-001/SCORE-GEO-003`;
5. política ou autorização corporativa necessária;
6. credencial, segredo ou acesso externo indispensável e indisponível para um gate obrigatório;
7. ação externa obrigatória que a ferramenta disponível não consiga executar;
8. falha persistente de validação obrigatória após diagnóstico e tentativas razoáveis de correção;
9. inconsistência de `main` que torne inseguro continuar;
10. risco de operação destrutiva não previamente autorizada;
11. qualquer decisão que a própria baseline determine explicitamente ser humana.

Problemas técnicos ordinários e solucionáveis não constituem blocker.

## 10. Pendências humanas de ambiente/corporativas

Podem incluir:

- acesso técnico aos providers de IA escolhidos;
- autorização corporativa de IA externa;
- provider/modelo permitido;
- execução de browser/Chromium;
- autorização/quotas para APIs Google/Bing quando usadas;
- distribuição portátil;
- filesystem;
- SQLite;
- EDR/políticas.

Essas pendências não bloqueiam automaticamente o desenvolvimento local. Tornam-se blocker somente quando impedirem um gate obrigatório do marco em execução.
