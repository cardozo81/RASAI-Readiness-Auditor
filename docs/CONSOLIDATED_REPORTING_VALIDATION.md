# Validação e reversibilidade - relatórios consolidados

## Estado atual

O relatório consolidado faz parte do baseline de desenvolvimento em `main`. Este documento descreve o contrato que deve permanecer verdadeiro antes da aprovação de uma versão publicável do RASAi; referências a branches/PRs usados durante a implementação não definem o comportamento do produto.

Formato atual:

```text
CONS-3
```

A alteração do identificador de formato invalida dedupe de snapshots produzidos com estruturas anteriores de desenvolvimento quando a semântica do HTML/manifest não é equivalente. Isso é controle interno de reprodutibilidade, não histórico de releases públicas.

## Fonte de verdade e escrita

As fontes são os `AUD-*/audit.db`, abertos em modo somente leitura (`SQLite mode=ro` e `PRAGMA query_only=ON`). A consolidação não recalcula auditorias e não grava nos bancos fonte.

Artefatos derivados:

```text
.rasai/consolidated-index.db
consolidated/CONS-*/report.html
consolidated/CONS-*/manifest.json
```

O índice consolidado é reconstruível.

## Contrato comportamental CONS-3

- resumo executivo de SARI informa pontuação, Cobertura, Confiança e estado de Consolidação;
- score não consolidado é identificado como pontuação parcial, não como SARI consolidado;
- a dimensão atual mais fraca é lida do mesmo `audit_id` do Overall atual;
- séries SARI exigem mesma `scoring_version` e mesmo fingerprint do universo completo de URLs;
- filtro parcial de URL não recebe score calculado com URLs que ficaram fora do filtro;
- mudança de método de scoring permanece segmentada e não é normalizada silenciosamente;
- Lighthouse/lab e Core Web Vitals/field continuam domínios distintos;
- Apdex só é agregado entre mesmo perfil e mesmo `T`, ponderado por amostras válidas;
- grupos `small_group` sem grupo final permanecem diagnósticos de base insuficiente;
- evolução de findings usa **ocorrências por URL auditada** como série comportamental; contagem bruta é apenas contexto;
- dado ausente não vira zero;
- extremos não são eliminados automaticamente por valor;
- estados acionáveis seguem a mesma semântica visual dos relatórios individuais;
- métodos anteriores encontrados em bases de teste são referências de desenvolvimento não comparáveis ao `SCORE-GEO-004`, salvo quando o próprio contrato de comparabilidade provar o contrário.

## Estatística e comparabilidade

### Readiness Search & AI

Uma série numérica é agregada somente na combinação compatível mais recente de:

```text
scoring_version
+
fingerprint do conjunto completo de URLs da auditoria
```

`scoring_version` é apresentado ao usuário como **Versão do método de pontuação**.

### Média, mediana e extremos

- média = média aritmética das observações elegíveis;
- mediana = valor central das observações elegíveis;
- mínimo/máximo são preservados;
- não há trimming, winsorization nem descarte automático por IQR/desvio-padrão;
- `NULL`/ausência de dado não é imputado como zero.

### Desempenho Web

Para estados Inicial/Atual de métricas por URL, a consolidação usa a média transversal da observação válida mais antiga/recente de cada URL elegível, evitando que a URL mais frequentemente auditada represente sozinha o domínio.

### Apdex

O agregado exige mesmo perfil sintético e mesmo limiar `T`. O valor é ponderado por amostras válidas. Coeficiente de variação é diagnóstico de estabilidade e não entra na fórmula Apdex. Consulte [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md).

### Ocorrências

Findings não recalculam SCORE-GEO. Para comparar auditorias de escopos diferentes, o gráfico comportamental usa `quantidade de findings / quantidade de URLs auditadas`. A contagem absoluta permanece disponível para dimensionar volume operacional.

## Metodologia e transparência

O HTML mostra somente versões realmente persistidas nas fontes selecionadas. `SCORE-GEO-004` é o contrato vigente para novas auditorias. Dados criados por propostas anteriores durante o desenvolvimento permanecem identificados por sua `scoring_version` e não são apresentados como versões públicas anteriormente lançadas.

O consolidado não deve afirmar validação externa do SARI/SCORE-GEO como preditor de ranking/citação. Fontes públicas sustentam métricas/domínios específicos, não homologam o índice proprietário.

## Dedupe

Exige igualdade de:

```text
report_format_version
+ filtros canônicos
+ conjunto/fingerprint dos AUDs elegíveis
```

Assim:

- mesma requisição + mesmas fontes: pode reutilizar;
- novo AUD elegível: novo snapshot;
- mudança de filtro: novo snapshot;
- mudança de formato: novo snapshot.

## Gates automatizados

Workflow principal da feature consolidada:

```text
.github/workflows/consolidated-reporting-ci.yml
```

O gate deve cobrir, no mínimo:

- geração read-only e hash dos `audit.db` inalterado;
- dedupe e invalidação por novo AUD/filtro/formato;
- segregação de método e universo de URLs;
- Snapshot com `N=1` sem falsa tendência;
- série histórica somente quando comparável;
- Apdex com regra de perfil + `T`;
- findings normalizados por URL;
- HTML/manifest com metodologia e limitações;
- regressões do console/configuração;
- contrato público de relatórios.

## Smoke humano

Após atualizar o checkout local de `main`:

1. abrir `iniciar.cmd`;
2. confirmar navegação normal do console;
3. gerar consolidado com 1 AUD e confirmar **Snapshot**;
4. gerar com 2 AUDs comparáveis e confirmar comparação sem afirmar tendência robusta;
5. gerar com 3+ AUDs comparáveis e validar gráfico/matriz;
6. conferir SARI, Cobertura, Confiança e Consolidação contra pelo menos um `audit.db`;
7. validar Apdex e indicação de amostra pequena quando aplicável;
8. validar evolução de ocorrências por URL e conferir o volume bruto contextual;
9. testar pesquisa/paginação das auditorias consideradas;
10. repetir mesmos filtros e confirmar dedupe;
11. comparar hash do `audit.db` antes/depois;
12. abrir o HTML com o console fechado e confirmar funcionamento estático.

## Reversibilidade

O consolidado é derivado. Em caso de falha, a reversão não exige migração dos `AUD-*`: os artefatos `consolidated/CONS-*` e o índice derivado podem ser reconstruídos a partir das fontes.

Veja também [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md), [`REPORT_GUIDE.md`](REPORT_GUIDE.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md).
