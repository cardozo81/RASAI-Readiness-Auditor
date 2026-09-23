# Configuração versionável de propriedade

O contrato `PROPERTY-CONFIG-001` define arquivos TOML de propriedade que podem ser mantidos no Git sem carregar credenciais.

Local recomendado:

```text
config/properties/<property-id>.toml
```

Um exemplo versionado está em `config/properties/example.toml`.

## Validar

```powershell
rasai property-config validate config/properties/example.toml
```

A validação verifica estrutura, origin, backend de banco, referências de ambiente e ausência de secrets inline.

## Inspecionar

```powershell
rasai property-config show config/properties/example.toml
```

A saída passa pela camada central de redaction. O comando nunca resolve nem imprime o conteúdo das variáveis que carregam credenciais.

## Referências externas

```powershell
rasai property-config references config/properties/example.toml
rasai property-config references config/properties/example.toml --missing-only
```

Os comandos mostram somente nomes de referências, por exemplo `OPENAI_API_KEY` ou `RASAI_PLATFORM_DATABASE_URL`. Valores não são exibidos.

## PostgreSQL

Para selecionar PostgreSQL em uma propriedade versionada:

```toml
[database]
backend = "postgresql"
database_url_env = "RASAI_PLATFORM_DATABASE_URL"
```

O DSN real permanece fora do arquivo. O mesmo contrato suporta Docker local e PostgreSQL remoto/hospedado.

## Providers

Providers seguem o mesmo padrão:

```toml
[providers.openai]
enabled = true
api_key_env = "OPENAI_API_KEY"
```

Nunca use `api_key`, `password`, `token`, `secret`, `credential` ou `database_url` com valor real dentro de um arquivo versionável.

## Escopo atual

Nesta fase o contrato fornece validação, inspeção segura e descoberta das referências necessárias. Ele não substitui silenciosamente argumentos do comando `rasai audit`; a adoção pelo pipeline de execução deve ser explícita para preservar compatibilidade com instalações existentes.

Consulte também [SECRET_AND_CONFIGURATION_SAFETY.md](SECRET_AND_CONFIGURATION_SAFETY.md).

A configuração de propriedade não modifica `SARI-001`, `SCORE-GEO-004` ou evidências históricas `AUD-*/audit.db`.
