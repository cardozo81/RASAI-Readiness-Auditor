# 30 - Identity & SaaS Access

**Estado:** VIGENTE para a fundação de identidade da camada Web/SaaS.  
**Natureza:** autenticação, vínculo de identidade e sessão Web; não altera scoring.

## 1. Objetivo

Definir uma fronteira de autenticação adequada à evolução SaaS sem criar banco de senhas próprio, sem transformar o Identity Provider em fonte de autorização RASAi e sem alterar `SARI-001`, `SCORE-GEO-004`, Search Intelligence ou a evidência imutável dos AUDs.

## 2. Separação normativa

```text
Identity Provider
  -> autenticação externa

External Identity Link
  -> issuer + subject -> USR-*

Membership / Role
  -> autorização RASAi
```

Uma identidade autenticada não recebe acesso sem vínculo interno e membership ativo aplicável ao recurso.

## 3. Requisitos normativos

`IAM-001` - o RASAi não deve possuir banco de senhas próprio como requisito da fundação SaaS.

`IAM-002` - o mecanismo preferencial de autenticação Web hospedada deve ser provider-neutral e baseado em OIDC/JWT, sem vincular o produto a um Identity Provider específico.

`IAM-003` - o modo default de autenticação deve permanecer fail-closed (`deny`).

`IAM-004` - `trusted-header` pode permanecer para desenvolvimento local ou gateway já autenticado, mas não deve ser tratado como autenticação pública autossuficiente.

`IAM-005` - em modo `oidc`, não pode existir fallback automático para `trusted-header` após falha, ausência ou indisponibilidade do IdP.

`IAM-006` - a identidade externa canônica deve ser o par estável `(issuer, subject)` e deve ser vinculada explicitamente a um `USR-*` interno.

`IAM-007` - e-mail, nome ou outros claims mutáveis não podem substituir `issuer + subject` como chave de autenticação.

`IAM-008` - autenticação válida no IdP não pode criar automaticamente usuário, membership, role ou acesso a tenant no baseline vigente.

`IAM-009` - o vínculo de identidade pertence ao control plane e nunca ao `audit.db`.

`IAM-010` - o Authorization Code flow do browser deve usar PKCE S256, `state` e `nonce`.

`IAM-011` - JWT deve ser validado contra issuer, audience, expiration, subject, algoritmo permitido e assinatura obtida por JWKS.

`IAM-012` - algoritmos simétricos e `none` não fazem parte do allowlist vigente da validação OIDC.

`IAM-013` - rotação de chave deve ser suportada por refresh de JWKS quando o `kid` do token não estiver no cache atual.

`IAM-014` - discovery e endpoints OIDC descobertos devem usar HTTPS; redirect HTTP somente pode ser aceito em loopback de desenvolvimento.

`IAM-015` - ID token, access token, refresh token, client secret e session secret não podem ser persistidos no control plane.

`IAM-016` - sessão Web deve conter somente identidade mínima e metadados temporais, protegidos por criptografia/autenticação com segredo fornecido pela implantação.

`IAM-017` - cookies de sessão devem ser `HttpOnly`, `SameSite=Lax` e `Secure` quando a origem configurada for HTTPS.

`IAM-018` - chamadas mutáveis autenticadas por cookie devem possuir defesa contra CSRF baseada em origem confiável ou mecanismo equivalente documentado.

`IAM-019` - autorização continua sendo decidida pelo `Principal(user_id)` e memberships do control plane; a camada OIDC não pode duplicar regras de tenancy.

`IAM-020` - usuário interno inativo ou vínculo inexistente deve falhar fechado mesmo quando o JWT externo for válido.

`IAM-021` - falha de discovery, JWKS, token endpoint ou configuração OIDC deve gerar indisponibilidade de autenticação, nunca bypass.

`IAM-022` - PostgreSQL deve aplicar a extensão de identidade somente por migration explícita; startup normal não aplica DDL hospedado.

`IAM-023` - SQLite local pode materializar a extensão de identidade de forma aditiva, preservando o baseline portátil e sem alterar workspaces AUD.

`IAM-024` - o runtime CLI sem `.[web]` deve continuar utilizável; dependências JWT/crypto pertencem à extra Web.

