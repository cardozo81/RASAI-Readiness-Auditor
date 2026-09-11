# Modelo de contexto de coleta

## Objetivo

O RASAi separa evidências pelo menor contexto em que o valor pode efetivamente mudar. O objetivo é evitar três classes de erro arquitetural:

1. repetir requisições globais sem necessidade;
2. misturar resultados Mobile e Desktop como se fossem a mesma execução;
3. contabilizar ou apresentar repetidamente um fato único apenas porque a auditoria possui várias URLs ou dispositivos.

O contrato vigente é `CONTEXT-SCOPE-001`. Ele define **coleta, persistência e apresentação**. Nenhuma fórmula, peso, fator, Coverage, Confidence ou regra de consolidação do `SCORE-GEO-004` é alterada.

## Escopos canônicos

| Escopo | Significado | Exemplos | Política de aquisição |
|---|---|---|---|
| `ORIGIN` | fato compartilhado pela origem/domínio | `robots.txt`, sitemap, `llms.txt`, política de crawler | adquirir uma vez por auditoria/origin e reutilizar |
| `URL` | fato próprio da URL antes de browser específico | HTTP preflight, HTML bruto, headers, redirects | adquirir uma vez por URL |
| `DEVICE_SNAPSHOT` | fato que pode mudar pelo ambiente de browser | DOM renderizado, runtime JavaScript, visual, Mobile/Desktop | executar separadamente por dispositivo selecionado |
| `PROFILE_MEASUREMENT` | medição sintética dependente do perfil operacional | Apdex de navegação e de experiência | persistir perfil e parâmetros junto do resultado |

## Domínio/origin

