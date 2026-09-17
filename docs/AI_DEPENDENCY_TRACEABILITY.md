# Dependências e rastreabilidade antes de IA

## Objetivo

O RASAi mantém uma regra global: **nenhuma chamada de IA é elegível antes de o contexto necessário à finalidade estar coletado, persistido e validado**.

A regra vale para análise semântica, IA técnica e análise profunda. Ela não cria roteadores paralelos por catálogo.

## Orquestração global preservada

Toda chamada continua usando a infraestrutura global existente para:

- provider/model/reasoning;
- routing e fallback;
- retry/circuit breaker;
- pricing e custo estimado;
- `ai_provider_attempts`;
- `ai_exchange_log` sanitizado;
- telemetria de tokens e duração.

CAT-03, CAT-08 e CAT-09 não possuem um mecanismo independente de provider.

## Contrato `AI-DEPENDENCY-001`

Imediatamente antes do limite de execução do provider, o runtime pode persistir um registro em `ai_dependency_snapshots` com:

- finalidade (`purpose`);
- escopo;
- dependências esperadas;
- estado efetivo das dependências;
- dependências ausentes/não prontas;
- IDs de evidência relacionados;
- fingerprint do contexto;
- flag `ready`;
- versão do contrato;
- data/hora.

O snapshot é metadado de governança. Ele não é evidência do site e não altera scoring.

## Semântica CAT-03

A primeira chamada semântica é bloqueada até `semantic_corpus_manifests.status=READY` para a AUD.

O manifesto inclui o universo de páginas/snapshots e o contexto efetivo. O provider recebe somente snapshots pertencentes ao corpus congelado.

A mesma chamada page-level pode retornar assessments BR-GEO, coerência `SC-P*` e sinais normalizados. O cross-page é agregado posteriormente a partir dos resultados persistidos, sem chamada adicional obrigatória.

## IA técnica

A IA técnica só é elegível quando existe evidência persistida dos recursos técnicos aplicáveis, como robots/sitemap.

Quando a evidência ainda não está pronta:

- o work item pode ficar `WAITING_FOR_DATA`;
- não é criado provider attempt;
- não há custo de IA;
- o snapshot de dependência registra o bloqueio.

## CAT-08 · análise profunda

Antes da análise profunda, o runtime verifica:

1. work items obrigatórios anteriores da AUD;
2. findings elegíveis;
3. contexto evidence-bound de suporte.

Se uma dependência obrigatória estiver pendente/falhando, a análise não atravessa o limite do provider. O estado de fulfillment continua sendo a autoridade sobre completude da AUD.

## Relatório `IA e integrações`

A página projeta os snapshots de dependência juntamente com as tentativas de IA.

Para cada finalidade, deve ser possível auditar:

- se o contexto estava pronto;
- quais dependências eram esperadas;
- quais estavam ausentes/não prontas;
- evidências relacionadas;
- fingerprint;
- momento da decisão.

Isso complementa — não substitui — request/response, tokens, custo, provider/model e diagnóstico de tentativas.

## Regra de custo

Um gate `NOT_READY` ou equivalente acontece **antes** da chamada externa. Portanto, um bloqueio de contexto não pode ser representado como falha cobrada de provider.

## Reprocessamento

O reprocessamento reutiliza o mesmo contrato de elegibilidade. Recuperar uma etapa não autoriza IA a operar sobre contexto incompleto; o gate é reavaliado com o estado efetivo da AUD.
