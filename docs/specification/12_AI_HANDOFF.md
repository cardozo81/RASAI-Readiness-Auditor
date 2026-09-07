# AI_HANDOFF.md

## 1. Objetivo do produto

Construir um auditor local de Search/GEO Readiness baseado em evidence, regras reproduzíveis, análise semântica opcional e evidências externas complementares explicitamente isoladas do scoring quando aplicável.

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
4. leia também todas as especificações evolutivas registradas em `00_SPEC_INDEX.md`, mesmo quando `09_IMPLEMENTATION_PLAN.md` ainda possuir descrições históricas de marcos anteriores;
5. derive o próximo marco do estado confirmado de `main` + baseline normativa vigente.

`main` é a referência operacional para determinar o que está efetivamente integrado.

## 4. Execução dos marcos

Cada marco continua sendo unidade independente de implementação, validação, branch, PR, merge e confirmação pós-merge.

O avanço automático ao marco seguinte é permitido somente depois de todos os gates funcionais e de integração do marco anterior terem sido satisfeitos, conforme D-034.

Durante a cascata Extração e evidências → Testes críticos e baseline local estável, a branch encerrada deve ser comparada com `main`, confirmada sem conteúdo exclusivo e registrada na lista acumulada de exclusão manual conforme D-036. A exclusão física diferida não bloqueia o avanço.

Nenhum marco pode ser considerado concluído apenas para permitir avanço.

Bloqueio real interrompe a cascata antes de iniciar o marco seguinte.

## 5. Restrições principais

- Windows;
- aplicação local;
- não web;
- CLI;
- uma máquina;
- um operador;
- SQLite embarcado + filesystem;
- sem database server;
- sem Docker obrigatório;
- Git/GitHub utilizados para versionamento do desenvolvimento, sem dependência de runtime;
- Desktop/Mobile independentes;
- RAW + RENDERED;
- Playwright + Chromium;
- SPA/non-SPA no mesmo pipeline;
- Evidence First;
- Deterministic First;
- IA opcional;
- NoneProvider obrigatório;
- OpenAI/DeepSeek/MiMo isolados por provider no runtime vigente;
- `SCORE-GEO-002` permanece scoring baseline enquanto não houver nova decisão/versionamento explícito;
- Sugestões e remediação de conteúdo por IA textual é opcional/advisory e não altera scoring;
- Web Performance externo PageSpeed/CrUX é evidência externa complementar, default OFF para rede externa e não altera scoring;
- Web Performance externo adiciona zero chamadas LLM;
- relatório HTML estático em português;
- testes mínimos orientados a risco.

## 6. Web Performance externo — regra de continuidade

Ao trabalhar com Core Web Vitals/Lighthouse:

1. leia `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md` e D-038;
2. mantenha Lighthouse lab e CrUX field semanticamente separados;
3. não converta Lighthouse score, LCP, INP ou CLS em `SCORE-GEO-002` sem nova decisão humana e novo scoring_version;
4. ausência/erro de CrUX/PageSpeed é limitação de coleta, não finding do website;
5. preserve `--web-performance` como opt-in de chamadas externas;
6. preserve limites de páginas, timeout e field source configuráveis;
7. nunca reutilize automaticamente API key de IA como chave PageSpeed/CrUX ou vice-versa;
8. não acrescente análise LLM de métricas Web Performance externo implicitamente;
9. preserve raw response artifacts e telemetria Web Performance externo sem secrets;
10. mantenha `report/web-performance.html` claramente separado de `ai-usage.html` e do score RASAI.

## 7. Não reabrir decisões

Não solicitar decisão humana para:

- nomes internos de classes;
- estrutura interna simples;
- pequenas bibliotecas compatíveis;
- refactors sem impacto funcional;
- organização de arquivos sem alteração de contrato;
- fixtures e ajustes de testes orientados a risco;
- erros de programação ordinários e solucionáveis.

Escolha a solução técnica mais simples compatível com a baseline, corrija falhas solucionáveis, revalide e continue.

## 8. Interromper somente diante de blocker real

A execução deve interromper quando houver pelo menos uma condição que dependa necessariamente de decisão ou ação humana, incluindo:

1. conflito normativo real não solucionável pela precedência documental;
2. impossibilidade técnica material após investigação;
3. alteração necessária de escopo ou comportamento funcional aprovado;
4. mudança material em scoring, priorização ou interpretação oficial — inclusive incorporar Web Performance externo ao `SCORE-GEO-002`;
5. política ou autorização corporativa necessária;
6. credencial, segredo ou acesso externo indispensável e indisponível para um gate obrigatório;
7. ação externa obrigatória que a ferramenta disponível não consiga executar, exceto exclusão física diferida de branches coberta por D-036;
8. falha persistente de validação obrigatória após diagnóstico e tentativas razoáveis de correção;
9. inconsistência de `main` que torne inseguro continuar;
10. risco de operação destrutiva não previamente autorizada;
11. qualquer decisão que a própria baseline determine explicitamente ser humana.

Problemas técnicos ordinários e solucionáveis não constituem blocker.

## 9. Pendências humanas de ambiente/corporativas

Permanecem sujeitas às decisões D-028 e D-029, entre elas:

- acesso técnico à OpenAI/provedores IA quando escolhidos;
- autorização corporativa de IA externa;
- provider permitido;
- execução de browser/Chromium;
- autorização/quotas para PageSpeed/CrUX quando Web Performance externo for usado;
- distribuição portátil;
- filesystem;
- SQLite;
- EDR/políticas.

Essas pendências não bloqueiam automaticamente o desenvolvimento local. Tornam-se blocker somente quando impedirem um gate obrigatório do marco em execução.
