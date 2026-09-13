# Logging operacional

O log operacional registra eventos de execução em:

```text
logs/audit.log
```

O objetivo é explicar o comportamento do auditor sem transformar falhas de ferramenta/integrador em findings do website.

## Formato

Eventos são estruturados em JSON Lines e podem incluir:

```text
timestamp
level
event
audit_id
url
device
service
status
duration_ms
http_status
error_code
error_message sanitizada
artifact_reference
```

## Integrações externas

Tentativas PageSpeed e CrUX registram serviço, status, duração e diagnóstico. Exemplo conceitual:

```json
{"level":"WARNING","service":"PAGESPEED_INSIGHTS","status":"ERROR","duration_ms":60131,"error_code":"TIMEOUTERROR"}
```

Esse registro significa falha operacional de coleta; não significa que o site recebeu um finding de performance.

## IA

Tentativas de provider registram somente metadados/diagnósticos sanitizados. API keys e payloads secretos não devem ser registrados.

## Synthetic Apdex

Eventos de navegação sintética podem manter identificadores internos históricos por compatibilidade. A apresentação ao usuário usa `Synthetic Apdex` e não os nomes de marcos de implementação.

## Progresso do console

O console lê apenas o tail limitado do log e o SQLite em modo read-only, aproximadamente uma vez por segundo, para atualizar etapa/progresso. Essa observação não gera chamada HTTP/API adicional e não aumenta a frequência de coleta do pipeline.

A apresentação separa conceitos que não devem ser confundidos:

- `Etapa`: fase funcional atualmente observada;
- `Andamento`: percentual interno da etapa somente quando existe uma unidade mensurável confiável; caso contrário informa `em execução` em vez de fabricar precisão;
- `Progresso`: posição global do pipeline. Enquanto a execução não termina, o valor usa `~` porque combina marcos de fases heterogêneas e opcionais;
- `Executando`: descrição textual derivada do estado já persistido e dos eventos operacionais existentes, por exemplo descoberta de URLs, análise semântica, geração de relatório ou último evento de Web Performance.

Quando uma etapa possui medição própria, por exemplo amostras/contextos de Synthetic Apdex, o percentual medido permanece restrito a `Andamento`. O console projeta esse avanço dentro da faixa global reservada à etapa, mas mantém o `Progresso` geral identificado como estimativa. Assim, `40%` de Synthetic Apdex não é apresentado como `40%` da auditoria inteira e o percentual global não regride ao entrar em uma etapa que começa em zero.

O progresso geral usa pesos de carga configurada/observada. Trabalho repetido e normalmente demorado - contextos Chromium, PageSpeed/CrUX, Synthetic Apdex, Search Intelligence e chamadas de IA - recebe mais peso do que bookkeeping local. Improvement Intelligence, quando habilitada, também participa dessa projeção conforme o esforço configurado, em vez de usar uma faixa terminal fixa.

Depois que Improvement Intelligence termina sua chamada de IA no console, a atualização necessária dos relatórios é uma passagem **somente local/read-only**. Ela atualiza `improvement-intelligence.html`, atribuição de consumo/custo de IA, navegação, UX e manifest a partir das evidências já persistidas. Essa segunda passagem não reexecuta GSC, PageSpeed, CrUX History, Microsoft Clarity, Common Crawl, SERP ou qualquer outro collector/provider externo.

Somente estados terminais como conclusão, conclusão com limitações, bloqueio técnico definitivo ou falha podem apresentar `100%` global como medido.

## Segurança

Nunca registrar:

- API keys;
- tokens bearer;
- passwords;
- cookies/sessões sensíveis;
- headers de autorização;
- secrets do ambiente.

Diagnósticos devem ser limitados em tamanho e sanitizados.

## Relação com o report

Quando uma integração falha, o report deve projetar a causa persistida no log/banco. O HTML não deve ocultar timeout/quota/HTTP nem preencher métricas ausentes com zeros artificiais.
