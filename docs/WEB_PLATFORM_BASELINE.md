# Web Platform Baseline / WebDX no RASAi

## Objetivo

O RASAi possui uma capacidade advisory denominada **Web Platform Baseline / WebDX**. O objetivo é relacionar recursos da Web observados em uma página com o dataset versionado do projeto `web-platform-dx/web-features`, que define o modelo Baseline usado para classificar recursos como **Widely Available**, **Newly Available** e **Limited Availability**.

Esta capacidade é separada de `SARI-001` e `SCORE-GEO-004`; não altera scoring.

Referência oficial do dataset:

- <https://github.com/web-platform-dx/web-features>
- <https://web-platform-dx.github.io/web-features-project/>

## Modelo conceitual: global, não por domínio

O dataset `web-features` é uma **base canônica global da plataforma Web**. Ele não deve ser criado ou escolhido de forma diferente para cada domínio auditado.

A distinção é importante:

- **dataset-base**: catálogo/versionamento das Web Features e respectivos estados Baseline; é independente do domínio;
- **domínio/página auditada**: determina quais features estão efetivamente presentes ou utilizadas;
- **resultado Baseline**: nasce do cruzamento entre features detectadas na página e a versão do dataset usada na auditoria.

Portanto, características de `example.com`, `loja.com.br` ou qualquer outro domínio **não mudam o modelo-base**. O que muda é o conjunto de features detectadas naquela página.

## Variáveis relacionadas

### `RASAI_WEB_PLATFORM_BASELINE`

Controla se a capacidade Web Platform Baseline é solicitada.

Valores canônicos no console:

- `true`
- `false`

O default do RASAi é `true`. A capacidade permanece habilitada por padrão porque não exige credencial paga nem segredo. Um `false` explícito continua sendo respeitado como desligamento do operador.

### `RASAI_WEB_FEATURES_DATASET`

Seleciona a fonte do dataset WebDX/web-features.

Default canônico:

```text
RASAI_WEB_FEATURES_DATASET=auto
```

Valores aceitos:

1. `auto` — modo recomendado. Usa a política canônica de fonte WebDX gerenciada pelo RASAi e não exige que o usuário escolha um dataset específico por domínio;
2. caminho para um arquivo local existente — override avançado para fixar explicitamente um snapshot/versionamento em homologação, reprodução ou operação controlada.

Exemplo de override Windows:

```text
RASAI_WEB_FEATURES_DATASET=C:\dados\web-features\web-features.json
```

Exemplo de override Linux:

```text
RASAI_WEB_FEATURES_DATASET=/opt/rasai/datasets/web-features/web-features.json
```

A variável não é sensível e pode ser persistida no `rasai-console.ini`.

### O que `auto` significa hoje

`auto` é a **política de seleção da fonte**, não uma afirmação de que a compatibilidade já foi calculada. No estado atual do runtime, o pipeline completo de detecção e mapeamento das features utilizadas pela página ainda não está implementado. Consequentemente, `auto` evita uma configuração manual desnecessária, mas **não inventa resultados e não transforma `NO_DATA` em sucesso técnico fictício**.

Quando o detector/mapeador for materializado, o modo `auto` deverá resolver uma fonte canônica suportada e registrar versão/pin suficiente para reprodutibilidade. Um caminho local continuará disponível como override explícito.

## Comportamento no console

No uso normal, o usuário não deve receber `RASAI_WEB_FEATURES_DATASET` como configuração obrigatória pendente apenas porque não informou um caminho local. O default `auto` atende o contrato de configuração da fonte.

O console deve apresentar a variável como pertencente à capacidade **Web Platform Baseline / WebDX**, com as seguintes regras:

- default: `auto`;
- entrada aceita: `auto` ou caminho de arquivo existente;
- caminho inexistente: rejeitado;
- `RASAI_WEB_PLATFORM_BASELINE=true`: default habilitado;
- `RASAI_WEB_PLATFORM_BASELINE=false`: desligamento explícito prevalece.

O arquivo de fábrica `src/rasai/config/rasai-defaults.ini` contém ambos os defaults para que **Restaurar padrões** e uma instalação limpa sejam coerentes com essa política.

## Estado atual da implementação

O contrato distingue **fonte configurada** de **análise Baseline materializada**.

No estado atual do runtime:

1. `RASAI_WEB_FEATURES_DATASET=auto` é o default da fonte;
2. um caminho local existente pode substituir o modo `auto`;
3. a referência à fonte fica disponível ao estado da capacidade;
4. o RASAi **ainda não possui um pipeline versionado completo que detecte quais Web Features a página utiliza e faça o mapeamento dessas features para o dataset**;
5. por esse motivo, a execução Web Platform Baseline permanece `NO_DATA` enquanto o detector/mapeador não estiver implementado.

Portanto, uma fonte configurada hoje **não significa que o RASAi já produz uma classificação Baseline por página**.

## Estados esperados

- `DISABLED`: a capacidade foi explicitamente desligada.
- `READY`: requisitos mínimos de configuração da capacidade estão presentes; no console padrão isso inclui a política de fonte `auto`.
- `NO_DATA`: a capacidade está configurada, mas ainda não há resultado materializado porque o pipeline de detecção/mapeamento não está implementado ou não há evidência suficiente.
- `ERROR`: falha técnica durante uma futura materialização da capacidade; não deve ser confundida com finding do website.

`NOT_CONFIGURED` continua válido quando uma implantação remove/invalida deliberadamente os requisitos mínimos de configuração ou fornece um override que não pode ser validado. Ele não deve ser o estado normal de uma instalação com defaults canônicos.

## Por que não inferir automaticamente

O RASAi não deve deduzir compatibilidade de Web Features apenas por heurística textual ou pela presença genérica de JavaScript/CSS. Uma classificação Baseline confiável exige pelo menos:

- detector determinístico de uso de features;
- identificadores compatíveis com o dataset `web-features`;
- versão/pin do dataset utilizada na auditoria;
- evidência rastreável entre feature detectada e classificação retornada;
- tratamento de features condicionais, polyfills e uso indireto;
- testes de regressão contra páginas controladas.

Enquanto esse pipeline não existir, `NO_DATA` é preferível a inventar uma conclusão de compatibilidade.

## Recomendação operacional

Para uso normal do RASAi, mantenha:

```text
RASAI_WEB_PLATFORM_BASELINE=true
RASAI_WEB_FEATURES_DATASET=auto
```

Use um caminho local somente quando houver necessidade explícita de pin/versionamento ou homologação. Não crie um dataset diferente por domínio auditado.
