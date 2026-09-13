# Relatórios históricos e consolidados

## Objetivo

O consolidador reúne indicadores persistidos em auditorias `AUD-*` e gera um snapshot HTML estático para análise por domínio, período, dispositivo e URL. A consolidação base é independente do pipeline de auditoria: não reexecuta crawl, regras, scoring, PageSpeed, CrUX ou outros collectors.

O formato materializado vigente continua:

```text
CONS-4
```

`CONS-4` inclui consolidação temporal de Apdex, análise determinística de evolução e, quando explicitamente solicitada pelo usuário, uma camada opcional de análise especialista por IA. O uso de IA não muda o contrato de scoring, não altera `SARI-001`/`SCORE-GEO-004` e nunca grava nos `AUD-*` fonte.

Contratos derivados atuais:

```text
TEMPORAL-APDEX-001
CONSOLIDATED-EVOLUTION-001
CONSOLIDATED-SPECIALIST-001
```

## Garantias de arquitetura

- `AUD-*/audit.db` permanece a fonte de verdade de cada auditoria;
- bancos fonte são abertos em modo somente leitura (`mode=ro` + `PRAGMA query_only=ON`);
- nenhum schema de `audit.db` é migrado pelo consolidador;
- `.rasai/consolidated-index.db` é cache derivado, descartável e reconstruível;
- Monitoring e Fix Verification calculam a evolução factual; a IA não redefine deltas;
- falha ou ausência de IA não impede a geração do relatório consolidado;
- `CONS-*` não substitui `AUD-*`;
- séries metodologicamente incompatíveis nunca são fundidas silenciosamente;
- dados ausentes nunca são convertidos em zero;
- segredos de providers não são persistidos no manifest nem em `specialist-analysis.json`.

```text
AUD-*/audit.db (fonte oficial, read-only)
        |\
        | +--> Monitoring / Fix Verification
        | +--> amostras Apdex brutas comparáveis
        |
        +----> .rasai/consolidated-index.db (cache reconstruível)
                    |
                    v
          filtros + comparabilidade
                    |
                    +--> evolução determinística
                    |
                    +--> IA especialista opcional
                    |
                    v
       consolidated/CONS-*/report.html
                     + manifest.json
                     + specialist-analysis.json
```

## Elegibilidade e filtros

Somente auditorias concluídas participam. A data efetiva segue:

```text
completed_at -> started_at -> created_at
```

Os limites do período são inclusivos. Web Performance, Apdex e ocorrências page-level podem ser filtrados por URL. Readiness persistida em nível de auditoria/dispositivo não é recalculada para um subconjunto arbitrário de URLs; quando o universo original não está contido no filtro, o valor é omitido e a limitação é declarada.

A análise de evolução exige pelo menos dois `AUD-*` elegíveis. O usuário pode selecionar:

```text
FIRST_LAST       primeira auditoria x última auditoria do período
LATEST_PREVIOUS  auditoria anterior x última auditoria
MANUAL           baseline/current escolhidos explicitamente
```

Mobile e Desktop permanecem separados quando o sinal possui escopo de dispositivo.

## Evolução determinística

`CONSOLIDATED-EVOLUTION-001` reutiliza o RASAi Monitor e Quality/Fix Verification. Os estados de mudança podem incluir `IMPROVED`, `RESOLVED`, `REGRESSED`, `NEW`, `CHANGED`, `DATA_UNAVAILABLE` e `NOT_COMPARABLE`.

A seção responde, sem IA:

- quais sinais melhoraram;
- quais regrediram;
- quais novos problemas surgiram;
- quais condições passaram de FAIL/WARNING para PASS;
- quais condições continuam `NOT_FIXED`, `PARTIALLY_FIXED` ou `NOT_VERIFIABLE`;
- valores antes/depois, delta, URL, dispositivo e regra quando disponíveis;
- limitações de comparabilidade.

A linguagem diferencia obrigatoriamente:

```text
melhora observada != correção verificada
correção verificada != impacto causal em Search/IA
```

`FIXED` prova apenas a transição persistida da regra entre os dois `AUD-*` selecionados. Não prova que a correção causou melhora de ranking, tráfego, conversão ou visibilidade em IA.

## Análise especialista por IA

A análise `CONSOLIDATED-SPECIALIST-001` é opcional, advisory e non-scoring. Ela interpreta apenas o pacote de mudanças e Fix Verification já calculado pelo RASAi.

Tópicos previstos:

- SEO;
- GEO / AI Readiness;
- Performance;
- UX / Apdex;
- Acessibilidade;
- Infraestrutura;
- Segurança passiva;
- Conteúdo e semântica.

