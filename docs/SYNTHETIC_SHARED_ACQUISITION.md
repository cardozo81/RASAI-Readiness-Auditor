# Shared Synthetic Apdex Acquisition

## Objetivo

O RASAi pode reduzir navegações físicas quando **Synthetic Navigation Apdex** e **Synthetic User Experience Apdex** estão habilitados na mesma auditoria.

O owner canônico da aquisição física é `src/rasai/synthetic_acquisition_engine.py`. Ele persiste envelopes brutos `LOAD_ONLY` e `FULL_EXPERIENCE`, congela a fronteira de `load` e armazena observáveis pós-load quando disponíveis. O engine não importa CAT-06/M23 nem CAT-07/M25 e não calcula Apdex. O runtime compartilhado anterior permanece nesta etapa somente como adapter de integração e será retirado após a homologação prevista em #207/#208.

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

## Device e número de amostras

Os targets continuam independentes, mas CAT-06 e CAT-07 usam o mesmo device da AUD.

Exemplo para uma AUD Mobile:

```text
Synthetic Navigation Apdex
  MOBILE: 150 amostras válidas

Synthetic User Experience Apdex
  MOBILE: 100 amostras válidas
```

Quando perfis, sessão e requisitos de coleta são compatíveis, até 100 aquisições Experience podem ser reutilizadas pelo Navigation. O Navigation ainda precisa completar as 50 amostras válidas restantes.

O mesmo raciocínio vale para uma AUD Desktop. Não existe compartilhamento cross-device dentro de uma nova AUD e Tablet não integra a população pública.

### Planner físico determinístico

Quando os contratos físicos são compatíveis, o planejamento usa:

```text
FULL_EXPERIENCE = N_EXPERIENCE
LOAD_ONLY = max(N_NAVIGATION - N_EXPERIENCE, 0)
TOTAL_PHYSICAL = max(N_NAVIGATION, N_EXPERIENCE)
```

Se `N_NAVIGATION < N_EXPERIENCE`, as observações Navigation são distribuídas deterministicamente ao longo de toda a população FULL. O planner não escolhe simplesmente as primeiras N. A seleção usa o ordinal atribuído antes do início/agendamento da aquisição; ordem de conclusão concorrente não muda a população escolhida.

O planner altera somente a quantidade e o reaproveitamento de aquisições físicas. Cada evaluator mantém target, validade, classificação e score próprios.

## Concorrência e ordem física

Os dois estágios não somam suas concorrências: o Experience executa antes do Navigation e, quando elegível, publica aquisições reutilizáveis para o estágio seguinte. O teto operacional é `1..3` no Experience e `1..4` no Navigation, ambos com default/recomendado `1`. Experience `3` e Navigation `3..4` exigem delay mínimo de `1 s`. A reutilização reduz navegações físicas; não autoriza aumentar os caps nem representa garantia de que o alvo suporte a carga.

Nos executores paralelos, a quantidade de trabalhos em voo deve ser limitada às amostras válidas ainda necessárias. Assim, atingir o target não deixa navegações adicionais já agendadas gerando carga sem representação na população persistida.

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
- mantém seu target total por página e o device herdado da AUD;
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

Esse ledger é materializado pelo Synthetic Acquisition Engine neutro e registra envelopes físicos, observáveis disponíveis, reutilizações da fronteira de load e incompatibilidades de timeout. É evidência operacional; não participa do cálculo de nenhum score.

`cat-06.html` e `cat-07.html` recebem a seção **Uma navegação física, avaliações Apdex independentes**, com:

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
