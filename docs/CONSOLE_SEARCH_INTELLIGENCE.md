# Search Intelligence no console interativo

## Objetivo

Search Intelligence observa posições e contexto SERP para termos informados pelo operador e associa a evidência ao `AUD-*` da auditoria.

O console separa três domínios:

1. **inputs da próxima execução**: termos, profundidade, região, device SERP e análise competitiva;
2. **provider/governança**: `RASAI_SERP_MODE`, `RASAI_SERP_PROVIDER`, limites `RASAI_SERP_*` e registry canônico;
3. **credencial**: variável secreta exigida pelo provider live selecionado.

Search Intelligence é evidence-bound e não altera `SARI-001` ou `SCORE-GEO-004` por ausência ou falha de SERP.

## Acesso

Na preparação da auditoria, selecione a capacidade:

```text
INÍCIO > PREPARAR AUDITORIA > SEARCH INTELLIGENCE
```

A tela apresenta estado, explicação, parâmetros próprios e somente as dependências/configurações relacionadas ao domínio Search.

As configurações do provider podem também ser encontradas em:

```text
INÍCIO > Integrações e serviços
```

ou pelo catálogo completo em:

```text
INÍCIO > Todas as configurações
```

## Inputs da próxima execução

O fluxo permite definir:

- um ou mais termos separados por `;`;
- profundidade SERP;
- device SERP `mobile` ou `desktop`;
- região/localidade opcional;
- classificação competitiva determinística.

Esses campos são inputs da execução, não variáveis de ambiente.

### Sessão e persistência explícita

Os inputs permanecem na sessão durante a configuração normal. Se o operador usar `Salvar configuração`, os valores não sensíveis são gravados no `rasai-console.ini` e restaurados ao carregar esse arquivo.

A seção persistida contém, quando a capacidade existe no estado do console:

```text
[search_intelligence]
queries = ...
depth = ...
region = ...
device = mobile|desktop
competitive = true|false
```

Credenciais SERP nunca são escritas nessa seção nem em qualquer outra parte do INI.

O snapshot do `AUD-*` também preserva inputs reproduzíveis da execução conforme o contrato de reutilização de auditoria.

## Provider e credencial

O catálogo de provider é publicado por `search_intelligence.provider_catalog`. O console não mantém uma lista concorrente de compatibilidade.

Providers live suportados pelo catálogo vigente incluem integrações baseadas em SerpApi, Zenserp e ScrapingDog, além das variantes de engine publicadas pelo registry.

Para `mode=live`, o preflight exige a credencial correspondente ao provider. A tela informa o nome da variável e, quando publicado pelo registry, a URL oficial de cadastro/login.

Exemplos de variáveis encontradas no catálogo vigente incluem:

```text
RASAI_SERPAPI_API_KEY
RASAI_ZENSERP_API_KEY
RASAI_SCRAPINGDOG_API_KEY
```

O nome efetivo deve ser obtido pelo registry do provider selecionado.

## Profundidade SERP

`depth=N` significa observar até a posição orgânica `N`, respeitando os limites do provider e do RASAi.

Exemplos:

```text
depth=1  -> posição 1
depth=10 -> Top 10
depth=20 -> Top 20
```

Se o domínio não for observado em `depth=10`, o significado é **não observado no Top 10**. Não é evidência de ausência além dessa profundidade.

Providers Google normalizados em blocos de até 10 posições podem exigir chamadas adicionais para profundidades maiores. O teto conservador considera termos, blocos e tentativas/retries do adapter.

Exemplo conceitual com `retries=1`:

```text
3 termos × depth 10 -> até 6 tentativas HTTP
3 termos × depth 20 -> até 12 tentativas HTTP
```

`RASAI_SERP_MAX_REQUESTS` é limite de tentativas HTTP do RASAi, não equivalência direta com créditos comerciais cobrados pelo fornecedor.

## Device e região

O device SERP é independente do `Device` principal da auditoria. Search pode observar `mobile` ou `desktop` sem alterar os contextos das demais etapas.

A região adiciona localização específica quando ranking geográfico é relevante. Deixar vazio preserva o contexto geral de mercado/país sem forçar uma localidade adicional.

## Classificação competitiva

A classificação competitiva determinística usa a SERP já coletada e não cria por si só uma nova chamada comercial.

Comparação aprofundada de conteúdo e análises por IA pertencem às capacidades próprias e, quando usam IA, reutilizam a seleção principal da execução.

## Readiness e preflight

Com termos configurados, o preflight valida o contrato SERP antes da auditoria. Podem bloquear a capacidade:

- `RASAI_SERP_MODE=disabled`;
- provider desconhecido ou engine incompatível;
- credencial ausente em modo live;
- quantidade de termos acima de `RASAI_SERP_MAX_QUERIES`;
- profundidade inválida ou acima de `RASAI_SERP_MAX_DEPTH`;
- teto projetado acima de `RASAI_SERP_MAX_REQUESTS` quando a paginação permite cálculo conservador.

O estado exibido na preparação é recalculado a partir desses validadores.

## Execução e persistência no AUD

Quando Search Intelligence é solicitado e a auditoria principal permite a etapa, o console executa o adapter com:

- domínio/origem auditada;
- mercado e idioma da auditoria;
- provider/mode/credencial configurados;
- termos, depth, device e região da próxima execução;
- workspace do `AUD-*` gerado.

A evidência persistida materializa o relatório:

```text
AUD-*/report/search-intelligence.html
```

Abrir ou renderizar o HTML usa a evidência persistida e não refaz chamadas SERP somente para exibição.

## Falhas externas

Falha de SERP após o core da auditoria é tratada como limitação da capacidade opcional conforme o contrato vigente. O RASAi não fabrica ranking nem reduz score por ausência de evidência externa.

O relatório distingue solicitado/concluído, parcial/falho, desabilitado ou indisponível.

## Monitoramento recorrente

Persistir inputs no INI facilita repetir uma configuração local, mas não substitui o contrato de monitoramento recorrente.

Para série temporal e scheduling de queries, use o domínio próprio de `rasai search-monitor`.

## Segurança

- termos e parâmetros Search não são secrets;
- chaves de provider são secrets e ficam fora do INI;
- relatórios não devem expor a credencial;
- uma key configurada não prova saldo, quota ou disponibilidade futura;
- diagnóstico de integração é consultivo e não substitui a tentativa real do adapter.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [PROVIDER_SETUP.md](PROVIDER_SETUP.md) e [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md).
