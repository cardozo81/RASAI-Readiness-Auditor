# Relatórios históricos e consolidados

## Objetivo

A funcionalidade reúne indicadores já persistidos em auditorias `AUD-*` e gera um snapshot HTML estático para análise por domínio, período, dispositivo e URL.

Ela é deliberadamente independente do pipeline de auditoria.

## Garantias de arquitetura

- `AUD-*/audit.db` permanece a fonte de verdade;
- cada banco fonte é aberto com SQLite `mode=ro` e `PRAGMA query_only=ON`;
- nenhuma API externa é chamada durante indexação, filtro, cálculo ou geração do consolidado;
- `searchgeo audit`, scoring, persistence, PageSpeed/CrUX, IA e Synthetic Apdex não dependem do consolidador;
- nenhum schema de `audit.db` é migrado ou alterado;
- falha do consolidador é `fail-open` em relação ao console existente;
- o índice analítico é derivado, descartável e reconstruível;
- relatórios `CONS-*` são snapshots derivados e não substituem `AUD-*`.

```text
AUD-*/audit.db (fonte oficial, somente leitura)
        |
        v
.searchgeo/consolidated-index.db (cache analítico reconstruível)
        |
        v
filtros + comparabilidade + estatística descritiva
        |
        v
consolidated/CONS-*/report.html + manifest.json
```

## Acesso pelo console

```text
C. Histórico / relatórios consolidados [OFFLINE | sem APIs]
```

O fluxo seleciona de forma dependente:

1. domínio;
2. período;
3. dispositivo;
4. filtro opcional de URL/caminho;
5. geração.

Mobile e Desktop permanecem séries separadas.

## Índice analítico

O índice é gravado em:

```text
audits/.searchgeo/consolidated-index.db
```

Ele contém somente projeções necessárias para consulta histórica: metadados, domínios, URLs, dispositivos, versões, pontuações, cobertura, confiança, Web Performance/Lighthouse/CrUX, Apdex e ocorrências já persistidas.

Não existe evidência exclusiva no índice. Sua exclusão não perde dados: a próxima atualização o reconstrói a partir dos `audit.db`.

### Atualização incremental

Cada `audit.db` recebe fingerprint técnico. Fontes sem mudança são reaproveitadas; fontes novas/alteradas são reindexadas; entradas removidas do filesystem saem do cache. Um AUD inválido não interrompe os demais.

## Elegibilidade e filtros

Somente auditorias com `status=COMPLETED` participam.

Data efetiva:

```text
completed_at -> started_at -> created_at
```

Os limites de período são inclusivos.

### Filtro por URL

Web Performance, Apdex e ocorrências page-level são filtrados diretamente por URL.

A Compatibilidade GEO é persistida em nível de auditoria/dispositivo/dimensão. Portanto, um filtro parcial de URL não pode receber uma pontuação originalmente calculada com páginas que ficaram fora do filtro. Nesses casos o score audit-level é omitido; o consolidador nunca reexecuta o scoring para fabricar um valor por URL.

## SCORE-GEO no consolidado

### Versão exibida

A interface usa o rótulo **Versão do método de pontuação**. O identificador persistido vigente é `SCORE-GEO-002`.

`SCORE-GEO-001` não é exibido como métrica concorrente nem recalculado em relatórios atuais. Se uma fonte histórica futura contiver outra versão persistida, a versão será tratada como quebra metodológica e não misturada silenciosamente.

### Natureza

`SCORE-GEO-002` é um método interno, determinístico e reproduzível do SearchGEO. Não é score oficial de Google, OpenAI ou outro mecanismo e não possui validação estabelecida como preditor de ranking, tráfego ou citação por sistemas generativos.

### Aritmética

No baseline atual:

1. regras aplicáveis produzem `PASS`, `WARNING`, `FAIL`, `UNKNOWN`, `ERROR` ou `NOT_APPLICABLE`;
2. `PASS` contribui com fator `1`;
3. `WARNING` usa fator padrão `0,5`;
4. `FAIL` contribui com fator `0`;
5. grupos correlacionados evitam dupla penalização da mesma causa;
6. score da dimensão = `soma(peso × fator) / soma dos pesos avaliados × 100`;
7. cobertura da dimensão = `peso avaliado / peso aplicável`;
8. dimensão legitimamente não aplicável não recebe `0` nem `100` e fica fora do denominador geral;
9. Compatibilidade GEO geral = média aritmética simples das dimensões aplicáveis suficientemente consolidadas;
10. cobertura geral = média das coberturas dessas dimensões.

### Confiança

A `Confidence` persistida representa força/cobertura da conclusão, não qualidade do website:

- Alta: cobertura >= 90%, evidência completa e nenhum erro;
- Média: cobertura >= 80% e nenhum erro;
- Baixa: demais casos mensuráveis;
- Indisponível: sem cobertura mensurável.

A confiança geral é conservadora e adota o menor nível entre as dimensões aplicáveis.

## Políticas estatísticas

- dado ausente nunca vira zero;
- Mobile e Desktop não são combinados silenciosamente;
- versões metodológicas incompatíveis são segregadas;
- pontuação histórica usa mesma versão do método e mesmo universo de URLs comparável;
- não existe interpolação de datas sem auditoria;
- **nenhum extremo é descartado automaticamente** apenas por ser mínimo, máximo ou distante da média;
- não há trimming, winsorization, corte por IQR/desvio-padrão ou outro descarte de outliers por valor;
- média = média aritmética das observações elegíveis;
- mediana = valor central das observações elegíveis;
- mínimo e máximo permanecem visíveis.

