# Search Intelligence no console interativo

## Objetivo

O console local expõe um input explícito de termos SERP sem transformar termos de busca em variáveis de ambiente.

A separação é intencional:

- `RASAI_SERP_MODE`, `RASAI_SERP_PROVIDER`, a credencial específica do provider e os limites `RASAI_SERP_*` configuram provider, credencial e governança;
- os **termos de busca** são dados da execução corrente;
- termos não são gravados no `rasai-console.ini`;
- Search Intelligence continua não alterando `SARI-001` ou `SCORE-GEO-004`.

Providers live atualmente selecionáveis:

| Provider | Engine | Credencial | URL de cadastro/login |
|---|---|---|---|
| `serpapi` | Google | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> |
| `serpapi-bing` | Bing | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> |
| `zenserp` | Google | `RASAI_ZENSERP_API_KEY` | <https://app.zenserp.com/> |
| `scrapingdog` | Google | `RASAI_SCRAPINGDOG_API_KEY` | <https://api.scrapingdog.com/> |

Os quatro possuem uma oferta gratuita limitada verificada em 11/09/2026; isso não significa uso ilimitado. Consulte [PROVIDER_SETUP.md](PROVIDER_SETUP.md) para a franquia verificada e as ressalvas de quota/custo.

## Uso

No console local, a seção `SEARCH INTELLIGENCE` expõe:

```text
T. Termos SERP
```

Ao selecionar `T`, o console mostra o provider configurado, **qual variável contém sua credencial e a URL oficial para cadastro/login**, além da nota de free tier. Em seguida permite:

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

Se o domínio auditado não aparecer, a interpretação é limitada pela profundidade escolhida. Com `depth=10`, por exemplo, o resultado significa **“domínio não observado no Top 10”**; não significa que o domínio não esteja ranqueado em posições posteriores.

Os adapters Google atuais (`serpapi`, `zenserp` e `scrapingdog`) trabalham com paginação normalizada pelo RASAi em blocos de até 10 posições para o cálculo conservador de orçamento. Portanto, posições `11-20` podem exigir uma segunda chamada. Aumentar a profundidade amplia a chance de localizar o domínio auditado e identificar concorrentes fora do Top 10, mas pode aumentar quota, créditos e duração.

O teto conservador de requests considera quantidade de termos, blocos de 10 posições e tentativas incluindo retries. Com `retries=1`, por exemplo:

```text
3 termos × depth 10 -> até 6 tentativas HTTP
3 termos × depth 20 -> até 12 tentativas HTTP
```

Assim, com `RASAI_SERP_MAX_REQUESTS=10`, três termos em `depth=20` não cabem no orçamento conservador atual.

Para Bing, a paginação é provider-driven; `depth` continua significando o máximo de posições observadas, enquanto `RASAI_SERP_MAX_REQUESTS` permanece como limite rígido global.

`RASAI_SERP_MAX_REQUESTS` limita tentativas HTTP do RASAi. Ele **não representa créditos comerciais**. No ScrapingDog, por exemplo, uma request Google pode consumir vários créditos do plano do fornecedor.

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
- credencial correspondente ao `RASAI_SERP_PROVIDER` ausente em modo `live`;
- provider/engine incompatíveis;
- quantidade de termos acima de `RASAI_SERP_MAX_QUERIES`;
- profundidade acima de `RASAI_SERP_MAX_DEPTH`;
- teto determinístico Google acima de `RASAI_SERP_MAX_REQUESTS`.

Quando a credencial está ausente, a mensagem de configuração inclui a variável esperada e a URL oficial do provider para obtê-la.

Uma falha externa ocorrida **depois** da auditoria principal é fail-open para scoring: o `AUD-*` continua válido e Search Intelligence é apresentado como limitação opcional. Nenhuma falha de SERP reduz o SARI.

## Persistência dos termos

Os termos permanecem somente no estado da sessão do console. Isso evita que salvar o INI transforme uma hipótese de busca específica em default silencioso de auditorias futuras.

Para monitoramento recorrente e persistente de queries, use `rasai search-monitor`, que possui contrato próprio de query registrada e scheduling.

## Exemplos

SerpApi:

```text
RASAI_SERP_MODE=live
RASAI_SERP_PROVIDER=serpapi
RASAI_SERPAPI_API_KEY=[SET]
```

Zenserp:

```text
RASAI_SERP_MODE=live
RASAI_SERP_PROVIDER=zenserp
RASAI_ZENSERP_API_KEY=[SET]
```

ScrapingDog:

```text
RASAI_SERP_MODE=live
RASAI_SERP_PROVIDER=scrapingdog
RASAI_SCRAPINGDOG_API_KEY=[SET]
```

Se o usuário informar no item `T`:

```text
seguro residencial; seguro residencial online
```

e executar uma auditoria de `https://loja.exemplo.com.br`, o console executará a observação com o adapter escolhido e associará o resultado ao mesmo `AUD-*` gerado pela auditoria.
