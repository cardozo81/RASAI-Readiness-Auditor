# Console — custo, quota e telemetria de execução

Este documento descreve como o `rasai-console` apresenta exposição prévia e consumo realmente persistido após uma auditoria.

## Regra de fonte única

O console não cria uma segunda contabilidade. Depois da execução, lê os dados persistidos em `audit.db` e artifacts/logs correspondentes.

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
- cadeia AUTO elegível;
- remediação textual;
- PageSpeed/CrUX e limites externos.

A faixa não é invoice e não garante preço final.

## Esforço de IA

O default público usa o modelo mais simples e o menor esforço suportado. Selecionar modelo/esforço maiores pode aumentar latência, tokens e custo, por isso o console exibe esses parâmetros na opção 4.

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

Se uma tentativa possui tokens mas não existe informação suficiente de pricing, ela é apresentada como não estimável; nunca como custo zero artificial.

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

## Configuração INI

`rasai-console.ini` persiste somente parâmetros não sensíveis, inclusive modelo, esforço, timeouts e limites. Credenciais não são gravadas no INI.

## Segurança

- secrets aparecem somente como `[SET]`;
- API keys/tokens não entram no INI, report ou log;
- custos são estimativas técnicas;
- não assuma que key configurada implica quota/saldo;
- não confunda carga Synthetic Apdex com custo financeiro de API.
