# Perfis de execução sintética

## Objetivo

Medições dependentes de browser não devem ser interpretadas apenas pelo rótulo `Mobile` ou `Desktop`. O RASAi separa a condição de laboratório em três dimensões configuráveis e persistidas:

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

### Compatibilidade histórica de Tablet

O runtime mantém presets Tablet apenas para leitura/reprocessamento de evidência histórica que já os tenha persistido. Tablet **não integra a superfície pública de novas AUDs**, não é opção de `Device` e não aparece no catálogo avançado de configuração.

## Configuração

As opções públicas são independentes para Mobile e Desktop:

```text
RASAI_APDEX_MOBILE_CLIENT_PROFILE
RASAI_APDEX_MOBILE_HARDWARE_PROFILE
RASAI_APDEX_MOBILE_NETWORK_PROFILE

RASAI_APDEX_DESKTOP_CLIENT_PROFILE
RASAI_APDEX_DESKTOP_HARDWARE_PROFILE
RASAI_APDEX_DESKTOP_NETWORK_PROFILE
```

O console interativo apresenta somente essas seis variáveis. O SaaS/worker projeta o mesmo contrato público. Identificadores Tablet, quando encontrados em dados históricos, são compatibilidade interna e não devem ser oferecidos para criar uma nova população.

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

O relatório `cat-06.html` mostra os presets efetivos e os valores de CPU/rede/viewport persistidos na execução.

## Synthetic User Experience Apdex

Experience usa o **mesmo device da AUD** e o perfil correspondente:

```text
AUD mobile  -> perfil MOBILE em 100% das amostras Experience
AUD desktop -> perfil DESKTOP em 100% das amostras Experience
```

Não existe `device_mix` público separado. O relatório `cat-07.html` mostra o device e os presets efetivos da população sintética, junto com concorrência, delay e sessão.

Os mesmos IDs públicos são usados localmente e no SaaS. Em uma nova AUD, o perfil efetivo é congelado na configuração persistida. Em um RPR da mesma AUD, o runtime reutiliza esse perfil congelado mesmo que operador, INI ou worker tenham sido alterados depois. Ao complementar uma AUD com CAT-07, a nova população usa a configuração efetiva do complemento e então também fica congelada.

## Synthetic Population Apdex

A camada populacional opcional de CAT-07 reutiliza este mesmo catálogo de presets. Cada estrato declara explicitamente cliente, hardware, rede, sessão e peso. Na V1, todos os estratos mantêm o mesmo device congelado da AUD; a população não reintroduz mix Mobile/Desktop e não oferece Tablet para novas execuções.

A composição é determinística: não existe jitter contínuo nem sorteio de perfil por amostra. Concorrência e delay continuam sendo política operacional de execução, e não uma dimensão da população. Geografia de rede não é modelada nesta versão; coordenadas de geolocalização do navegador não representam região física do runner, rota de rede, CDN/POP ou latência geográfica.

Pesos devem somar 100 e possuem origem explícita. Os resultados por estrato e o agregado ponderado são persistidos separadamente do baseline Synthetic User Experience Apdex. Detalhes em [SYNTHETIC_POPULATION_APDEX.md](SYNTHETIC_POPULATION_APDEX.md).

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
