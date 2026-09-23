# Identity & Access do RASAi

## Estado e objetivo

**Identity & Access - Identidade e Acesso** é o contrato de autenticação da superfície Web/SaaS do RASAi. Ele não altera o **Índice de Prontidão Search & IA**, o **Método de Pontuação de Prontidão**, o `audit.db`, as **Regras de Avaliação de Prontidão** ou as evidências da auditoria. IDs técnicos relacionados: `SARI-001`, `SCORE-GEO-004` e `BR-GEO-*`.

A separação é:

```text
Identity Provider
  -> autentica a pessoa

RASAi external identity link
  -> mapeia issuer + subject para USR-*

RASAi memberships / roles
  -> autorizam Organization, Workspace e Project
```

Autenticação válida no Identity Provider não concede acesso automaticamente ao RASAi.

## Modos de autenticação

`RASAI_API_AUTH_MODE` aceita:

| Modo | Default/uso | Limite |
|---|---|---|
| `deny` | default fail-closed | não autentica chamadas protegidas |
| `trusted-header` | gateway autenticado ou smoke local controlado | não é autenticação pública por si só |
| `oidc` | recomendado para Web/SaaS | exige configuração OIDC válida |

`trusted-header` só é seguro fora de loopback quando o gateway remove o header de identidade recebido do cliente, autentica a requisição, injeta a identidade confiável e impede acesso direto ao processo RASAi.

## Identidade externa

O vínculo canônico é:

```text
(issuer, subject) -> user_id
```

E-mail pode ser metadata, mas não é a chave de autenticação.

Vincular identidade:

```powershell
rasai platform identity link `
  --user USR-EXISTENTE `
  --issuer https://login.example.com `
  --subject 00u123456789 `
  --email analyst@example.com
```

Consultar:

```powershell
rasai platform identity list
rasai platform identity list --user USR-EXISTENTE
```

Remover vínculo:

```powershell
rasai platform identity unlink --identity IDN-EXISTENTE
```

Remover o vínculo impede novas resoluções daquela identidade. Memberships continuam registros independentes.

## Configuração OIDC mínima

```powershell
$env:RASAI_API_AUTH_MODE = "oidc"
$env:RASAI_OIDC_ISSUER = "https://login.example.com"
$env:RASAI_OIDC_CLIENT_ID = "rasai-web"
$env:RASAI_OIDC_AUDIENCE = "rasai-api"
$env:RASAI_OIDC_REDIRECT_URI = "https://rasai.example.com/auth/callback"
$env:RASAI_OIDC_SESSION_SECRET = "<segredo-forte>"
```

