# Instalação

## Requisitos

- Windows como alvo operacional principal;
- CPython `>=3.13,<3.14`;
- pip;
- filesystem local;
- Playwright `>=1.57,<2`;
- Chromium;
- acesso HTTP/HTTPS às URLs auditadas;
- egress adicional somente para integrações externas efetivamente habilitadas.

## Inicialização recomendada no Windows

Na raiz do projeto, execute por duplo clique ou pelo terminal:

```cmd
iniciar.cmd
```

O launcher foi criado para deixar o ambiente local pronto para **todas as capacidades implementadas no produto**, inclusive integrações externas. A cada abertura ele:

1. posiciona a execução na raiz do repositório;
2. valida se existe uma `.venv` compatível com CPython 3.13;
3. se Python 3.13 não estiver disponível, tenta instalá-lo pelo Windows Package Manager (`winget`) usando o pacote `Python.Python.3.13`;
4. cria `.venv` quando necessário;
5. verifica se o pacote RASAi e as dependências-base declaradas em `pyproject.toml` estão instalados a partir deste repositório;
6. lê também todos os grupos existentes em `[project.optional-dependencies]` e, quando existirem, inclui esses extras no comando de instalação para que recursos opcionais declarados pelo projeto também fiquem disponíveis;
7. compara um hash local de `pyproject.toml` para detectar mudança de dependências, extras ou entrypoints sem reinstalar desnecessariamente a cada abertura;
8. executa `pip install -e .` - ou `pip install -e ".[extra1,extra2,...]"` quando houver extras - somente quando a instalação local está ausente, inconsistente ou o `pyproject.toml` mudou;
9. verifica o Chromium gerenciado pelo Playwright e executa `python -m playwright install chromium` somente quando o browser está ausente;
10. abre imediatamente a primeira tela do console interativo pelo entrypoint oficial `rasai-console`.

O marcador usado para a verificação de dependências fica dentro de `.venv` e não é versionado.

### Dependências das integrações externas

OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, PageSpeed Insights, CrUX e os adapters SERP HTTP usam transporte da biblioteca padrão do Python (`urllib`) e não exigem SDK Python adicional.

**GitHub Copilot é a exceção atual.** A integração usa o SDK oficial e está declarada no extra `copilot` de `pyproject.toml`. No fluxo recomendado, `iniciar.cmd` descobre os grupos de `[project.optional-dependencies]` e instala os extras automaticamente. No fluxo manual, instale explicitamente:

```powershell
python -m pip install -e ".[copilot]"
```

A presença da biblioteca não habilita o provider por si só. Para Copilot também são necessários `COPILOT_GITHUB_TOKEN`, uma assinatura Copilot elegível e permissões compatíveis. O provider permanece `explicit-only` e não entra em `AI=auto`.

Depois de o `iniciar.cmd` concluir o bootstrap, o software fica preparado do ponto de vista de dependências para utilizar as integrações declaradas no projeto. O que continua sendo necessário, quando cada integração for habilitada, é sua respectiva credencial e disponibilidade externa: key/token compatível, modelo/plano, saldo/quota, permissões e conectividade de rede.

O launcher não cria credenciais, não compra quota e não habilita providers automaticamente. Esses itens são configuração operacional, não dependência de instalação.

Se futuramente uma integração passar a exigir biblioteca adicional, ela deve ser declarada em `pyproject.toml`. Dependências-base serão instaladas normalmente; dependências declaradas em qualquer grupo de `[project.optional-dependencies]` também serão incluídas pelo launcher. A alteração do arquivo será detectada pelo hash e provocará a reconciliação automática do ambiente.

### Ambiente incompatível

Se uma `.venv` existente usar uma versão incompatível de Python, o launcher não a remove silenciosamente. Ele interrompe e orienta a renomear/remover `.venv` antes de tentar novamente.

Se Python 3.13 estiver ausente e `winget` não estiver disponível, a instalação automática do Python não é possível; instale CPython 3.13 manualmente e execute `iniciar.cmd` novamente.

## Instalação manual

O fluxo manual continua suportado como fallback:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

Para usar GitHub Copilot no fluxo manual, instale o extra correspondente:

```powershell
python -m pip install -e ".[copilot]"
```

Para instalar todos os extras declarados sem depender do launcher, consulte os grupos atuais em `pyproject.toml`. O `iniciar.cmd` continua sendo o caminho recomendado porque os descobre e reconcilia automaticamente.

Validar:

```powershell
rasai --version
rasai audit --help
rasai-console
```

## Execução mínima pela CLI

```powershell
rasai audit https://example.com `
  --project "Smoke" `
  --max-pages 1 `
  --device-context mobile `
  --ai-provider none `
  --no-ai-content-remediation `
  --no-web-performance
```

A execução deve gerar `audit.db`, `logs/audit.log` e o mini-site em `report/`.

## Console interativo

Forma recomendada no Windows:

```cmd
iniciar.cmd
```

Forma direta, quando o ambiente já está ativado/preparado:

```powershell
rasai-console
```

Na primeira abertura, o console cria `rasai-console.ini` com defaults não sensíveis. O arquivo é ignorado pelo Git e não armazena API keys/tokens.

## Integrações opcionais

Para IA, configure somente as credenciais dos providers que pretende usar. Não é obrigatório configurar todos. As URLs oficiais para cadastro/login e geração de credenciais estão em [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

Para PageSpeed/CrUX, use as variáveis descritas em [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md).

Para Search Intelligence/SERP, consulte [PROVIDER_SETUP.md](PROVIDER_SETUP.md) e [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md). As franquias gratuitas documentadas são limitadas; o RASAi não classifica nenhum provider SERP externo atual como gratuito e ilimitado.

## Atualização da instalação editável

Após atualizar o repositório, a forma recomendada é simplesmente executar novamente:

```cmd
iniciar.cmd
```

Como a instalação é editável, alterações em `src/` são utilizadas diretamente. Se `pyproject.toml` mudar, o launcher detecta a alteração pelo hash e reconcilia dependências, extras e entrypoints automaticamente.

O fluxo manual equivalente permanece:

```powershell
git fetch origin --prune
git switch main
git pull --ff-only origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

Se o ambiente manual precisar de Copilot, reaplique `python -m pip install -e ".[copilot]"` após mudanças relevantes de dependências.

## Diagnóstico

Se `rasai` não for reconhecido no terminal, confirme que a `.venv` está ativada ou use `iniciar.cmd`, que chama diretamente o executável do console dentro da `.venv`.

Se Chromium estiver ausente no fluxo manual:

```powershell
python -m playwright install chromium
```

Consulte [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para falhas de provider, PageSpeed/Lighthouse, CrUX e artifacts.
