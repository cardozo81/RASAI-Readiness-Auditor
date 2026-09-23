# Execução externa e agendamento

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado.

Este documento descreve como transformar a configuração resolvida no console em um comando reproduzível para execução manual ou agendada, sem alterar o motor de auditoria, reprocessamento ou consolidação.

## Objetivo

A superfície **Ver linha de comando** existe para quatro usos:

- revisar exatamente quais parâmetros e variáveis não sensíveis compõem uma execução;
- copiar a execução para outro terminal ou mecanismo de agendamento;
- reproduzir uma auditoria, um reprocessamento ou um consolidado sem refazer a configuração manualmente;
- manter rastreabilidade operacional sem registrar o valor real de API keys, tokens, senhas ou outros secrets.

O recurso não altera scoring, Índice de Prontidão Search & IA, Método de Pontuação de Prontidão, coleta, `audit.db`, catálogos ou HTMLs. A geração do comando é uma projeção da configuração efetiva.

## Atalho canônico

Nas superfícies de AUD, RPR e CONS:

```text
M. Ver linha de comando
```

A mesma ação usa sempre a mesma tecla. `E` permanece reservado às superfícies já existentes de variáveis de ambiente e credenciais.

Dentro de **Ver linha de comando**:

```text
1. Windows
2. Linux
3. macOS
C. Copiar comando executável para clipboard
O. Abrir log de comandos
P. Abrir pasta da execução
V. Voltar
```

`P` aparece quando existe uma pasta contextual disponível. Antes de uma AUD existir fisicamente, a pasta contextual pode ser a raiz de auditorias.

## Onde o comando aparece

### Nova auditoria

Em:

```text
INÍCIO
> Nova auditoria / configurar e executar
> PREPARAR AUDITORIA
> M. Ver linha de comando
```

o comando está no estado **PLANEJADO** e representa a configuração corrente da próxima auditoria.

Depois que o subprocesso da AUD termina, a tela de resultado oferece novamente:

```text
M. Ver linha de comando
```

Nesse ponto o comando está no estado **EXECUTADO** e usa o mesmo `argv` entregue ao subprocesso.

### Reprocessamento

O comando só é fechado depois de selecionar:

- a AUD;
- os work-items que serão tentados;
- o uso ou não de IA;
- provider, modelo e reasoning quando aplicáveis.

Depois de o escopo ser selecionado, a ação final apresenta:

```text
1. Reprocessar itens selecionados com IA quando aplicável
2. Reprocessar itens selecionados sem IA
V. Voltar
```

O comando é fechado com a opção escolhida e continua disponível no log após a tentativa. A visualização/cópia do comando não exige uma segunda confirmação do RPR.

Após a tentativa, a tela de resultado mantém `M. Ver linha de comando`.

### Relatório consolidado

O comando só é fechado depois de resolver:

- BASE;
- ATUAL;
- auditorias intermediárias;
- política `ALL`, `SUCCESS_ONLY` ou `MANUAL`;
- modo determinístico ou determinístico + IA;
- configuração de IA quando solicitada.

Na ação final:

```text
1. Gerar relatório consolidado com IA
2. Gerar relatório consolidado sem IA
V. Voltar
```

O comando correspondente é registrado para a execução e o resultado/histórico do CONS continua expondo `M. Ver linha de comando`. Não existe uma segunda pergunta para confirmar a geração.

### Histórico

Quando há log materializado, o detalhe de uma AUD ou CONS permite recuperar o comando mesmo em uma sessão posterior do console.

No caso da AUD, o mesmo arquivo pode conter a execução original e blocos posteriores de RPR. A leitura interativa usa o bloco mais recente de cada sistema operacional.

## Logs: técnico x comando humano

São arquivos diferentes e têm finalidades diferentes.

### `console.log`

Local padrão:

```text
<audits_root>/.rasai/logs/console.log
```

É log técnico estruturado do console. Pode usar eventos JSON/JSONL e não é a superfície recomendada para copiar comandos.

### `execution-commands/*.log`

Local padrão:

```text
<audits_root>/.rasai/logs/execution-commands/
```

Exemplos:

```text
<audits_root>/.rasai/logs/execution-commands/AUD-....log
<audits_root>/.rasai/logs/execution-commands/CONS-....log
```

