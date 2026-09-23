# PostgreSQL local para desenvolvimento

O PostgreSQL local é uma infraestrutura opcional para desenvolver e validar o control plane do RASAi. Ele **não substitui automaticamente o SQLite**, não altera auditorias históricas e não muda `SARI-001` nem `SCORE-GEO-004`.

## Pré-requisito

Use Docker Desktop no Windows com o daemon em execução. Não é necessário instalar PostgreSQL diretamente no Windows.

A topologia local esperada é:

```text
Windows
├─ RASAi
├─ SQLite                         # backend local padrão
└─ Docker Desktop
   └─ postgres:18
      ├─ container: rasai-postgres-dev
      ├─ database: rasai_control_plane
      ├─ user: rasai_app
      └─ volume: rasai_postgres_data
```

## Arquivos versionados e locais

Versionados:

```text
compose.postgres.yml
.env.postgres.example
scripts/postgres/start.ps1
scripts/postgres/stop.ps1
scripts/postgres/status.ps1
scripts/postgres/reset.ps1
```

Local e ignorado pelo Git:

```text
.env.postgres.local
```

O arquivo local contém a senha de desenvolvimento. A senha nunca deve ser copiada para documentação, issue, log, manifest, relatório ou arquivo versionado.

## Primeira inicialização

Na raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\postgres\start.ps1
```

Na primeira execução o helper:

1. valida que Docker Desktop/daemon está disponível;
2. cria `.env.postgres.local` se ele ainda não existir;
3. gera uma senha forte aleatória sem mostrá-la no terminal;
4. tenta usar `127.0.0.1:5432`;
5. se `5432` estiver ocupada por outro serviço, tenta `127.0.0.1:5433` sem interromper o serviço existente;
6. executa `docker compose up -d`;
7. aguarda o healthcheck do PostgreSQL.

O container continua ouvindo na porta `5432` internamente; somente a porta publicada no host pode ser `5432` ou `5433`.

Executar `start.ps1` novamente é idempotente e preserva banco, volume e credenciais locais existentes.

## Status e contrato do servidor

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\postgres\status.ps1
```

O helper valida:

- container `rasai-postgres-dev` em estado saudável;
- `pg_isready`;
- versão do PostgreSQL;
- database atual;
- usuário atual;
- `server_encoding=UTF8`;
- timezone de sessão `UTC`.

Nenhuma senha é exibida.

## Parar sem perder dados

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\postgres\stop.ps1
```

O comando faz `docker compose down`, mas **não remove**:

- o volume `rasai_postgres_data`;
- `.env.postgres.local`.

A próxima inicialização reutiliza os dados existentes.

## Reset destrutivo

O reset é a única operação local que remove o volume PostgreSQL e exige sinalização explícita:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\postgres\reset.ps1 -ConfirmReset
```

Ele remove `rasai_postgres_data`, recria o container vazio e preserva `.env.postgres.local`. Portanto o database é recriado com a mesma configuração local, mas todos os dados anteriores do PostgreSQL de desenvolvimento são apagados.

Não use reset quando houver dados locais que precisem ser preservados.

## SQLite continua sendo o default

Sem configuração explícita:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

O RASAi continua usando:

```text
audits/.rasai/platform.db
```

Ter o container PostgreSQL em execução não altera essa decisão.

## Ativar PostgreSQL no processo atual

Quando for necessário testar o backend PostgreSQL, obtenha localmente o host port e a senha de `.env.postgres.local` sem copiá-los para arquivos versionados. Configure a sessão:

```powershell
$env:RASAI_PLATFORM_DB_BACKEND = "postgresql"
$env:RASAI_PLATFORM_DATABASE_URL = "postgresql://rasai_app:<password>@127.0.0.1:<port>/rasai_control_plane"
```

`<password>` e `<port>` são placeholders. Não grave o valor real da senha na documentação ou em scripts versionados.

Não existe fallback silencioso: se PostgreSQL for selecionado e a URL estiver ausente, inválida ou indisponível, a operação falha em vez de usar SQLite.

## Migrations do control plane

O Compose apenas entrega um PostgreSQL vazio e saudável. Schema do RASAi é aplicado por operação explícita:

```powershell
rasai platform database status
rasai platform database migrate
```

A inicialização normal do aplicativo e `start.ps1` não executam DDL de produção automaticamente.

## Dados históricos de teste

Os bancos SQLite já produzidos durante desenvolvimento não precisam ser importados para PostgreSQL. O fluxo de validação é:

```text
PostgreSQL vazio
  -> migrations ordenadas
  -> schema canônico
  -> fixtures/testes controlados
  -> paridade SQLite/PostgreSQL
```

`AUD-*/audit.db` continua sendo evidência pontual imutável e não é movido para o control plane PostgreSQL.

## Segurança

Regras obrigatórias:

- `.env.postgres.local` nunca é versionado;
- `.env.postgres.example` contém somente placeholders seguros;
- credenciais reais não entram em CLI persistida, schedules, manifests, logs ou HTML;
- URLs de banco expostas ao usuário são redigidas antes de exibição;
- integrações persistem referências de secret, não o valor;
- grandes evidências imutáveis permanecem fora do banco transacional central.

## CI

O workflow PostgreSQL usa um service container `postgres:18` isolado e aplica migrations antes dos testes. O conjunto de paridade valida Product Platform, Search Monitoring, CLI, persistência e os contratos de segurança sem alterar o backend SQLite padrão.
