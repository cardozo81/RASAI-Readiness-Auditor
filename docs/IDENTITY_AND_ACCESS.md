# Identity & Access do RASAi

## Estado

Esta é a fundação vigente de identidade para a superfície Web/SaaS do RASAi.

Ela não altera `SARI-001`, `SCORE-GEO-004`, `audit.db`, regras BR-GEO ou qualquer evidência de auditoria.

## Objetivo

Separar claramente três conceitos:

```text
Identity Provider
  -> autentica a pessoa

RASAi external identity link
  -> mapeia issuer + subject para USR-*

RASAi memberships / roles
  -> autorizam Organization, Workspace e Project
```

Autenticar no Identity Provider não concede acesso automaticamente ao RASAi.

## Modos de autenticação

`RASAI_API_AUTH_MODE` aceita:

| Modo | Uso | Estado |
|---|---|---|
| `deny` | fail-closed quando autenticação não foi configurada | default |
| `trusted-header` | desenvolvimento local ou gateway que já autenticou o usuário | compatibilidade |
| `oidc` | validação direta de OIDC/JWT e sessão Web | recomendado para evolução SaaS |

`trusted-header` não transforma um header HTTP em autenticação pública segura. Em bind público ele somente pode ser usado atrás de infraestrutura que remova headers do cliente, autentique a requisição e injete a identidade confiável.

## Identidade externa

O RASAi não usa e-mail como chave de autenticação e não converte automaticamente `sub` em `USR-*`.

O vínculo canônico é:

```text
(issuer, subject) -> user_id
```

Exemplo:

```powershell
rasai platform identity link `
  --user USR-EXISTENTE `
  --issuer https://login.example.com `
  --subject 00u123456789 `
  --email analyst@example.com
```

Listagem:

```powershell
rasai platform identity list
rasai platform identity list --user USR-EXISTENTE
```

Remoção:

```powershell
rasai platform identity unlink --identity IDN-EXISTENTE
```

A remoção do vínculo impede novas resoluções daquela identidade. Memberships permanecem registros separados e podem ser administradas independentemente.

## OIDC - configuração mínima

```powershell
$env:RASAI_API_AUTH_MODE = "oidc"
$env:RASAI_OIDC_ISSUER = "https://login.example.com"
$env:RASAI_OIDC_CLIENT_ID = "rasai-web"
$env:RASAI_OIDC_AUDIENCE = "rasai-api"
$env:RASAI_OIDC_REDIRECT_URI = "https://rasai.example.com/auth/callback"
$env:RASAI_OIDC_SESSION_SECRET = "<segredo-forte-fornecido-pelo-secret-manager>"
```

`RASAI_OIDC_SESSION_SECRET` deve ter pelo menos 32 bytes UTF-8. Ele protege estado PKCE e sessões Web. Não deve ser commitado, materializado em TOML, exibido em logs ou gravado no control plane.

### Client secret opcional

O fluxo usa Authorization Code + PKCE e pode funcionar como public client quando o Identity Provider permitir.

Para confidential client, configure somente a referencia para o nome da variável que contém o segredo:

```powershell
$env:RASAI_OIDC_CLIENT_SECRET_ENV = "RASAI_IDP_CLIENT_SECRET"
$env:RASAI_IDP_CLIENT_SECRET = "<segredo-do-client>"
```

O valor do client secret não é persistido pelo RASAi.

## Variáveis OIDC

| Variável | Default | Finalidade |
|---|---|---|
| `RASAI_OIDC_ISSUER` | nenhum | issuer HTTPS exato do Identity Provider |
| `RASAI_OIDC_CLIENT_ID` | nenhum | client usado no Authorization Code flow |
| `RASAI_OIDC_AUDIENCE` | `RASAI_OIDC_CLIENT_ID` | audience esperada para bearer JWT da API |
| `RASAI_OIDC_REDIRECT_URI` | nenhum | callback absoluto; HTTP somente em loopback |
| `RASAI_OIDC_SESSION_SECRET` | nenhum | segredo de criptografia/autenticacao da sessao |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | nenhum | nome da variável que contém client secret opcional |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | allowlist de algoritmos assimétricos |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | scopes do login; `openid` é obrigatório |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | TTL entre 300 e 86400 segundos |

