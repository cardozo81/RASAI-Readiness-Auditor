# Segurança de secrets e configuração versionável

O RASAi separa configuração operacional de material sensível. O contrato público para configuração versionável de propriedade é `PROPERTY-CONFIG-001`.

Esta política é transversal: banco de dados, IA, SERP, Google APIs, OAuth, integrações e qualquer provider futuro seguem as mesmas regras.

## Regra principal

Arquivos versionados descrevem **o que usar** e **onde encontrar uma credencial**, nunca o valor da credencial.

Permitido em Git:

```toml
[property]
id = "cliente"
name = "Cliente"
origin = "https://www.example.com"

[database]
backend = "postgresql"
database_url_env = "RASAI_PLATFORM_DATABASE_URL"

[providers.openai]
api_key_env = "OPENAI_API_KEY"
```

Proibido:

```toml
password = "<valor-real>"
api_key = "<valor-real>"
database_url = "postgresql://user:<senha-real>@host/database"
```

Os valores acima são apenas representação documental; nenhum segredo real deve ser colocado no arquivo.

## Configuração de propriedades

Arquivos de propriedade podem ser mantidos em:

```text
config/properties/*.toml
```

Eles são deliberadamente versionáveis. Podem conter domínio/origin, idioma, mercado, device, limites de coleta, providers selecionados, parâmetros de Search Intelligence, opções de execução e referências a secrets.

O loader `PROPERTY-CONFIG-001` rejeita:

- campo cujo nome represente API key, token, password, secret, credential ou chave privada quando o campo contém valor direto;
- `database_url` literal em configuração de propriedade;
- URL/origin com credenciais embutidas;
- referência `*_env` que não seja um nome válido de variável de ambiente;
- conteúdo que tenha padrão de credencial inline detectável.

Para PostgreSQL, a configuração versionável usa:

```toml
[database]
backend = "postgresql"
database_url_env = "RASAI_PLATFORM_DATABASE_URL"
```

A mesma configuração funciona com PostgreSQL em Docker local ou endpoint remoto/hospedado. O DSN real fica fora do Git.

## Origem dos secrets

No runtime local, secrets podem vir de variáveis de ambiente. Em hospedagem, podem ser projetados para o processo por um secret manager ou mecanismo equivalente.

Exemplos de referências:

```text
OPENAI_API_KEY
RASAI_SERPAPI_API_KEY
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
RASAI_PLATFORM_DATABASE_URL
```

A presença da referência no arquivo é segura; o valor da variável não é versionável.

## Redaction em runtime

A camada central de secret safety fornece classificação e redaction para dados estruturados e texto. Ela cobre, entre outros:

- campos por nome (`API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, `PRIVATE_KEY`, `ACCESS_KEY`);
- `Authorization`, bearer tokens e cookies;
- URLs/DSNs contendo usuário e senha;
- query parameters com nomes sensíveis;
- blocos de chave privada;
- estruturas aninhadas destinadas a output ou persistência.

Outputs devem exibir apenas estado como `SET`, referência ou valor redigido. O segredo não deve aparecer em CLI, console, logs, exceptions, manifests, artifacts, provider evidence, HTML ou banco de dados de metadados.

## Gate do repositório

O workflow `Secret and Configuration Safety` executa antes de integração e procura exposições de alta confiança em arquivos versionados. O gate falha ao detectar, entre outros:

- chave privada;
- bearer token literal;
- URL/DSN com password inline;
- assignment de campo sensível com valor não reconhecido como placeholder/referência.

Placeholders documentais explícitos e valores sintéticos de teste identificados como tal não são tratados como credenciais reais.

O gate complementa, mas não substitui, secret scanning nativo da plataforma Git e boas práticas de revisão.

## Arquivos locais

Arquivos destinados a conter valores locais de secrets devem ficar fora do Git, por exemplo:

```text
.env
.env.local
.env.*.local
```

Arquivos de exemplo sem secrets podem ser versionados, por exemplo:

```text
.env.example
.env.postgres.example
```

## Incidente de exposição

Se uma credencial real entrar em commit, removê-la do arquivo não basta. Ela deve ser considerada comprometida e rotacionada/revogada no provider. A limpeza do histórico Git, quando necessária, é uma operação adicional e não substitui a rotação.

Esta política não altera `SARI-001`, `SCORE-GEO-004` nem a imutabilidade de `AUD-*/audit.db`.
