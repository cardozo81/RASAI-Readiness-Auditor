# Modelo de contexto de coleta

## Objetivo

O RASAi separa evidências pelo menor contexto em que o valor pode efetivamente mudar. Essa separação evita três erros arquiteturais:

1. repetir requisições globais sem necessidade;
2. misturar resultados Mobile e Desktop como se fossem a mesma execução;
3. penalizar ou contabilizar duas vezes um fato único apenas porque a auditoria possui mais de um dispositivo.

O contrato vigente é `CONTEXT-SCOPE-001`. Ele é um contrato de **coleta, persistência e apresentação**. Nenhuma fórmula, peso, fator, Coverage, Confidence ou regra de consolidação do `SCORE-GEO-004` é alterada por este modelo.

## Escopos canônicos

| Escopo | Significado | Exemplos | Política de aquisição |
|---|---|---|---|
| `ORIGIN` | fato compartilhado pela origem/domínio | `robots.txt`, sitemap, `llms.txt` raiz, política de crawler | adquirir uma vez por auditoria/origin e reutilizar |
| `URL` | fato próprio da URL antes de browser específico | HTTP preflight, HTML bruto, headers, redirects | adquirir uma vez por URL |
| `DEVICE_SNAPSHOT` | fato que pode mudar pelo ambiente de browser | DOM renderizado, runtime JavaScript, visual, Mobile/Desktop | executar separadamente por dispositivo selecionado |
| `PROFILE_MEASUREMENT` | medição sintética dependente do perfil operacional | Apdex de navegação e de experiência | persistir perfil e parâmetros junto do resultado |

## Recursos de domínio/origin

`robots.txt`, sitemaps e os recursos globais de discovery não são requisitados novamente porque a auditoria passou de Mobile para Desktop ou porque possui N URLs.

Fluxo esperado:

```text
Origin
├── robots.txt                  1 aquisição por auditoria/origin
├── sitemap A                   1 aquisição por recurso descoberto
├── sitemap B                   1 aquisição por recurso descoberto
└── llms.txt                    aquisição bounded conforme discovery

URLs auditadas
├── /a
├── /b
└── /c
```

A evidência global pode ser usada pelas avaliações aplicáveis sem transformar uma única aquisição em N fatos independentes.

## URL e HTML bruto

O HTTP preflight e o artifact de HTML bruto pertencem à URL. Um erro estrutural presente nos mesmos bytes do documento não se torna um erro diferente somente porque existem dois dispositivos.

Entretanto, servidores, CDNs e aplicações podem entregar documentos diferentes conforme User-Agent ou Client Hints. Para tornar essa diferença observável sem adicionar uma nova navegação, o RASAi registra no `browser_metadata` de cada snapshot:

- hash SHA-256 do corpo do documento principal recebido naquela navegação;
- tamanho em bytes;
- Content-Type;
- escopo `DEVICE_SNAPSHOT`;
- indicação explícita de que não houve requisição adicional para essa verificação.

Quando Mobile e Desktop foram executados, `context.html` compara esses hashes e informa se o documento recebido foi igual, diferente ou se a comparação ficou inconclusiva.

## JavaScript e erros de runtime

Erros de execução de JavaScript são associados ao dispositivo/snapshot em que foram observados. A captura bounded inclui:

- `CONSOLE_ERROR`;
- `PAGE_ERROR`;
- `REQUEST_FAILED`.

A coleta ocorre na navegação de browser já necessária ao snapshot. Não é criada uma segunda visita apenas para procurar erros.

Exemplo:

```text
URL /produto
├── MOBILE
│   ├── documento recebido: hash A
│   ├── DOM renderizado
│   └── PAGE_ERROR: erro de hidratação
└── DESKTOP
    ├── documento recebido: hash A
    ├── DOM renderizado
    └── sem erro de runtime
```

Nesse cenário o HTML recebido é comum, mas a falha observada é Mobile. O finding/evidência de runtime não deve ser apresentado como falha Desktop.

## Lighthouse

Lighthouse continua sendo uma medição por contexto de dispositivo. Mobile e Desktop são execuções distintas e devem permanecer separadas na apresentação.

Não existe regra de negócio que transforme automaticamente as duas medições em uma média única. Os category scores Lighthouse permanecem independentes do SARI conforme o contrato vigente.

## Apdex sintético

Apdex pertence a `PROFILE_MEASUREMENT`, pois o resultado depende do perfil aplicado, e não apenas do nome do dispositivo.

O perfil deve preservar, quando aplicável:

- device;
- viewport;
- identidade do browser;
- CPU slowdown;
- RTT;
- download e upload;
- tipo de conexão;
- política de cache/sessão;
- thresholds Apdex;
- parâmetros de erro da experiência.

