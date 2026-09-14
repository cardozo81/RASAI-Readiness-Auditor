# Google Search Console - escopo de property e política de execução

**Estado:** vigente.

## Regra central

Google Search Console não é uma fonte pública consultável para qualquer domínio. O RASAi só pode usar dados GSC quando a conta Google representada pelo OAuth 2.0 possui acesso à property configurada e essa property cobre a URL auditada.

Autenticação e property têm papéis diferentes.

O contrato atual aceita duas formas OAuth:

```text
# modo recomendado para uso repetido
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN

# alternativa temporária/manual
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

No modo recomendado, o RASAi usa Client ID, Client Secret e Refresh Token para obter um access token temporário imediatamente antes da chamada ao Google. Esse access token permanece somente em memória.

No modo manual, `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` recebe um OAuth 2.0 bearer token já emitido e ainda válido. Uma Google API Key, normalmente iniciada por `AIza`, não substitui OAuth para dados privados do Search Console.

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

é a **property real do Google Search Console** usada nas chamadas de Sitemaps, URL Inspection e Search Analytics. Ela não deve ser preenchida simplesmente com o domínio que o RASAi está auditando.

Exemplos válidos de property:

```text
sc-domain:example.com
https://www.example.com/
https://www.example.com/blog/
```

A conta autenticada precisa ter acesso à property informada.

## Compatibilidade entre property e URL auditada

O preflight local consegue validar o **escopo estrutural** da property sem chamar o Google.

### Property `sc-domain:`

```text
sc-domain:example.com
```

cobre `example.com` e seus subdomínios, independentemente de `http`/`https` e do path.

Exemplos estruturalmente compatíveis:

```text
https://example.com/
https://www.example.com/
https://shop.example.com/produto
```

### Property URL-prefix

Uma property URL-prefix é específica de protocolo, host/porta e prefixo de path.

```text
https://www.example.com/blog/
```

pode cobrir:

```text
https://www.example.com/blog/post-1
```

mas não cobre:

```text
http://www.example.com/blog/post-1
https://example.com/blog/post-1
https://www.example.com/produtos/
```

## O que o preflight não consegue provar

Compatibilidade de domínio/property não comprova autenticação.

Mesmo quando a property cobre a URL, ainda podem ocorrer:

- Refresh Token revogado ou inválido;
- Client ID/Client Secret incompatíveis com o grant OAuth;
- access token manual expirado ou revogado;
- OAuth scope insuficiente;
- conta sem acesso à property;
- quota/rate limit;
- indisponibilidade da API ou do endpoint OAuth do Google;
- bloqueio/interferência de rede, proxy ou VPN.

Por isso o console informa explicitamente que **escopo compatível não significa OAuth validado**. A confirmação definitiva de autenticação e permissão ocorre quando o Google aceita a chamada.

## Política global `RASAI_GSC_ENABLED`

A variável possui três semânticas operacionais:

| Configuração | Semântica |
|---|---|
| sem override | automático por requisitos |
| `true` | GSC explicitamente obrigatório |
| `false` | GSC explicitamente desabilitado |

### Automático

Quando uma forma OAuth completa e a property existem, o RASAi pode tentar GSC. Se a property **não cobre** a URL auditada, o runtime classifica a integração como `NOT_APPLICABLE` para aquela execução e não realiza chamadas GSC incompatíveis.

Esse mismatch não vira requisito de conclusão do AUD em modo automático.

### Obrigatório

Com:

```text
RASAI_GSC_ENABLED=true
```

GSC faz parte do contrato de fulfillment da auditoria.

Se a property não cobre a URL auditada, o estado é:

```text
PROPERTY_URL_MISMATCH
```

A falha é de **configuração**, não de rede/provider. Nenhuma chamada GSC incompatível é necessária para descobrir o problema.

Nesse cenário:

- o GSC não é considerado sucesso;
- o requisito permanece não atendido/reprocessável;
- o relatório permanece preliminar/parcial conforme o contrato de fulfillment;
- a auditoria não deve ser considerada `COMPLETE/FINAL` enquanto GSC continuar obrigatório e incompatível;
- reprocessar sem corrigir property/política não resolve o problema.

Exemplo:

```text
URL auditada:
https://www.portoseguro.com.br/

Property configurada:
sc-domain:sersolucao.com.br

