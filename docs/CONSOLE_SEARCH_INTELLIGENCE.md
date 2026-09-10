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
