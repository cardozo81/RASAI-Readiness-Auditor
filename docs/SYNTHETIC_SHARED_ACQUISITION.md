# Shared Synthetic Apdex Acquisition

## Objetivo

O RASAi pode reduzir navegações físicas quando **Synthetic Navigation Apdex** e **Synthetic User Experience Apdex** estão habilitados na mesma auditoria.

O contrato é **shared acquisition, independent evaluation**:

- a página pode ser carregada fisicamente uma única vez;
- a fronteira temporal de `load` dessa aquisição pode alimentar o Synthetic Navigation Apdex;
- a mesma página continua aberta durante a janela pós-load necessária ao Synthetic User Experience Apdex;
- cada método mantém seu próprio conjunto de amostras, thresholds, regras de classificação e consolidação;
- nenhum score é usado como entrada do outro;
- a funcionalidade não altera `SCORE-GEO-004`, `SARI-001`, pesos ou gates de readiness.

## Quando uma aquisição pode ser compartilhada

O modo padrão é `auto`. Uma aquisição do Experience Apdex só pode ser reutilizada pelo Navigation Apdex quando todos os critérios abaixo forem verdadeiros:

1. mesma auditoria;
2. mesma URL de entrada;
3. mesmo tipo de dispositivo;
4. mesmo `profile_id`, portanto mesmo cliente/browser, CPU relativa e envelope de rede;
5. `session_mode=cold` no Experience Apdex;
6. a navegação chegou à fronteira de `load` com `SUCCESS` ou `APPLICATION_ERROR`;
7. o tempo até `load` cabe dentro do timeout configurado para o Navigation Apdex.

Se qualquer critério falhar, a coleta do Navigation Apdex continua de forma isolada. Não há compartilhamento forçado.

## Device mix e número de amostras

Os targets continuam independentes.

Exemplo:

```text
Synthetic Navigation Apdex
  Mobile:  100 amostras válidas
  Desktop: 100 amostras válidas

Synthetic User Experience Apdex
  total por página: 100
  Mobile:  60%
  Desktop: 35%
  Tablet:   5%
```

Quando os perfis são compatíveis, o planner efetivo pode reutilizar até:

```text
Mobile:   60 aquisições
Desktop:  35 aquisições
Tablet:    0 aquisições para Navigation
```

O Navigation Apdex ainda precisa completar 100 Mobile e 100 Desktop. Portanto, após consumir as aquisições compartilhadas, executa somente as navegações físicas restantes.

O Experience Apdex continua consolidando exatamente sua população 60/35/5. Tablet permanece exclusivo da população `PROFILE_MEASUREMENT` e não vira um `DeviceContext` core.

## Independência metodológica

A mesma aquisição pode produzir duas classificações diferentes porque cada método aplica sua própria regra sobre a evidência bruta.

### Synthetic Navigation Apdex

- usa o tempo capturado exatamente ao redor de `page.goto(..., wait_until="load")`;
- aplica o threshold `T` e a regra clássica `T / 4T`;
- preserva seu próprio target de amostras por contexto/dispositivo.

### Synthetic User Experience Apdex

- mantém sua KPM configurada;
- mantém thresholds Satisfied/Frustrated independentes;
- mantém política de erros;
- mantém `device_mix` e target total por página;
- continua observando XHR/fetch, recursos tardios, erros e sinais pós-load até sua janela de settle.

A observação pós-load do Experience Apdex não altera retroativamente o tempo de `load` já congelado para o Navigation Apdex.

## Timeout e falhas

`TIMEOUT` e `NAVIGATION_ERROR` do Experience Apdex não são reutilizados pelo Navigation Apdex, porque os métodos podem ter budgets de timeout diferentes.

Também não é reutilizada uma aquisição cujo tempo de `load` seja maior que o timeout efetivo do Navigation Apdex. Nesse caso o Navigation executa sua própria tentativa.

## Configuração

Variável avançada:

```text
RASAI_APDEX_ACQUISITION_MODE=auto|isolated
```

- `auto` é o default e compartilha somente aquisições comprovadamente compatíveis;
- `isolated` mantém duas populações fisicamente separadas, útil para comparação ou troubleshooting.

Valor inválido opera de forma fail-safe como `isolated`.

Não existe modo `shared` forçado.

## Rastreabilidade

Durante a auditoria o RASAi mantém um ledger técnico em `audit.db`:

- `synthetic_apdex_acquisition_runs`;
- `synthetic_apdex_acquisitions`.

Esse ledger registra aquisições Experience elegíveis, reutilizações pelo Navigation e incompatibilidades de timeout. É evidência operacional; não participa do cálculo de nenhum score.

`apdex.html` e `apdex-experience.html` recebem a seção **Uma navegação física, avaliações Apdex independentes**, com:

- modo de aquisição;
- aquisições Experience elegíveis;
- quantidade efetivamente reutilizada pelo Navigation;
- navegações físicas evitadas;
- baseline estimado sem compartilhamento;
- navegações físicas efetivas;
- percentual de redução;
- incompatibilidades de timeout.

## Limites

O compartilhamento cria correlação entre as duas populações porque uma parte das avaliações deriva da mesma ocorrência física. Isso é intencional e melhora a comparabilidade entre métodos, mas não significa equivalência metodológica entre eles.

Quando o Experience Apdex usa `session_mode=warm`, as aquisições permanecem isoladas porque o Navigation Apdex exige contexto frio. Perfis, sessão, URL ou device diferentes também impedem compartilhamento.
