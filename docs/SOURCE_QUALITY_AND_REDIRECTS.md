# Qualidade da origem, redirecionamentos e bloqueios técnicos

## Objetivo

O RASAI deve distinguir claramente:

1. a URL informada pelo usuário;
2. a cadeia HTTP efetivamente observada;
3. a URL final alcançada pelo cliente HTTP;
4. a URL final alcançada pelo Chromium, quando houver divergência;
5. a existência de falha de transporte que impeça uma análise representativa do conteúdo.

Essa camada é anterior a interpretações GEO, Web Performance e Synthetic Apdex. Ela existe para impedir que uma falha de infraestrutura seja apresentada como ausência de conteúdo, baixa performance ou resultado estatístico normal.

## Fonte da evidência

A aquisição HTTP de Descoberta e aquisição HTTP continua sendo a primeira fonte determinística. `HttpClient` mantém validação TLS normal e registra:

- URL solicitada;
- cada salto de redirecionamento;
- status HTTP de cada salto;
- valor `Location`;
- URL de destino de cada salto;
- URL final observada pelo cliente HTTP;
- status HTTP final, quando obtido;
- classe do erro de rede/transporte;
- mensagem técnica sanitizada.

O RASAI **não desabilita validação TLS** para conseguir auditar um site com certificado inválido.

Descoberta e aquisição HTTP utiliza um cliente HTTP determinístico e crawler-like. Renderização Desktop e Mobile utiliza Chromium com o perfil real do dispositivo auditado. Como CDN, WAF, proxy, regras por `User-Agent` ou outras políticas podem entregar rotas diferentes a esses clientes, um bloqueio técnico observado somente em Descoberta e aquisição HTTP não encerra mais a auditoria antes de uma confirmação única pelo Chromium.

## Redirecionamento não é erro por definição

Um 301/302/307/308 pode representar comportamento correto, por exemplo migração de hostname ou canonicalização operacional.

O relatório, portanto, separa:

- **observação:** houve redirecionamento;
- **fato técnico:** cadeia, status e destino final;
- **visão HTTP:** rota recebida pelo cliente Descoberta e aquisição HTTP;
- **visão de navegador:** rota efetivamente alcançada pelo Chromium;
- **avaliação determinística:** se existe bloqueio técnico confirmado;
- **validação humana:** se a mudança de hostname/domínio é a intenção de negócio correta.

Troca de hostname e salto `HTTPS → HTTP` recebem destaque porque merecem revisão, mas não são automaticamente tratados como falha quando a cadeia termina corretamente.

## Bloqueios técnicos determinísticos

A política `SOURCE-QUALITY-1` considera sinais fortes de bloqueio, entre outros:

- `TLS` — certificado/cadeia/hostname não validável;
- `DNS` — hostname não resolvido;
- `REDIRECT_LOOP` — cadeia circular;
- `TOO_MANY_REDIRECTS` — limite de saltos excedido;
- `INVALID_REDIRECT` — `Location` ausente ou inválido;
- `PROTOCOL` — falha do protocolo HTTP antes de resposta utilizável.

`TIMEOUT` e erro genérico de conexão não são tratados automaticamente como bloqueadores definitivos nessa política, pois podem ser transitórios. Eles continuam registrados e analisáveis.

## Confirmação por navegador antes do fail-fast

Quando Descoberta e aquisição HTTP indica que **todas as páginas do universo auditado** estão bloqueadas por uma condição forte, o RASAI não encerra imediatamente.

A sequência obrigatória passa a ser:

1. Descoberta e aquisição HTTP preserva integralmente a evidência HTTP original;
2. o sinal é registrado como `SOURCE_QUALITY_PREFLIGHT_BLOCKER`;
3. Renderização Desktop e Mobile executa **uma única navegação Chromium normal por contexto de dispositivo**, a mesma navegação que já seria necessária numa auditoria saudável;
4. o resultado HTTP e o resultado Chromium são reconciliados;
5. somente se o Chromium também não produzir conteúdo utilizável o estado definitivo `SOURCE_QUALITY_BLOCKED` é emitido;
6. depois da confirmação, PageSpeed/CrUX e a população repetitiva do Synthetic Apdex são interrompidos.

Essa verificação não é um bypass de TLS e não é uma repetição sintética. Chromium permanece com validação normal de certificado.

