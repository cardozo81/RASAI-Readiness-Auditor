# Consolidação temporal de métricas

**Estado:** vigente.

## Objetivo

O relatório consolidado `CONS-*` deve combinar execuções independentes do RASAi ao longo de um período sem tratar métricas distintas como se compartilhassem a mesma regra estatística.

O contrato `TEMPORAL-APDEX-001` formaliza o caso que exige acesso às amostras brutas: **Synthetic Navigation Apdex** e **Synthetic User Experience Apdex**.

O modelo recomendado para monitoramento é:

```text
08:00 -> AUD-1 -> poucas amostras controladas
11:00 -> AUD-2 -> poucas amostras controladas
14:00 -> AUD-3 -> poucas amostras controladas
17:00 -> AUD-4 -> poucas amostras controladas
20:00 -> AUD-5 -> poucas amostras controladas
                    |
                    v
              CONS-* do período
```

Isso não transforma execuções próximas em RUM. Continua sendo uma medição sintética, porém com diversidade temporal maior do que uma bateria longa executada em sequência.

## Princípio de agregação por domínio de métrica

O consolidado não possui uma fórmula universal de média. Cada família preserva a semântica da origem:

| Família | Política de consolidação |
|---|---|
| SARI / SCORE-GEO | série de valores já persistidos; não recalcula o scoring do website para o período |
| Web Performance | estado por URL/dispositivo e estatística descritiva entre observações comparáveis |
| Findings | contagens, severidade, páginas afetadas e taxas contextualizadas pelo universo auditado |
| Navigation Apdex | soma Satisfied/Tolerating/Frustrated + pool bruto de durações |
| User Experience Apdex | soma Satisfied/Tolerating/Frustrated + pool bruto da KPM efetiva |
| CrUX / dados externos agregados | preserva a agregação do provider; percentis externos não são repercentilizados a partir de percentis |
| Estados categóricos | distribuição/contagem; não recebem média numérica artificial |

Esse contrato evita o erro de aplicar `AVG()` indiscriminadamente a scores, percentis, estados e contagens de naturezas diferentes.

## Apdex do período

O Apdex consolidado não é calculado pela média simples dos scores de cada `AUD-*`.

Para uma série metodologicamente comparável:

```text
Satisfied_total  = soma dos Satisfied de todos os AUDs
Tolerating_total = soma dos Tolerating de todos os AUDs
Valid_total      = soma das amostras válidas

Apdex_periodo =
    (Satisfied_total + 0.5 * Tolerating_total)
    / Valid_total
```

Essa forma preserva o peso real das amostras e evita distorção quando as execuções possuem quantidades diferentes de medições válidas.

## Percentis e dispersão do período

Percentis não são aditivos.

Portanto, são metodologicamente inválidas operações como:

```text
p95_periodo = média(p95_AUD1, p95_AUD2, ...)
```

`TEMPORAL-APDEX-001` lê as amostras brutas persistidas dos `AUD-*` elegíveis e reconstrói o pool do período. A partir desse pool são recalculados:

- média;
- mediana / p50;
- p75;
- p90;
- p95;
- p99;
- mínimo e máximo;
- desvio-padrão populacional;
- coeficiente de variação.

A interpolação de percentis segue a mesma regra linear utilizada pelo runtime de Synthetic Navigation Apdex.

Uma amostra válida sem duração/KPM numérica continua participando do Apdex pelas contagens persistidas, mas não participa da distribuição de tempos. O relatório declara essa diferença explicitamente.

## Unidade da série temporal

A série é **URL-scoped**. URLs diferentes não são fundidas silenciosamente em um único pool de tempos.

Além da URL, a consolidação exige contexto compatível.

### Synthetic Navigation Apdex

A identidade considera, no mínimo:

- URL;
- dispositivo;
- task;
- profile;
- threshold `T`;
- threshold de frustração `4T` persistido/derivado;
- pacing relevante (`delay` e `concurrency`).

### Synthetic User Experience Apdex

A identidade considera, no mínimo:

- URL;
- dispositivo ou `POPULATION`;
- task;
- profile;
- KPM efetiva;
- threshold Satisfied;
- threshold Frustrated;
- session mode;
- política `errors_affect_apdex`;
- error scope;
- pacing/settle relevantes;
- mix de dispositivos quando a série é `POPULATION`.

Se qualquer elemento material muda, outra série é criada. O consolidador não contamina a série atual com medições incompatíveis.

## Navigation e Experience permanecem separados

`Synthetic Navigation Apdex` mantém o contrato clássico `T/4T`.

`Synthetic User Experience Apdex` mantém KPM, thresholds e política de erros próprios. Mesmo quando ambos observam a mesma URL e o mesmo horário, não são fundidos.

Para `POPULATION` no Experience, a distribuição do período é formada pela união das amostras reais dos devices que compõem a população daquela execução, desde que o mix e o restante do contexto sejam comparáveis.

## Tempo da observação versus tempo da revisão

Esse controle pertence à governança de fontes `CONSOLIDATED-SOURCE-GOVERNANCE-003`.

RPR não cria automaticamente uma nova observação longitudinal. O CONS distingue:

```text
observation_at  = data semântica do marco observado
revision_at     = última revisão material da mesma AUD usada pelo CONS
revision_mode   = NONE | REPLAY_SAFE | LIVE_RECOLLECTION | UNKNOWN
source_revision_id = identidade content-addressed da revisão lógica do audit.db
```

Somente RPR com item materialmente resolvido participa da cronologia de revisão. Tentativas sem sucesso não avançam `revision_at`.

Se `revision_at` de uma AUD anterior ocorre depois de `observation_at` da AUD seguinte, a governança cria `temporal_revision_overlap`:

