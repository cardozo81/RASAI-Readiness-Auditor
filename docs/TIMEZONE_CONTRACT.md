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

## Preferência do usuário no console local

O console interativo expõe **Timezone apresentação** como configuração não sensível. O default é `America/Sao_Paulo` e a preferência salva fica no arquivo `rasai-console.ini`:

```ini
[presentation]
timezone = America/Sao_Paulo
```

O console apresenta uma lista curta de regiões comuns e permite informar qualquer identificador IANA suportado pelo runtime, por exemplo `Pacific/Auckland`. O valor é validado antes de ser aceito.

Offsets numéricos como `-03:00` **não são persistidos como timezone do usuário**. O console mostra o offset atual apenas como orientação, por exemplo:

```text
America/Sao_Paulo (UTC-03:00)
```

O identificador IANA é necessário porque um offset fixo não carrega regras regionais, transições históricas ou eventuais mudanças de horário de verão. Assim, o usuário escolhe uma região compreensível sem comprometer a semântica temporal.

Durante a execução local, a preferência é projetada para `RASAI_PRESENTATION_TIMEZONE`. Um override de ambiente IANA válido pode prevalecer sobre o INI para automação avançada. Esse override altera somente a camada de apresentação; timestamps canônicos continuam UTC.

INIs anteriores que não possuem `[presentation]` permanecem compatíveis e usam `America/Sao_Paulo`. Valor IANA inválido no INI é rejeitado com aviso e o console retorna ao default seguro.

## Scheduling

Horários de agenda podem ser informados no timezone IANA associado ao usuário ou ao agendamento. `America/Sao_Paulo` é o padrão de apresentação/configuração inicial do produto, mas a ocorrência resolvida e os timestamps de execução devem ser armazenados em UTC.

A preferência de apresentação pode servir como default para novos agendamentos, porém um agendamento futuro poderá possuir timezone próprio sem alterar a preferência do usuário.

## Evolução SaaS

A preferência de timezone permanece uma propriedade da camada de apresentação. No modo local ela é persistida em `rasai-console.ini`; no SaaS deverá migrar para o perfil do usuário/workspace no control plane.

Alterar a preferência de exibição não deve reescrever timestamps históricos, modificar evidências imutáveis nem mudar o instante real de jobs já resolvidos.

## Projeção de relatório por AUD — evolução #692

Na materialização de `report-catalog`, a origem preferida do timezone é
`audit_execution_configurations.configuration_json.settings.presentation.timezone`.
Se ausente, utiliza-se o campo persistido `settings.environment.RASAI_PRESENTATION_TIMEZONE`.
Não é permitido substituir uma configuração histórica pelo ambiente Windows,
variáveis do processo atual ou fuso do navegador. Quando não existe valor persistido
ou ele é inválido, o relatório identifica **fuso histórico N/D** e aplica
explicitamente o padrão do produto `America/Sao_Paulo`, sem alegar que foi
escolhido pelo operador. Se os dois campos persistidos divergem, a apresentação
privilegia `settings.presentation.timezone` e sinaliza conflito.

O shell compartilhado projeta a preferência nas 21 páginas (incluindo
`geo-content-review.html`) para timestamps ISO 8601 com offset conhecido.
O literal sem fuso e a data-only não sofrem deslocamento inferido; `code`,
`pre`, `script` e `style` continuam como prova técnica. O manifesto e o
banco da AUD mantêm seus valores e hashes. A apresentação de datas de fontes
em formatos adicionais, como cabeçalhos RFC 7231 e epoch, deve ser resolvida
pelo renderer de cada campo tipado, nunca por substituição cega de texto.