### Estado inicial e atual em métricas por URL

Para métricas page-level, o estado inicial usa a primeira observação válida de cada URL e o estado atual usa a última observação válida de cada URL; depois é feita a média transversal. Isso impede uma URL auditada mais vezes de representar sozinha o estado do domínio.

## Modos históricos do HTML

O relatório se adapta à quantidade de auditorias:

| Base | Comportamento |
|---|---|
| 1 AUD | **Snapshot**; não sugere tendência e oculta estatísticas redundantes por padrão |
| 2 AUDs | **Comparação de dois pontos**; mostra variação, mas declara que não caracteriza tendência |
| 3+ AUDs comparáveis | **Série histórica descritiva**; gráficos podem ser exibidos sem atribuição causal |

Gráficos usam somente observações efetivamente persistidas e compatíveis.

## Visualizações e navegação

O HTML `CONS-2` possui navegação fixa entre:

- Resumo;
- Evolução;
- Compatibilidade GEO;
- Desempenho;
- Apdex;
- Ocorrências;
- Confiabilidade;
- Auditorias;
- Metodologia.

### Compatibilidade GEO e dimensões

A visão principal prioriza:

- valor atual;
- cobertura;
- confiança;
- estado de consolidação;
- N;
- versão do método.

Média, mediana, mínimo, máximo e variações ficam em uma área expansível. A tabela possui filtro textual e altura controlada.

Quando há base comparável suficiente, são gerados:

- gráfico de Compatibilidade GEO + Cobertura ao longo do tempo;
- matriz histórica das dimensões.

### Auditorias consideradas

A tabela de proveniência possui:

- pesquisa local;
- paginação local;
- 25/50/100 linhas por página;
- cabeçalho fixo;
- nenhum acesso a servidor/API para filtrar ou paginar.

### Ocorrências

São exibidos total, páginas afetadas, distribuição por severidade/categoria e evolução do volume bruto quando há pelo menos dois AUDs. O report avisa que quantidade bruta deve ser interpretada junto com o tamanho do universo auditado.

## Web Performance

São consolidados quando persistidos:

- Lighthouse Performance/Acessibilidade/Boas práticas/SEO;
- FCP, Speed Index, LCP, TBT e CLS de laboratório;
- LCP p75, INP p75 e CLS p75 de campo;
- Core Web Vitals assessment;
- fonte/escopo dos dados de campo.

Dados de laboratório e de campo permanecem separados.

## Apdex sintético

Apdex só é agregado entre mesmo dispositivo, perfil e T compatíveis:

```text
sum(apdex_score * valid_samples) / sum(valid_samples)
```

A interface destaca quando existem somente grupos com amostra pequena (`small_group`) e nenhum `final_group`, evitando interpretar `1,000` com poucas amostras como evidência robusta.

## Confiabilidade analítica do consolidado

O relatório não cria outro score numérico arbitrário. Em vez disso apresenta matriz com:

- fidelidade às fontes;
- comparabilidade metodológica;
- suficiência da base histórica;
- Confidence/Coverage persistidas;
- robustez do Apdex;
- situação da validação externa do SCORE-GEO.

Essa matriz diferencia **dados fiéis** de **base estatisticamente suficiente**.

## Metodologia e base técnica no HTML

O final do relatório documenta:

- fonte dos dados;
- versão do método;
- fórmula de Score e Coverage;
- regra de Confidence;
- média/mediana/mínimo/máximo;
- política de outliers/extremos;
- comparabilidade de URL/versionamento;
- política Apdex;
- ausência de interpolação;
- limitações detectadas;
- referências técnicas internas e públicas.

Referência normativa interna principal:

```text
docs/specification/19_SCORE_APPLICABILITY_GEO_MINIMUMS.md
```

Referências externas apresentadas no HTML incluem documentação oficial do Google Search, Web Vitals e Apdex.

## Relatório estático

Cada resultado novo é salvo em:

```text
audits/consolidated/CONS-YYYYMMDD-HHMMSS-mmm/
    report.html
    manifest.json
```

`report.html` é autocontido quanto aos dados. JavaScript local é usado somente para interação de tabela; abrir o arquivo não relê bancos nem chama APIs.

O `manifest.json` registra também:

- modo histórico (`Snapshot`, comparação ou série);
- versões do método encontradas;
- políticas de agregação;
- política de dados ausentes;
- política de extremos;
- ausência de interpolação.

## Dedupe

Um `CONS-*` existente é reutilizado somente se permanecerem idênticos:

```text
versão do formato
+ filtros canônicos
+ fingerprint do conjunto de AUDs elegíveis
```

`CONS-2` invalida corretamente snapshots `CONS-1` quando o layout/metodologia muda.

## Reversão segura

Para remover a feature após eventual merge:

1. reverter o commit/PR da feature;
2. opcionalmente remover `.searchgeo/consolidated-index.db`;
3. opcionalmente arquivar/remover `consolidated/`;
4. nenhum `AUD-*/audit.db` precisa ser restaurado ou migrado.

Se o merge for autorizado, recomenda-se `Squash and merge` para materializar toda a feature em um único commit reversível.

## Gate de merge

Não integrar em `main` sem:

- testes específicos verdes;
- testes existentes de console/configuração verdes;
- hashes dos bancos fonte inalterados;
- ausência de import/acoplamento no audit runner, scoring e persistence;
- diff restrito à feature, documentação, testes, CI e adapter mínimo do console;
- ausência de chamadas de rede no pacote `consolidation`;
- smoke humano do HTML em base real.
