# Perfis de execução sintética

## Objetivo

Medições dependentes de browser não devem ser interpretadas apenas pelo rótulo `Mobile`, `Desktop` ou `Tablet`. O RASAi separa a condição de laboratório em três dimensões configuráveis e persistidas:

1. **cliente**: viewport, DPR, mobile/touch e identidade Chromium coerente;
2. **hardware**: capacidade relativa de CPU aplicada por slowdown controlado;
3. **rede**: RTT, download, upload e tipo de conexão usados na execução sintética.

Esses perfis pertencem a `PROFILE_MEASUREMENT`. Eles alteram a condição em que uma medição sintética é coletada, mas **não alteram a fórmula Apdex nem o SCORE-GEO-004**.

## Limite de equivalência com hardware real

O RASAi aproxima condições observáveis que o runtime consegue controlar de forma reproduzível. Ele não apresenta como emulado o que não consegue reproduzir fisicamente.

| Característica | Estado |
|---|---|
| viewport | controlado |
| DPR / device scale factor | controlado |
| mobile/touch | controlado |
| identidade de browser | Chromium alinhado ao browser executado |
| CPU | slowdown relativo por Chrome DevTools Protocol |
| RTT | controlado |
| download | controlado |
| upload | controlado |
| cache/sessão | controlado conforme a medição |
| RAM física | não emulada |
| GPU física | não emulada |
| estado térmico | não emulado |
| scheduler do sistema operacional | não emulado |
| Safari/WebKit físico | não emulado |
| Firefox físico | não emulado |

Trocar apenas um User-Agent não transforma Chromium em Safari ou Firefox. Por isso os presets atuais mantêm o engine explícito como Chromium.

## Defaults

Os defaults são envelopes de laboratório controlados e reproduzíveis. Eles não são apresentados como média estatística da população de usuários.

A mudança estrutural mantém a baseline sintética já utilizada pelo RASAi para evitar que uma auditoria mude de resultado apenas porque o catálogo de configuração passou a existir.

### Mobile

Default:

```text
cliente  = mobile-balanced-chromium
hardware = mobile-balanced
rede     = mobile-4g-balanced
```

Condição principal:

```text
viewport = 412 × 915
DPR      = 2.625
CPU      = 4× slowdown relativo
RTT      = 150 ms
download = 1638.4 Kbps
upload   = 750 Kbps
```

Alternativas disponíveis:

```text
cliente  : mobile-compact-chromium | mobile-balanced-chromium | mobile-large-chromium
hardware : mobile-entry | mobile-balanced | mobile-premium
rede     : mobile-3g-constrained | mobile-4g-balanced | mobile-4g-fast | mobile-5g
```

### Desktop

Default:

```text
cliente  = desktop-balanced-chromium
hardware = desktop-balanced
rede     = desktop-balanced
```

Condição principal:

```text
viewport = 1440 × 900
DPR      = 1
CPU      = 1×
RTT      = 40 ms
download = 10240 Kbps
upload   = 10240 Kbps
```

Alternativas:

```text
cliente  : desktop-1366-chromium | desktop-balanced-chromium | desktop-wide-chromium
hardware : desktop-constrained | desktop-balanced
rede     : desktop-constrained | desktop-balanced | desktop-fiber
```

### Tablet

Default:

```text
cliente  = tablet-balanced-chromium
hardware = tablet-balanced
rede     = tablet-4g-balanced
```

Condição principal:

```text
viewport = 1024 × 1366
DPR      = 2
CPU      = 2× slowdown relativo
RTT      = 100 ms
download = 4096 Kbps
upload   = 2048 Kbps
```

Alternativas:

```text
cliente  : tablet-compact-chromium | tablet-balanced-chromium
hardware : tablet-entry | tablet-balanced | tablet-premium
rede     : tablet-4g-balanced | tablet-wifi
```

## Configuração

As opções são independentes por dispositivo:

```text
RASAI_APDEX_MOBILE_CLIENT_PROFILE
RASAI_APDEX_MOBILE_HARDWARE_PROFILE
RASAI_APDEX_MOBILE_NETWORK_PROFILE

RASAI_APDEX_DESKTOP_CLIENT_PROFILE
RASAI_APDEX_DESKTOP_HARDWARE_PROFILE
RASAI_APDEX_DESKTOP_NETWORK_PROFILE

RASAI_APDEX_TABLET_CLIENT_PROFILE
RASAI_APDEX_TABLET_HARDWARE_PROFILE
RASAI_APDEX_TABLET_NETWORK_PROFILE
```

No console interativo cada variável é apresentada como lista enumerada com os valores permitidos e o default efetivo. Overrides não secretos são persistidos no arquivo de configuração do console.

O SaaS usa os mesmos identificadores como campos enum do job de auditoria. O worker projeta os valores para o mesmo runtime usado localmente; não existe uma tabela de defaults específica para o SaaS.

## Synthetic Navigation Apdex

Cada combinação URL × dispositivo usa o perfil correspondente ao dispositivo observado no snapshot.

Exemplo:

```text
URL /produto
├── MOBILE
│   ├── cliente  mobile-balanced-chromium
│   ├── CPU      mobile-balanced
│   └── rede     mobile-4g-balanced
└── DESKTOP
    ├── cliente  desktop-balanced-chromium
    ├── CPU      desktop-balanced
    └── rede     desktop-balanced
```

O relatório `apdex.html` mostra os presets efetivos e os valores de CPU/rede/viewport persistidos na execução.

## Synthetic User Experience Apdex

O device mix e o perfil são conceitos diferentes:

```text
device mix
= proporção de user actions por Mobile/Desktop/Tablet

perfil do dispositivo
= condição de cliente + CPU + rede usada para executar cada ação daquele grupo
```

O relatório `apdex-experience.html` mantém essa distinção e mostra os presets efetivos da população sintética.

## Lighthouse / PageSpeed Insights

A integração atual com PageSpeed Insights permite ao RASAi escolher a estratégia `mobile` ou `desktop`. O serviço remoto decide os detalhes efetivos de throttling, CPU e screen emulation usados pela execução Lighthouse.

Por isso os presets sintéticos do RASAi **não são enviados ao PageSpeed Insights como se fossem parâmetros Lighthouse customizáveis**.

Quando o resultado PageSpeed contém `lighthouseResult.configSettings`, o RASAi preserva e apresenta os valores efetivos retornados pelo provider, incluindo quando disponíveis:

- form factor;
- throttling method;
- RTT;
- throughput;
- request latency;
- download/upload throughput;
- CPU slowdown multiplier;
- screen emulation;
- user agents;
- benchmark index.

Isso permite comparar a condição efetivamente usada pelo Lighthouse com a condição controlada do Apdex sem declarar equivalência onde ela não existe.

## Princípio de leitura

```text
Resultado sintético
= página observada
+ dispositivo/contexto
+ perfil de cliente
+ perfil de CPU
+ perfil de rede
+ política de sessão/cache
+ protocolo da métrica
```

Comparar resultados coletados sob perfis diferentes sem considerar essas dimensões pode produzir conclusão incorreta. Por isso os identificadores dos perfis fazem parte da evidência persistida e da apresentação do relatório.
