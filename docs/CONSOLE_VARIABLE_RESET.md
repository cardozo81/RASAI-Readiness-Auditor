# Restauração e gerenciamento seguro de configurações no console

Este documento descreve a restauração de configurações e o tratamento de credenciais no `rasai-console`.

A baseline oficial do produto é distribuída em `src/rasai/config/rasai-defaults.ini` e documentada em [SYSTEM_DEFAULTS.md](SYSTEM_DEFAULTS.md).

## 1. Princípios

- restauração de configuração usa contratos canônicos do console;
- secrets nunca são gravados no `rasai-console.ini`;
- Windows/User só é alterado por ação explícita;
- Windows/Machine é observado, mas nunca modificado automaticamente;
- restauração não apaga auditorias, relatórios ou bancos;
- remover uma credencial do RASAi não revoga a credencial no fornecedor.

## 2. Restaurar uma variável

Abra:

```text
INÍCIO > Todas as configurações
```

Localize a variável pelo ID numérico, nome, owner, estado ou finalidade e abra o editor.

Ações relevantes:

```text
S. Definir / alterar
L. Limpar override somente desta sessão
R. Restaurar default/ausência canônica e salvar no arquivo    # não secret
P. Gerenciar persistência Windows/User                         # secret
V. Voltar
```

Para uma configuração não sensível, `R` remove o override efetivo da sessão, reaplica o default/ausência canônica por meio do runtime de configuração e usa o writer normal do console para persistir o estado resultante.

`L` atua somente sobre a sessão atual.

## 3. Secrets

Secrets são tratados separadamente das configurações comuns.

Exemplos:

- API keys;
- bearer tokens;
- passwords;
- client secrets;
- refresh tokens;
- DSNs classificados como credenciais.

O valor real não é exibido após a configuração. O estado é mostrado como presença/ausência, por exemplo `[SET]`.

Secrets não são gravados no INI nem em snapshots reutilizáveis de AUD.

## 4. Destino de uma alteração

Para valor não sensível:

```text
1. Aplicar somente nesta sessão
2. Aplicar na sessão e salvar no arquivo de configuração
```

Para secret:

```text
1. Aplicar somente nesta sessão
2. Aplicar na sessão e persistir em Windows/User
```

A segunda opção de secret só é aplicável no Windows e exige o fluxo explícito de persistência do console.

## 5. Windows/User

O RASAi administra credenciais persistidas no escopo do usuário quando o operador solicita essa ação.

O console pode:

- persistir o secret atual em Windows/User;
- remover a persistência de Windows/User;
- sincronizar o estado efetivo da sessão após a alteração.

Persistência no perfil do usuário não transforma variável de ambiente em secret manager. Processos com acesso ao mesmo perfil podem ler esses valores conforme as permissões do sistema.

## 6. Windows/Machine

O console não cria, altera nem remove automaticamente variáveis em Windows/Machine.

Motivos:

- o escopo afeta outros usuários/processos;
- pode exigir privilégio administrativo;
- uma aplicação de auditoria local não deve executar essa mudança global implicitamente.

Se um valor Machine for herdado por um novo processo, ele pode influenciar a precedência efetiva. A UI informa a origem para permitir diagnóstico.

## 7. Restaurar padrões do produto

A restauração integral fica em:

```text
INÍCIO > Sistema / restaurar padrões
```

Esse fluxo reconstrói a configuração a partir da baseline versionada do produto e usa os mecanismos normais de persistência do console.

As opções de sistema permitem preservar credenciais ou remover credenciais gerenciadas, conforme apresentado na própria tela.

A restauração exige confirmação explícita antes de executar a operação destrutiva.

## 8. O que a restauração integral afeta

Ela pode redefinir parâmetros não sensíveis conhecidos pelo RASAi e, quando o operador escolhe remover credenciais, limpar os secrets gerenciados nos escopos permitidos.

No Windows, a administração automatizada permanece limitada a sessão e Windows/User.

## 9. O que não é apagado

Os fluxos de restauração de configuração não apagam:

- `AUD-*`;
- `audit.db`;
- relatórios HTML;
- banco do control plane;
- arquivos do projeto;
- evidências já persistidas;
- Windows/Machine;
- credenciais existentes no painel do fornecedor.

## 10. INI

O arquivo padrão é:

```text
rasai-console.ini
```

O writer canônico grava somente parâmetros não sensíveis permitidos pelo catálogo.

O comando geral de salvar e a restauração por variável usam esse mesmo contrato. Inputs não sensíveis da próxima execução que fazem parte do estado persistível, como Search Intelligence, podem ser gravados quando o operador escolhe salvar.

## 11. Defaults e AUTO

Restaurar uma configuração significa voltar ao default, `AUTO` ou ausência definidos pelo contrato daquela variável. O console não inventa um valor apenas para preencher o campo.

Quando o runtime já possui um default interno, a UI pode mostrar `DEFAULT` como origem sem exigir um override redundante.

## 12. Cancelamento e segurança

Quando a edição de credencial usa fluxo staged, o novo valor só substitui o atual depois da confirmação apresentada pela tela. Cancelar mantém a configuração vigente.

Regras de segurança:

- nenhum secret é ecoado em claro;
- erro de persistência não é apresentado como sucesso;
- alteração de Windows/User é explícita;
- Windows/Machine permanece fail-safe;
- configuração restaurada é reavaliada pelos validadores/readiness existentes.

## 13. Revogação externa

Apagar uma key da sessão ou do Windows não revoga a credencial no fornecedor. Revogação definitiva deve ser feita no painel oficial do provider.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [SYSTEM_DEFAULTS.md](SYSTEM_DEFAULTS.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