É texto UTF-8 legível por pessoas. Não é JSON.

O arquivo contém blocos distintos:

```text
[WINDOWS]
...
[/WINDOWS]

[LINUX]
...
[/LINUX]

[MACOS]
...
[/MACOS]
```

O log fica fora do workspace da AUD e fora do pacote CONS. Portanto, não altera `audit.db`, manifesto, hashes, conteúdo HTML ou integridade dos artefatos homologados.

Falha ao gravar esse log é tratada como falha de observabilidade e não muda o resultado da AUD, RPR ou CONS.

## Credenciais e placeholder `**********`

Secrets nunca são gravados com seu valor real.

Quando uma credencial é aplicável, o modelo mostra explicitamente a variável, mas a linha fica comentada.

Windows:

```cmd
REM set "OPENAI_API_KEY=**********"
REM set "RASAI_SERPAPI_API_KEY=**********"
```

Linux e macOS:

```sh
# export OPENAI_API_KEY='**********'
# export RASAI_SERPAPI_API_KEY='**********'
```

O texto `**********` significa **substituir manualmente por um secret somente se o operador quiser fazer override daquela execução**.

Nunca execute uma linha ativa contendo literalmente `**********`.

### Usar a credencial do sistema operacional

Mantenha a linha do secret comentada ou remova a linha.

O processo utilizará o valor disponível no ambiente efetivo.

No Windows, a entrada pública `rasai` ativa explicitamente secrets conhecidos persistidos em Windows/User ou Windows/Machine quando eles não já existem na sessão. Um valor já definido na sessão/processo prevalece e não é sobrescrito.

### Usar outra credencial somente naquela execução

Windows:

```cmd
set "OPENAI_API_KEY=sk-chave-especifica"
```

Linux/macOS:

```sh
export OPENAI_API_KEY='chave-especifica'
```

Esse valor passa a valer para o processo e seus processos filhos. Ele **não modifica** a variável persistida no SO.

Assim é possível, por exemplo:

- manter a credencial padrão da OpenAI no SO;
- executar uma tarefa pontual com outra credencial;
- terminar o processo;
- continuar com a credencial persistida original intacta.

### Clipboard

`C. Copiar comando executável para clipboard` remove comentários e placeholders de secrets antes de copiar.

Portanto, por padrão, o comando copiado usa as credenciais fornecidas pelo ambiente do SO/processo.

Para usar um override secreto, o operador deve editar conscientemente o modelo exibido e inserir a credencial no ambiente da execução.

## Variáveis não sensíveis

Configurações não sensíveis que pertencem ao ambiente efetivo aparecem ativas.

Windows:

```cmd
set "RASAI_SERP_MODE=live"
set "RASAI_SERP_PROVIDER=serpapi"
```

Linux/macOS:

```sh
export RASAI_SERP_MODE='live'
export RASAI_SERP_PROVIDER='serpapi'
```

Parâmetros já expressos como argumentos da CLI continuam na linha `rasai audit`, `rasai reprocess` ou `rasai consolidate`.

## Windows

### Mecanismos

Caminho principal documentado:

- **Agendador de Tarefas do Windows**.

Também pode ser usado:

- `schtasks.exe`, que administra tarefas do mesmo Agendador por linha de comando;
- scripts `.cmd` ou `.bat` chamados pelo Agendador, quando o operador prefere manter um bloco de configuração em arquivo.

### Testar antes de agendar

Copie o comando Windows e execute em um `cmd.exe` novo usando a mesma conta que executará a tarefa.

Valide:

- caminho do Python/venv;
- diretório de trabalho;
- acesso à raiz de auditorias;
- credenciais;
- permissões de arquivo;
- conectividade das integrações selecionadas.

### Agendador de Tarefas

Quando houver mais de uma instrução `set`, use `cmd.exe` como programa da ação ou salve o bloco em um `.cmd`.

Modelo conceitual:

```text
Programa/script:
cmd.exe

Argumentos:
 /d /s /c "<sets não sensíveis> && <comando RASAi>"
```

A expressão de agenda, conta de execução, política de repetição e tratamento de falhas pertencem ao Agendador e não fazem parte do comando RASAi.

