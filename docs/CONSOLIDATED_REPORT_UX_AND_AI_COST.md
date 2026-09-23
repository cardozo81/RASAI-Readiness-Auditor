# Relatório consolidado - UX, linguagem, IA e custos

## Objetivo

Este contrato complementa `CONSOLIDATED_REPORTING.md` para a apresentação do HTML consolidado e para a experiência de custo no console. Ele não altera cálculo, score, evidência, comparabilidade, `SARI`, `SCORE-GEO`, Monitoring ou Fix Verification. As mudanças são de apresentação, proveniência e transparência operacional.

## Linguagem do HTML

O relatório continua usando identificadores técnicos em inglês quando eles fazem parte de contratos, nomes de métricas, códigos ou protocolos. Texto de interface e explicações destinadas ao usuário devem usar pt-BR sempre que não houver perda de precisão. Exemplos visíveis tratados pela camada de apresentação incluem `Snapshot` -> `Leitura pontual`, `Fix Verification` -> `Verificação de correções`, `Provider` -> `Provedor` e `Reasoning` -> `Perfil de raciocínio`.

Códigos como `FIXED`, `IMPROVED`, IDs de regra e IDs de evidência podem continuar presentes em `<code>` para rastreabilidade, mas o estado legível exibido ao usuário deve ser traduzido.

## Hierarquia dos cartões quantitativos

Cartões de indicadores seguem a hierarquia visual **título -> valor -> contexto**. O título deve ser menor e estável; o valor quantitativo deve ser visualmente dominante, usar algarismos tabulares e não disputar espaço com o título. A regra vale para as grades do consolidado e para o resumo de consumo de IA.

A cor não substitui o texto. Estados positivos, de atenção e negativos devem ter rótulo textual além do destaque visual.

## Cores de sinaleiro

As cores são aplicadas a **mudança observada**, não como julgamento arbitrário de qualidade absoluta:

- verde: melhora ou resolução observada;
- amarelo: novo sinal, alteração, dado não comparável ou estado que exige atenção;
- vermelho: regressão ou condição não corrigida.

A mesma semântica é usada na comparação determinística. Scores que já possuem faixas metodológicas próprias mantêm sua classificação original.

## Proveniência de IA

A análise por IA é opcional no `CONS-5`. Quando o usuário escolhe **Determinístico + IA**, todo texto produzido pela análise especialista deve estar dentro de uma seção explicitamente marcada como **Conteúdo gerado por IA** ou **Conteúdo assistido por IA**. No modo **Determinístico**, essa camada não é produzida e `NOT_REQUESTED` é estado neutro. A marcação deve deixar claro que:

- a análise é orientativa e não altera `SARI`/`SCORE-GEO`;
- a evidência e os deltas continuam vindo do processamento determinístico persistido;
- revisão humana é necessária;
- associação temporal não é prova de causalidade.

Quando IA é autorizada, a metodologia do relatório não pode afirmar genericamente que o consolidado fez "nenhuma chamada externa". A formulação correta é que a consolidação dos AUDs é local/somente leitura e somente a análise especialista explicitamente autorizada pode chamar IA. PageSpeed e CrUX não são reexecutados pelo consolidado.

## Priorização das correções

A resposta especialista já possui prioridades `P0` a `P3`; a apresentação deve ordenar e classificar as recomendações antes de exibi-las:

| Prioridade | Interpretação visual |
|---|---|
| P0 | Crítica - ação imediata |
| P1 | Alta - próxima ação |
| P2 | Média - planejar |
| P3 | Baixa - oportunidade |

A prioridade vem do contrato especialista evidence-bound. A camada de apresentação não recalcula prioridade.

## Destaques do que melhorou

O HTML deve destacar melhorias e regressões materiais da trajetória, incluindo cada intervalo consecutivo e o marco inicial contra o final. A seleção usa apenas eventos determinísticos persistidos e prioriza resolução, severidade e magnitude disponível. O bloco é apresentado como **destaque de melhora observada**, não como prova de que uma correção causou resultado de Search, ranking, tráfego, conversão ou visibilidade em IA.

## Uso e custo da IA no consolidado

A prévia de custo e a autorização externa existem somente no modo **Determinístico + IA**. No modo **Determinístico**, o console registra IA não solicitada e custo zero de chamadas de IA do consolidado.

Quando IA é solicitada, ao final da geração o console deve exibir o consumo da análise especialista do próprio CONS:

- estado da análise;
- tentativas e sucessos;
- tokens de entrada, cache, saída e raciocínio;
- custo técnico estimado por moeda quando o adapter retornou telemetria suficiente;
- quantidade de tentativas sem custo calculável.

O HTML também contém esse detalhamento na seção de IA. Valores são estimativas técnicas baseadas na telemetria retornada e no catálogo de preços do RASAi; não são invoice/fatura do provedor.

Quando houver forecast persistido, a seção humana mostra também **Confiança da previsão**, **Cobertura de preços** e **Base da confiança**. A finalidade é tornar o desvio entre custo previsto e observado interpretável sem exigir leitura do JSON.

No forecast pré-execução do especialista longitudinal, **cobertura de preço não equivale a alta confiança financeira**. Mesmo quando todos os providers/modelos possuem tarifa conhecida e moeda compatível, o volume de tokens - em especial a saída - ainda é estimado. Por isso cobertura integral de pricing, isoladamente, produz confiança no máximo **MÉDIA**. Cobertura parcial produz **BAIXA** e ausência de preço produz **NENHUMA**. O campo `pricing_coverage` registra a cobertura objetiva e `confidence_basis` explica a incerteza; nenhuma dessas mudanças altera a aritmética de custo.

Se houver somente uma auditoria elegível, o `CONS-5` não pode ser gerado. O console deve explicar que a base longitudinal exige pelo menos duas auditorias da mesma URL e do mesmo dispositivo. Nesse caso não ocorre chamada de IA nem materialização de relatório consolidado.

## Primeira execução com IA no console de auditoria

A estimativa monetária histórica depende de execuções comparáveis com telemetria de custo conhecida. Na primeira execução isso pode não existir. A ausência de histórico **não deve mais eliminar a prévia**.

Quando há IA potencial e o forecast histórico ainda não consegue calcular um total monetário confiável, o console mostra uma prévia de exposição com:

- faixa de tentativas potenciais de IA;
- nível de exposição;
- tarifas atuais conhecidas por provider/modelo, inclusive contexto tarifário;
- justificativa de por que um total monetário ainda não pode ser calculado.

O console não inventa quantidade de tokens antes de conhecer o conteúdo real. Portanto, sem histórico comparável, não exibe um total financeiro falso. O usuário precisa confirmar explicitamente a exposição antes da execução.

Após a auditoria, permanece o relatório de consumo real persistido já existente no fluxo: tentativas, tokens, custo técnico estimado e chamadas externas. Quando existir forecast histórico monetário, a aderência entre estimativa e custo observado continua sendo exibida normalmente.

## Testes mínimos

A validação automatizada deve cobrir:

1. tradução/normalização dos estados visíveis sem alterar IDs técnicos;
2. classes positivas, de atenção e negativas na evolução;
3. marcação explícita de conteúdo gerado por IA;
4. ordenação `P0 -> P3`;
5. destaque de melhoria usando somente mudanças persistidas;
6. soma de tokens/custos do `specialist-analysis.json`;
7. prévia de primeira execução quando há IA e não há histórico monetário;
8. possibilidade de cancelar antes de qualquer chamada tarifável;
9. disponibilidade da IA não bloqueia o modo determinístico; bloqueia somente a escolha **Determinístico + IA** quando nenhum provider apto estiver disponível.
