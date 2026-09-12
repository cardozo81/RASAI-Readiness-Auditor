# Web Platform Baseline / WebDX no RASAi

## Objetivo

O RASAi possui uma capacidade advisory denominada **Web Platform Baseline / WebDX**. O objetivo é relacionar recursos da Web usados por uma página com o dataset versionado do projeto `web-platform-dx/web-features`, permitindo futuramente classificar compatibilidade em estados como **Widely Available**, **Newly Available** e **Limited Availability**.

Esta capacidade é separada de `SARI-001` e `SCORE-GEO-004`; não altera scoring.

Referência oficial do dataset:

- https://github.com/web-platform-dx/web-features

## Variáveis relacionadas

### `RASAI_WEB_PLATFORM_BASELINE`

Controla se a capacidade Web Platform Baseline é solicitada.

Valores canônicos no console:

- `true`
- `false`

O serviço possui default solicitado como `true`, mas só fica efetivamente configurado quando os seus requisitos técnicos estão presentes.

### `RASAI_WEB_FEATURES_DATASET`

Informa o **caminho local para um arquivo de dataset versionado** relacionado ao projeto `web-features`.

Esta variável **não é um enum**. Não existe uma lista de nomes como `stable`, `latest` ou `2026` aceita pelo runtime.

O valor permitido é:

> qualquer caminho para um arquivo existente e legível pelo processo do RASAi.

Exemplo Windows:

```text
C:\dados\web-features\web-features.json
```

Exemplo Linux:

```text
/opt/rasai/datasets/web-features/web-features.json
```

O console valida a existência do arquivo. Caminho inexistente é rejeitado.

A variável não é sensível e pode ser persistida no `rasai-console.ini`.

## Estado atual da implementação

O contrato atual distingue **dataset configurado** de **análise Baseline materializada**.

No estado atual do runtime:

1. `RASAI_WEB_FEATURES_DATASET` é validada como caminho de arquivo existente;
2. a referência ao dataset é registrada como parte do estado da capacidade;
3. o RASAi **ainda não possui um pipeline versionado completo que detecte quais Web Features a página utiliza e faça o mapeamento dessas features para o dataset**;
4. por esse motivo, mesmo com um arquivo configurado, a execução Web Platform Baseline permanece `NO_DATA` até que o detector/mapeador seja implementado.

Portanto, configurar a variável hoje **não significa que o RASAi já produz uma classificação Baseline por página**.

## Estados esperados

- `DISABLED`: a capacidade foi explicitamente desligada.
- `NOT_CONFIGURED`: a capacidade foi solicitada, mas falta `RASAI_WEB_FEATURES_DATASET`.
- `NO_DATA`: o requisito de dataset está configurado, porém ainda não há materialização de resultado porque o pipeline de detecção/mapeamento não está implementado.
- `READY`/resultado materializado: reservado para a evolução em que o detector e o mapeamento versionado estiverem implementados e validados.

## Por que não inferir automaticamente

O RASAi não deve deduzir compatibilidade de Web Features apenas por heurística textual ou por presença genérica de JavaScript/CSS. Uma classificação Baseline confiável exige pelo menos:

- detector determinístico de uso de features;
- identificadores compatíveis com o dataset `web-features`;
- versão/pin do dataset utilizada na auditoria;
- evidência rastreável entre feature detectada e classificação retornada;
- tratamento de features condicionais, polyfills e uso indireto;
- testes de regressão contra páginas controladas.

Enquanto esse pipeline não existir, `NO_DATA` é preferível a inventar uma conclusão de compatibilidade.

## Recomendação operacional atual

Para uso normal do RASAi, deixe `RASAI_WEB_FEATURES_DATASET` sem valor, a menos que esteja homologando especificamente esta capacidade ou preparando o ambiente para a futura materialização Baseline.

A ausência da variável não deve ser interpretada como problema do website auditado; é apenas uma capacidade opcional não configurada do ambiente RASAi.
