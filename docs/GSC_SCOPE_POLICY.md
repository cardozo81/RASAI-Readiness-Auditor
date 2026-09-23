# Google Search Console - escopo de property e política de execução

**Estado:** vigente.

## Regra central

Google Search Console não é uma fonte pública consultável para qualquer domínio. O RASAi só pode usar dados GSC quando a conta OAuth possui acesso à property configurada e essa property cobre a URL auditada.

Autenticação e property têm papéis diferentes.

Formas OAuth suportadas:

```text
# recomendado para uso repetido
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN

# alternativa temporária/manual
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

Uma Google API Key não substitui OAuth para dados privados do Search Console.

A property é configurada por:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

Exemplos:

```text
sc-domain:example.com
https://www.example.com/
https://www.example.com/blog/
```

## Compatibilidade property x URL

### Domain property

```text
sc-domain:example.com
```

cobre o domínio e subdomínios, independentemente de protocolo/path.

### URL-prefix

É específica de protocolo, host/porta e prefixo de path.

```text
https://www.example.com/blog/
```

pode cobrir:

```text
https://www.example.com/blog/post-1
```

mas não necessariamente outro protocolo, host ou path fora do prefixo.

## O que o preflight consegue provar

O preflight local consegue validar formato e cobertura estrutural da property para a URL alvo.

Ele não consegue garantir:

- validade futura do Refresh Token/access token;
- OAuth scope suficiente;
- permissão real da conta sobre a property;
- quota/rate limit;
- disponibilidade da API;
- interferência de proxy/VPN/rede.

Por isso `APTO` no console significa configuração estrutural suficiente conhecida, não garantia de resposta futura do Google.

## Política `RASAI_GSC_ENABLED`

| Configuração | Semântica |
|---|---|
| sem override | automático por requisitos |
| `true` | GSC explicitamente obrigatório |
| `false` | GSC explicitamente desabilitado |

O override é booleano e a UI deve usar seleção guiada `true|false`.

### Automático

Com OAuth/property suficientes, GSC pode ser usado. Se a property não cobre a URL, o runtime classifica a fonte como não aplicável para aquela execução e não realiza chamada incompatível.

O mismatch não vira requisito de conclusão em modo automático.

### Obrigatório

Com:

```text
RASAI_GSC_ENABLED=true
```

GSC participa do contrato de fulfillment. Property incompatível é erro de configuração detectável antes da chamada:

```text
PROPERTY_URL_MISMATCH
```

Nesse caso, reprocessar sem corrigir property/política não resolve.

### Desabilitado

Com:

```text
RASAI_GSC_ENABLED=false
```

GSC não deve ser executado nem tratado como requisito da auditoria.

## CAT-05 Search & AI Intelligence

No console interativo, GSC faz parte das fontes de `CAT-05`, junto de SERP, visibilidade em IA e observabilidade aplicável. Isso é agrupamento de produto; os contratos técnicos continuam independentes.

Regras de readiness:

- SERP pode estar apto sem GSC;
- GSC pode estar apto sem termos SERP;
- GSC automático não aplicável não deve invalidar uma fonte Search apta;
- GSC explicitamente obrigatório e incompatível bloqueia `CAT-05`;
- GSC desabilitado não é falha.

Ao abrir `CAT-05`, o console expõe configurações relacionadas de SERP/GSC pelos owners canônicos. Não existe cópia local das variáveis.

## Tela de configuração

A UI deve deixar explícito:

- `RASAI_GSC_ENABLED`: automático/obrigatório/desabilitado;
- `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`: property real do Search Console;
- `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID`: identificador OAuth não secreto;
- `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET`: secret, nunca no INI;
- `RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN`: secret, nunca no INI;
- `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`: alternativa manual temporária e secreta.

`[SET]` significa apenas que há valor disponível; não prova validade, scope ou permissão.

## Reporting e fulfillment

Quando GSC obrigatório falha por incompatibilidade estrutural, o diagnóstico persistido continua usando:

```text
error_class=CONFIGURATION
error_code=PROPERTY_URL_MISMATCH
```

Quando GSC está desabilitado/não solicitado pelo plano efetivo, ausência de dados GSC não deve ser convertida em falha.

Falhas runtime diferentes continuam classificadas conforme sua camada, por exemplo:

```text
OAuth invalid_grant / invalid_client
HTTP 401 / UNAUTHENTICATED
HTTP 403 / PERMISSION_DENIED
HTTP 429
HTTP 5xx
timeout
```

A taxonomia do catálogo não altera essas regras do core.
