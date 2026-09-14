# Persistência de credenciais no Windows

**Estado:** contrato vigente do RASAi. O produto ainda não foi publicado.

O console local nunca grava API keys, tokens, senhas ou outros secrets no `rasai-console.ini`.

No Windows, uma credencial pode ser mantida entre execuções por ação explícita do operador no escopo do usuário atual:

```text
Windows/User -> HKEY_CURRENT_USER\Environment
```

Essa operação **não exige execução como Administrador**. O console não precisa de elevação para gravar o ambiente do usuário atual.

O escopo `Windows/Machine` pode ser lido quando já existe, mas o gerenciamento normal de credenciais do console não cria, altera nem remove valores nesse escopo.

## Fluxo pelo console

Para uma credencial, a tela apresenta ações equivalentes a:

```text
S. Definir/alterar na sessão
P. Persistência Windows/User
R. Remover da sessão
```

O fluxo normal é:

```text
1. definir o secret na sessão;
2. validar a integração, se desejado;
3. escolher Persistência Windows/User;
4. confirmar a operação;
5. o RASAi grava o valor em HKCU e confirma a gravação por leitura do próprio registro.
```

Se a leitura de confirmação não devolver exatamente o valor gravado, a persistência é considerada falha e o console não deve apresentar a operação como concluída.

## Ativação ao iniciar o RASAi

Uma alteração em `HKEY_CURRENT_USER\Environment` não atualiza obrigatoriamente o bloco de ambiente de um `cmd.exe`, PowerShell, Windows Terminal ou outro processo que já estava aberto antes da gravação.

Por isso, o RASAi **não depende do processo pai ter recebido a atualização do Windows**.

Na inicialização do console local, depois que o catálogo de credenciais conhecido está composto e antes do preflight/configuração da execução, o RASAi lê diretamente a persistência Windows para cada variável classificada como secret.

Quando o processo atual não possui valor para a variável:

```text
Windows/User definido    -> ativa Windows/User no processo RASAi
Windows/User ausente
  + Windows/Machine      -> ativa Windows/Machine no processo RASAi
nenhum valor persistido  -> permanece não configurada
```

O valor é colocado somente em `os.environ` do processo atual. Nenhum secret é copiado para INI, AUD, relatório ou catálogo de modelos/preços.

## Precedência

Para secrets do console local, a precedência efetiva é:

```text
valor não vazio já presente no processo/sessão
> Windows/User
> Windows/Machine
> ausente
```

Assim, um valor explicitamente fornecido ao processo continua podendo substituir temporariamente o valor persistido.

A ativação automática de Windows/User ou Windows/Machine ocorre apenas quando a variável está ausente ou vazia no processo atual.

## Exemplo: GitHub Copilot

Depois de definir `COPILOT_GITHUB_TOKEN` na sessão e escolher a persistência Windows/User, uma nova execução do RASAi deve reconhecer a credencial mesmo quando for iniciada a partir de um terminal que já estava aberto antes da persistência.

O estado esperado no console é equivalente a:

```text
COPILOT_GITHUB_TOKEN    [SET] [SO:USER] DEFINIDO
```

O valor do token nunca é exibido.

Se o operador remover somente o valor da sessão durante a execução atual, a persistência continua existindo e a tela pode indicar temporariamente:

```text
SO:USER persistida (não ativa nesta sessão)
```

Na próxima inicialização normal, se não houver um override explícito no processo, o valor Windows/User volta a ser ativado.

## Exemplo: OpenAI, DeepSeek e outras integrações

A mesma regra é aplicada de forma central às variáveis classificadas como secrets no catálogo efetivo do console. Não existe uma implementação de persistência separada por provider.

Exemplos de categorias cobertas incluem:

```text
credenciais de providers de IA
credenciais de SERP
Google Search Console OAuth
PageSpeed / CrUX
serviços externos com token
credenciais de identidade/deployment quando classificadas como secret
```

O comportamento é determinado pela classificação de segurança da variável, não por uma lista especial criada apenas para uma integração.

## Verificação sem revelar o valor

Para verificar apenas a existência de uma variável no ambiente User do Windows sem imprimir seu conteúdo, pode-se usar PowerShell:

```powershell
$exists = $null -ne (Get-ItemProperty -Path 'HKCU:\Environment' -Name 'COPILOT_GITHUB_TOKEN' -ErrorAction SilentlyContinue)
$exists
```

Resultado esperado após persistência:

```text
True
```

Não copie o conteúdo da credencial para logs, screenshots, documentação ou chamados.

## Segurança

Variáveis de ambiente não são um cofre de segredos. Processos executados no mesmo contexto de usuário podem conseguir lê-las.

O contrato do RASAi é:

- nunca persistir secrets no INI;
- nunca mostrar o valor em claro depois da entrada;
- exigir ação explícita para persistir em Windows/User;
- não exigir privilégio administrativo para Windows/User;
- confirmar a escrita antes de reportar sucesso;
- reativar secrets persistidos no início do console local quando não existir override explícito de processo;
- nunca administrar automaticamente Windows/Machine.
