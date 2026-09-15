# Web Platform Baseline / WebDX no RASAi

## Objetivo

O RASAi possui uma capacidade advisory denominada **Web Platform Baseline / WebDX**, implementada pelo contrato `WEB-PLATFORM-BASELINE-001`. Ela relaciona Web Features diretamente observáveis nos artifacts da auditoria com o dataset versionado oficial `web-platform-dx/web-features`, preservando a classificação **Widely Available**, **Newly Available**, **Limited Availability** ou `UNKNOWN` quando o próprio dado não permite classificação.

A capacidade permanece separada de `SARI-001` e `SCORE-GEO-004`; não altera scoring e não transforma incompatibilidade de browser em finding do website por si só.

Referências oficiais:

- <https://github.com/web-platform-dx/web-features>
- <https://web-platform-dx.github.io/web-features-project/>

## Modelo conceitual: dataset global, observação por página

O dataset `web-features` é uma **base canônica global da plataforma Web**. Ele não varia por hostname, setor, tipo de negócio ou domínio auditado.

O contrato separa três níveis:

- **dataset-base**: catálogo/versionamento das Web Features e respectivos estados Baseline; global e independente do domínio;
- **evidência da página/snapshot**: recursos diretamente observáveis no HTML persistido e em CSS/JavaScript inline;
- **resultado Baseline**: cruzamento entre as chaves de compatibilidade observadas e a versão congelada do dataset usada naquele `AUD-*`.

Características do domínio podem alterar relevância, criticidade e o conjunto de features efetivamente usado, mas **não escolhem nem modificam o dataset-base**.

## Configuração

### `RASAI_WEB_PLATFORM_BASELINE`

Controla a capacidade.

- default: `true`;
- `false`: desligamento explícito e prevalente;
- não exige credencial paga nem segredo.

### `RASAI_WEB_FEATURES_DATASET`

Seleciona a fonte do dataset WebDX/web-features.

Default canônico:

```text
RASAI_WEB_FEATURES_DATASET=auto
```

Valores aceitos:

1. `auto` - modo recomendado. Resolve o pacote oficial `web-features` no registry npm;
2. caminho para arquivo local existente - override avançado para homologação, reprodução ou pin operacional explícito.

Exemplos:

```text
# Windows
RASAI_WEB_FEATURES_DATASET=C:\dados\web-features\data.json

# Linux
RASAI_WEB_FEATURES_DATASET=/opt/rasai/datasets/web-features/data.json
```

A variável não é sensível e pode ser persistida no `rasai-console.ini`.

## O que `auto` faz

Na primeira materialização WebDX de um `AUD-*`, o runtime:

1. consulta por HTTPS a metadata corrente do pacote oficial `web-features` no registry npm;
2. obtém o tarball oficial de forma bounded;
3. extrai somente `package/data.json`;
4. valida a estrutura mínima necessária ao contrato;
5. calcula SHA-256;
6. congela o dataset e sua metadata dentro do workspace da auditoria;
7. usa esse snapshot congelado para a classificação.

Artifacts persistidos:

```text
artifacts/standards/web-features/data.json
artifacts/standards/web-features/metadata.json
artifacts/standards/web-features/observations.json
```

A metadata registra, conforme a fonte, contrato, versão, origem, timestamp de freeze, SHA-256, tamanho e quantidade de features. No modo npm também preserva metadata de distribuição disponível, como integrity/shasum.

### Reprocessamento e reprodutibilidade

Se o mesmo `AUD-*` já possui `data.json` e `metadata.json` íntegros, o runtime **reabre o snapshot congelado antes de qualquer resolução de rede**. O SHA-256 é revalidado e uma inconsistência do snapshot é tratada como erro técnico, sem substituição silenciosa por uma versão mais nova.

Assim, mudanças futuras no pacote `web-features` não alteram retrospectivamente a interpretação de uma auditoria já materializada.

Um arquivo local configurado também é copiado/congelado no workspace da auditoria; o caminho externo não se torna dependência permanente do reprocessamento.

## Detector implementado

O detector é determinístico e trabalha somente sobre artifacts já pertencentes à auditoria. Para cada snapshot ele prefere o HTML renderizado disponível e usa o HTML bruto como fallback quando aplicável.

