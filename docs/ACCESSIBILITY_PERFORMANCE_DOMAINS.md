# Acessibilidade e Web Performance - domínios separados

O RASAi apresenta Acessibilidade, Web Performance e **Search & AI Readiness** como domínios distintos para evitar mistura de métricas e conclusões.

| Domínio | Finalidade | Fonte principal | Altera SARI/SCORE-GEO-004? |
|---|---|---|---|
| Search & AI Readiness | descoberta, extração, entendimento, answerability e citation readiness | evidências locais, regras e IA opcional | somente pelas regras próprias do SARI/SCORE-GEO-004 |
| Acessibilidade automatizada | diagnóstico auxiliar de problemas detectáveis por Lighthouse | categoria `accessibility` do artifact Lighthouse | não |
| Web Performance | lab Lighthouse + dados de campo CrUX/CWV + diagnósticos técnicos | PageSpeed/Lighthouse e CrUX | não |
| Synthetic Apdex | experiência sintética de uma Task explícita de navegação | Chromium local e perfis controlados | não |

## Acessibilidade

O relatório de Acessibilidade não é certificação WCAG. Ele apresenta somente checks automatizados e evidências efetivamente disponíveis.

A coleta não faz uma chamada externa separada: reutiliza o artifact Lighthouse obtido por PageSpeed. Assim:

```text
PageSpeed timeout/erro
→ artifact Lighthouse ausente
→ Acessibilidade automatizada não obtida
```

O report deve mostrar essa relação e a causa concreta.

### Score Lighthouse e ocorrências

O score Lighthouse de Acessibilidade é apresentado com a convenção visual oficial do Lighthouse para scores 0-100:

```text
90-100  Bom
50-89   Precisa melhorar
0-49    Ruim
```

`Ocorrências automatizadas` conta elementos/nós apontados pelos audits reprovados. Um mesmo audit pode produzir várias ocorrências; por isso o report também explica essa diferença.

`Conformidade WCAG = NÃO DETERMINADA` é estado deliberado. Auditoria automatizada não substitui os critérios que exigem julgamento humano.

As tags de prioridade visual servem para triagem operacional e não alteram o score Lighthouse nem equivalem a nível de conformidade WCAG.

## Web Performance

Web Performance pode conter:

- Lighthouse Performance;
- FCP, LCP, TBT, CLS e Speed Index de laboratório quando fornecidos;
- LCP/INP/CLS p75 de campo via CrUX quando disponíveis;
- assessment de Core Web Vitals;
- diagnóstico de recursos/bloqueios/primeira dobra conforme evidência disponível.

Dados lab e field não são intercambiáveis.

### Faixas visuais

Para o score Lighthouse 0-100, o report usa:

```text
90-100  Bom
50-89   Precisa melhorar
0-49    Ruim
```

Para Core Web Vitals no percentil 75, o report usa os thresholds publicados pelo Google/web.dev:

| Métrica | Bom | Precisa melhorar | Ruim |
|---|---:|---:|---:|
| LCP | `<= 2,5 s` | `> 2,5 s` e `<= 4,0 s` | `> 4,0 s` |
| INP | `<= 200 ms` | `> 200 ms` e `<= 500 ms` | `> 500 ms` |
| CLS | `<= 0,1` | `> 0,1` e `<= 0,25` | `> 0,25` |

O assessment `CWV PASS` requer que todas as métricas Core Web Vitals disponíveis atendam à faixa boa no p75. As cores/tags do report são projeção desses estados; não recalculam os valores persistidos.

Diagnósticos técnicos podem receber tags de prioridade visual para facilitar triagem. Essas tags são auxiliares e não modificam Lighthouse, CrUX, SARI-001 ou os artifacts originais.

## Coleta parcial

É possível que PageSpeed falhe e CrUX direto funcione. Nesse caso, dados de campo permanecem utilizáveis, mas Lighthouse/Acessibilidade ficam indisponíveis. O estado deve ser `PARTIAL`/limitado, não sucesso integral.

## Synthetic Apdex

Apdex possui página própria e não deve ser inferido de Lighthouse/Core Web Vitals. A duração da requisição PageSpeed também não é uma amostra Apdex.

Apdex é relativo ao threshold `T` configurado para a Task:

```text
Satisfied   resposta <= T
Tolerating  T < resposta <= 4T
Frustrated  resposta > 4T
```

Logo, `Apdex = 1,00` com `T = 8 s` significa que 100% das amostras válidas ficaram dentro do alvo configurado de oito segundos. Isso **não** significa que oito segundos sejam globalmente rápidos ou que Core Web Vitals/Lighthouse devam aprovar a página.

O report destaca conflitos de sinal quando Apdex está alto pelo `T` escolhido, mas CWV/Lighthouse indicam degradação. O usuário deve revisar se `T` representa de fato o objetivo operacional da Task; o RASAi não substitui silenciosamente esse threshold por outro valor.

O perfil sintético exibido deve ser o perfil persistido para o mesmo URL/dispositivo do card. A normalização final reconcilia essa projeção com `audit.db` para impedir que um card `MOBILE` apresente por engano o perfil Desktop.

## Rastreabilidade

A página inicial do report inclui **Configuração × resultado obtido** para indicar o que foi solicitado, o que foi materializado e o motivo de qualquer ausência.

As cores e tags são semântica de apresentação. Os números, findings, RuleExecutions e artifacts persistidos continuam sendo a fonte de verdade.

`SCORE-GEO-003` é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica; estes domínios externos não são recalculados nem reinterpretados por essa mudança de scoring.
