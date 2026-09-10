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

## Autenticação local para exercício do piloto

O modo default continua sendo `deny`.

Para smoke humano em loopback, sem um gateway local, pode-se iniciar:

```powershell
rasai api `
  --host 127.0.0.1 `
  --port 8000 `
  --auth-mode trusted-header
```

Ao abrir `/app`, informe um `USR-*` existente quando a tela solicitar. A identidade de desenvolvimento fica somente no `sessionStorage` da aba e é enviada como `x-rasai-user-id` nas chamadas da API.

Isso é uma conveniência **exclusivamente de desenvolvimento em loopback**. Não é um mecanismo de autenticação para Internet, não cria senha própria e não substitui gateway/OIDC.

## Bind público

Um bind fora de loopback é recusado por padrão. Em implantação controlada atrás de gateway/reverse proxy com TLS e autenticação, a exposição precisa ser assumida explicitamente:

```powershell
rasai api `
  --host 0.0.0.0 `
  --port 8000 `
  --allow-public-bind `
  --auth-mode trusted-header
```

`--allow-public-bind` apenas reconhece a intenção operacional; ele não substitui TLS, firewall, autenticação ou proteção contra spoofing do header de identidade.

Em exposição pública, o gateway deve remover qualquer `x-rasai-user-id` recebido do cliente e injetar a identidade somente após autenticação bem-sucedida. O campo de identidade local da UI não deve ser usado nesse cenário.

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

A UI cria durable execution jobs; ela não processa crawling dentro do processo HTTP. Para um piloto interativo contínuo, execute workers em processo separado usando a estratégia operacional adequada ao ambiente.

O worker usa o mesmo backend de control plane selecionado para a aplicação. PostgreSQL é selecionado explicitamente pelas variáveis de backend; SQLite permanece default.

O worker não requer `.[web]`.

## PostgreSQL

Antes de iniciar API/worker com um PostgreSQL cujo schema ainda não possui a extensão de execution jobs:

```powershell
rasai platform database migrate
```

Normal startup não aplica migrations automaticamente.

## Referência detalhada

Consulte `SAAS_PILOT_WEB.md` para arquitetura, endpoints aditivos, boundary dos HTML reports, tenancy e limites desta fase.