## 4. Configuração dos modos de autenticação

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_API_AUTH_MODE` | `deny` | `deny`, `trusted-header`, `oidc` | `deny` enquanto não configurado; `oidc` para hospedagem; `trusted-header` somente atrás de gateway confiável ou em desenvolvimento local |
| `RASAI_API_TRUSTED_USER_HEADER` | `x-rasai-user-id` | nome de header não vazio e sem espaços | manter default, salvo contrato explícito com gateway |

### `deny`

Endpoints protegidos retornam indisponibilidade de autenticação. É o estado seguro quando o operador ainda não configurou identidade.

### `trusted-header`

Compatível com:

- smoke local em loopback;
- gateway/reverse proxy que já autenticou o usuário e controla o header de identidade.

O gateway precisa remover o header recebido externamente, injetar identidade somente após autenticação e impedir acesso direto ao processo RASAi.

### `oidc`

É o modo recomendado para uma implantação hospedada. O RASAi valida identidade diretamente por OIDC/JWT e converte o resultado para `Principal` somente após resolver o vínculo explícito no control plane.

## 5. External Identity Link

Contrato de persistência:

```text
external_identity_id
user_id
issuer
subject
email                 opcional, informativo
created_at
UNIQUE(issuer, subject)
```

O vínculo não contém token ou segredo.

Operações administrativas:

```text
rasai platform identity link
rasai platform identity list
rasai platform identity unlink
```

Um `(issuer, subject)` não pode apontar simultaneamente para dois usuários RASAi.

## 6. Fluxo no navegador

```text
/app
  -> sessão ausente
/auth/login
  -> discovery
  -> state + nonce + PKCE S256
Identity Provider
/auth/callback
  -> state
  -> code exchange
  -> assinatura + iss + aud + exp + sub + nonce
  -> external identity link
  -> sessão mínima
/app
```

O callback somente estabelece sessão se o vínculo resolver para usuário interno ativo.

## 7. Bearer API

Clientes que não usam browser podem enviar JWT via `Authorization: Bearer`.

O token deve ser validado antes do lookup de identidade. Token criptograficamente válido, mas não vinculado ao control plane, resulta em recusa; não existe provisionamento automático implícito.

## 8. Sessão e CSRF

A sessão Web pode conter:

```text
version
issued_at
expires_at
issuer
subject
```

Não deve conter OAuth token, API key ou client secret.

Chamadas mutáveis por cookie precisam comprovar origem esperada. Bearer requests são independentes desse cookie e usam o próprio token como credencial.

## 9. PostgreSQL e SQLite

PostgreSQL:

```text
platform_identity_schema_migrations
external_identities
```

Migration explícita:

```text
rasai platform database migrate
```

O health/status deve reportar versão corrente e suportada da extensão de identidade.

SQLite continua sendo o backend default do piloto local e cria a extensão de forma aditiva.

## 10. Respostas de falha

Estados mínimos esperados:

```text
503  autenticação não configurada ou IdP indisponível
401  credencial/sessão ausente, inválida ou expirada
403  identidade válida mas não provisionada ou acesso fora do membership
```

Detalhes de erro não devem revelar tokens, cookies, secrets ou conteúdo sensível recebido do IdP.

## 11. Fora de escopo desta fundação

Não fazem parte desta especificação:

- SCIM;
- Just-In-Time provisioning;
- SAML direto;
- MFA implementado pelo RASAi;
- política própria de senha;
- recuperação própria de senha;
- refresh token persistido;
- federation multi-issuer por Organization;
- billing;
- definição de IdP obrigatório.

MFA, password policy, Conditional Access e lifecycle primário da identidade pertencem ao Identity Provider.

## 12. Evidência de validação

A regressão deve cobrir no mínimo:

- vínculo estável e idempotente de identidade externa;
- rejeição de colisão `(issuer, subject)` entre usuários;
- JWT válido e mapeado;
- JWT expirado/inválido;
- identidade autenticada sem vínculo;
- Authorization Code + PKCE + state + nonce;
- criação e expiração lógica de sessão;
- CSRF em operação mutável autenticada por cookie;
- preservação do modo `trusted-header` existente;
- preservação de tenancy após resolução do `Principal`;
- schema/migration PostgreSQL;
- baseline SQLite portátil;
- regressão integral do produto.

Documentação operacional: `../IDENTITY_AND_ACCESS.md`, `../WEB_API_FOUNDATION.md` e `../WEB_API_CLI.md`.