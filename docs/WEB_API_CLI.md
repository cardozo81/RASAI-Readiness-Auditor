# CLI da fundação Web/API

Esta referência complementa `CLI_REFERENCE.md` durante a evolução da camada SaaS.

## API + SaaS Pilot Web

Instale as dependências opcionais:

```powershell
pip install -e ".[web]"
```

Inicialização local pelo router principal:

```powershell
rasai api --host 127.0.0.1 --port 8000
```

O comando inicia a API tenant-aware e a superfície zero-build do SaaS Pilot Web. A interface fica disponível em:

```text
http://127.0.0.1:8000/app
```

A API permanece deliberadamente sob o entrypoint canônico `rasai`; não é instalado um segundo executável público específico para API ou Web UI.

## Modos de autenticação

O modo default continua sendo `deny`:

```text
RASAI_API_AUTH_MODE=deny
```

Os modos disponíveis são:

```text
deny
trusted-header
oidc
```

### Smoke local com trusted-header

Para exercício humano estritamente em loopback:

```powershell
rasai api `
  --host 127.0.0.1 `
  --port 8000 `
  --auth-mode trusted-header
```

Ao abrir `/app`, informe um `USR-*` existente quando a tela solicitar. A identidade de desenvolvimento fica somente no `sessionStorage` da aba e é enviada como `x-rasai-user-id` nas chamadas da API.

Isso é conveniência exclusivamente de desenvolvimento em loopback. Não é autenticação para Internet e não substitui OIDC ou um gateway autenticado.

### OIDC/JWT

Para a fundação SaaS, configure primeiro o Identity Provider:

```powershell
$env:RASAI_API_AUTH_MODE = "oidc"
$env:RASAI_OIDC_ISSUER = "https://login.example.com"
$env:RASAI_OIDC_CLIENT_ID = "rasai-web"
$env:RASAI_OIDC_AUDIENCE = "rasai-api"
$env:RASAI_OIDC_REDIRECT_URI = "https://rasai.example.com/auth/callback"
$env:RASAI_OIDC_SESSION_SECRET = "<segredo-forte>"
```

Depois inicie normalmente:

```powershell
rasai api `
  --host 0.0.0.0 `
  --port 8000 `
  --allow-public-bind `
  --auth-mode oidc
```

`--allow-public-bind` apenas reconhece a intenção de exposição. TLS, firewall, reverse proxy e demais controles de implantação continuam necessários.

O browser usa Authorization Code + PKCE. Clientes de API podem usar Bearer JWT quando o token atende ao issuer/audience/algoritmos configurados.

Detalhes completos: `IDENTITY_AND_ACCESS.md`.

## Provisionamento de identidade

Autenticação externa não cria usuário nem membership automaticamente.

Crie ou identifique o usuário interno:

```powershell
rasai platform user add `
  --name "Analista" `
  --email analyst@example.com
```

Crie o membership conforme o escopo necessário e então associe a identidade externa:

```powershell
rasai platform identity link `
  --user USR-EXISTENTE `
  --issuer https://login.example.com `
  --subject 00u123456789 `
  --email analyst@example.com
```

Listar vínculos:

```powershell
rasai platform identity list
rasai platform identity list --user USR-EXISTENTE
```

Remover vínculo:

```powershell
rasai platform identity unlink --identity IDN-EXISTENTE
```

O par `issuer + subject` é a identidade externa estável. E-mail não é usado como chave de autenticação.

## Bind público com trusted-header

O modo de compatibilidade continua disponível quando um gateway externo já executa autenticação:

```powershell
rasai api `
  --host 0.0.0.0 `
  --port 8000 `
  --allow-public-bind `
  --auth-mode trusted-header
```

Nesse cenário o gateway precisa remover qualquer `x-rasai-user-id` vindo do cliente, injetar a identidade somente após autenticação e bloquear acesso direto ao processo Uvicorn.

Para uma implantação SaaS nova, prefira `oidc` quando o Identity Provider puder ser integrado diretamente.

## Variáveis relevantes

API/control plane:

```text
RASAI_API_AUDITS_ROOT
RASAI_API_DOCS_ENABLED
RASAI_API_AUTH_MODE
RASAI_API_TRUSTED_USER_HEADER
RASAI_PLATFORM_DB_BACKEND
RASAI_PLATFORM_DATABASE_URL
```

OIDC:

```text
RASAI_OIDC_ISSUER
RASAI_OIDC_CLIENT_ID
RASAI_OIDC_AUDIENCE
RASAI_OIDC_REDIRECT_URI
RASAI_OIDC_SESSION_SECRET
RASAI_OIDC_CLIENT_SECRET_ENV
RASAI_OIDC_ALGORITHMS
RASAI_OIDC_SCOPES
RASAI_OIDC_SESSION_TTL_SECONDS
```

O default de autenticação continua `deny`.

## Worker

Executar no máximo um job disponível:

```powershell
rasai worker run-once `
  --worker-id worker-01 `
  --audits-root audits `
  --lease-seconds 900
```

Resultado quando não há trabalho:

```json
{"status":"IDLE"}
```

A UI cria durable execution jobs; ela não processa crawling dentro do processo HTTP. Para um piloto interativo contínuo, execute workers em processo separado usando a estratégia operacional adequada ao ambiente.

O worker usa o mesmo backend de control plane selecionado para a aplicação. PostgreSQL é selecionado explicitamente pelas variáveis de backend; SQLite permanece default.

O worker não requer `.[web]` e não valida tokens OIDC.

## PostgreSQL

Antes de iniciar API/worker com PostgreSQL cujo schema ainda não possui as extensões vigentes de execution jobs e Identity & Access:

```powershell
rasai platform database migrate
```

Normal startup não aplica migrations automaticamente.

Status:

```powershell
rasai platform database status
```

A saída inclui a versão principal do control plane e as versões das extensões de execution e identity.

## Referência detalhada

Consulte:

- `SAAS_PILOT_WEB.md` para a superfície do piloto;
- `WEB_API_FOUNDATION.md` para arquitetura da API/worker;
- `IDENTITY_AND_ACCESS.md` para OIDC, JWT, sessão, provisionamento e limites de identidade.