O RASAi é provider-neutral. Não existe uma URL universal para criar o client OIDC: ele deve ser registrado no Identity Provider escolhido pela implantação. A orientação de credencial está em [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

## Variáveis OIDC

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade / dependência |
|---|---|---|---|---|
| `RASAI_OIDC_ISSUER` | sem default | URL HTTPS absoluta, sem credenciais, query ou fragmento | issuer exato do IdP | obrigatório no modo `oidc`; base para discovery e validação `iss` |
| `RASAI_OIDC_CLIENT_ID` | sem default | texto não vazio | client registrado no IdP | identifica o client no Authorization Code flow |
| `RASAI_OIDC_AUDIENCE` | valor de `RASAI_OIDC_CLIENT_ID` | texto | manter client ID salvo requisito distinto do IdP | audience esperada para bearer JWT da API |
| `RASAI_OIDC_REDIRECT_URI` | sem default | URL absoluta; HTTPS; HTTP somente em loopback | HTTPS | callback do browser; define origem esperada para proteção CSRF |
| `RASAI_OIDC_SESSION_SECRET` | sem default | segredo com pelo menos 32 bytes UTF-8 | secret manager | cifra/autentica transações e sessões Web |
| `RASAI_OIDC_CLIENT_SECRET_ENV` | sem default | nome válido de variável de ambiente | referência para secret store | opcional para confidential client; não contém o segredo diretamente |
| `RASAI_OIDC_ALGORITHMS` | `RS256,ES256` | CSV de algoritmos assimétricos suportados | default salvo contrato do IdP | allowlist de assinatura JWT; `none` e algoritmos simétricos não são aceitos |
| `RASAI_OIDC_SCOPES` | `openid,profile,email` | CSV contendo obrigatoriamente `openid` | reduzir ao necessário | scopes do login |
| `RASAI_OIDC_SESSION_TTL_SECONDS` | `28800` | inteiro `300..86400` | `28800` | duração máxima da sessão Web emitida pelo RASAi |

`RASAI_OIDC_SESSION_SECRET` nunca deve ser commitado, gravado em TOML/INI, exibido em log ou persistido no control plane.

### Client secret opcional

Authorization Code + PKCE pode operar como public client quando o IdP permitir. Para confidential client:

```powershell
$env:RASAI_OIDC_CLIENT_SECRET_ENV = "RASAI_IDP_CLIENT_SECRET"
$env:RASAI_IDP_CLIENT_SECRET = "<segredo-do-client>"
```

Somente o nome `RASAI_IDP_CLIENT_SECRET` pode ser tratado como configuração. O valor real permanece no secret boundary.

## Browser login

Com `oidc` ativo:

```text
GET /app
  -> sem sessão válida: /auth/login

/auth/login
  -> OIDC discovery
  -> state + nonce
  -> PKCE S256
  -> authorization_endpoint

/auth/callback
  -> valida state
  -> troca code no token_endpoint
  -> valida id_token
  -> resolve issuer + sub para USR-*
  -> cria sessão Web curta
  -> redirect /app
```

O access token e o ID token recebidos durante login não são persistidos no control plane nem copiados para a sessão do browser.

A sessão contém apenas os dados mínimos para revalidar o vínculo interno. Cookies são `HttpOnly` e `SameSite=Lax`; em HTTPS também são `Secure`.

## Bearer JWT para API

Clientes podem enviar:

```text
Authorization: Bearer <JWT>
```

O RASAi valida:

- algoritmo na allowlist;
- `kid`;
- assinatura por JWKS;
- `iss`;
- `aud`;
- `exp`;
- `sub`;
- rotação de chave por atualização de JWKS quando necessária.

Depois da validação, `(issuer, sub)` precisa estar vinculado a usuário interno ativo e a autorização continua dependendo de memberships.

## Discovery e JWKS

Issuer e endpoints descobertos precisam cumprir o contrato HTTPS. Discovery e JWKS são cacheados em memória por janela curta e atualizados quando necessário. Falha de rede ou configuração resulta em indisponibilidade de autenticação, nunca em bypass.

## CSRF

Operação mutável autenticada por cookie exige `Origin` igual à origem derivada de `RASAI_OIDC_REDIRECT_URI`. Bearer JWT não usa cookie e não depende dessa verificação.

## PostgreSQL e SQLite

Vínculo de identidade pertence ao control plane, não ao `audit.db`.

Em PostgreSQL, migrations são explícitas:

```powershell
rasai platform database migrate
```

Startup normal não aplica migration automaticamente.

SQLite continua disponível para operação local e mantém a mesma separação conceitual.

## Provisionamento

Acesso exige, nesta ordem lógica:

1. `USR-*` existente no control plane;
2. membership/role correspondente;
3. vínculo `(issuer, subject)`;
4. modo `oidc` corretamente configurado.

O runtime não cria Just-In-Time provisioning automaticamente.

## Falhas

| Situação | Resultado esperado |
|---|---|
| auth não configurada | `503` fail-closed |
| bearer/cookie ausente | `401` |
| JWT inválido ou expirado | `401` |
| identidade válida sem vínculo RASAi | `403` |
| membership ausente ou fora do tenant | `403` |
| discovery/JWKS/IdP indisponível | `503` |
| tentativa CSRF com cookie | `403` |

Nenhuma dessas situações cai automaticamente para `trusted-header`.

## Fora do contrato atual

Não fazem parte do contrato vigente:

- SCIM;
- Just-In-Time provisioning automático;
- MFA próprio do RASAi;
- recuperação de senha própria;
- banco de senhas próprio;
- SAML direto;
- federation multi-issuer por Organization;
- refresh token persistido;
- Identity Provider obrigatório específico.

MFA, política de senha, Conditional Access e lifecycle de credenciais pertencem ao Identity Provider escolhido, não ao RASAi.