A resposta estruturada da IA inclui síntese, avaliação por tópico, prioridade, confiança, próximas ações e `evidence_ids`. O contrato rejeita referências a evidências que não tenham sido fornecidas no request.

São proibidas alegações causais não demonstradas. Formulações como "a correção aumentou o ranking" não são aceitas somente por coincidência temporal. O texto deve usar conceitos como observado, comparável, verificado e associação temporal quando apropriado.

### Seleção de provider

O consolidado reutiliza a seleção de IA já ativa no console. Não existe um registry paralelo.

- `none`: relatório gerado sem IA;
- provider explícito: usa provider/model/reasoning configurados;
- `auto`: reutiliza o roteamento canônico cost-aware do RASAi, incluindo elegibilidade, preço por horário/contexto, modelo, reasoning e circuit breaker/quarentena.

A feature não altera a lógica de quarentena.

### Prévia e confirmação de custo

Antes de qualquer chamada externa de IA, o console calcula uma estimativa usando o mesmo catálogo e a mesma função canônica de custo do roteamento AUTO.

A prévia informa, conforme disponível:

- provider;
- modelo;
- reasoning;
- tokens de input/output estimados;
- contexto tarifário;
- versão do catálogo de preços;
- custo estimado;
- ranking de candidatos quando a seleção é `AUTO`.

A estimativa não é fatura. Usage real, cache, fallback e políticas do provider podem alterar o custo observado.

A chamada externa só ocorre após confirmação explícita. Se o usuário negar, ou se não houver IA configurada/apta, o consolidado continua normalmente sem a seção especialista por IA.

## SARI-001 e SCORE-GEO-004

O índice público permanece **SARI-001 - Search & AI Readiness Index** e o motor vigente para novas auditorias permanece **SCORE-GEO-004**.

O consolidado não recalcula o Overall do período. Ele lê de cada `AUD-*` os valores já persistidos de Score, Coverage, Confidence, Consolidation, Critical Gates e `scoring_version`.

Séries de score exigem compatibilidade de versão metodológica e universo de URLs. `NOT_APPLICABLE`, ausência de evidência, `UNKNOWN` e `ERROR` não são tratados como zero.

## Comparabilidade histórica

O consolidado segmenta ou sinaliza, conforme o domínio:

- `scoring_version` e universo de URLs para readiness;
- dispositivo;
- URL para métricas page-level;
- metodologia lab/field e fonte/escopo para Web Performance;
- tipo de Apdex, task/KPM, perfil, thresholds, sessão/política de erros e pacing relevante;
- mix de dispositivos quando a série Experience usa `POPULATION`;
- versão do auditor/ruleset quando materialmente relevante.

Mudança material de contexto cria outra série em vez de contaminar a série anterior.

## Políticas estatísticas gerais

- não existe interpolação de datas sem auditoria;
- extremos não são descartados automaticamente;
- não há trimming, winsorization ou remoção por IQR/desvio-padrão apenas por distância da média;
- média, mediana, mínimo e máximo usam somente observações elegíveis/comparáveis;
- para métricas page-level, estado inicial/atual é resolvido por URL antes da agregação transversal;
- percentis externos ou já agregados não são tratados como amostras brutas.

### Quantidade de auditorias

| Base | Interpretação |
|---|---|
| 1 AUD | **Snapshot**; não caracteriza tendência e não produz comparação especialista |
| 2 AUDs | **Comparação de dois pontos**; variação não equivale a tendência |
| 3+ AUDs comparáveis | **Série histórica descritiva**; não atribui causalidade |

## Web Performance

Permanecem separados por metodologia:

- Lighthouse Performance/Acessibilidade/Boas práticas/SEO;
- FCP, Speed Index, LCP, TBT e CLS de laboratório;
- LCP p75, INP p75 e CLS p75 de campo;
- Core Web Vitals assessment;
- fonte e escopo do dado de campo.

Lab e field data não são fundidos como se fossem a mesma população.

## Apdex temporal

Synthetic Navigation Apdex e Synthetic User Experience Apdex permanecem domínios distintos.

Para cada série comparável, o **Apdex do período** é recalculado pelas contagens persistidas:

```text
Apdex_periodo =
  (sum Satisfied + 0,5 x sum Tolerating)
  / sum amostras_validas
```

Percentis não são aditivos. `TEMPORAL-APDEX-001` usa as amostras brutas comparáveis para recalcular média, mediana/p50, p75, p90, p95, p99, mínimo/máximo, desvio-padrão e coeficiente de variação.

A série é por URL e contexto. URLs diferentes não são juntadas em um único pool de tempos. Navigation preserva `T/4T`; Experience preserva KPM, thresholds, sessão, política de erros e população efetiva.