### Quando Chromium recupera a navegação

Se Descoberta e aquisição HTTP observar, por exemplo, uma cadeia que termina em TLS inválido, mas Chromium alcançar conteúdo válido:

- o bloqueio global é revogado;
- o evento `SOURCE_QUALITY_BROWSER_RECOVERED` é persistido;
- a auditoria continua com extração, regras, Score GEO, IA semântica, Web Performance e Apdex conforme a configuração normal;
- o relatório registra `HTTP_BROWSER_ROUTE_DIVERGENCE`;
- a cadeia HTTP original permanece preservada para análise;
- a URL final observada pelo Chromium passa a ser explicitada;
- a auditoria termina com limitação de rastreabilidade, pois os dois clientes receberam rotas técnicas distintas.

Esse cenário pode indicar, sem afirmar causalidade automaticamente:

- roteamento condicionado por `User-Agent`;
- regra de CDN/proxy/WAF;
- política anti-bot;
- canonicalização diferente entre clientes;
- comportamento transitório ou geograficamente condicionado.

O RASAI registra os fatos; a intenção de negócio precisa ser validada pelo analista responsável.

### Quando Chromium confirma o bloqueio

Se Chromium também falhar:

1. o RASAI grava limitação explícita;
2. a análise semântica completa não é chamada sobre conteúdo inexistente;
3. Sugestões e remediação de conteúdo por IA não tenta remediar texto sem corpus confiável;
4. PageSpeed/CrUX não são chamados;
5. Synthetic Apdex não executa 100/125 navegações redundantes;
6. Web Performance externo e Synthetic Navigation Apdex registram `SKIPPED_SOURCE_BLOCKER`, com zero tentativas correspondentes;
7. o audit termina como `COMPLETE_WITH_LIMITATIONS`, preservando o diagnóstico produzido.

Essa política economiza tráfego, tempo e custo de API sem converter a falha do site em sucesso.

### Escopo parcial

Se somente parte das URLs estiver bloqueada, o RASAI não interrompe globalmente o audit. O fail-fast global é aplicado somente quando todo o universo auditado permanece tecnicamente bloqueado após a reconciliação disponível. As URLs problemáticas continuam identificadas individualmente.

## Synthetic Apdex

A metodologia Synthetic Navigation Apdex não foi modificada.

A especificação existente permite classificar uma tentativa de Task como `FRUSTRATED` quando ocorre erro de aplicação, timeout ou erro de navegação após o perfil sintético ter sido aplicado.

A correção de qualidade da origem atua antes da população repetitiva:

- Descoberta e aquisição HTTP identifica um bloqueio candidato;
- Chromium confirma ou revoga o bloqueio;
- somente um bloqueio confirmado impede Synthetic Navigation Apdex.

Quando confirmado, Synthetic Navigation Apdex persiste:

```text
status = SKIPPED_SOURCE_BLOCKER
attempted_samples = 0
valid_samples = 0
```

Dessa forma, o RASAI não produz um Apdex 0,000 baseado em cem repetições da mesma incompatibilidade técnica já confirmada.

Se Chromium alcançar a página normalmente, Synthetic Navigation Apdex executa segundo a configuração habitual.

## Web Performance externo

Quando a origem permanece totalmente bloqueada após a confirmação por navegador:

```text
web_performance_runs.status = SKIPPED_SOURCE_BLOCKER
context_attempts = 0
PageSpeed attempts = 0
CrUX attempts = 0
```

Se Chromium recuperar a navegação, Web Performance continua normalmente, respeitando as configurações e chaves existentes.

## Explicação opcional por IA

Quando um provider compatível está ativo, o RASAI pode fazer **uma análise complementar de infraestrutura** com base exclusivamente na evidência técnica persistida.

Contrato atual:

```text
SOURCE-QUALITY-AI-v1
```

A IA pode receber, conforme o cenário:

- URL solicitada;
- URL final observada pelo cliente HTTP;
- URL final observada pelo Chromium;
- cadeia de redirecionamentos;
- status HTTP observados;
- classe determinística do erro;
- texto técnico do erro sanitizado;
- indicação de divergência HTTP × navegador;
- flags de troca de hostname e downgrade HTTPS→HTTP.

A IA pode explicar:

