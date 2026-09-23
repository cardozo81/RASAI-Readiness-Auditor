# Readiness e orientação contextual do console

Este documento registra a semântica de readiness aplicada ao catálogo da auditoria. Runtime, registries e validadores canônicos continuam sendo a fonte de verdade.

## Regra agregada

Um catálogo selecionado é:

```text
APTO                 requisitos mínimos conhecidos satisfeitos
APTO COM LIMITAÇÕES  executável com perda conhecida de fonte/enriquecimento opcional
BLOQUEADO            falta requisito obrigatório para o resultado escolhido
```

Catálogo fora do plano aparece `NÃO SELECIONADO` e não participa dos blockers.

## Observabilidade externa

Observabilidade externa permanece uma capacidade/fonte técnica consumida quando aplicável. Ela não transforma automaticamente integrações não selecionadas em requisitos da auditoria.

As fontes atuais incluem, conforme registry/configuração:

1. CrUX History;
2. Microsoft Clarity Data Export;
3. Common Crawl CDX History.

Dynatrace continua sendo uma fonte de calibração do Synthetic User Experience Apdex, não um dataset genérico de observabilidade externa.

## Search & AI Intelligence

`CAT-05` agrega objetivo de produto, mas mantém contratos independentes:

```text
Search Intelligence / SERP
Google Search Console
Visibilidade em IA
Observabilidade aplicável
```

SERP com termos e configuração válida pode tornar o catálogo apto mesmo quando GSC automático é não aplicável. GSC explicitamente obrigatório e incompatível é blocker.

## Dynatrace no editor de variáveis

Valores de domínio aberto mostram formato, exemplo e critério de uso.

### `RASAI_DYNATRACE_APPLICATION_ID`

Identificador técnico da Web Application usado pela Config API. Exemplo publicado:

```text
APPLICATION-XXXXXXXXXXXX
```

É necessário somente no modo live quando `RASAI_APDEX_DYNATRACE_IMPORT=true` e não existe `RASAI_DYNATRACE_CONFIG_JSON`.

### `RASAI_DYNATRACE_CONFIG_JSON`

Caminho para JSON exportado da Web Application, por exemplo:

```text
C:\dados\dynatrace-web-application.json
```

Quando definido, o loader pode usar a calibração offline sem exigir base URL/Application ID/token para essa leitura.

### Modo live

Quando não há JSON offline e `RASAI_APDEX_DYNATRACE_IMPORT=true`, continuam necessários:

```text
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
DYNATRACE_API_TOKEN
```

O token permanece secret e não entra no INI/HTML/log sanitizado.

## Uso opcional de IA

Com somente `CAT-03`/`CAT-09` como consumidores de IA, o plano usa **sem IA** por padrão. Escolher **com IA** passa a exigir uma IA principal configurada/apta; sem isso o plano fica `BLOQUEADO` antes da execução.

## Análise profunda

`CAT-08` é consumidor de evidências. Fica `BLOQUEADO` quando:

- nenhum catálogo produtor foi selecionado; ou
- a IA principal necessária não está apta.

O console não deve descobrir essa incompatibilidade somente depois de iniciar o AUD.

## Remediações

`CAT-09` exige evidências produzidas. Remediações determinísticas podem existir sem IA; enriquecimento advisory por IA não altera scoring técnico.

## Dependências e variáveis

A mensagem de blocker deve indicar a dependência/variável concreta quando conhecida. O usuário pode abrir a configuração canônica pelo ID exibido no submenu do catálogo e retornar ao mesmo contexto após salvar.

Detalhes completos: [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md).