RASAI_GSC_ENABLED=true
```

Resultado previsível:

```text
PROPERTY_URL_MISMATCH
AUD parcial/não final
```

Trocar a property para `sc-domain:portoseguro.com.br` **não é solução** se a conta autenticada não possuir acesso real a essa property no Search Console.

## Perfis do console interativo

Os Perfis de Execução possuem uma política GSC **somente para a sessão/próxima execução**. Ela não grava `rasai-console.ini`, não altera Windows/User e não modifica credenciais.

Ao selecionar um perfil, o console oferece:

```text
1. Usar somente se a property GSC cobrir a URL auditada (recomendado)
2. Exigir GSC para considerar a auditoria completa/final
3. Não usar GSC nesta execução
4. Herdar exatamente a política global RASAI_GSC_ENABLED
```

### Precedência e duração da política do perfil

Depois que um perfil é aplicado, sua escolha GSC é autoritativa durante **todo o ciclo daquela execução**, inclusive finalização do mini-site, enriquecimentos de relatório e reconciliações que ocorram depois do processamento físico principal.

A política do perfil não pode ser perdida apenas porque uma camada interna terminou e restaurou temporariamente o ambiente. Em particular:

- `Não usar GSC nesta execução` mantém o GSC desligado até o ciclo do perfil terminar, mesmo quando `RASAI_GSC_ENABLED=true` está configurado globalmente;
- `Usar somente se compatível` mantém semântica automática para o ciclo completo e não herda um `true` global no meio da finalização;
- `Exigir GSC` mantém o requisito até a conclusão da execução;
- `Herdar global` não cria overlay durável e usa a configuração global normal.

Ao remover/limpar o perfil, o valor global anterior é restaurado. Esse mecanismo é transitório de sessão: não persiste alteração no INI, no Windows/User ou no Windows/Machine.

O console e o CLI usam o mesmo gate de escopo property/URL. Assim, uma property incompatível em modo automático é `NOT_APPLICABLE` sem chamada ao Google; em modo obrigatório é erro de configuração; em modo desabilitado nenhuma operação GSC é executada.

### Usar somente se compatível

É o default seguro dos presets.

O perfil projeta GSC como automático durante a execução. Se a property não cobrir a URL, GSC é `NOT_APPLICABLE` e não bloqueia a conclusão.

### Exigir GSC

O perfil projeta GSC como obrigatório somente naquela execução.

Antes de aplicar o perfil, o console valida localmente:

- existência de uma forma OAuth completa: access token manual ou Client ID + Client Secret + Refresh Token;
- presença da property;
- formato da property;
- cobertura estrutural da URL auditada.

Se houver conflito previsível, o perfil fica `CONFIGURAR` e não é aplicado. Isso evita iniciar uma execução que já se sabe incapaz de chegar a resultado final.

Mesmo com esse preflight aprovado, autenticação/permissão continuam dependentes da resposta do Google. Se a renovação OAuth falhar ou o Google rejeitar autenticação/acesso durante a execução, o GSC obrigatório falha e o AUD permanece parcial.

### Não usar GSC

Projeta `RASAI_GSC_ENABLED=false` durante todo o ciclo efetivo do perfil. Nenhuma chamada Sitemaps, URL Inspection ou Search Analytics deve ocorrer nessa execução, ainda que exista credencial/property válida e a política global esteja ativa.

### Herdar global

Não altera a política global. Se a configuração global exigir GSC, as consequências de `true` permanecem válidas.

## Tela de configuração

O console deve deixar explícito:

- `RASAI_GSC_ENABLED`: diferença entre automático, obrigatório e desabilitado;
- `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`: property real, não domínio arbitrário do alvo;
- `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID`: identificador OAuth não secreto;
- `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET`: secret do cliente OAuth, nunca gravado no INI;
- `RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN`: grant de longa duração usado para renovação automática, nunca gravado no INI;
- `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`: alternativa manual temporária, também secreta.

A indicação `[SET]` de um secret significa apenas que existe um valor na sessão. Não prova validade, expiração, scope OAuth ou permissão sobre a property.

## Reporting e fulfillment

Quando GSC obrigatório falha por incompatibilidade estrutural, o diagnóstico persistido usa:

```text
error_class=CONFIGURATION
error_code=PROPERTY_URL_MISMATCH
```

A mensagem deve informar a property e a URL auditada e explicar que a configuração impede conclusão completa/final.

Quando GSC está desabilitado pelo perfil, a ausência de dados GSC não é pendência nem requisito de fulfillment. Um relatório pode mencionar que a integração não foi solicitada naquela execução, mas não deve tratá-la como falha ou motivo de `PARTIAL_RETRYABLE`.

O tratamento é diferente de falhas como:

```text
OAuth invalid_grant / invalid_client
HTTP 401 / UNAUTHENTICATED
HTTP 403 / PERMISSION_DENIED
HTTP 429
HTTP 5xx
timeout
```

`PROPERTY_URL_MISMATCH` é detectável localmente antes da chamada. Falhas OAuth, HTTP e de transporte são classificadas conforme a camada em que ocorrerem.

## Reprocessamento

Um RPR não deve ser usado para tentar resolver repetidamente uma incompatibilidade de property.

Antes de reprocessar um GSC obrigatório pendente por `PROPERTY_URL_MISMATCH`, corrija uma destas condições:

1. configure uma property GSC que realmente cubra a URL e à qual a conta OAuth possua acesso; ou
2. mude a política para automático/se compatível quando GSC não for requisito da auditoria; ou
3. desabilite GSC para a execução quando os dados privados do Search Console não fizerem parte do objetivo.

A alteração de política deve ser consciente: transformar um requisito obrigatório em opcional muda o contrato esperado da auditoria, não "corrige" a coleta anterior.

Consulte [GSC_OAUTH.md](GSC_OAUTH.md) para o fluxo de autenticação atual e [INTEGRATION_DIAGNOSTICS.md](INTEGRATION_DIAGNOSTICS.md) para a classificação de falhas de conectividade/autenticação.
