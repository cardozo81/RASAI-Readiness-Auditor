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
