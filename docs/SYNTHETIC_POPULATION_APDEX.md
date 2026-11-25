# Synthetic Population Apdex

## Objetivo

Synthetic Population Apdex é uma camada opcional e aditiva de **CAT-07**. Ela mede o mesmo contrato de experiência sintética sob uma população **estratificada, ponderada e reproduzível** de condições de cliente, CPU, rede e sessão.

Ela não substitui Synthetic Navigation Apdex / CAT-06, o Apdex Experience baseline do CAT-07, SCORE-GEO-004 ou RUM real. A versão inicial do runtime é `SYNTHETIC-POPULATION-001`.

## Ativação

A camada só executa com Synthetic User Experience Apdex habilitado.

```text
--apdex-experience
--apdex-population-profile-json JSON

RASAI_APDEX_POPULATION_PROFILE_JSON=<objeto JSON>
```

Sem perfil populacional, CAT-07 mantém exatamente o comportamento baseline.

## Contrato do perfil

```json
{
  "population_profile_id": "POP-MOBILE-BR-1",
  "profile_version": "1",
  "weight_source": "ANALYTICS",
  "weight_source_ref": "analytics-export-2026-10",
  "target_samples_per_page": 100,
  "strata": [
    {
      "stratum_id": "constrained",
      "weight": 35,
      "device": "MOBILE",
      "client_profile_id": "mobile-balanced-chromium",
      "hardware_profile_id": "mobile-entry",
      "network_profile_id": "mobile-3g-constrained",
      "session_mode": "cold"
    },
    {
      "stratum_id": "balanced",
      "weight": 65,
      "device": "MOBILE",
      "client_profile_id": "mobile-balanced-chromium",
      "hardware_profile_id": "mobile-balanced",
      "network_profile_id": "mobile-4g-balanced",
      "session_mode": "warm"
    }
  ]
}
```

O perfil exige ID e versão, pelo menos dois estratos, pesos positivos somando 100, presets existentes e sessão `cold` ou `warm`. Campos não reconhecidos são rejeitados para impedir semântica implícita.

## Device e dimensões

A V1 mantém o **mesmo device da AUD** em todos os estratos:

```text
AUD mobile  -> todos os estratos MOBILE
AUD desktop -> todos os estratos DESKTOP
```

Não há mix Mobile/Desktop e Tablet não é opção para novas populações.

Cada estrato pode variar perfil de cliente, slowdown relativo de CPU, envelope de rede e sessão. Concorrência e delay são guardrails operacionais, não dimensões populacionais.

A V1 não usa jitter aleatório e não modela geografia. Coordenadas de geolocalização do navegador não representam região física do runner, rota de rede, CDN/POP ou latência geográfica.

## Origem dos pesos

`weight_source` aceita:

```text
RUM
DYNATRACE_RUM
ANALYTICS
CRUX
BENCHMARK
RASAI_OPERATOR
```

Fontes observadas/externas exigem `weight_source_ref`, que identifica dataset, exportação, período ou referência metodológica. `RASAI_OPERATOR` representa ponderação deliberada e não deve ser apresentada como distribuição observada de usuários.

## Alocação

O target por página é distribuído deterministicamente pelos pesos. Cada estrato recebe no mínimo uma amostra; o restante usa maior resto com desempate estável por `stratum_id`.

Não existe sorteio por amostra e não existe seed porque a V1 não usa randomização.

## Métricas

Cada estrato usa a classificação CAT-07 existente:

```text
SATISFIED  -> 1.0
TOLERATING -> 0.5
FRUSTRATED -> 0.0
```

```text
Apdex_h = (Satisfied_h + 0.5 × Tolerating_h) / N_h
Apdex_population = Σ(weight_h × Apdex_h) / Σ(weight_h observado)
```

O somatório inclui somente estratos com amostras válidas. O estado é completo quando todos alcançam as respectivas metas; parcial quando há amostras válidas, mas ao menos uma meta não foi alcançada; indisponível quando não há amostras válidas. O percentual de peso observado é registrado. Se nenhum estrato tiver amostra válida, não há indicador numérico. Exemplo: estrato A com peso 60% e Apdex 0,90; estrato B com peso 40% sem amostras válidas. O resultado observado é 0,90, com somente 60% de peso observado, e não 0,54 nem uma conclusão sobre toda a população.

Também são persistidos S/T/F, shares ponderadas, mediana, P75/P90/P95 e um IC95 amostral aproximado do Apdex.

## Incerteza e representatividade

O IC95 mede **incerteza amostral condicionada aos estratos e pesos fixados**. Ele não mede erro do dataset de pesos, viés de seleção, usuários não representados, variação geográfica não modelada nem a diferença entre laboratório e tráfego real.

O relatório mantém separados o percentual de peso observado, a provenance dos pesos e a incerteza amostral.

## Persistência e RPR

Tabelas próprias:

```text
synthetic_population_apdex_runs
synthetic_population_apdex_samples
synthetic_population_apdex_strata
synthetic_population_apdex_summaries
```

As tabelas `synthetic_ux_apdex_*` do baseline não são substituídas.

A run populacional persiste profile ID/versão, versão do runtime, origem dos pesos, device, target, KPM, versão da fronteira temporal, estratos e política de execução.

O RPR reconstrói o perfil a partir da configuração congelada da AUD. Se a população já estiver concluída, ela não é refeita apenas porque presets atuais da máquina mudaram. Se a população necessária estiver ausente ou não concluída, a recuperação usa o perfil congelado; eventual falha permanece fail-open para o baseline.

## Relatório

`report-catalog/cat-07.html` mantém baseline e população em blocos separados e mostra Apdex ponderado, peso observado, IC95 amostral, percentis, estratos, pesos, presets, origem dos pesos e versões metodológicas.

A apresentação declara que Synthetic Population Apdex **não é RUM** e que a V1 não modela geografia de rede.

## Fronteiras

Falha da camada populacional não invalida o baseline CAT-07. A camada não altera CAT-06, scoring, IA ou collectors fora da medição sintética existente.

A execução reutiliza gateway Chromium, perfis e classificação CAT-07; não existe um segundo motor de browser.
