# Métricas HTTP operacionais derivadas

## Objetivo

Este contrato consolida disponibilidade e comportamento HTTP a partir da **aquisição física M2 já executada por URL**. Nenhuma request adicional ao website é criada para calcular estas métricas.

Relação com RASAi: **4/5**. Um crawler, buscador ou agente não consegue interpretar conteúdo que não consegue recuperar de forma consistente; ainda assim, estas métricas permanecem diagnósticas e não alteram automaticamente `SARI-001`/`SCORE-GEO-004`.

## Unidade física correta

O M2 realiza uma aquisição HTTP direta por URL auditada. O M3 preserva os metadados dessa aquisição em `page_snapshots.browser_metadata.raw_http` para cada snapshot de device.

Isso significa que, em uma auditoria Mobile + Desktop, o mesmo `raw_http` pode aparecer em mais de um `DEVICE_SNAPSHOT`. Somar snapshots duplicaria artificialmente a mesma request física.

O contrato operacional portanto:

```text
unidade física = page_id / URL auditada
```

A consolidação deduplica `raw_http` por `page_id` antes de calcular taxas.

## Métricas

### Physical HTTP Observation Coverage

```text
URLs auditadas com raw_http materializado
----------------------------------------- x 100
URLs auditadas
```

Indica cobertura da própria medição.

### HTTP 2xx Success Rate

```text
Aquisições físicas finalizadas em HTTP 2xx
------------------------------------------ x 100
Todas as aquisições físicas observadas
```

Erros de transporte e timeout permanecem no denominador. Isso evita elevar artificialmente a taxa de sucesso retirando justamente as tentativas que falharam antes de receber status HTTP.

### HTTP 4xx Rate

```text
Aquisições físicas finalizadas em HTTP 4xx
------------------------------------------ x 100
Todas as aquisições físicas observadas
```

### HTTP 5xx Rate

```text
Aquisições físicas finalizadas em HTTP 5xx
------------------------------------------ x 100
Todas as aquisições físicas observadas
```

### Transport Error Rate

```text
Aquisições físicas com network_error
------------------------------------ x 100
Todas as aquisições físicas observadas
```

### Transport Timeout Rate

```text
Aquisições físicas com network_error=TIMEOUT
-------------------------------------------- x 100
Todas as aquisições físicas observadas
```

### Redirect Rate

```text
Aquisições físicas com redirect_count > 0
----------------------------------------- x 100
Todas as aquisições físicas observadas
```

### Redirect Completion Rate

```text
Aquisições redirecionadas que terminam sem erro em HTTP 2xx/3xx
-------------------------------------------------------------- x 100
Aquisições físicas redirecionadas
```

### Cross-host Redirect Rate

```text
Aquisições redirecionadas cujo hostname final difere do solicitado
----------------------------------------------------------------- x 100
Aquisições físicas redirecionadas
```

A métrica não afirma, sozinha, que um redirect cross-host é incorreto. Migrações, canonicalização de host e autenticação podem torná-lo intencional. Ela sinaliza topologia observada.

## Escopo e persistência

As métricas consolidadas usam `scope=URL_SET`, com detalhes que preservam:

- quantidade de URLs auditadas;
- quantidade de observações físicas encontradas;
- quantidade de statuses HTTP determináveis;
- chave de deduplicação `page_id`;
- metodologia de cada taxa.

A fonte é identificada como a aquisição física M2 persistida em `page_snapshots.browser_metadata.raw_http`.

## Relação com TTFB e CrUX

Estas métricas não devem ser confundidas com:

- TTFB browser-native de `OPEN-WEB-METRICS-001`, que pertence ao `DEVICE_SNAPSHOT`;
- Core Web Vitals/CrUX, que são dados de campo agregados;
- PageSpeed/Lighthouse, que é execução lab externa;
- Apdex, que possui população, thresholds e metodologia próprios.

Não existe média implícita entre essas famílias.

## Custo SaaS

Custo de provider: **zero**.

Aquisições adicionais ao target: **zero**.

O cálculo usa apenas evidência já persistida, portanto deve permanecer habilitado por default sob `RASAI_DERIVED_READINESS_METRICS=true`.