O escopo atual inclui sinais diretamente observáveis em:

- elementos e atributos HTML/SVG/MathML presentes no documento persistido;
- propriedades, valores, at-rules e seletores de CSS inline (`style` e `<style>`);
- APIs JavaScript reconhecíveis em JavaScript inline, com filtragem bounded de comentários/literais para reduzir falso positivo textual.

Os sinais são convertidos em chaves compatíveis com `compat_features` do dataset WebDX. Só existe classificação quando há vínculo determinístico entre a evidência observada e uma feature do dataset.

## Limites deliberados

O contrato **não refaz requests para CSS ou JavaScript externos do site auditado** apenas para ampliar WebDX. Portanto:

- `<script src="...">` e stylesheets externos são contabilizados como não analisados por este detector;
- uma feature existente somente dentro de asset externo pode não aparecer na classificação;
- caminhos JavaScript não diretamente observáveis no artifact não são presumidos;
- polyfills, feature detection em runtime e uso indireto não são convertidos em suporte garantido sem evidência suficiente;
- ausência de feature detectada não prova ausência absoluta em todo o código do site.

Por isso, `SUCCESS` significa **materialização bem-sucedida do universo diretamente observável do contrato**, e não inventário exaustivo de todo o front-end.

## Classificação

A classificação mantém a semântica do dataset:

- `WIDELY_AVAILABLE` - `status.baseline = "high"`;
- `NEWLY_AVAILABLE` - `status.baseline = "low"`;
- `LIMITED_AVAILABILITY` - `status.baseline = false`;
- `UNKNOWN` - a feature foi vinculada, mas o dado aplicável não fornece uma classificação Baseline conclusiva.

Quando a feature possui estado específico por `compat_features`, o runtime usa o estado aplicável à chave observada. Se uma Web Feature agregada possuir chaves observadas com estados diferentes, a consolidação é conservadora e preserva o estado mais restritivo entre as evidências observadas.

## Estados operacionais

- `DISABLED`: capacidade explicitamente desligada;
- `READY`: requisitos de configuração presentes antes da materialização; `auto` atende o default normal;
- `SUCCESS`: snapshots analisáveis produziram uma ou mais Web Features mapeadas/classificadas;
- `PARTIAL`: somente parte dos snapshots elegíveis pôde ser analisada;
- `NO_DATA`: não há snapshot/artifact elegível ou nenhum sinal diretamente observável mapeou para `compat_features`; não é falha do website;
- `ERROR`: falha técnica de dataset, integridade, resolução ou materialização;
- `NOT_CONFIGURED`: continua reservado a configuração explicitamente inválida/incompleta fora do default canônico.

`NO_DATA`, `PARTIAL` e `ERROR` desta integração não alteram automaticamente SARI, Coverage, Confidence ou SCORE-GEO.

## Evidência e relatório

Cada feature materializada gera observação em `standards_metric_observations` no escopo `DEVICE_SNAPSHOT`, com URL, device, classificação, feature id e detalhes de proveniência. Contagens por classe também são persistidas. O resumo da execução fica em `standards_service_runs` e `observations.json` preserva o payload auditável do detector.

A superfície HTML canônica é `report/standards.html`. O relatório deve deixar separados:

- estado da integração;
- versão/hash do dataset;
- resultado de compatibilidade observado;
- limitações do detector.

## Comportamento no console

No uso normal, o usuário **não precisa configurar nada adicional** para WebDX. Os defaults de fábrica são:

```text
RASAI_WEB_PLATFORM_BASELINE=true
RASAI_WEB_FEATURES_DATASET=auto
```

O console aceita `auto` ou caminho de arquivo existente, rejeita caminho inexistente e mantém `false` explícito como hard-off da capacidade. `src/rasai/config/rasai-defaults.ini` contém os defaults para instalação limpa e **Restaurar padrões**.

## Recomendação operacional

Mantenha `auto` no uso comum. Use arquivo local somente quando precisar controlar explicitamente o snapshot de referência. Não mantenha catálogos WebDX diferentes por domínio.

Para auditorias que dependem de reprodutibilidade, preserve o diretório `artifacts/standards/web-features/` junto do `audit.db`: ele contém a referência exata usada para interpretar aquela execução.
