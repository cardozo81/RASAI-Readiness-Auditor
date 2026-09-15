# Readiness e orientação contextual do console

Este documento registra a semântica de apresentação aplicada às áreas revisadas do console. O runtime, registries e validadores canônicos continuam sendo a fonte de verdade.

## Observabilidade externa

A capacidade de preparação denominada **Observabilidade externa** representa exatamente as fontes do runtime de observabilidade externa:

1. CrUX History;
2. Microsoft Clarity Data Export;
3. Common Crawl CDX History.

Ela não agrega:

- Search Intelligence / SERP, que possui capacidade própria;
- Google Search Console, que possui capacidade própria;
- Dynatrace, que é uma fonte de **calibração do Synthetic User Experience Apdex**, não um dataset da capacidade de observabilidade externa.

### Estado por fonte

```text
APTO         fonte solicitada/elegível e configuração suficiente
CONFIGURAR   fonte solicitada, mas falta requisito obrigatório
DESABILITADO fonte desligada, sem opt-in ou sem elegibilidade automática
```

### Estado agregado

```text
CONFIGURAR      se qualquer fonte solicitada estiver incompleta
APTO            se ao menos uma fonte estiver pronta e nenhuma solicitada estiver incompleta
NÃO SOLICITADO  se nenhuma fonte estiver ativa/elegível
```

Com os defaults atuais, Common Crawl é público, bounded e habilitado por default, portanto o agregado normalmente aparece `APTO` mesmo com Clarity e CrUX History desabilitados/não solicitados.

Clarity permanece opt-in. `RASAI_CLARITY_API_TOKEN` sozinho não solicita a coleta; `RASAI_CLARITY_ENABLED=true` sem token gera `CONFIGURAR`.

CrUX History pode ficar elegível por credencial conforme o registry, salvo desligamento explícito.

## Dynatrace no editor de variáveis

Valores de domínio aberto devem mostrar mais do que `entrada específica`. A UI apresenta:

```text
Como preencher
formato aceito
exemplo válido, quando conhecido
critério de uso/ativação
referências do contrato
```

### `RASAI_DYNATRACE_APPLICATION_ID`

É o identificador técnico da Web Application usado pela Config API.

Exemplo publicado:

```text
APPLICATION-XXXXXXXXXXXX
```

O runtime trata o valor como texto não vazio e URL-escapa o identificador ao montar o endpoint. A UI não impõe um regex rígido adicional para não rejeitar identificadores válidos do provider.

É necessário somente no modo live:

```text
RASAI_APDEX_DYNATRACE_IMPORT=true
e
RASAI_DYNATRACE_CONFIG_JSON ausente
```

### `RASAI_DYNATRACE_CONFIG_JSON`

É um caminho para arquivo JSON existente com configuração exportada da Web Application.

Exemplo:

```text
C:\dados\dynatrace-web-application.json
```

É uma alternativa offline/reprodutível. Quando definido, o loader prefere o JSON e não exige base URL, Application ID ou token para carregar a calibração.

O arquivo precisa conter objeto JSON compatível com thresholds/KPM de Load Action. O payload bruto não é persistido nos relatórios.

### Modo live

Quando o JSON offline não está definido e `RASAI_APDEX_DYNATRACE_IMPORT=true`, o modo live exige em conjunto:

```text
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
DYNATRACE_API_TOKEN
```

`DYNATRACE_API_TOKEN` continua sendo secret e não entra no INI, SQLite, HTML ou logs sanitizados.

## Perfis

As referências canônicas exibidas em `Falta` são:

```text
6  IA principal
12 Synthetic Apdex
13 Termos SERP
```

Análise profunda é solicitada pelo próprio perfil quando esse módulo faz parte da composição; por isso `item 8 desligado` não deve aparecer como pendência prévia isolada.

Perfis com Análise profunda exigem IA principal/AUTO apta e não oferecem a combinação contraditória `Análise profunda + SEM IA`.

Detalhes completos: [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md).
