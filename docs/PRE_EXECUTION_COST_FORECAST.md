# Previsão financeira de custo antes da execução

## Objetivo

O RASAi pode estimar a exposição monetária antes do início de uma auditoria acionada por uma pessoa quando a configuração selecionada possui telemetria histórica comparável com custo conhecido do provider.

A estimativa é consultiva. Ela não substitui a fatura do provider e não inventa preços para integrações cujo modelo monetário é desconhecido pelo RASAi.

## Console interativo local

Fluxo:

1. o operador seleciona `R. Executar`;
2. perfis de execução e overrides da sessão são aplicados primeiro;
3. o RASAi lê históricos recentes e imutáveis de `AUD-*/audit.db`;
4. chamadas comparáveis de provider/modelo/configuração são reprecificadas com o catálogo atual de preços do RASAi quando a telemetria de tokens é suficiente;
5. somente quando existe previsão monetária, o console mostra baseline de chamadas bem-sucedidas, custo esperado, faixa provável P25-P75, cenário potencial P90, tamanho da amostra, volume estimado de páginas e confiança;
6. o operador escolhe explicitamente executar com IA, executar sem IA ou voltar; a escolha do modo é a autorização final da operação não destrutiva.

Quando não existe base monetária suficiente, a execução segue o fluxo normal sem inventar uma estimativa.

Para alvo TXT, usa-se a quantidade conhecida de URLs. Para crawl iniciado por uma URL, usa-se a mediana histórica comparável de páginas, limitada pelo `max_pages` atual.

Improvement Intelligence é incluída quando provider/modelo históricos e contrato persistido forem comparáveis, pois suas tentativas usam a telemetria canônica `ai_provider_attempts`.

A previsão antes da execução normal é distinta da previsão de **reprocessamento seletivo**. No reprocessamento, uma pendência sem IA pode alterar evidência e tornar análises dependentes obsoletas; nesse caso o console deve informar IA condicional em vez de prometer custo zero. Consulte [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md).

## SaaS / control plane

O SaaS expõe:

```text
POST /api/v1/projects/{project_id}/execution-cost-estimate
```

A requisição usa o mesmo payload não secreto de AUDIT que seria enfileirado. O estimador respeita tenant/projeto/property/environment e usa o usage ledger centralizado com a configuração durável do execution job.

Fluxo web:

```text
configurar -> estimar -> exibir somente quando houver valor monetário -> escolher modo com IA/sem IA -> enfileirar
```

O contrato atual de `POST /execution-jobs` permanece independente de confirmação interativa. Schedules, workers e automações de API seguem seu fluxo próprio e não dependem de uma interação humana no navegador.

Para `ai_provider=auto`, a previsão SaaS usa a distribuição provider/modelo efetivamente observada em jobs comparáveis. Não infere credenciais do worker a partir do navegador ou do control plane.

## Modelo estatístico

Para cada auditoria histórica comparável, o RASAi calcula custo por página materializada.

- baseline de sucesso: mediana do custo por página das chamadas bem-sucedidas;
- esperado: mediana do custo por página de todas as chamadas faturáveis conhecidas;
- faixa provável: P25-P75;
- cenário potencial: P90.

Essas taxas são multiplicadas pelo volume estimado de páginas da execução solicitada.

A confiança depende da quantidade de execuções comparáveis: 1-4 baixa, 5-19 moderada, 20-49 boa e 50 ou mais alta. A confiança é reduzida quando menos de 80% das chamadas conhecidas podem ser reprecificadas a partir da telemetria atual de tokens.

## Salvaguardas de cobrança

O RASAi não presume que todo erro seja faturável. Uma tentativa com falha só contribui para a previsão monetária quando possui telemetria suficiente de tokens/custo para estabelecer uma estimativa.

O RASAi não faz conversão cambial implícita. Históricos comparáveis com moedas distintas suprimem a previsão em vez de fabricar um único valor.

SERP, PageSpeed, CrUX e outras integrações permanecem fora da decisão monetária quando o RASAi possui telemetria de quota/uso, mas não possui estimativa monetária canônica.
