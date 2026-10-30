# GEO Perplexity multiquery e reanálise consultiva pós-AUD (v0.9.2 candidata)

**Status:** implementação incremental nas issues #681 e #682, branch única
`feat/geo-multiquery-ai-only-rpr`. **Não homologado para publicação** até
CI/checks relevantes verdes e aceite do fluxo final. A tag/release v0.9.2
não deve ser criada antes do gate de publicação.

## 1. Limite metodológico

A Perplexity Search API admite até cinco queries por request, mas o resultado
agregado pode não informar inequivocamente a que query pertence cada fonte.
Não inferir essa atribuição por posição, snippet, título ou ranking. Fonte
externa não comprova citação em resposta generativa. O ledger observacional
pré-existente já admite atributo `query` por fonte quando fisicamente disponível
e consistente; a síntese GEO canônica usa uma query por execução para garantir
proveniência.

## 2. AUD inicial: GEO IA por 2-5 consultas

Quando GEO IA NÃO estiver solicitada, a Search API mantém o comportamento
histórico de agrupamento econômico. Quando houver 2-5 termos com GEO IA
solicitada, CAT-05 solicita **autorização adicional** de exatamente N requests
individuais, com estimativa **somente Search** pelo pricing canônico vigente.
Sem regra aplicável, o custo é N/D, jamais presumido como zero. **IA generativa tem custo adicional variável**,
que não deve ser representado como US$ 0.

A aprovação é vinculada por SHA-256 à sequência de queries, modo
WEB/FAST, filtros efetivos e alvo. Mudar qualquer um dos dois invalida o aceite anterior. Uma
aprovação ausente ou desatualizada interrompe o fluxo antes da rede.

O módulo `geo_multiquery_batch` reserva um grupo de consultas no `audit.db`
antes do primeiro request. O módulo `geo_multiquery_runtime` chama **o
adapter Perplexity existente** uma vez por query e o consumidor `geo_ai`
canônico sobre a evidência individual correspondente, sem novo cliente,
provider registry, fallback ou motor de pricing.

O lote tem `batch_id`, `request_fingerprint`, ordem, query, `run_id`,
estados por query e motivos de limitação. Cada sucesso persiste
independentemente. Após timeout/crash, resultado ambíguo fica
`PENDING_UNCERTAIN` e o mesmo fingerprint não é enviado automaticamente
outra vez. Nova observação exige intenção nova, separadamente autorizada,
preferencialmente via AUD nova ou suplemento explícito.

O `geo.html` apresenta seção consultiva read-only do lote, resultados por
query, contagem física de fontes e síntese de cobertura **determinística**. Não há chamada LLM extra
para gerar a visão transversal, nem alteração de SARI/SCORE-GEO.

## 3. AUD COMPLETE: reanálise de integrações sem coleta física

O comando experimental e conservador `ai-reanalysis` verifica o selo de
AUD `COMPLETE` ou `COMPLETE_WITH_LIMITATIONS` encerrada, integridade da base, manifesto e freshness do catálogo
pela rotina canônica `_sealed_audit`. Não instala o runtime de providers,
não ativa secrets, não executa busca, IA, browser, SERP, PSI/CrUX, Apdex
nem RPR físico.

Prévia (read-only, zero requisições e sem gravação):

```powershell
rasai ai-reanalysis .\audits\AUD-EXEMPLO
```

Publicação explícita de **nova projeção consultiva local** em pacote
independente versionado, sem alterar a AUD original:

```powershell
rasai ai-reanalysis .\audits\AUD-EXEMPLO --write-local-replay
```

O pacote fica em
`audits/.rasai-ai-reanalyses/AUD-EXEMPLO/AI-REPLAY-*/` com
`reanalysis.json`, `reanalysis.html` e manifesto hash. Repetir a
mesma intenção reutiliza o pacote verificado; não inicia providers.
O SHA-256 do `audit.db` e do manifesto de relatório são
conferidos antes e depois da derivação.

A matriz distingue:
- **GEO_PER_QUERY_LEDGER_LOCAL:** inventário offline canônico #304 a partir de
  SERP e Perplexity persistidas. A ausência de atribuição física resulta em N/D,
  sem forçar comparação. O console oferece `CAT-05 > Perplexity > A` para
  prévia e pacote local independente, sem provedor remoto;
- **GEO_LOCAL_EVIDENCE_REPLAY:** consulta única com fontes externas
  realmente persistidas, usando somente projeção local;
- **NEW_CANONICAL_AI_INFERENCE:** requer autorização financeira específica.
  **Não é executada por este comando local**;
- **NEW_PERPLEXITY_RESEARCH:** usar o complemento GEO versionado opt-in
  existente; não é replay do mesmo estado físico;
- **PHYSICAL_RECOLLECTION:** proibida na reanálise consultiva.

A execução opcional de **nova inferência GEO por IA canônica** está
disponível exclusivamente com sinalização explícita de possível custo,
usando uma **cópia SQLite isolada** do pacote original. O comportamento
padrão continua sendo zero chamadas externas:

```powershell
rasai ai-reanalysis .\\audits\\AUD-EXEMPLO --authorize-paid-geo-ai --provider auto
```

Para limitar a um run histórico específico, informar também
`--run-id ID-DO-RUN`. O modo padrão pago seleciona somente o grupo
multiquery elegível mais recente, limitado a cinco runs, ou a última
consulta única elegível nas AUDs anteriores. A reserva de intenção
é gravada antes de enviar qualquer modelo; nova tentativa idêntica
reutiliza ou mantém estado incerto, nunca reenvia. **Custo de IA N/D
antes da execução:** não alegar teto monetário garantido.

Limite da entrega incremental: a execução remota implementada atende
a interpretação GEO a partir de resultados Search fisicamente atribuídos.
Outras operações IA com replay-safe comprovado exigem adaptadores
adicionais em #682. A prévia e a projeção local não constituem inferência LLM,
e fontes preservadas continuam sendo observações históricas.

## 4. Contratos de regressão indispensáveis

Executar os testes direcionados offline (sem API comercial):

```powershell
python -m pytest -q tests/test_geo_multiquery_batch.py tests/test_geo_post_aud_ai_reanalysis.py
```

Validar também os testes preexistentes afetados somente:
`tests/test_geo_ai.py`, `tests/test_geo_report.py`,
`tests/test_geo_post_audit_complement.py`,
`tests/test_console_post_core_progress.py` e
`tests/test_geo_query_ledger.py`. Não criar novos workflows
especializados: reaproveitar os checks existentes quando relevantes.
Uma auditoria Windows real e a autorização de eventual custo de
proveedores **não** são implicadas pela execução automática de testes.

## 5. Publicação e segurança

Nenhuma alteração funcional nos motores de coleta, SARI, SCORE-GEO,
CONS ou RPR físico. Não migrar ou reinterpretar retroativamente
snapshots históricos. Relatórios e derivativos devem manter UI pt-BR
e IDs/taxonomia técnicas, apresentar limitações específicas e
referências aos registros de origem.

Apenas depois de testes focados e CI verde no SHA final, revisão de
impacto e evidências de compatibilidade, liberar o merge único em
`main`. Publicação v0.9.2 exige gate de release específico posterior.