Algoritmos simétricos e `none` não são aceitos pelo contrato atual.

## Browser login

Com `oidc` ativo:

```text
GET /app
  -> se não autenticado: /auth/login

/auth/login
  -> discovery OIDC
  -> state + nonce
  -> PKCE S256
  -> redirect para authorization_endpoint

/auth/callback
  -> valida state
  -> troca code no token_endpoint
  -> valida assinatura, issuer, audience, exp, sub e nonce do id_token
  -> resolve issuer + sub para USR-*
  -> cria sessão Web curta
  -> redirect /app
```

O access token e o ID token recebidos no callback não são persistidos no control plane nem colocados na sessão do browser.

A sessão contém apenas o mínimo necessário para revalidar o vínculo interno e é cifrada/autenticada com o segredo da implantação.

Cookies são `HttpOnly` e `SameSite=Lax`. Em redirect HTTPS também recebem `Secure`.

## Bearer JWT para API

Clientes de API podem enviar:

```text
Authorization: Bearer <JWT>
```

O RASAi valida:

- algoritmo dentro da allowlist;
- `kid`;
- assinatura por JWKS;
- `iss`;
- `aud`;
- `exp`;
- `sub`;
- rotação de chave por refresh do JWKS quando o `kid` não está no cache.

Depois da validação, `issuer + sub` ainda precisa existir no control plane e apontar para usuário ativo.

## Discovery e JWKS

O issuer e os endpoints descobertos precisam usar HTTPS.

Discovery e JWKS são mantidos em cache de memória por janela curta e são atualizados quando necessário. Falha de rede ou configuração do Identity Provider gera indisponibilidade de autenticação, não bypass.

## CSRF

Quando uma operação mutável usa cookie de sessão, a origem do browser precisa coincidir com a origem configurada em `RASAI_OIDC_REDIRECT_URI`.

Bearer JWT não depende de cookie e portanto não usa essa verificação de origem.

## PostgreSQL

O vínculo de identidade é metadado do control plane. Ele não pertence ao `audit.db`.

Em PostgreSQL a tabela é criada somente por migration explícita:

```powershell
rasai platform database migrate
```

Normal startup continua sem aplicar migrations automaticamente.

`platform database status` passa a expor também as versões `identity_current_version` e `identity_supported_version`.

SQLite continua local/default e materializa a extensão de identidade local de forma aditiva.

## Provisionamento

O baseline atual é deliberadamente administrado:

1. criar ou identificar `USR-*`;
2. criar memberships e roles;
3. vincular `issuer + subject` ao usuário;
4. habilitar `oidc` na aplicação.

Não existe Just-In-Time provisioning automático neste estágio.

Essa decisão evita que qualquer conta válida no tenant do Identity Provider passe a ganhar acesso ao RASAi por acidente.

## Falhas

| Situação | Resultado esperado |
|---|---|
| auth não configurada | `503` fail-closed |
| bearer/cookie ausente | `401` |
| JWT inválido/expirado | `401` |
| identidade válida mas não provisionada | `403` |
| membership ausente ou fora do tenant | `403` |
| discovery/JWKS/IdP indisponível | `503` |
| tentativa CSRF com cookie | `403` |

Nenhuma dessas situações deve cair para `trusted-header` automaticamente.

## Fora de escopo desta fundação

Ainda não são baseline obrigatório:

- SCIM;
- Just-In-Time provisioning;
- MFA próprio do RASAi;
- recuperação de senha própria;
- password database;
- SAML direto;
- federation multi-issuer por Organization;
- refresh token persistido;
- billing;
- Identity Provider específico obrigatório.

MFA, políticas de senha, Conditional Access e lifecycle de credenciais devem permanecer no Identity Provider, não ser reimplementados pelo RASAi.
