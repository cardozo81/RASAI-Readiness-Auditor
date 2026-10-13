# #355 - Conferência simultânea e explícita de Settings e USQL Dynatrace

O consumidor `python -m rasai.dynatrace_live_crosscheck_355` une
os dois adaptadores já disponíveis (Settings API v2 e RUM Classic USQL)
**na mesma chamada de comando**, com um único tenant Dynatrace SaaS,
application ID e janela de ação. Ele não acessa o Dynatrace por padrão:
exige **as duas flags** `--allow-live-settings-read` e
`--allow-live-usql-read`, além de credenciais separadas no ambiente:

- `DYNATRACE_API_TOKEN`: escopo somente de leitura `settings.read`
- `DYNATRACE_USQL_API_TOKEN`: permissão para consulta USQL RUM

Antes do primeiro request, valida HTTPS SaaS sem redirecionamento,
ID de aplicação, URL exata, dispositivo, janela UTC de até 24 horas,
tokens sem caracteres de controle, **valores de token distintos** e
arquitetura declarada. Se os dois tokens forem idênticos, a execução
é recusada antes de qualquer requisição HTTP. Essa é uma restrição
local de separação de credenciais, não uma prova das permissões
atribuídas a cada token pelo tenant.
Executa exatamente um GET Settings 2.0 e um GET USQL Classic,
com limites próprios de tamanho e timeout; se a leitura Settings
falhar, a segunda requisição não é iniciada. Falhas não imprimem
tokens, headers nem corpo bruto da API.

O diagnóstico `SAME_LIVE_TENANT_APPLICATION_SCOPE_ONLY` comprova,
*somente durante aquela execução*, que os dois adaptadores apontaram
ao **mesmo host e app declarados** e retornaram sucesso autenticado
sob seus filtros. Portanto pode marcar
`application_scope_verified_across_sources=true`, mas nunca
`rasai_same_browser_sample_verified`,
`rum_observation_matches_architecture_sample` ou censo de ações
reais como verdadeiros. A identidade RUM de URL/device/janela
não prova a mesma sessão Playwright/M6. Um valor de USQL
`extrapolationLevel` maior que um continua caracterizado como
extrapolação, e zero XHR não prova captura desabilitada.

Não altera settings, thresholds, índices Apdex, SARI, M23/M25,
bancos, AUD, CONS, snapshots ou saída de produção.

Exemplo (executa duas chamadas externas **somente** quando aprovado):

```powershell
python -m rasai.dynatrace_live_crosscheck_355 `
  --live-base-url https://abc123.live.dynatrace.com `
  --application-id APPLICATION-0123456789ABCDEF `
  --target-url https://example.org/produto `
  --dynatrace-device MOBILE `
  --start-timestamp-ms 1791626400000 `
  --end-timestamp-ms 1791630000000 `
  --architecture CSR_SPA `
  --architecture-evidence-id SNP-DECLARADO `
  --soft-navigation observed --async-requests observed `
  --allow-live-settings-read --allow-live-usql-read
```

O resultado é JSON apenas em stdout, sem gravar evidência no sistema.
A CI usa fake readers e não faz GET real. Sem autorização e credenciais
para tenant físico, não é possível homologar o mesmo usuário/
dispositivo/janela RUM e RASAi, nem validar a relação causal com Apdex.
A issue #355 e o épico #357 permanecem abertos.


## Transporte autenticado com IP fixado (12/10/2026)

Antes desta correção, os dois GETs Dynatrace Settings/USQL eram feitos
pelo `urllib` padrão após validar apenas o hostname do tenant.
O socket podia fazer uma segunda resolução DNS, inclusive para
um endereço não público, e poderia obedecer aos proxies do ambiente.
Como ambos os requests contêm tokens de API, essa condição não deve
ser aceita como egress autorizado.

O transporte padrão agora usa `DynatracePinnedOpener`, adaptador
isolado sobre o `PublicWebPinnedOpener` testado no COBS: a conexão
TCP se dirige **somente ao IP público numérico verificado**, o cabeçalho
Host/SNI e a validação do certificado TLS permanecem vinculados ao
hostname original `*.live.dynatrace.com`. É proibido usar proxy,
seguir redirect ou acessar outros endpoints; o GET só é admitido
para `/api/v2/settings/effectiveValues` ou
`/api/v1/userSessionQueryLanguage/table` com query explícita.
Endereços DNS privados/loopback ou respostas mistas são bloqueados
**antes do TCP**. Erros de rede permanecem genéricos, sem retornar
token, headers ou corpo remoto.

Os testes exercitam sockets e TLS simulados em memória, incluindo
mudança público→privado entre DNS preflight e conexão e tentativas
de desviar o token para outros hosts/paths. Não há qualquer consulta
ao Dynatrace real em CI. O transporte explicitamente injetado continua
disponível apenas para testes/fixtures, não é atestado por esta regra.
Ambientes com proxy obrigatório deverão validar uma rota de egress
apropriada separadamente, sem desabilitar o pinning ou TLS.

A consulta live segue **opt-in** e não demonstra a mesma sessão RUM,
dispositivo, URL observada, ações SPA ou equivalência com o Apdex
Sintético M23/M25.


## Integridade JSON da Settings API (12/10/2026)

O leitor live read-only da Settings 2.0 recusa respostas JSON que contenham
**qualquer chave duplicada**, inclusive duplicidade idêntica no objeto raiz
ou aninhada nos valores de threshold/KPM. O parser JSON padrão manteria
silenciosamente a última ocorrência (`last-key-wins`), atribuindo uma
configuração potencialmente conflitante à aplicação consultada. Agora a
resposta ambígua é rejeitada antes da projeção, com mensagem genérica que
não expõe token ou tenant. Testes com resposta HTTP simulada verificam
objetos raiz e aninhados; nenhuma alteração do endpoint, TLS, token,
permissões, M23/M25 ou dados de AUD/CONS.


## Contrato HTTP da resposta Settings 2.0 (12/10/2026)

O leitor live de Settings API exige HTTP 200 **e** media type
`application/json` (aceitando apenas parâmetros opcionais como
`charset=UTF-8`). Respostas com `text/html`, `application/problem+json`,
`application/vnd.api+json`, `application/jsonp` ou `Content-Type` ausente
não são tratadas como dados da configuração Apdex, **mesmo que o corpo
contenha JSON sintaticamente válido**. A rejeição ocorre antes de ler o
corpo, com diagnóstico genérico sem vazar tenant/token. É a mesma fronteira
de MIME já adotada pelo leitor USQL. Testes com transporte falso validam
respostas aceitas/recusadas sem acesso real ao Dynatrace.
Não modifica endpoint, permissões, threshold, interpretação arquitetural,
M23/M25, banco AUD ou score.
