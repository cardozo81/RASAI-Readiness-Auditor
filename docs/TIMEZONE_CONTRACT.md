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

## Projeção de relatório por AUD - evolução #692

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


## Correções verificáveis posteriores na branch #692

A exibição de validade TLS no CAT-01 utilizava `configured_presentation_timezone()`
(host atual) mesmo quando a configuração histórica da AUD definia outro IANA.
O materializador passa a configuração congelada da AUD para
`architecture_audit_facts_html`, preservando os valores Unix UTC e os campos
UTC como evidências. Teste focal usa 11/09/2026 00:00:00 UTC =
10/09/2026 21:00:00 America/Sao_Paulo com o host configurado em Asia/Tokyo.

O companheiro privado contextual agora lê o mesmo campo persistido por SQLite
somente leitura (`immutable=1`), exibe o fuso aplicado e preserva o literal no
`evidence.json`. Sem configuração histórica, o fallback é explícito com N/D.

As funções tipadas `format_presentation_http_date` e
`format_presentation_unix_epoch` permitem representar cabeçalhos HTTP GMT e
epoch em segundos/milissegundos sem presumir unidade para números avulsos,
alterar duração, ou converter data-only. Aplicação por campo exige prova de
tipo; não se aplica substituição global a strings externas.

**#692 ainda não pode ser encerrada:** falta inventário exaustivo por campo
temporal renderizado e testes/homologação física do conjunto completo de 21
páginas da AUD real, inclusive provas RFC/epoch quando disponíveis. O resultado
sintético não certifica essa cobertura.

A leitura HTTP-date tipada aceita as três variantes do RFC 7231 (IMF-fixdate, RFC850 e asctime), incluindo GMT implícito apenas no asctime do contrato HTTP. Datas genéricas de e-mail ou sem tipo não recebem conversão automática.


## Inventário temporal por campo e página — evolução da #692

A leitura offline usa o módulo rasai.report_temporal_inventory. O resumo
report-temporal-presentation-inventory-v1 foi preservado. A extensão aditiva
report-temporal-field-inventory-v1 identifica o tipo do dado temporal em
cada nó de texto do HTML final, linha, caminho das tags e gerador estático
do corpo até o shell de apresentação. O resultado registra apenas classes,
posições e totais; não publica timestamps literais, URLs, hashes, atributos
ou conteúdo comercial adjacente. Há limite de 512 campos por página, com
contador de registros omitidos e resumo que não é truncado.

Classes de leitura: LOCAL_PRESENTATION (fuso exibido);
OTHER_DECLARED_TIMEZONE_REVIEW (outro fuso explícito — revisar, não presumir
erro); AWARE_ISO_VISIBLE_REVIEW (ISO aware ainda apresentado em texto);
HTTP_DATE_VISIBLE_REVIEW (data GMT cuja conversão depende de campo tipado);
NAIVE_TIMEZONE_ND (timestamp sem fuso); DATE_ONLY_UNSHIFTED (data civil,
sem deslocamento); TECHNICAL_ISO_PRESERVED e
TECHNICAL_HTTP_DATE_PRESERVED (evidência literal em bloco técnico).

Comando, sobre saída derivada — nunca sobre a AUD histórica selada:

    python -m rasai.report_temporal_inventory --report-dir CAMINHO_DO_REPORT --timezone America/Sao_Paulo

**Limitação de aceite:** os campos podem estar divididos entre nós de texto;
atributos, epoch sem tipo, duração e horários externos não comprovados
continuam N/D. O mapa de geradores é estático e os wrappers em runtime
podem especializar a origem efetiva. Mesmo 21/21 páginas inspecionadas
não representam prova de cobertura exaustiva nem homologação física Windows.
Fechar a #692 exige reconciliação dos candidatos, documentação por campo,
testes de paridade não temporal e validação da AUD real sem alteração de hashes.
