# Relatórios históricos e consolidados

## Objetivo

O consolidador reúne indicadores **já persistidos** em auditorias `AUD-*` e gera um snapshot HTML estático para análise por domínio, período, dispositivo e URL. Ele é independente do pipeline de auditoria e não reexecuta coleta, regras, IA ou scoring.

## Garantias de arquitetura

- `AUD-*/audit.db` permanece a fonte de verdade de cada auditoria;
- bancos fonte são abertos em modo somente leitura;
- nenhuma API externa é chamada para gerar um `CONS-*`;
- nenhum schema de `audit.db` é migrado pelo consolidador;
- `.rasai/consolidated-index.db` é cache derivado, descartável e reconstruível;
- falha do consolidador é `fail-open` para `rasai audit` e para o console;
- relatórios `CONS-*` não substituem `AUD-*`;
- Mobile e Desktop permanecem séries distintas;
- versões de scoring incompatíveis nunca são fundidas silenciosamente.

```text
AUD-*/audit.db (fonte oficial, read-only)
        |
        v
.rasai/consolidated-index.db (cache reconstruível)
        |
        v
filtros + comparabilidade + estatística descritiva
        |
        v
consolidated/CONS-*/report.html + manifest.json
```

## Elegibilidade e filtros

Somente auditorias concluídas participam. A data efetiva segue:

```text
completed_at -> started_at -> created_at
```

Os limites de período são inclusivos.

Web Performance, Apdex e ocorrências page-level podem ser filtrados diretamente por URL. Readiness persistida em nível de auditoria/dispositivo não é recalculada para um subconjunto arbitrário de URLs: quando o universo do score não está contido no filtro, o valor é omitido e a limitação é declarada.

## SARI-001 e SCORE-GEO-004

### Método vigente

O índice público do RASAi é **SARI-001 - Search & AI Readiness Index**. O motor de scoring vigente para novas auditorias é **`SCORE-GEO-004`**.

Séries com contratos de scoring distintos permanecem segmentadas por `scoring_version` e não são convertidas ou agregadas silenciosamente.

### Dimensões

As dimensões de readiness continuam baseadas em regras aplicáveis, evidência, Coverage, Confidence e estado de consolidação. `PASS`, `WARNING`, `FAIL`, `UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são tratados como equivalentes. Ausência de aplicabilidade não é convertida em zero.

### Overall Readiness

No `SCORE-GEO-004`, o Overall é a média de igual peso das dimensões aplicáveis, desde que o contrato esteja suficientemente materializado. Dimensões legitimamente `NOT_APPLICABLE` saem do denominador; dimensões aplicáveis sem valor ou `NOT_CONSOLIDATED` impedem uma conclusão consolidada.

O consolidado **não recalcula** esse Overall. Ele lê o valor, Coverage, Confidence, Consolidation e `scoring_version` persistidos no AUD fonte.

`SCORE-GEO-003` permanece histórico e usava um model artifact calibrado. Um ponto 003 e um ponto 004 pertencem a contratos metodológicos distintos e não devem ser tratados como série contínua sem ressalva explícita.

### Confidence e Coverage

`Score`, `Coverage` e `Confidence` têm semânticas diferentes. Confidence qualifica a força da conclusão/evidência; não é sinônimo de qualidade do website. Coverage não pode substituir Score, e dado indisponível não pode ser apresentado como zero.

## Comparabilidade histórica

O consolidado deve segmentar ou sinalizar, no mínimo:

- `scoring_version`;
- versão do auditor/ruleset quando materialmente relevante;
- dispositivo;
- universo de URLs;
- perfil/threshold no caso de Apdex;
- fonte/escopo no caso de dados de campo.

Mudança de `scoring_version` define fronteira metodológica. Campos históricos de `model_version`/`dataset_version` podem existir em auditorias 003, mas não são requisitos do runtime 004.

## Políticas estatísticas

- dado ausente nunca vira zero;
- não existe interpolação de datas sem auditoria;
- extremos não são descartados automaticamente;
- não há trimming, winsorization ou remoção por IQR/desvio-padrão apenas por distância da média;
- média, mediana, mínimo e máximo usam somente observações elegíveis/comparáveis;
- para métricas page-level, o estado inicial/atual é resolvido por URL antes da agregação transversal, evitando que uma URL auditada mais vezes domine a série.

### Quantidade de auditorias

| Base | Interpretação |
|---|---|
| 1 AUD | **Snapshot**; não caracteriza tendência |
| 2 AUDs | **Comparação de dois pontos**; variação não equivale a tendência |
| 3+ AUDs comparáveis | **Série histórica descritiva**; não atribui causalidade |

## Web Performance

Quando persistidos, permanecem separados por metodologia:

- Lighthouse Performance/Acessibilidade/Boas práticas/SEO;
- FCP, Speed Index, LCP, TBT e CLS de laboratório;
- LCP p75, INP p75 e CLS p75 de campo;
- Core Web Vitals assessment;
- fonte e escopo do dado de campo.

Lab e field data não são fundidos como se fossem a mesma medição.

## Apdex

Synthetic Navigation Apdex e Synthetic User Experience Apdex permanecem domínios próprios. Agregações exigem compatibilidade de dispositivo, perfil e thresholds. Grupos pequenos continuam identificados e não devem ser interpretados como evidência robusta apenas porque o score é alto.

## Ocorrências

O consolidado pode exibir volume, severidade, categoria, páginas afetadas e evolução bruta. A quantidade de findings deve ser interpretada junto ao universo auditado; mais páginas analisadas podem produzir mais ocorrências sem representar piora proporcional.

## Confiabilidade analítica

O consolidador não cria um novo “score de confiabilidade”. Ele apresenta sinais como:

- fidelidade à fonte;
- comparabilidade metodológica;
- suficiência da base histórica;
- Coverage/Confidence persistidas;
- robustez/amostragem de Apdex;
- status de Consolidation persistido.

## Relação com RASAi Monitor

`CONS-*` e **RASAi Monitor** possuem propósitos diferentes:

- consolidado: exploração histórica/estatística descritiva;
- `rasai monitor compare`: comparação explícita baseline → current e classificação de mudança;
- `rasai monitor gate`: release gate determinístico;
- `rasai monitor impact`: associação temporal entre regressões e outcomes observados, sem atribuir causalidade.

Nenhuma dessas superfícies altera o `audit.db` fonte.

## Relação com Search & AI Observability

Dados coletados após a auditoria (Search Console, URL Inspection, CrUX History e imports observacionais suportados) são armazenados em `observability.db` + `artifacts/observability/`. Eles não entram automaticamente em SARI-001/SCORE-GEO-004 e não são copiados para o consolidado como se fossem evidência original do AUD.

## Saída estática

Cada snapshot novo é salvo em:

```text
audits/consolidated/CONS-*/
    report.html
    manifest.json
```

O manifest registra filtros, fingerprints, versões metodológicas e limitações relevantes. O HTML não relê bancos nem chama APIs ao ser aberto.

## Reversão e segurança

A feature é derivada: remover o cache consolidado e/ou os `CONS-*` não remove evidência dos `AUD-*`. Nenhum banco fonte precisa ser migrado ou restaurado.

## Gate de integração

Antes de integrar mudanças do consolidador/monitoramento em `main`, exigir:

- testes específicos e regressão existente verdes;
- hashes/bancos fonte não alterados por operações read-only;
- ausência de dependência do audit runner em consolidação/monitoring/observability;
- HTML reabrível e navegação consistente;
- comparabilidade entre `scoring_version` explícita;
- smoke humano quando a mudança exigir inspeção visual/operacional.
