# AI_HANDOFF.md

## 1. Objetivo do produto

Construir e manter o RASAi como auditor de Search & AI Readiness baseado em evidence, regras reproduzíveis, análise semântica opcional e evidências externas complementares explicitamente isoladas do scoring quando aplicável.

O produto é **Windows-first no runtime local**, mas a arquitetura já possui control plane para multiusuário/multiprojeto/multidomínio e fronteiras preparadas para evolução SaaS.

## 2. Fonte de verdade

Leia primeiro:

`00_SPEC_INDEX.md`

Depois siga a ordem indicada nele.

Não derive requisitos do histórico de chats quando houver definição normativa vigente nestes arquivos.

## 3. Estado atual

`main` é a referência operacional para determinar o que está efetivamente integrado.

Antes de qualquer novo trabalho:

1. confirme o HEAD corrente de `main`;
2. confirme comandos/entrypoints existentes no código, não apenas em documentação histórica;
3. confirme que não existe branch/PR com conteúdo exclusivo necessário ao escopo;
4. leia as especificações vigentes registradas em `00_SPEC_INDEX.md`;
5. preserve compatibilidade com AUDs históricos e `scoring_version` persistida;
6. derive o próximo trabalho do estado real de `main` + baseline normativa vigente.

Planos/roadmaps históricos não prevalecem sobre contratos atuais.

## 4. Restrições e invariantes principais

- Windows local permanece o alvo operacional principal atual;
- CLI/console interativo permanecem superfícies suportadas;
- SQLite + filesystem continuam válidos para execução local;
- Docker não é requisito local;
- Git/GitHub são ferramentas de desenvolvimento, não dependências de runtime;
- `audit.db` e artifacts do AUD são evidência fonte e não devem ser regravados por superfícies derivadas;
- Product Platform/control plane fica separado do `audit.db`;
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
- `SCORE-GEO-004` é o scoring runtime vigente para novas auditorias;
- Overall 004 é determinístico e não exige model artifact externo;
- Sugestões/remediação textual por IA são opcionais/advisory e não alteram scoring por si só;
- Search Console, URL Inspection, CrUX, PageSpeed, Apdex e outcomes observados permanecem metodologias separadas salvo contrato versionado explícito;
- relatório HTML estático em português;
- `report/scoring.html` é a página canônica estável da metodologia; versão fica em `scoring_version`/conteúdo;
- testes orientados a risco são obrigatórios.

## 5. Product Platform e evolução SaaS

No local Windows:

```text
audits/.rasai/platform.db
```

é o control plane para tenancy/projetos/properties/environments, users/memberships, milestones/deployments, baselines, schedules, alerts, integrations e usage ledger.

Esse banco não substitui `audit.db`.

No alvo SaaS, o control plane deve migrar para PostgreSQL e os workers podem operar em Linux/container, preservando o contrato imutável dos AUD bundles.

Não interpretar a presença do modelo multi-user como afirmação de autenticação SaaS já implementada no runtime local.

## 6. Web Performance e observability externos

Ao trabalhar com Core Web Vitals, Lighthouse ou Search/AI Observability:

1. mantenha Lighthouse lab e CrUX field semanticamente separados;
2. não converta Lighthouse score, LCP, INP, CLS, Search Performance, URL Inspection ou outros outcomes externos em `SARI-001/SCORE-GEO-004` sem nova decisão metodológica versionada;
3. ausência/erro de API externa é limitação de coleta, não finding automático do website;
4. preserve opt-in, limites, timeout e escopo de coleta quando houver chamada externa;
5. nunca reutilize automaticamente credencial de IA como chave/token de outro serviço;
6. não acrescente análise LLM implícita de métricas externas;
7. preserve raw artifacts/telemetria sem secrets;
8. mantenha páginas de Web Performance, Observability, Apdex, AI Visibility e AI Usage separadas do score;
9. monitoring/observability não migra `audit.db` nem altera a evidência original;
10. associação temporal entre regressão e outcome observado não autoriza linguagem causal.

## 7. SCORE-GEO-004

As dez dimensões permanecem evidence-bound.

Overall:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

- dimensões aplicáveis têm igual peso;
- `NOT_APPLICABLE` legítimo sai do denominador;
- dimensão aplicável `NOT_CONSOLIDATED` bloqueia Overall consolidado;
- Coverage e Confidence qualificam a medição;
- calibração externa não é requisito nem input do runtime.

`rasai scoring inspect` é a superfície atual de inspeção do contrato.

## 8. HTML/reporting

A página de metodologia deve ser:

```text
report/scoring.html
```

## 9. Não reabrir decisões sem necessidade

Não solicitar decisão humana para:

- nomes internos de classes;
- estrutura interna simples;
- pequenas bibliotecas compatíveis;
- refactors sem impacto funcional;
- organização de arquivos sem alteração de contrato;
- fixtures e ajustes de testes orientados a risco;
- erros de programação ordinários e solucionáveis.

Escolha a solução técnica mais simples compatível com a baseline, corrija falhas solucionáveis, revalide e continue.

## 10. Interromper somente diante de blocker real

A execução deve interromper quando houver condição que dependa necessariamente de decisão ou ação humana, incluindo:

1. conflito normativo real não solucionável pela precedência documental;
2. impossibilidade técnica material após investigação;
3. alteração necessária de escopo ou comportamento funcional aprovado;
4. mudança material em scoring, priorização ou interpretação oficial;
5. política ou autorização corporativa necessária;
6. credencial, segredo ou acesso externo indispensável e indisponível para um gate obrigatório;
7. ação externa obrigatória que a ferramenta disponível não consiga executar;
8. falha persistente de validação obrigatória após diagnóstico e tentativas razoáveis de correção;
9. inconsistência de `main` que torne inseguro continuar;
10. risco de operação destrutiva não previamente autorizada;
11. decisão que a baseline determine explicitamente ser humana.

Problemas técnicos ordinários e solucionáveis não constituem blocker.

## 11. Pendências humanas de ambiente/corporativas

Podem incluir:

- acesso técnico aos providers de IA escolhidos;
- autorização corporativa de IA externa;
- provider/modelo permitido;
- execução de browser/Chromium;
- autorização/quotas para APIs externas quando usadas;
- políticas de proxy/EDR/filesystem;
- credenciais de integrações;
- decisões comerciais/security para SaaS.

Essas pendências não bloqueiam automaticamente o desenvolvimento local. Tornam-se blocker somente quando impedirem um gate obrigatório do trabalho em execução.