- `REPLAY_SAFE_AFTER_NEXT_OBSERVATION`: a revisão usa evidência persistida do marco original; permanece válida para leitura contextual, mas conteúdos derivados materializados depois são identificados como revisão posterior;
- `LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION`: houve nova coleta após o marco seguinte; a confiança do conjunto é reduzida e os dados afetados não podem ser descritos como reprodução controlada do estado cronológico original;
- `UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION`: o modo não foi comprovado e requer qualificação manual.

Esse controle é transversal ao CONS. Ele não altera a fórmula do Apdex e não recalcifica SARI/SCORE-GEO.

## Integridade e persistência

A implementação preserva o contrato de evidência do RASAi:

- `AUD-*/audit.db` continua sendo a fonte de verdade da revisão selecionada;
- o consolidador não altera a AUD; cada banco fonte é aberto com `mode=ro` e `PRAGMA query_only=ON`;
- RPR governado pode produzir revisão posterior fora do consolidador, e essa revisão é identificada por digest lógico no `source_revision_id`;
- nenhum schema de `audit.db` é migrado;
- nenhuma amostra é regravada;
- a construção de `TEMPORAL-APDEX-001` não chama API, IA, PageSpeed, CrUX ou provider; a análise especialista de IA do `CONS-5`, quando autorizada, ocorre em camada separada e consome somente a evidência já materializada;
- o cache `.rasai/consolidated-index.db` continua derivado e reconstruível;
- o HTML e o `manifest.json` são artefatos derivados;
- o manifest persiste estatísticas e proveniência da série, **não as amostras brutas completas**.

O contrato do manifest é identificado como:

```text
TEMPORAL-APDEX-001
```

A política registra separadamente:

```text
apdex_period_score = sum_satisfied_tolerating_frustrated_per_exact_context
apdex_period_distribution = raw_sample_pool_per_url_exact_context
```

## HTML do relatório consolidado

A seção `Apdex` de `CONS-*/report.html` distingue:

- tipo de Apdex;
- URL;
- dispositivo/população;
- Apdex do período;
- amostras válidas e inválidas;
- número de `AUD-*` comparáveis;
- classificação da base como um marco, dois marcos ou série temporal;
- p95 do pool;
- distribuição completa sob detalhe expansível;
- contexto de comparabilidade;
- limitações de dados.

A apresentação humana dessa seção usa pt-BR: **Satisfeitas / Toleráveis / Frustradas**, nomes legíveis para KPM, perfil, calibração e pacing. Identificadores internos como `USER_ACTION_DURATION`, `MANUAL_CALIBRATION` e IDs compostos de perfil pertencem à rastreabilidade técnica e não devem substituir o rótulo humano no HTML.

A composição é `fail-open`: se não houver dados temporais utilizáveis, o relatório permanece válido e mantém a apresentação de Apdex disponível a partir dos dados efetivamente materializados, sem fabricar série temporal.

## Agendamento e SaaS

O contrato atual não exige mudança no schema do SaaS/control plane.

O scheduler pode materializar execuções independentes em horários distintos. Para uma campanha temporal confiável, os jobs devem manter o mesmo contexto metodológico e variar principalmente a janela de execução.

Exemplo conceitual:

```text
Project / Property / Environment
        |
        +-- schedule 08:00 -> AUD
        +-- schedule 11:00 -> AUD
        +-- schedule 14:00 -> AUD
        +-- schedule 17:00 -> AUD
        +-- schedule 20:00 -> AUD
                           |
                           v
                     CONS-* do período
```

O consolidador exige acesso aos artefatos `AUD-*` que participam da série. Em execução distribuída, o nó responsável pela consolidação precisa receber acesso à evidência imutável correspondente; sem esse acesso, a consolidação não é executável nesse nó.

Região/origem de execução não integra atualmente a identidade metodológica da série de forma suficiente para fundir automaticamente resultados de hubs distintos. Sem proveniência regional persistida e comparável, resultados de origens diferentes não devem ser apresentados como uma única população homogênea.

## Estratégia operacional recomendada

Para auditoria pontual, poucas amostras por contexto podem ser suficientes para diagnóstico local.

Para monitoramento, é preferível distribuir a mesma carga total em N janelas ao longo do período em vez de concentrar dezenas ou centenas de navegações consecutivas. Isso reduz correlação temporal e aumenta a utilidade operacional da série, sem converter a medição em experiência real de usuários.

O volume deve continuar respeitando autorização e capacidade do alvo. Uma navegação sintética pode gerar muitos requests HTTP de subrecursos; quantidade de amostras não equivale a quantidade de requests.

## Testes direcionados

A validação de `TEMPORAL-APDEX-001` cobre:

- recálculo do Apdex pelas contagens persistidas;
- percentis do pool bruto entre múltiplos `AUD-*`;
- separação de thresholds incompatíveis;
- população Experience formada pela união das amostras dos devices;
- preservação byte a byte dos `audit.db` fonte;
- preservação das demais seções do HTML ao substituir a seção Apdex;
- inclusão do contrato e das políticas no `manifest.json` sem persistir amostras brutas.

## Limites metodológicos

- três ou mais `AUD-*` caracterizam uma série temporal descritiva, não causalidade;
- janelas temporais diferentes aumentam representatividade operacional, mas não transformam Synthetic Apdex em RUM;
- mudanças de infraestrutura externa, CDN, rede e terceiros continuam fazendo parte do fenômeno observado;
- percentis e CV do período só usam amostras com valor temporal/KPM numérico;
- SARI, SCORE-GEO, Lighthouse, CrUX e Findings mantêm contratos próprios e não são somados ao Apdex.