## Ocorrências e confiabilidade analítica

O consolidado pode exibir volume, severidade, categoria, páginas afetadas e evolução. O volume deve ser interpretado junto ao universo auditado; mais páginas podem gerar mais findings sem representar piora proporcional. Findings não recalculam SARI/SCORE-GEO.

O consolidado apresenta, conforme disponível, fidelidade à fonte, comparabilidade metodológica, suficiência da base histórica, Coverage/Confidence persistidas, robustez/amostragem de Apdex, status de Consolidation persistido e limitações explícitas.

## Relação com RASAi Monitor e Quality

`CONS-*` compõe capacidades já existentes, sem duplicar metodologia:

- consolidado: exploração histórica e estatística descritiva;
- Monitoring: baseline/current e deltas determinísticos;
- Fix Verification: prova de transição persistida da regra;
- IA especialista: interpretação/priorização opcional sobre os deltas já calculados.

Nenhuma dessas superfícies altera o `audit.db` fonte.

## Relação com Search & AI Observability

Dados pós-auditoria como Search Console, URL Inspection, CrUX History e imports observacionais ficam em `observability.db`/artifacts próprios. Eles não são copiados para o consolidado como se fossem evidência original do AUD nem entram automaticamente em SARI/SCORE-GEO.

## Agendamento e SaaS

O scheduler/control plane já é suficiente para gerar N execuções independentes em horários distintos. Não é necessária migração de schema SaaS para `TEMPORAL-APDEX-001`, `CONSOLIDATED-EVOLUTION-001` ou `CONSOLIDATED-SPECIALIST-001`.

Na implementação atual, a geração interativa de `CONS-*` continua exposta no console local. A lógica de evolução, preview de custo e análise foi mantida em módulos independentes de `input()` para que uma futura Web API possa reutilizar o mesmo contrato. Não deve ser criado um caminho SaaS alternativo que recalcule deltas, preço ou roteamento de IA com regras próprias.

Ao expor essa capacidade no SaaS, o endpoint deverá manter duas etapas explícitas para IA: preview de custo e confirmação/autorização antes da execução. Secrets continuam no secret store/runtime e nunca fazem parte do request persistido de consolidação.

Para uma campanha temporal, os jobs devem manter o contexto metodológico comparável e variar principalmente a janela de execução.

## Snapshot, fingerprint e dedupe

O fingerprint é derivado de:

```text
report_format_version
+ TEMPORAL-APDEX-001
+ filtros canônicos
+ seleção de comparação
+ opção/configuração não secreta da análise especialista
+ fingerprint do conjunto de AUDs
```

Assim, um consolidado com IA nunca é reutilizado silenciosamente quando o usuário pede um consolidado sem IA, e vice-versa.

Regras:

- mesma requisição + mesmas fontes + mesmos contratos: reutiliza o snapshot;
- novo AUD, novo filtro, novo par de comparação ou mudança de análise: novo snapshot;
- artifacts antigos não são reescritos para incorporar a nova análise.

## Saída estática

```text
audits/consolidated/CONS-*/
    report.html
    manifest.json
    specialist-analysis.json
```

`specialist-analysis.json` é derivado e não contém credenciais. O HTML final é estático e não relê bancos nem chama APIs ao ser aberto.

## Reversão e segurança

A feature é derivada. Remover `.rasai/consolidated-index.db` e/ou `consolidated/CONS-*` não remove evidência dos `AUD-*`; tudo pode ser reconstruído a partir das fontes imutáveis.

## Gate de integração

Mudanças do consolidador devem validar, no mínimo:

- testes específicos e regressões de consolidação;
- hashes dos `audit.db` inalterados;
- segregação de contextos incompatíveis;
- percentis do período calculados do pool bruto quando aplicável;
- evolução calculada por Monitoring/Fix Verification, não pela IA;
- preview de custo antes da autorização da IA;
- fallback sem IA quando não configurada/indisponível/negada;
- roteamento `AUTO` usando a política canônica de custo e quarentena;
- HTML reabrível, estático e com demais seções preservadas;
- manifest/fingerprint coerentes;
- ausência de dependência do audit runner em consolidação/monitoring/observability.

Testes de console/runtime local são direcionados a Windows. Testes de control plane/SaaS permanecem direcionados a Linux quando houver mudança pertinente ao SaaS.

Veja também [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md), [`CONSOLIDATED_REPORTING_TEMPORAL.md`](CONSOLIDATED_REPORTING_TEMPORAL.md), [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`REPORT_GUIDE.md`](REPORT_GUIDE.md).
