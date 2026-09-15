# Console - custo, quota e telemetria de execução

Este documento descreve como o `rasai-console` apresenta exposição prévia e consumo realmente persistido após uma auditoria.

## Regra de fonte única

O catálogo canônico de preços de IA é `src/rasai/ai_cost_policy.py`. O console não mantém preços próprios nem cria uma segunda contabilidade.

Depois da execução, o console lê os dados persistidos em `audit.db` e artifacts/logs correspondentes. A tabela `provider_pricing_catalog` é uma projeção auditável do catálogo canônico usado naquela execução, não uma fonte concorrente de regras.

| Finalidade | Fonte persistida | Dados principais |
|---|---|---|
| análise semântica por IA | `ai_provider_attempts` | provider/modelo, status, tokens, duração, custo estimado, pricing version |
| catálogo de preço IA | `provider_pricing_catalog` | preço unitário, moeda, versão e referência |
| remediação textual por IA | `content_remediation_attempts` | provider/modelo, tokens, status, custo quando estimável |
| Web Performance | `web_performance_attempts` | PageSpeed/CrUX, status, HTTP, duração, erro, artifact |
| Synthetic Apdex | `synthetic_apdex_runs` / `synthetic_apdex_samples` | tentativas, válidas/inválidas, duração/classificação |

## Antes da execução

A faixa financeira é uma heurística de exposição:

```text
NENHUM | BAIXO | MÉDIO | ALTO | EXCESSIVO
```

Ela considera, quando aplicável:

- quantidade conhecida/teto de páginas;
- quantidade de contextos de dispositivo;
- provider/modelo de IA;
- pool AUTO elegível e preços vigentes;
- reasoning/esforço configurado;
- remediação textual;
- PageSpeed/CrUX e limites externos.

A faixa não é invoice e não garante preço final.

Quando `AI=auto` está selecionado, a execução não usa a faixa qualitativa do console para escolher provider. O coordenador calcula o custo estimado de cada requisição específica com o catálogo canônico, o modelo/reasoning efetivo, input/output esperado, cache observado e o contexto tarifário do instante da chamada. A lógica detalhada está em [`AUTO_COST_AWARE_AI_ROUTING.md`](AUTO_COST_AWARE_AI_ROUTING.md).

## Esforço de IA

O default público usa o modelo mais simples e o menor esforço suportado. Selecionar modelo/esforço maiores pode aumentar latência, tokens e custo, por isso o console exibe esses parâmetros na opção 4.

No AUTO, o reasoning efetivamente configurado também participa da estimativa de custo da requisição. Isso não altera o scoring e não muda a política de quarentena/circuit breaker.

## Web Performance

O console contabiliza chamadas PageSpeed/CrUX como consumo de API/quota. Não inventa preço monetário quando não existe catálogo confiável no projeto.

O timeout configurável não representa custo por si só. Ele apenas determina quanto o cliente aguarda a chamada externa antes de registrar timeout.

## Synthetic Apdex

Synthetic Apdex é exibido separadamente da faixa financeira porque não possui API paga própria. A projeção é de **carga sintética**:

```text
páginas × devices × máximo de tentativas/contexto
```

Cada navegação pode gerar muitos requests de subrecursos, portanto a quantidade de navegações não equivale a requests HTTP.

## Depois da execução

O console pode mostrar:

```text
Tentativas IA / sucessos
Tokens input / cache / output / reasoning / total
Custo IA estimado
Chamadas Web Performance
PageSpeed sucesso/tentativas
CrUX sucesso/tentativas
Cobertura de Acessibilidade e motivo
Navegações Synthetic Apdex
Amostras válidas / inválidas
```

A estimativa pré-chamada usada para roteamento e o custo pós-chamada não são a mesma coisa. Antes da chamada, o AUTO pode assumir cache miss e usar heurísticas de tokens apenas para ordenar candidatos. Depois da chamada, custo monetário de telemetria só é materializado quando o usage nativo contém informação suficiente para aplicar a tarifa sem inventar a divisão entre input cacheado e não cacheado.

Se uma tentativa possui tokens mas não existe informação suficiente de pricing/usage, ela é apresentada como não estimável; nunca como custo zero artificial.

## Falhas e cobertura

Falha de integração é separada de finding do website. Exemplos:

```text
PageSpeed timeout
CrUX HTTP/quota
provider sem crédito
provider quarantined
artifact ausente
```

O console e o report devem explicar qual coleta foi afetada.

Quando havia estimativa monetária prévia para IA, mas a execução termina com **zero sucessos de IA** e sem consumo monetário materializado, o fechamento financeiro não classifica o resultado como `DENTRO DO ESPERADO`. O estado exibido é `NÃO CONSUMIDO`, o campo `Desvio vs esperado` permanece sem valor comparativo e a observação deixa explícito que a IA solicitada não produziu execução bem-sucedida/consumo tarifável. Quando existe uma tentativa de IA falha persistida, o bloco reutiliza somente o diagnóstico técnico estruturado já registrado (`provider/model`, `error_class` ou `status`, `error_code/error_type` e `HTTP` quando disponível). Se esse diagnóstico não estiver disponível, o bloco orienta consultar as pendências canônicas do AUD. Nenhuma nova classificação de erro de integração é criada pela camada financeira.

Menor custo não reativa provider em quarentena, não reduz contador de falhas e não modifica a classificação de erro. A seleção econômica altera somente a ordem dos candidatos ainda elegíveis no `AI=auto`.

## Configuração INI

`rasai-console.ini` persiste somente parâmetros não sensíveis, inclusive modelo, esforço, timeouts e limites. Credenciais não são gravadas no INI.

## Segurança

- secrets aparecem somente como `[SET]`;
- API keys/tokens não entram no INI, report ou log;
- custos são estimativas técnicas;
- não assuma que key configurada implica quota/saldo;
- não confunda carga Synthetic Apdex com custo financeiro de API.
