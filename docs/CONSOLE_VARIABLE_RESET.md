# Cancelamento de credenciais e reset de variáveis no console

Este documento descreve o comportamento seguro do menu **E. Variáveis de ambiente / credenciais** e do gerenciamento de credenciais de IA no `rasai-console`.

## 1. Cancelamento ao definir Key/token/secret

A edição de um secret é transacional do ponto de vista do operador.

Fluxo esperado:

1. o usuário escolhe **Definir/alterar**;
2. digita ou cola o valor;
3. o terminal mostra apenas `*` para os caracteres recebidos;
4. o valor é validado em memória;
5. o console apresenta:

```text
C. Confirmar alteração
V. Cancelar e manter o valor atual
```

Somente `C` grava o novo valor na sessão.

Ao escolher `V`:

- o valor anterior permanece intacto;
- um secret que ainda não existia continua ausente;
- nada é persistido no Windows/User;
- nada é escrito no `rasai-console.ini`;
- o valor digitado é descartado após sair do fluxo.

O conteúdo real do secret nunca é exibido.

## 2. Reset geral de variáveis

O menu avançado passa a oferecer:

```text
R. Resetar variáveis por grupo ou todas
```

O reset usa o catálogo `EnvironmentSpec` vigente. Portanto, ele só atua sobre variáveis conhecidas pelo RASAi e não executa uma limpeza genérica do ambiente do sistema operacional.

### Escopo

O usuário pode selecionar:

- um grupo funcional, por exemplo `Web Performance / Google APIs`, `Métricas e padrões`, `IA - credenciais` ou `Synthetic Apdex`;
- **Todas as variáveis conhecidas**.

### Camadas que podem ser resetadas

Após escolher o escopo, o usuário escolhe a camada:

1. **somente sessão atual**;
2. **sessão + persistência do estado resetado no `rasai-console.ini`**;
3. no Windows, **sessão + INI + Windows/User**.

A terceira opção é deliberadamente explícita porque remove persistência do sistema operacional.

## 3. Windows/User versus Windows/Machine

O RASAi só gerencia persistência no escopo **Windows/User**.

O reset nunca remove valores de **Windows/Machine**.

Motivos:

- `Machine` pode exigir privilégio administrativo;
- a alteração afetaria outros usuários e processos;
- uma ferramenta de auditoria local não deve realizar esse tipo de limpeza global implicitamente.

Quando uma variável existe em `Machine`, o console informa que o valor foi preservado. Mesmo após remover sessão e User, um novo processo pode herdar novamente o valor de Machine.

A remoção administrativa de `Machine` permanece responsabilidade explícita do operador/sistema.

## 4. Confirmação destrutiva

Nenhum reset é executado apenas pela escolha do menu.

Antes da execução o console mostra uma prévia do escopo e exige a confirmação textual:

```text
RESETAR
```

Qualquer outra entrada cancela a operação sem alterar dados.

## 5. Efeito sobre defaults e AUTO

Para variáveis não secretas, reset significa retornar ao comportamento canônico do runtime:

- default explícito, quando existir;
- `AUTO`/resolução por requisitos, quando esse for o contrato;
- ausência de valor, quando não existir default seguro.

Algumas configurações do menu principal são projetadas novamente como variáveis de runtime. Nesses casos, após o reset pode existir uma variável materializada com o **valor default efetivo**. Isso não representa a restauração do override antigo.

## 6. INI e secrets

O writer canônico do `rasai-console.ini` continua sendo usado quando o usuário escolhe persistir o reset.

Secrets permanecem fora do arquivo em qualquer cenário.

O reset não converte uma credencial em texto persistente e não cria cópia de segurança contendo secrets.

## 7. Operações que não fazem parte do reset

O reset de variáveis não apaga:

- auditorias existentes;
- `AUD-*/audit.db`;
- relatórios HTML;
- banco do control plane;
- arquivos de projeto do usuário;
- variáveis Windows/Machine;
- credenciais externas no fornecedor original.

Remover uma API key do RASAi não revoga a credencial no provider. Revogação deve ser feita no painel oficial do fornecedor.

## 8. Segurança e rastreabilidade

O fluxo preserva os seguintes princípios:

- secrets nunca aparecem em claro;
- a troca de secret só ocorre depois de confirmação;
- reset de Windows/User requer escolha explícita;
- Windows/Machine é fail-safe/preservado;
- erros de remoção são exibidos e não são mascarados como sucesso;
- o catálogo canônico continua sendo a fonte de quais variáveis pertencem a cada grupo.

Documentos relacionados:

- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [WEB_PLATFORM_BASELINE.md](WEB_PLATFORM_BASELINE.md)
