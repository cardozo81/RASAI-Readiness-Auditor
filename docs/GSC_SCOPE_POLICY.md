# Google Search Console — escopo de property e política de execução

**Estado:** vigente.

## Regra central

Google Search Console não é uma fonte pública consultável para qualquer domínio. O RASAi só pode usar dados GSC quando a conta Google representada pelo OAuth 2.0 access token possui acesso à property configurada e essa property cobre a URL auditada.

As duas configurações têm papéis diferentes:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

é um **OAuth 2.0 access token temporário** da conta Google autenticada. O token não pertence tecnicamente a um domínio específico e uma mesma conta pode ter acesso a várias properties.

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

A conta autenticada pelo token precisa ter acesso à property informada.

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

- access token expirado;
- access token revogado;
- OAuth scope insuficiente;
- conta sem acesso à property;
- quota/rate limit;
- indisponibilidade da API do Google.

Por isso o console informa explicitamente que **escopo compatível não significa OAuth validado**. A confirmação definitiva de token e permissão ocorre quando o Google aceita a chamada.

## Política global `RASAI_GSC_ENABLED`

A variável possui três semânticas operacionais:

| Configuração | Semântica |
|---|---|
| sem override | automático por requisitos |
| `true` | GSC explicitamente obrigatório |
| `false` | GSC explicitamente desabilitado |

### Automático

Quando credencial e property existem, o RASAi pode tentar GSC. Se a property **não cobre** a URL auditada, o runtime classifica a integração como `NOT_APPLICABLE` para aquela execução e não realiza chamadas GSC incompatíveis.

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

### Usar somente se compatível

É o default seguro dos presets.

O perfil projeta GSC como automático durante a execução. Se a property não cobrir a URL, GSC é `NOT_APPLICABLE` e não bloqueia a conclusão.

### Exigir GSC

O perfil projeta GSC como obrigatório somente naquela execução.

Antes de aplicar o perfil, o console valida localmente:

- presença do token;
- presença da property;
- formato da property;
- cobertura estrutural da URL auditada.

Se houver conflito previsível, o perfil fica `CONFIGURAR` e não é aplicado. Isso evita iniciar uma execução que já se sabe incapaz de chegar a resultado final.

Mesmo com esse preflight aprovado, OAuth/permissão continuam dependentes da resposta do Google. Se o Google rejeitar token/acesso durante a execução, o GSC obrigatório falha e o AUD permanece parcial.

### Não usar GSC

Projeta `RASAI_GSC_ENABLED=false` somente durante a execução do perfil.

### Herdar global

Não altera a política global. Se a configuração global exigir GSC, as consequências de `true` permanecem válidas.

## Tela de configuração

O console deve deixar explícito nos detalhes das três variáveis:

- `RASAI_GSC_ENABLED`: diferença entre automático, obrigatório e desabilitado;
- `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`: property real, não domínio arbitrário do alvo;
- `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`: token da conta Google, não token vinculado diretamente ao domínio.

A indicação `[SET]` de um secret significa apenas que existe um valor na sessão. Não prova validade, expiração, scope OAuth ou permissão sobre a property.

## Reporting e fulfillment

Quando GSC obrigatório falha por incompatibilidade estrutural, o diagnóstico persistido usa:

```text
error_class=CONFIGURATION
error_code=PROPERTY_URL_MISMATCH
```

A mensagem deve informar a property e a URL auditada e explicar que a configuração impede conclusão completa/final.

O tratamento é diferente de falhas como:

```text
HTTP 401 / UNAUTHENTICATED
HTTP 403 / PERMISSION_DENIED
HTTP 429
HTTP 5xx
timeout
```

Essas últimas dependem de resposta do provider. `PROPERTY_URL_MISMATCH` é detectável localmente antes da chamada.

## Reprocessamento

Um RPR não deve ser usado para tentar resolver repetidamente uma incompatibilidade de property.

Antes de reprocessar um GSC obrigatório pendente por `PROPERTY_URL_MISMATCH`, corrija uma destas condições:

1. configure uma property GSC que realmente cubra a URL e à qual a conta OAuth possua acesso; ou
2. mude a política para automático/se compatível quando GSC não for requisito da auditoria; ou
3. desabilite GSC para a execução quando os dados privados do Search Console não fizerem parte do objetivo.

A alteração de política deve ser consciente: transformar um requisito obrigatório em opcional muda o contrato esperado da auditoria, não "corrige" a coleta anterior.