`robots.txt`, sitemaps, `llms.txt` e demais recursos globais de discovery não são requisitados novamente porque a auditoria passou de Mobile para Desktop ou porque possui N URLs.

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
└── /n
```

A evidência global pode contribuir para avaliações aplicáveis sem transformar uma única aquisição em N fatos independentes.

### Apresentação canônica de ORIGIN

Os detalhes de `robots.txt`, sitemaps, `llms.txt`, descoberta e controles de crawler ficam concentrados em:

```text
report/crawling-discovery.html
Menu: Domínio e descoberta
```

Essa é a superfície canônica de dados `ORIGIN`. Páginas Mobile, Desktop e `context.html` não repetem o conteúdo detalhado desses recursos. Quando necessário para interpretação, exibem somente referência curta para **Domínio e descoberta**.

## URL e HTML bruto

O HTTP preflight e o artifact de HTML bruto pertencem à URL. Um erro estrutural presente nos mesmos bytes do documento não se torna um erro diferente somente porque existem dois dispositivos.

Entretanto, servidores, CDNs e aplicações podem entregar documentos diferentes conforme User-Agent ou Client Hints. Para tornar essa diferença observável sem adicionar uma navegação extra, o RASAi registra no `browser_metadata` de cada snapshot:

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

Nesse cenário o HTML recebido é comum, mas a falha de execução observada é Mobile.

## Lighthouse

Lighthouse permanece uma medição por contexto de dispositivo. Mobile e Desktop são execuções distintas e devem permanecer separadas na apresentação.

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

O RASAi não apresenta esses perfis como emulação completa de hardware físico. RAM real, GPU real, térmica e scheduler do sistema operacional não são reproduzidos pelo perfil sintético atual.

## Relatórios

A auditoria possui `report/context.html`, responsável por:

- explicar os quatro escopos;
- mostrar snapshots por dispositivo;
- apresentar hash do documento recebido por dispositivo;
- identificar variação do documento Mobile × Desktop;
- exibir diagnósticos de runtime por snapshot;
- apontar para **Domínio e descoberta** em vez de repetir detalhes `ORIGIN`;
- deixar explícito que a superfície é read-only e não recalcula scoring.

A navegação do mini-site é agrupada em:

- Visão e readiness;
- Coleta e dispositivos;
- Search e IA;
- Ações e referência.

No grupo **Coleta e dispositivos**, a organização lógica é:

1. Contexto de captura;
2. Domínio e descoberta;
3. Mobile;
4. Desktop;
5. Web Performance;
6. Acessibilidade;
7. Apdex de navegação;
8. Apdex de experiência.

## Escala de apresentação para múltiplas URLs

O relatório simples permanece para auditorias com **uma única URL**.

Quando uma coleção de resultados possui **duas ou mais URLs distintas**, a camada de apresentação habilita controles locais de leitura:

- filtro por URL;
- filtro por contexto `MOBILE`/`DESKTOP` quando ambos estiverem presentes;
- busca textual por URL, regra, status ou conteúdo visível;
- seleção de quantidade de itens por página;
- paginação local.

A quantidade de URLs não possui limite fixo de apresentação. O gatilho é semântico: `>= 2 URLs distintas`.

A paginação e os filtros são client-side e atuam somente sobre a visualização. Todos os cartões/linhas continuam presentes no HTML gerado para preservar portabilidade, evidência e impressão completa. Listas sem URL só recebem controles quando se tornam materialmente grandes.

## Console interativo e arquivo de configuração

A seleção canônica continua sendo:

```text
RASAI_DEVICE_CONTEXT=mobile|desktop|both
```

O console interativo projeta e persiste essa escolha no arquivo de configuração. O contrato de contexto **não cria uma nova chave liga/desliga**, porque a rastreabilidade de escopo é obrigatória e não deve depender de uma configuração que possa ser esquecida.

Consequências:

- `mobile`: somente snapshots e medições Mobile aplicáveis;
- `desktop`: somente snapshots e medições Desktop aplicáveis;
- `both`: snapshots independentes dos dois dispositivos e comparação de variância quando houver dados suficientes;
- recursos `ORIGIN` continuam sendo adquiridos uma vez por auditoria/origin em qualquer das três opções.

A regra acima descreve os **snapshots core**. Synthetic User Experience Apdex pertence a `PROFILE_MEASUREMENT` e possui um mix populacional próprio: em `mobile` ou `desktop` a experiência é restringida a 100% do dispositivo selecionado para evitar tráfego inesperado; em `both`, o mix Experience explicitamente configurado é preservado, inclusive TABLET quando presente. Isso não promove TABLET a `DeviceContext` core e não cria snapshot Tablet no restante da auditoria.

Toda configuração futura que altere comportamento de aquisição deve ser adicionada simultaneamente ao console, validação, persistência do arquivo de configuração e contrato SaaS. Não é permitido criar parâmetro operacional acessível somente por código.

## SaaS e workers

O control plane persiste `device_context` no payload estruturado do `ExecutionJob` de auditoria. O worker converte o valor persistido para `--device-context`, preservando a mesma semântica da execução local.

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

A estratégia é **uma chamada estruturada por snapshot para todo o conjunto de regras semânticas contratado**, e não uma chamada por regra.

Isso reduz overhead de prompt, latência e tokens sem misturar evidências de snapshots distintos.

Mobile e Desktop não são automaticamente fundidos em uma única chamada porque `evidence_ids`, DOM e conteúdo efetivo podem divergir. Reutilizar cegamente a resposta de um dispositivo no outro quebraria a rastreabilidade evidence-bound.

### Recursos globais

Uma evidência `ORIGIN` não cria N chamadas de IA apenas porque há N dispositivos. Quando a análise técnica de domínio/descoberta usa IA, a avaliação é consolidada sobre o conjunto bounded de fatos globais da auditoria.

### Remediação de conteúdo

Quando vários findings elegíveis da mesma página compartilham contexto e o contrato do provider permite resposta estruturada, é preferível consolidá-los na mesma requisição em vez de gerar uma chamada por finding isolado.

### Prompts

Prompts estruturados devem instruir o provider a:

- não repetir o conteúdo de entrada;
- não reproduzir o schema na resposta;
- usar texto mínimo nos campos de justificativa;
- não inventar evidências;
- retornar estado de indeterminação quando a evidência não sustentar conclusão;
- manter a resposta estritamente no schema solicitado.

O runtime adiciona orientação de concisão aos adapters estruturados atuais. Não é imposto um limite agressivo de output tokens que possa truncar JSON obrigatório.

## Regra de decisão

Antes de criar uma nova chamada externa:

```text
O contexto mudou materialmente?
├── não -> reutilizar evidência persistida / não chamar novamente
└── sim
    ├── múltiplas perguntas compartilham a mesma evidência e schema? -> uma chamada estruturada
    └── evidências independentes ou escopos incompatíveis? -> chamadas separadas
```

A economia de tokens nunca justifica misturar evidências de dispositivos diferentes quando isso reduz rastreabilidade ou muda a semântica da avaliação.
