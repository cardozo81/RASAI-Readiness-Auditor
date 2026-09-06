# M18 — Multi-AI Provider Abstraction, Reliability Routing & Usage Telemetry

**Status:** APPROVED — reconciliado com `SCORE-GEO-002`, report site e contexto de dispositivo configurável.

M18 é uma extensão aditiva de infraestrutura de IA. Não transforma LLM em scoring engine, não altera as Business Rules e não converte falha/ausência de IA em defeito do website. O scoring vigente é `SCORE-GEO-002`.

## Providers e contrato

Runtime aprovado:

- `OPENAI`;
- `DEEPSEEK`;
- `MIMO`;
- `NONE`.

GitHub Copilot não é `SemanticProvider`.

Todos os adapters produzem contrato normalizado. A aceitação de uma resposta semântica exige o conjunto esperado de BR-GEO semânticas, sem regra ausente/duplicada/desconhecida, enums válidos e `evidence_ids` existentes. HTTP 200 ou JSON parseável isoladamente não significam resultado `AVAILABLE`.

## Routing default

Ordem de política SearchGEO:

1. OPENAI / `gpt-5.6-sol` / HIGH-XHIGH / QUALIFIED-A+;
2. OPENAI / `gpt-5.6-terra` / HIGH / QUALIFIED-A;
3. DEEPSEEK / `deepseek-v4-pro` / HIGH / PROVISIONAL-A-;
4. MIMO / `mimo-v2.5-pro` / THINKING_ENABLED / PROVISIONAL-B+;
5. OPENAI / `gpt-5.6-luna` / HIGH / QUALIFIED-B+;
6. DEEPSEEK / `deepseek-v4-flash` / HIGH / PROVISIONAL-B;
7. MIMO / `mimo-v2.5` / THINKING_ENABLED / PROVISIONAL-B.

A classificação é política interna SearchGEO, não benchmark científico universal. DeepSeek/MiMo permanecem `PROVISIONAL` até benchmark específico com rule agreement, evidence fidelity, completeness, schema compliance, hallucination rate, repeatability, disciplina de UNKNOWN, PT-BR, entity/intent accuracy e operational success rate.

## Seleção explícita e AUTO

Provider explícito nunca faz failover cruzado para outro fornecedor. Chaves ausentes de providers não selecionados não podem interferir na execução do provider explícito.

`AUTO` detecta somente providers com configuração utilizável, ordena a cadeia uma vez no início do audit e não reintroduz provider quarantined. As tentativas são sequenciais. O primeiro resultado válido encerra a cadeia naquele contexto; providers posteriores não sobrescrevem o resultado aceito.

Falha qualificadora antes de resultado válido permite fallback na mesma URL somente em `AUTO`.

## URL lock e contexto de dispositivo

Quando mais de um dispositivo é auditado, o primeiro provider que entrega resultado válido para a URL fixa `PINNED_TO_URL`; os demais contextos dessa URL reutilizam esse provider. Se o provider fixado falhar no outro dispositivo, não ocorre troca silenciosa de fornecedor nessa mesma URL; a lacuna permanece degradada/UNKNOWN conforme dependências semânticas e o provider pode ser quarantined para URLs posteriores.

O escopo de dispositivo é definido pelo runtime atual por `SEARCHGEO_DEVICE_CONTEXT` / `--device-context`:

- `mobile` — somente Mobile;
- `desktop` — somente Desktop;
- `both` — Desktop e Mobile.

A CLI usa `mobile` como default. M18 só pode chamar provider para snapshots/contextos efetivamente produzidos. Portanto um audit Mobile-only não deve gerar chamada Desktop apenas para completar simetria. Essa regra reduz custo sem alterar score retrospectivamente.

A comparação BR-GEO-052 só existe quando ambos os dispositivos fazem parte do escopo. Em contexto único, a comparação é `NOT_APPLICABLE` com reason code `DEVICE_COMPARISON_DISABLED_BY_CONTEXT`; isso não representa falha de rendering.

## Failover e quarantine

Em provider explícito, uma falha qualificadora pode colocar o provider em `QUARANTINED_FOR_AUDIT`; não há fallback para outro fornecedor. O status operacional é `DEGRADED` quando a semântica necessária não foi atendida.

`CHAIN_EXHAUSTED` é reservado à estratégia `AUTO` quando todos os providers elegíveis foram esgotados/quarantined.

Falha do provider nunca cria finding do website por si só. Dependências semânticas sem conclusão permanecem UNKNOWN/limitadas conforme o contrato das regras e do scoring.

## Timeout

O timeout operacional da CLI é configurável por `SEARCHGEO_AI_TIMEOUT_SECONDS` e possui default atual de 180 segundos por chamada. O valor deve ser finito e maior que zero.

Timeout não implica retry automático da mesma chamada, evitando consumo duplicado quando a requisição pode ter alcançado o provider.

## Telemetria e custo

`ai_provider_attempts` registra, quando disponível:

- tentativa, URL e device;
- provider/model/depth/rank;
- timestamps e duração;
- status e diagnóstico sanitizado;
- usage reportado;
- `ESTIMATED_COST`;
- versão de pricing;
- summary bounded/hash;
- versão do contrato semântico.

Nunca persistir secret, `Authorization`, corpo sensível integral ou chain-of-thought. Tokens ausentes ficam `NULL`. Custo é calculado por catálogo local versionado; não é billing/invoice do fornecedor e nunca participa do score.

Logging operacional sanitizado pode registrar provider/model/status/duração/tokens/custo/error class conforme `log_level`, sem API key, header de autorização ou request body integral. A baseline não exige `audit.log` persistente.

A fonte persistente de verdade para telemetria é `audit.db`.

## Reporting vigente

A projeção pública de telemetria fica em:

`report/ai-usage.html`

Essa página distingue habilitado/configurado/tentado/sucesso, estratégia, provider inicial/efetivo, modelo, status, failover, uso e custo estimado.

`report/remediation.html` pode apresentar somente contexto operacional quando necessário para interpretar limitações; falha de IA não deve ser convertida em finding/recommendation de qualidade do website.

Os HTMLs legados temporários usados durante a composição interna do pipeline não constituem output público. O ponto de entrada final é `report/index.html`.

## Invariantes

1. IA permanece opcional.
2. `NONE` executa o auditor sem chamadas externas.
3. ausência/falha de IA não equivale a baixa qualidade do website.
4. LLM não calcula score.
5. somente evidência persistida pode sustentar resultados aceitos.
6. primeiro resultado válido em uma cadeia não pode ser sobrescrito por tentativa posterior.
7. provider não selecionado/sem credencial não pode invalidar provider explícito funcional.
8. contexto de dispositivo limita rendering e chamadas de IA ao escopo solicitado.
9. telemetria é separada de findings e score.


## DeepSeek wire contract por chaves obrigatórias

Para DeepSeek via Responses API, o contrato de transporte das 22 avaliações semânticas usa um objeto cujas chaves obrigatórias são `BR-GEO-028` até `BR-GEO-049`. Isso evita depender de `minItems`/`maxItems` para cardinalidade de arrays, restrições que a documentação do DeepSeek declara não suportadas em seu subconjunto estrito de JSON Schema. Antes da persistência, o adapter converte o objeto para o array canônico SearchGEO e reaplica todas as validações locais de schema, evidência, completude e duplicidade. A alteração não muda scoring nem a semântica das regras.
