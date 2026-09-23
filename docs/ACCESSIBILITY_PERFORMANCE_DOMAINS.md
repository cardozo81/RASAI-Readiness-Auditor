# Acessibilidade e Web Performance - domínios separados

O RASAi apresenta Acessibilidade, Web Performance e **Search & AI Readiness** como domínios distintos para evitar mistura de métricas e conclusões.

| Domínio | Finalidade | Fonte principal | Altera SARI/SCORE-GEO-004? |
|---|---|---|---|
| Search & AI Readiness | descoberta, extração, entendimento, answerability e citation readiness | evidências locais, regras e IA opcional | somente pelas regras próprias do SARI/SCORE-GEO-004 |
| Acessibilidade automatizada | diagnóstico auxiliar de problemas detectáveis por Lighthouse | categoria `accessibility` do artifact Lighthouse | não |
| Web Performance | métricas browser-native same-session + lab Lighthouse + dados de campo CrUX/CWV | W3C Web Performance APIs no Chromium local, PageSpeed/Lighthouse e CrUX | não |
| Synthetic Apdex | experiência sintética de uma Task explícita de navegação | Chromium local e perfis controlados | não |

## Acessibilidade

O relatório de Acessibilidade não é certificação WCAG. Ele apresenta somente checks automatizados e evidências efetivamente disponíveis.

A coleta Lighthouse de acessibilidade não faz uma chamada externa separada: reutiliza o artifact Lighthouse obtido por PageSpeed. Assim:

```text
PageSpeed timeout/erro
→ artifact Lighthouse ausente
→ Acessibilidade automatizada Lighthouse não obtida
```

O report deve mostrar essa relação e a causa concreta.

O RASAi não executa uma segunda bateria axe-core por default apenas para duplicar a mesma família de checks já fornecida pelo Lighthouse. Uma integração direta futura só deve ser adicionada se ampliar cobertura ou operar sob um contrato independente claramente identificado.

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

Web Performance pode conter três famílias distintas de evidência:

1. **Open Web Metrics (`OPEN-WEB-METRICS-001`)** - métricas browser-native coletadas por default no mesmo `DEVICE_SNAPSHOT`, sem nova navegação ou API externa;
2. **Lighthouse/PageSpeed** - medição de laboratório independente executada pelo provider externo quando habilitado;
3. **CrUX** - dados de campo agregados quando disponíveis para a URL/origin elegível.

A família Open Web pode incluir:

- Navigation Timing: DNS, conexão, TLS, TTFB, download, DOM milestones e protocolo;
- Resource Timing: quantidade/tamanhos observáveis, initiator types e recursos de outra origem;
- Paint: FP, FCP e LCP observado quando suportados;
- Layout Instability: CLS observado no snapshot;
- Event Timing: somente eventos de interação realmente observados;
- Long Tasks e Long Animation Frames quando suportados;
- presença de Server-Timing;
- User Timing agregado;
- sinais básicos de standards mode, doctype, lang, charset, viewport e secure context.

Contrato da família Open Web:

```text
enabled_by_default = true
additional_navigation_requests = 0
additional_external_api_calls = 0
score_impact = NONE
scope = DEVICE_SNAPSHOT
```

Ela é capturada antes da interação diagnóstica bounded de lazy loading para preservar o baseline do snapshot.

Além disso, Web Performance pode conter:

- Lighthouse Performance;
- FCP, LCP, TBT, CLS e Speed Index de laboratório quando fornecidos;
- LCP/INP/CLS p75 de campo via CrUX quando disponíveis;
- assessment de Core Web Vitals;
- diagnóstico de recursos/bloqueios/primeira dobra conforme evidência disponível.

Dados same-session, lab e field **não são intercambiáveis**. O fato de duas fontes possuírem uma métrica com o mesmo nome não as transforma em amostras independentes que possam ser somadas ou receber peso duplicado.

### INP e interação sintética

Open Web Metrics não inventa INP a partir de uma navegação sem interação qualificável. Event Timing é mostrado somente quando o Chromium realmente observou interação identificável. CrUX continua sendo a fonte de field INP quando esse dado estiver disponível.

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

LCP/CLS observados same-session podem usar as mesmas bandas apenas como **contexto visual**, com identificação explícita da fonte. Isso não transforma a observação local em CrUX, RUM ou Lighthouse.

O assessment `CWV PASS` requer que todas as métricas Core Web Vitals de campo necessárias ao assessment estejam disponíveis e atendam à faixa boa conforme o contrato da fonte. As cores/tags do report são projeção desses estados; não recalculam os valores persistidos.

Diagnósticos técnicos podem receber tags de prioridade visual para facilitar triagem. Essas tags são auxiliares e não modificam Lighthouse, CrUX, SARI-001 ou os artifacts originais.

### Múltiplas URLs e devices

Open Web Metrics são apresentadas por URL + dispositivo. Quando o relatório oferece resumo de vários snapshots, usa faixa mínimo-máximo em vez de uma média implícita. Mobile e Desktop permanecem observações distintas.

## Coleta parcial

É possível que PageSpeed falhe e CrUX direto funcione. Nesse caso, dados de campo permanecem utilizáveis, mas Lighthouse/Acessibilidade ficam indisponíveis. O estado externo deve ser `PARTIAL`/limitado, não sucesso integral.

A indisponibilidade de PageSpeed/CrUX não remove Open Web Metrics já persistidas no snapshot local; da mesma forma, falha na captura de uma Performance API específica não deve ser convertida em falha do website.

## Synthetic Apdex

Apdex possui página própria e não deve ser inferido de Lighthouse/Core Web Vitals/Open Web Metrics. A duração da requisição PageSpeed também não é uma amostra Apdex.

Apdex é relativo ao threshold `T` configurado para a Task:

```text
Satisfied   resposta <= T
Tolerating  T < resposta <= 4T
Frustrated  resposta > 4T
```

Logo, `Apdex = 1,00` com `T = 8 s` significa que 100% das amostras válidas ficaram dentro do alvo configurado de oito segundos. Isso **não** significa que oito segundos sejam globalmente rápidos ou que Core Web Vitals/Lighthouse devam aprovar a página.

O report destaca conflitos de sinal quando Apdex está alto pelo `T` escolhido, mas CWV/Lighthouse indicam degradação. O usuário deve revisar se `T` representa de fato o objetivo operacional da Task; o RASAi não substitui silenciosamente esse threshold por outro valor.

O perfil sintético exibido deve ser o perfil persistido para o mesmo URL/dispositivo do card. A normalização final reconcilia essa projeção com `audit.db` para impedir que um card `MOBILE` apresente por engano o perfil Desktop.

## Métodos externos avaliados

A ausência de cobrança direta não torna automaticamente um serviço externo parte do core. W3C validators, MDN HTTP Observatory, WebPageTest e serviços semelhantes continuam candidatos a adapters/integrações opt-in porque adicionam dependência externa, exposição do alvo ou execução própria. Browsertime/sitespeed.io exigem runtime/dependências adicionais. Web Platform Baseline/MDN BCD exige dataset versionado e reproduzível.

Detalhes e fronteiras estão documentados em `docs/OPEN_WEB_METRICS.md`.

## Rastreabilidade

A página inicial do report inclui **Configuração × resultado obtido** para indicar o que foi solicitado, o que foi materializado e o motivo de qualquer ausência.

As cores e tags são semântica de apresentação. Os números, findings, RuleExecutions, `browser_metadata` e artifacts persistidos continuam sendo a fonte de verdade.