- causa provável dentro dos limites das evidências;
- se a cadeia parece tecnicamente coerente;
- se a divergência entre clientes exige investigação de infraestrutura;
- quais ações devem ser verificadas por infraestrutura;
- quais pontos dependem de confirmação humana de intenção de negócio.

### Limites obrigatórios

A IA:

- **não altera** a classificação técnica determinística;
- não pode declarar um certificado inválido como comportamento normal sem considerar a evidência de navegador;
- não pode recomendar desabilitar validação TLS;
- não pode inventar CDN, proxy, servidor, SAN/CN ou configuração não observada;
- não altera SCORE-GEO-002;
- é fail-open: se indisponível, o diagnóstico determinístico continua completo.

O consumo dessa chamada é persistido em `ai_provider_attempts` com tokens/custo estimado quando o provider fornece telemetria.

Providers com wire format que ainda não possuem contrato homologado para essa explicação permanecem sem chamada extra; o relatório continua com diagnóstico determinístico.

## Relatórios individuais

Quando houver diferença entre URL solicitada e URL final, erro técnico ou divergência entre HTTP e Chromium, **todas as páginas HTML do report** recebem o bloco:

> Origem, redirecionamentos e integridade de transporte

O bloco apresenta, conforme disponibilidade:

- URL solicitada;
- cadeia HTTP observada;
- status HTTP de cada salto;
- URL final da visão HTTP;
- URL final efetiva da visão Chromium;
- status HTTP final;
- classe técnica;
- explicação da divergência;
- recomendações determinísticas;
- explicação complementar de IA, quando disponível.

O bloco é idempotente e é aplicado após os enriquecimentos Web Performance externo/Synthetic Navigation Apdex para cobrir também as páginas de Web Performance e Apdex.

## Exemplo que motivou a proteção

A aquisição Descoberta e aquisição HTTP observada em smoke mostrou:

```text
https://mdsgroup.com/
  301 → http://www.mdsgroup.com/
  301 → https://mds.pt/
  TLS  → certificado não validável para o hostname final
```

No mesmo ambiente humano, um navegador convencional alcançou:

```text
https://www.mdsgroup.com/pt/
```

Isso demonstrou que encerrar a auditoria somente pela visão Descoberta e aquisição HTTP era prematuro. O comportamento correto passou a ser **confirmar uma vez com Chromium**.

Resultado esperado após a correção:

```text
Descoberta e aquisição HTTP/HTTP detecta bloqueio candidato
→ Chromium verifica a URL configurada
→ se Chromium chega a conteúdo válido:
     registrar divergência e continuar métricas
→ se Chromium também falha:
     SOURCE_BLOCKED confirmado
     PageSpeed/CrUX = 0 chamadas
     Synthetic Apdex = 0 amostras
```

## Console interativo

O console normal não exibe mais o `stdout` bruto como `Saída recente`/`Saída final`.

Durante execução ele mostra somente estado operacional estruturado:

- Status;
- URL;
- dispositivo;
- operação;
- início/fim/duração;
- etapa;
- progresso;
- detalhe acionável;
- Audit ID;
- caminho do log técnico.

Um `SOURCE_BLOCKED` só deve aparecer depois da confirmação disponível pelo navegador. Quando Chromium recupera a navegação, o pipeline continua e o diagnóstico fica registrado no report/log, sem encerrar a auditoria prematuramente.

Logs internos completos continuam em:

```text
audits/<AUD-ID>/logs/audit.log
```

## Reversibilidade e artefatos

A implementação é aditiva e não cria migration no schema base de `audit.db`.

Artefatos:

```text
artifacts/source-quality-preflight.json  # visão HTTP original antes da reconciliação
artifacts/source-quality.json            # estado técnico reconciliado usado pelo pipeline
artifacts/source-quality-ai.json         # somente quando a camada opcional é executada
```

O artefato `source-quality-preflight.json` preserva a evidência Descoberta e aquisição HTTP original mesmo quando Chromium demonstra que a página é navegável e `source-quality.json` deixa de considerar o caso um bloqueio global.

Web Performance externo/Synthetic Navigation Apdex utilizam suas tabelas aditivas já existentes para registrar `SKIPPED_SOURCE_BLOCKER` somente quando o bloqueio permanece confirmado.

Não há alteração na fórmula de `SCORE-GEO-002` ou na fórmula Apdex.
