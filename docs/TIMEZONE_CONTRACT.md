# Contrato de timezone do RASAi

## Decisão

O RASAi usa **UTC (timezone 0)** como referência canônica de tempo no núcleo da aplicação.

A camada de apresentação para o usuário usa, por padrão, o timezone IANA **`America/Sao_Paulo`**.

Essa separação é obrigatória para manter comparabilidade entre auditorias, execução distribuída de workers, scheduling, APIs, PostgreSQL, logs e futuras implantações SaaS em múltiplas regiões.

## Persistência e processamento

Timestamps persistidos ou trocados entre componentes devem ser timezone-aware e normalizados para UTC. O formato canônico é ISO 8601 com offset explícito, por exemplo:

```text
2026-09-10T22:02:15+00:00
```

São abrangidos, entre outros:

- `audit.db` e evidências;
- manifests;
- logs operacionais;
- jobs e workers;
- timestamps de scoring, Apdex, Web Performance e Search Intelligence;
- PostgreSQL/control plane;
- índices analíticos e artefatos derivados;
- payloads de API.

Valores de data sem horário (`YYYY-MM-DD`) não recebem conversão de timezone, pois não representam um instante por si só.

## Relatórios HTML

A apresentação padrão converte timestamps ISO timezone-aware para `America/Sao_Paulo` sem alterar a fonte persistida. Exemplo:

```text
Persistido:  2026-09-10T22:02:15+00:00
Apresentado: 10/09/2026 19:02:15 (America/Sao_Paulo)
```

A transformação ocorre somente em conteúdo visível. Blocos técnicos como `code`, `pre`, `script`, `style` e valores em atributos HTML permanecem canônicos para preservar rastreabilidade e reprodutibilidade.

## Scheduling

Horários de agenda podem ser informados no timezone IANA associado ao usuário ou ao agendamento. `America/Sao_Paulo` é o padrão de apresentação/configuração inicial do produto, mas a ocorrência resolvida e os timestamps de execução devem ser armazenados em UTC.

## Evolução SaaS

A preferência de timezone deve permanecer uma propriedade da camada de apresentação e, futuramente, poderá ser configurada por usuário/workspace. Alterar a preferência de exibição não deve reescrever timestamps históricos nem modificar evidências imutáveis.