Se o usuário optar por colocar uma key diretamente na ação ou em arquivo `.cmd`, essa key deixa de estar protegida pelo mecanismo normal de secrets do SO e passa a existir em texto no artefato criado pelo usuário. Use apenas quando houver necessidade operacional explícita.

## Linux

### Mecanismos

Caminho principal documentado:

- **cron / crontab**.

Alternativa comum quando a distribuição usa systemd:

- **systemd timer** associado a uma unit de serviço.

O RASAi gera o comando da execução. A expressão de calendário do cron ou do systemd timer é definida pelo operador.

### cron

Exemplo conceitual:

```cron
0 3 * * * /caminho/do/python -m rasai audit ...
```

O ambiente do cron costuma ser menor que o ambiente de um terminal interativo. Por isso, prefira:

- caminho absoluto para o Python do ambiente virtual;
- caminho absoluto para arquivos usados pela configuração;
- variáveis necessárias definidas no ambiente do job ou em mecanismo seguro do serviço.

Perfis como `.bashrc` e `.profile` não devem ser presumidos como carregados pelo cron.

### systemd timer

O timer define quando executar. A unit de serviço define o processo.

Secrets podem ser fornecidos pelo mecanismo administrativo adotado pela instalação. Evite materializá-los diretamente em arquivos compartilháveis do projeto.

## macOS

### Mecanismos

Caminho principal documentado:

- **launchd**, administrado por arquivos `.plist` e `launchctl`.

`cron` pode existir em algumas instalações, mas não é o caminho principal recomendado pelo RASAi para macOS.

O bloco macOS exibido por **Ver linha de comando** representa a execução no shell. Ao criar um `.plist`, o operador deve converter o comando para `ProgramArguments` ou executar um shell controlado, por exemplo `/bin/sh -lc`, conforme a política local.

Use caminho absoluto para o Python/venv e para a raiz de auditorias.

## Comando gerado para outro SO

Quando o comando é visualizado para o SO em que o RASAi está rodando, o executável Python corrente pode ser projetado diretamente.

Ao visualizar Windows a partir de Linux/macOS, ou Linux/macOS a partir de Windows, o RASAi não consegue conhecer o caminho real do Python na máquina de destino. Nesses casos a projeção usa `python` ou `python3` como referência.

Antes de agendar em outra máquina ou outro SO, substitua pela localização real do Python/venv instalado no destino.

Essa limitação não afeta argumentos, seleção de AUDs, política de IA ou demais parâmetros do comando.

## Comandos públicos usados

### Auditoria

```text
python -m rasai audit ...
```

O console reutiliza o mesmo builder canônico usado para iniciar a AUD.

### Reprocessamento

```text
python -m rasai reprocess AUD-... --item ... --use-ai ...
```

A CLI usa o mesmo `reprocess_policy` e o mesmo `reprocess_audit` do fluxo interativo.

### Consolidado

```text
python -m rasai consolidate AUD-BASE AUD-ATUAL ...
```

A CLI é apenas um adapter para `resolve_selection`, `normalize_filter` e `generate`, os mesmos contratos usados pelo console. Não existe um segundo motor de consolidação.

## Quando usar

Use execução externa quando for necessário:

- rodar auditorias recorrentes;
- repetir uma recuperação em janela operacional específica;
- gerar um consolidado em horário definido;
- integrar RASAi a um orquestrador local;
- reproduzir exatamente uma configuração sem navegar novamente pelo console.

Não use o log de comandos como cofre de credenciais. Ele é deliberadamente secret-free.

## Diagnóstico de tarefa agendada

Quando uma tarefa funciona no console mas falha no agendador, verifique nesta ordem:

1. conta/usuário que executa a tarefa;
2. caminho absoluto do Python/venv;
3. diretório de trabalho;
4. raiz de auditorias e permissões;
5. variáveis do ambiente do processo;
6. disponibilidade das credenciais para aquela conta;
7. caminhos de configuração;
8. rede/proxy/firewall;
9. log técnico da execução;
10. log humano de comando para conferir os parâmetros usados.

O comando reproduzível não transforma indisponibilidade de API, rede, quota ou permissão em sucesso. Ele apenas garante que a mesma intenção de execução possa ser materializada fora do console.
