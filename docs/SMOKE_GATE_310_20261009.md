# Gate único de smoke humano - PR #336

**Controladora:** #310. **Branch:** `feat/310-linear-residual-hardening-20261009`.
**Escopo:** regressões read-only e UI da AUD já homologada; nenhuma auditoria
nova, cobrança externa, reparo de pacote histórico ou medição fictícia de Apdex.

## Pré-condições automáticas, antes de envolver o operador

- HEAD efetivo do PR registrado no GitHub; `main` e branch reconciliadas.
- Todos os workflows relevantes do HEAD `COMPLETED/SUCCESS`; testes fake da
  Perplexity, GEO v4, integridade SQLite/FK, #319, #322 e #318 incluídos.
- PR não integrado; decisão de merge separada após resultado humano.
- Todo erro de coletor ou de IA permanece preservado em evidência, não
  transformado em diagnóstico do site auditado.

## Smoke humano mínimo (uma AUD existente)

1. No PowerShell do diretório `C:\IA-PROJETOS\github\RASAI-Readiness-Auditor`:
   `git fetch origin --prune`, `git switch feat/310-linear-residual-hardening-20261009`
   e `git pull --ff-only`. Confirmar `git rev-parse HEAD` contra o HEAD
   canônico informado na #310, **sem** forçar `main`.
2. Verificar AUD original completa em
   `%TEMP%\rasai-apdex-final-20261008164107\AUD-3CDB4E407A6A40FDA5CAB5D82FA672A8`.
   Validar `Test-Path "$aud\audit.db"` e `Test-Path "$aud\report-catalog"`.
   Se a cópia não estiver presente, **não** iniciar nova AUD; reportar N/D.
3. Opcionalmente obter SHA-256 do `audit.db` antes e depois:
   `(Get-FileHash "$aud\audit.db" -Algorithm SHA256).Hash`.
4. Em diretório temporário **novo**:
   `python -m rasai rematerialize-report --audit-dir "$aud" --output-root "$out"`
   usando a `.venv\Scripts\python.exe` local. A original não pode ser
   regravada. Abrir o novo `report-catalog/index.html`.
5. Inspecionar apenas o recorte alterado: seção GEO e referências
   CAT-01/03/05/08/09, index, directed-analysis, ai-integrations;
   confirmar que fontes **não solicitadas** não viram evidência de citação
   generativa e que a ausência de Perplexity indica N/D.
6. Se desejar verificar a prévia #319, entrar no console com a mesma
   configuração de auditoria e abrir a prévia financeira **sem confirmar
   execução**. Sem >=5 AUDs equivalentes, duração fica N/D; somas HTTP
   PSI/CrUX jamais aparecem como duração da fase inteira. Escolher Voltar.
7. Registrar saída, SHA do HEAD, hash do banco original, resultado do
   relatorio renderizado e eventual diagnóstico N/D como evidência de gate.

## Explicitamente fora do smoke mínimo

- **#318:** chamada Perplexity real é ação potencialmente tarifável e demanda
  autorização *separada* de query, método WEB/FAST, escopo, limite monetário,
  credencial e novo `intent_id`; não executar por padrão.
- **#306:** síntese IA comercial opt-in não se comprova com transporte fake.
- **#322:** adapter `observe_existing_playwright_page` está isolado e não
  conectado aos gateways M23/M25. Nenhum delta de prontidão real foi coletado;
  não exigir nova AUD somente para ilustrar o classificador.
- **#319:** prévia de estágios físicos sem telemetria histórica não pode ser
  homologada por inspeção visual.
- A seção de duas colunas da #334 teve 7/7 validações humanas em rodada
  anterior. Não repetir seu smoke integral sem regressão comprovada.

## Critérios objetivos para decisão pós-smoke

**Aprovado:** HEAD/CI verdes, banco/manifestos originais intactos,
rematerialização sem regressão, conteúdo observacional com ressalvas e
N/D coerentes, nenhuma chamada externa não autorizada.

**Reprovado:** mudança de hash do original, diferença de pacote não
explicada, exceção em HTML/read-only, promessa de equivalência causal,
novo gasto sem aceite, ou regressão em outputs homologados.

Gates comerciais e de instrumentação física podem permanecer em issues
independentes, explicitamente não homologados, sem bloquear a aprovação
do **recorte read-only e seguro**. A integração em `main` exige decisão
separada da controladora #310.
