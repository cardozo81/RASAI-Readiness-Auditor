# CLI da fundação Web/API

Esta referência complementa `CLI_REFERENCE.md` durante a evolução da camada SaaS.

## API

Instale as dependências opcionais:

```powershell
pip install -e ".[web]"
```

Inicialização local pelo router principal:

```powershell
rasai api --host 127.0.0.1 --port 8000
```

Entrada dedicada equivalente:

```powershell
rasai-api --host 127.0.0.1 --port 8000
```

Um bind fora de loopback é recusado por padrão. Em implantação controlada atrás de gateway/reverse proxy com TLS e autenticação, a exposição precisa ser assumida explicitamente:

```powershell
rasai api `
  --host 0.0.0.0 `
  --port 8000 `
  --allow-public-bind `
  --auth-mode trusted-header
```

`--allow-public-bind` apenas reconhece a intenção operacional; ele não substitui TLS, firewall, autenticação ou proteção contra spoofing do header de identidade.

Variáveis relevantes:

```text
RASAI_API_AUDITS_ROOT
RASAI_API_DOCS_ENABLED
RASAI_API_AUTH_MODE
RASAI_API_TRUSTED_USER_HEADER
RASAI_PLATFORM_DB_BACKEND
RASAI_PLATFORM_DATABASE_URL
```

O modo de autenticação default é `deny`.

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

O worker usa o mesmo backend de control plane selecionado para a aplicação. PostgreSQL é selecionado explicitamente pelas variáveis de backend; SQLite permanece default.

O worker não requer `.[web]`.

## PostgreSQL

Antes de iniciar API/worker com um PostgreSQL cujo schema ainda não possui a extensão de execution jobs:

```powershell
rasai platform database migrate
```

Normal startup não aplica migrations automaticamente.
