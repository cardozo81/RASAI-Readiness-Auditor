# Open Web Metrics no RASAi

O RASAi coleta um conjunto de métricas e sinais baseados nas APIs abertas da Web diretamente no snapshot Chromium já necessário à auditoria.

Esta capacidade segue quatro premissas:

1. **custo monetário zero por medição**;
2. **nenhuma navegação adicional** contra a URL auditada;
3. **nenhuma chamada a API externa** para produzir esses dados;
4. **nenhuma alteração automática em SARI-001 ou SCORE-GEO-004**.

A implementação é identificada por `OPEN-WEB-METRICS-001`.

## Estado default

Open Web Metrics é **habilitado por default**.

Não existe credencial, quota de provider nem variável obrigatória para habilitar a coleta. O runtime lê as informações disponíveis no próprio `window.performance`, `PerformanceObserver` e no documento já carregado pelo Chromium.

A coleta pertence ao escopo `DEVICE_SNAPSHOT`. Portanto, os resultados são associados à combinação concreta:

```text
URL + dispositivo + snapshot
```

Não existe média implícita Mobile/Desktop nem média implícita entre URLs.

## Aquisição

O collector é executado na mesma sessão Playwright da captura normal do dispositivo e antes de qualquer interação diagnóstica de lazy loading.

Contrato operacional:

```text
additional_navigation_requests = 0
additional_external_api_calls = 0
score_impact = NONE
```

A implementação não cria `page.goto()` adicional, não faz HTTP auxiliar e não consulta serviços de terceiros.

No Windows, onde o snapshot normal é protegido por um worker `spawn` com deadline wall-clock, o collector é instalado explicitamente dentro do mesmo worker para preservar o mesmo contrato.

## Métricas e sinais coletados

### Navigation Timing

Quando exposto pelo Chromium:

- tipo de navegação;
- quantidade de redirects observados pelo Navigation Timing;
- protocolo negociado (`nextHopProtocol`);
- duração da navegação;
- DNS;
- conexão;
- TLS quando aplicável;
- request → first byte;
- TTFB relativo ao início da navegação;
- download da resposta;
- `domInteractive`;
- fim de `DOMContentLoaded`;
- `domComplete`;
- `loadEventEnd`;
- tamanhos transferido, encoded e decoded do documento quando observáveis;
- quantidade de métricas `Server-Timing` expostas pelo navegador.

### Paint e experiência visual

Quando suportado:

- First Paint;
- First Contentful Paint;
- Largest Contentful Paint observado no snapshot;
- tamanho do candidato de LCP quando exposto;
- Cumulative Layout Shift observado até o momento da captura.

As bandas de LCP e CLS podem ser usadas no HTML como **referência contextual de Core Web Vitals**, mas o RASAi não apresenta essa observação sintética como CrUX, RUM ou Lighthouse.

### Event Timing e responsividade

O RASAi registra somente o que foi realmente observado:

- First Input Delay quando existir uma entrada `first-input` válida;
- quantidade de eventos de interação identificados por `interactionId`;
- maior duração de evento de interação observada.

**INP não é inferido.** Uma navegação sintética sem interação humana/automatizada qualificável não recebe um valor artificial de INP.

### Main thread

Quando suportado pelo Chromium:

- quantidade de Long Tasks;
- duração total e máxima de Long Tasks;
- quantidade de Long Animation Frames;
- duração total e máxima de Long Animation Frames.

### Resource Timing

O RASAi registra:

- quantidade de recursos;
- quantidade de recursos cuja origem difere da origem do documento;
- tamanhos transferido, encoded e decoded observáveis;
- quantidade de entradas sem visibilidade de tamanho;
- distribuição por `initiatorType`.

Recursos cross-origin podem ocultar timing/tamanhos sem `Timing-Allow-Origin`. Por isso, tamanho zero/não observável **não é interpretado como recurso vazio**.

### User Timing

Para evitar exposição desnecessária de nomes internos de instrumentação da aplicação, o RASAi registra somente:

- número de marks;
- número de measures;
- duração total dos measures observados.

Os nomes individuais de marks/measures não são exportados pelo relatório.