O RASAi não deve apresentar esses perfis como emulação completa de hardware físico. RAM real, GPU real, térmica e scheduler do sistema operacional não são reproduzidos pelo perfil sintético atual.

## Relatórios

A auditoria passa a possuir `report/context.html`, com as seguintes funções:

- explicar os quatro escopos;
- listar recursos origin-scoped;
- mostrar snapshots por dispositivo;
- apresentar hash do documento recebido por dispositivo;
- identificar variação de documento Mobile × Desktop;
- exibir diagnósticos de runtime por snapshot;
- deixar explícito que a superfície é read-only e não recalcula scoring.

A navegação do mini-site é agrupada em:

- Visão e readiness;
- Coleta e dispositivos;
- Search e IA;
- Ações e referência.

## Console interativo e arquivo de configuração

A seleção canônica continua sendo:

```text
RASAI_DEVICE_CONTEXT=mobile|desktop|both
```

O console interativo já projeta e persiste essa escolha no arquivo de configuração. O contrato de contexto **não cria uma nova chave liga/desliga**, porque a rastreabilidade de escopo é obrigatória e não deve depender de uma configuração que possa ser esquecida.

Consequências:

- `mobile`: somente snapshots e medições Mobile aplicáveis;
- `desktop`: somente snapshots e medições Desktop aplicáveis;
- `both`: snapshots independentes dos dois dispositivos e comparação de variância quando houver dados suficientes;
- recursos `ORIGIN` continuam sendo adquiridos uma vez por auditoria/origin em qualquer das três opções.

Toda configuração futura que altere o comportamento de aquisição deve ser adicionada simultaneamente ao console, validação, persistência do arquivo de configuração e contrato SaaS. Não é permitido criar parâmetro operacional acessível somente por código.

## SaaS e workers

O control plane já persiste `device_context` no payload estruturado do `ExecutionJob` de auditoria. O worker converte o valor persistido para `--device-context`, preservando a mesma semântica da execução local.

O contrato de contexto é automático no worker. Não existe um segundo default específico do SaaS.

Princípios obrigatórios:

- control plane e execução local usam a mesma enumeração `mobile|desktop|both`;
- payload de job permanece sem secrets;
- o worker não refaz recursos globais por dispositivo;
- o `AUD-*/audit.db` continua sendo a fonte de evidência da auditoria;
- `context.html` é produzido a partir das evidências persistidas, sem chamadas de rede ou IA durante sua renderização.

## Política de chamadas de IA

O contrato `AI-CALL-POLICY-001` prioriza menos chamadas, desde que a evidência continue corretamente vinculada ao contexto.

### Análise semântica

A estratégia correta é **uma chamada estruturada por snapshot para todo o conjunto de regras semânticas contratado**, e não uma chamada por regra.

Isso reduz overhead de prompt, latência e tokens sem misturar evidências de snapshots distintos.

Mobile e Desktop não são automaticamente fundidos em uma única chamada porque os `evidence_ids`, o DOM e o conteúdo efetivo podem divergir. Reusar cegamente a resposta de um dispositivo no outro quebraria a rastreabilidade evidence-bound.

### Recursos globais

Uma evidência origin-scoped não deve criar N chamadas de IA apenas porque há N dispositivos. Quando M24 técnico usa IA, a avaliação é consolidada sobre o conjunto bounded de fatos de discovery da auditoria.

### Remediação de conteúdo

Quando houver vários findings elegíveis da mesma página e o contrato do provider permitir resposta estruturada, é preferível consolidá-los na mesma requisição em vez de gerar uma chamada por frase ou por finding isolado.

### Prompts

Prompts estruturados devem instruir o provider a:

- não repetir o conteúdo de entrada;
- não reproduzir o schema na resposta;
- usar texto mínimo nos campos de justificativa;
- não inventar evidências;
- retornar `UNKNOWN` quando a evidência não sustentar conclusão;
- manter a resposta estritamente no schema solicitado.

O runtime adiciona orientação de concisão aos adapters estruturados atuais. Não é imposto um limite agressivo de output tokens que possa truncar JSON obrigatório.

## Regra de decisão

Antes de criar uma nova chamada externa, aplicar esta ordem:

```text
O contexto mudou materialmente?
├── não -> reutilizar evidência persistida / não chamar novamente
└── sim
    ├── múltiplas perguntas compartilham a mesma evidência e schema? -> uma chamada estruturada
    └── evidências independentes ou escopos incompatíveis? -> chamadas separadas
```

A economia de tokens nunca justifica misturar evidências de dispositivos diferentes quando isso reduz rastreabilidade ou muda a semântica da avaliação.
