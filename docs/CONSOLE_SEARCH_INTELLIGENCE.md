# Search Intelligence no console interativo

## Objetivo

O console local expõe um input explícito de termos SERP sem transformar termos de busca em variáveis de ambiente.

A separação é intencional:

- `RASAI_SERP_MODE`, `RASAI_SERP_PROVIDER`, `RASAI_SERPAPI_API_KEY` e os limites `RASAI_SERP_*` configuram provider, credencial e governança;
- os **termos de busca** são dados da execução corrente;
- termos não são gravados no `rasai-console.ini`;
- Search Intelligence continua não alterando `SARI-001` ou `SCORE-GEO-004`.

## Uso

No console local, a seção `SEARCH INTELLIGENCE` expõe:

```text
T. Termos SERP
```

Ao selecionar `T`, o console permite:

1. habilitar Search Intelligence para a próxima auditoria desta sessão;
2. informar um ou mais termos separados por `;`;
3. definir a profundidade, limitada por `RASAI_SERP_MAX_DEPTH`;
4. selecionar `mobile` ou `desktop` para a observação;
5. informar uma região/localidade opcional;
6. habilitar a classificação competitiva determinística dos resultados à frente.

O console exibe orientação contextual antes dos campos de profundidade, dispositivo, região e classificação competitiva. A ajuda é apenas de apresentação: não modifica o contrato de execução nem o scoring.

### O que significa profundidade SERP

`depth=N` define até qual **posição orgânica** o RASAi tentará observar para cada termo.

Exemplos:

- `depth=1`: somente a posição orgânica 1;
- `depth=10`: Top 10;
- `depth=20`: Top 20.

No provider Google/SerpApi vigente, a paginação usada pelo adapter trabalha em blocos de 10 posições. Portanto, posições `1-10` pertencem ao primeiro bloco/página consultado e posições `11-20` exigem um segundo bloco/página. Aumentar a profundidade amplia a chance de localizar o domínio auditado e identificar concorrentes fora do Top 10, mas pode aumentar quota e duração.

O teto conservador de requests para Google/SerpApi considera quantidade de termos, blocos de 10 posições e tentativas incluindo retries. Com `retries=1`, por exemplo:

```text
3 termos × depth 10 -> até 6 requests
3 termos × depth 20 -> até 12 requests
```

Assim, com `RASAI_SERP_MAX_REQUESTS=10`, três termos em `depth=20` não cabem no orçamento conservador atual. O console passa a sinalizar isso no momento do preenchimento e informa uma profundidade compatível quando possível.

Para Bing, a paginação é provider-driven; `depth` continua significando o máximo de posições observadas, enquanto `RASAI_SERP_MAX_REQUESTS` permanece como limite rígido global.

### Dispositivo e região

`mobile` e `desktop` representam contextos de busca distintos e podem produzir ordenações diferentes. Essa escolha vale para a observação SERP e não altera automaticamente o dispositivo das demais etapas da auditoria.

A região/localidade deve ser informada quando o ranking tiver componente geográfico relevante, por exemplo `Porto Alegre, RS, Brazil`. Deixar vazio preserva o contexto de país/mercado já configurado sem adicionar localização mais específica.

A classificação competitiva usa a SERP já observada e não cria uma chamada adicional ao provider de Search. Comparação de conteúdo de páginas e Competitive AI continuam fora deste input básico e exigem as superfícies explícitas correspondentes.

## Execução vinculada ao AUD

Quando a auditoria principal termina com sucesso e existem termos configurados na sessão, o console executa Search Intelligence usando:

- domínio derivado da origem auditada;
- mercado e idioma da auditoria;
- provider/mode/credencial definidos nas variáveis `RASAI_SERP_*`;
- termos, profundidade, device e região informados no item `T`;
- `--audit-workspace` apontando para o `AUD-*` recém-criado.

A persistência especializada permanece aditiva no workspace e materializa, quando a observação foi persistida corretamente:

```text
AUD-*/report/search-intelligence.html
```

O renderer usa a evidência já persistida; ele não executa novas chamadas ao provider durante a abertura do HTML.

## Falhas e preflight

Quando termos estão configurados, o preflight do console também valida o contrato SERP. Exemplos de bloqueio antes da auditoria:

- `RASAI_SERP_MODE=disabled`;
- `RASAI_SERPAPI_API_KEY` ausente em modo `live`;
- quantidade de termos acima de `RASAI_SERP_MAX_QUERIES`;
- profundidade acima de `RASAI_SERP_MAX_DEPTH`;
- teto determinístico Google acima de `RASAI_SERP_MAX_REQUESTS`.

Uma falha externa ocorrida **depois** da auditoria principal é fail-open para scoring: o `AUD-*` continua válido e Search Intelligence é apresentado como limitação opcional. Nenhuma falha de SERP reduz o SARI.

## Persistência dos termos

Os termos permanecem somente no estado da sessão do console. Isso evita que salvar o INI transforme uma hipótese de busca específica em default silencioso de auditorias futuras.

Para monitoramento recorrente e persistente de queries, use `rasai search-monitor`, que possui contrato próprio de query registrada e scheduling.

## Exemplo

Com:

```text
RASAI_SERP_MODE=live
RASAI_SERP_PROVIDER=serpapi
RASAI_SERPAPI_API_KEY=[SET]
```

se o usuário informar no item `T`:

```text
seguro residencial; seguro residencial online
```

e executar uma auditoria de `https://loja.exemplo.com.br`, o console executará a observação Google/SerpApi para esses termos e a associará ao mesmo `AUD-*` gerado pela auditoria.
