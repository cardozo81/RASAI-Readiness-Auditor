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
5. verifica se o pacote RASAI e as dependências-base declaradas em `pyproject.toml` estão instalados a partir deste repositório;
6. lê também todos os grupos existentes em `[project.optional-dependencies]` e, quando existirem, inclui esses extras no comando de instalação para que recursos opcionais declarados pelo projeto também fiquem disponíveis;
7. compara um hash local de `pyproject.toml` para detectar mudança de dependências, extras ou entrypoints sem reinstalar desnecessariamente a cada abertura;
8. executa `pip install -e .` — ou `pip install -e ".[extra1,extra2,...]"` quando houver extras — somente quando a instalação local está ausente, inconsistente ou o `pyproject.toml` mudou;
9. verifica o Chromium gerenciado pelo Playwright e executa `python -m playwright install chromium` somente quando o browser está ausente;
10. abre imediatamente a primeira tela do console interativo pelo entrypoint oficial `rasai-console`.

O marcador usado para a verificação de dependências fica dentro de `.venv` e não é versionado.

### Dependências das integrações externas

Os adapters atuais de OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, PageSpeed Insights e CrUX usam transporte HTTP da biblioteca padrão do Python (`urllib`). Portanto, **não existe hoje um SDK Python opcional adicional que precise ser instalado para habilitar essas APIs**.

Isso significa que, depois de o `iniciar.cmd` concluir o bootstrap, o software já está preparado do ponto de vista de dependências para utilizar qualquer integração suportada. O que continua sendo necessário, quando a integração for habilitada, é a respectiva credencial e disponibilidade externa: key/token compatível, modelo/plano, saldo/quota, permissões e conectividade de rede.

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

Se `pyproject.toml` passar a possuir extras em `[project.optional-dependencies]`, o fluxo manual deve instalá-los explicitamente ou usar `iniciar.cmd`, que os descobre automaticamente.

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

Para IA, configure somente as credenciais dos providers que pretende usar. Não é obrigatório configurar todos.

Para PageSpeed/CrUX, use as variáveis descritas em [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md).

No código atual não há SDK adicional a instalar para essas APIs; o transporte HTTP necessário já faz parte do Python 3.13. Qualquer futura dependência opcional declarada no `pyproject.toml` será incluída pelo launcher.

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

## Diagnóstico

Se `searchgeo` não for reconhecido no terminal, confirme que a `.venv` está ativada ou use `iniciar.cmd`, que chama diretamente o executável do console dentro da `.venv`.

Se Chromium estiver ausente no fluxo manual:

```powershell
python -m playwright install chromium
```

Consulte [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para falhas de provider, PageSpeed/Lighthouse, CrUX e artifacts.