### Contexto básico da plataforma

Também são projetados sinais determinísticos do documento carregado:

- standards mode (`CSS1Compat`);
- presença de `doctype`;
- presença de `lang` no elemento raiz;
- charset observado;
- presença de viewport meta;
- secure context;
- estado de `crossOriginIsolated`.

Esses itens são diagnósticos técnicos. Eles não constituem um score W3C.

## Relatório

Os dados são incorporados à página canônica:

```text
report/web-performance.html
```

Não é criada uma superfície pública paralela de relatório.

Quando existem múltiplas URLs ou dispositivos, o resumo usa **faixas mínimo–máximo** para métricas numéricas e a tabela preserva uma linha por URL + dispositivo. Isso evita atribuir uma média sem semântica explícita ao conjunto auditado.

## Relação com PageSpeed, Lighthouse e CrUX

Open Web Metrics não substitui esses mecanismos:

| Fonte | Natureza | Nova navegação/API | Default | Papel |
|---|---|---:|---|---|
| Open Web Metrics | navegador local, same-session | não | habilitado | diagnóstico técnico por snapshot |
| Lighthouse/PageSpeed | laboratório externo | sim, quando configurado | conforme configuração vigente | auditoria Lighthouse e categorias suportadas |
| CrUX | dados de campo agregados | consulta externa | quando disponível/configurado | experiência real de usuários elegíveis |
| Synthetic Apdex | medição sintética independente | pode exigir navegação própria | conforme configuração | disponibilidade/experiência sintética parametrizada |

Os sinais não devem ser somados como se fossem evidências estatisticamente independentes quando medem o mesmo fenômeno.

## Relação com SARI-001 e SCORE-GEO-004

`OPEN-WEB-METRICS-001` é **advisory/non-scoring**.

O relatório pode ajudar a explicar problemas de experiência, carregamento e plataforma, mas não altera pesos, gates, Coverage, Confidence, Consolidation ou Overall de SARI-001/SCORE-GEO-004.

Qualquer mudança futura que torne uma dessas evidências parte do scoring exige decisão metodológica explícita, versão adequada do contrato e proteção contra dupla contagem.

## Métodos avaliados, mas não ativados automaticamente nesta etapa

O princípio “sem custo fica habilitado por default” não significa executar qualquer serviço externo apenas porque ele possui acesso gratuito. O RASAi também preserva privacidade, previsibilidade, carga no alvo, reprodutibilidade e independência de terceiros.

Por isso:

- **Web Platform Baseline / WebDX / MDN BCD**: excelente candidato, mas requer integrar e versionar dataset de compatibilidade de forma reprodutível; não é inventado a partir do Chromium local;
- **WCAG 2.2 / axe-core direto**: não é duplicado nesta etapa porque a superfície de Accessibility já pode receber Lighthouse/axe; uma segunda execução deve demonstrar ganho de cobertura antes de gerar nova aquisição/duplicação;
- **W3C HTML/CSS validators**: permanecem candidatos a adapter opcional; são serviços externos e não fazem parte do snapshot local;
- **Browsertime/sitespeed.io**: permanecem candidatos a provider sintético opcional; exigem dependências e execução próprias;
- **MDN HTTP Observatory**: permanece candidato a provider de postura HTTP/security; consulta externa e exposição pública do scan devem ser opt-in;
- **WebPageTest**: permanece adapter opcional pela sobreposição com Lighthouse/Browsertime e por depender de serviço externo;
- **SSL Labs**: permanece opcional por limitações operacionais/comerciais da API;
- **ISO 9241-11**: é referência conceitual de usabilidade, não um score que possa ser honestamente inferido de um crawl sintético.

## Proveniência

Todo consumidor desses dados deve tratar, no mínimo, os seguintes campos como parte do contrato:

```text
contract_version
state
enabled_by_default
scope
additional_navigation_requests
additional_external_api_calls
score_impact
methodology
collector
```

O conteúdo efetivo permanece persistido junto ao `browser_metadata` do snapshot em `audit.db`, mantendo a auditoria autocontida e reproduzível sem depender de nova consulta externa para renderizar o HTML.
