# Instalação

## Requisitos

- Windows como alvo operacional principal;
- CPython `>=3.13,<3.14`;
- pip;
- filesystem local;
- Playwright `>=1.57,<2`;
- Chromium;
- acesso HTTP/HTTPS às URLs auditadas;
- acesso de saída conforme as fontes ativas, inclusive descoberta externa de IP público habilitada por padrão; desabilitar IA não impede as demais comunicações.

## Dependências declaradas pelo pacote

O pacote exige Python 3.13, Playwright (>=1.57,<2) e tzdata (>=2026.1). A instalação editável usa setuptools (>=68) para empacotamento. Os grupos opcionais abaixo são declarados em [pyproject.toml](../pyproject.toml):

| Grupo | Dependências | Finalidade |
| --- | --- | --- |
| documents | pypdf | Leitura de PDF |
| postgresql | psycopg[binary] | Persistência PostgreSQL |
| web | fastapi, uvicorn, httpx, PyJWT[crypto] | API e componentes Web |
| copilot | github-copilot-sdk | Integração Copilot |
| geoip | maxminddb | Leitura de bases GeoIP locais |
| attestation | cryptography | Recursos de atestação |

O Chromium é um componente separado, instalado pelo Playwright. A preparação opcional do GeoIP também é chamada pelo inicializador e não bloqueia a abertura do console em caso de falha; a aquisição de software depende de consentimento persistido. As bases e credenciais têm requisitos próprios.

## Inicialização recomendada no Windows

Na raiz do projeto, execute por duplo clique ou pelo terminal:

```cmd
abrir-rasai-console.cmd
```

O inicializador prepara as dependências declaradas para as capacidades locais e opcionais. A disponibilidade efetiva de cada integração depende também de credenciais, permissões, rede e pré-requisitos próprios. A cada abertura ele:

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

OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, Mistral, PageSpeed Insights, CrUX e os adapters SERP HTTP usam transporte da biblioteca padrão do Python (`urllib`) e não exigem SDK Python adicional.

**GitHub Copilot é a exceção atual.** A integração usa o SDK oficial e está declarada no extra `copilot` de `pyproject.toml`. No fluxo recomendado, `abrir-rasai-console.cmd` descobre os grupos de `[project.optional-dependencies]` e instala os extras automaticamente. Na instalação manual, instale explicitamente:

```powershell
python -m pip install -e ".[copilot]"
```

A presença da biblioteca não habilita o provider por si só. Mistral não exige SDK adicional, mas requer `MISTRAL_API_KEY`. Para Copilot também são necessários `COPILOT_GITHUB_TOKEN`, uma assinatura Copilot elegível e permissões compatíveis. Quando configurados e aptos, ambos podem participar de `AI=auto`; `RASAI_AI_AUTO_EXCLUDE` permite exclusão operacional.

Depois de o `abrir-rasai-console.cmd` concluir o bootstrap, o software fica preparado do ponto de vista de dependências para utilizar as integrações declaradas no projeto. O que continua sendo necessário, quando cada integração for habilitada, é sua respectiva credencial e disponibilidade externa: key/token compatível, modelo/plano, saldo/quota, permissões e conectividade de rede.

O launcher não cria credenciais, não compra quota e não habilita providers automaticamente. Esses itens são configuração operacional, não dependência de instalação.

Se futuramente uma integração passar a exigir biblioteca adicional, ela deve ser declarada em `pyproject.toml`. Dependências-base serão instaladas normalmente; dependências declaradas em qualquer grupo de `[project.optional-dependencies]` também serão incluídas pelo launcher. A alteração do arquivo será detectada pelo hash e provocará a reconciliação automática do ambiente.

### Ambiente incompatível

Se uma `.venv` existente estiver incompleta ou não executar CPython 3.13, o launcher interrompe **sem excluí-la**. A mensagem de erro corresponde a uma verificação real da pasta local; isoladamente, não demonstra falha do console, da opção 8 nem da auditoria.

**Recuperação conservadora no PowerShell (Windows):** confirme primeiro que não há execução do console ou Python usando `.venv`, que está na pasta correta e que alterações locais não serão perdidas. Não rode `git switch` ou `git pull` com trabalho local não salvo.

```powershell
Set-Location 'C:\IA-PROJETOS\github\RASAI-Readiness-Auditor'
git status --short
py -0p
py -3.13 --version
```

Se o `git status --short` exibir modificações, interrompa e reconcilie-as antes de trocar de branch/atualizar. Se `py -3.13` não estiver disponível, instale o **CPython 3.13** apropriado para o Windows e confirme novamente a versão antes de mexer na `.venv`. Se necessário, investigue separadamente a arquitetura do Windows e do executável; a caixa `Este aplicativo não pode ser executado em seu PC` não prova, sozinha, sua causa.

Com Python 3.13 confirmado e o diretório sem processos em uso, preserve o ambiente antigo e recrie um novo:

```powershell
if (Test-Path -LiteralPath '.venv') {
    $backup = '.venv-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
    Rename-Item -LiteralPath '.venv' -NewName $backup
}
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe --version
.\abrir-rasai-console.cmd
```

A versão exibida deve ser `Python 3.13.x`. O launcher oficial instala/reconcilia os extras declarados no projeto e o Chromium quando necessário; não é necessário executar duas instalações redundantes por padrão. O backup `.venv-backup-*/` é ignorado pelo Git, mas **não é apagado automaticamente**; preserve-o até concluir o smoke. Se o launcher falhar, capture a mensagem textual completa em vez de remover arquivos adicionais.

Para validar a opção 8 em **smoke sem coleta externa**, selecione **Não executar descoberta** e execute com URL/dispositivo válidos; não deve haver DNS/HTTP/Chromium do site. Não use o modo básico HTTP nesse smoke, pois ele pode consultar a rede sem Docker. Para ensaio direto de `capture_public_architecture`, sem `RASAI_ARCH_PROBE_OFFLINE_CONTAINER=1`, espera-se `SAFE_EGRESS_NOT_CONFIGURED` sem DNS/HTTP; a flag legada `RASAI_ARCH_PROBE_EGRESS_GUARDED` não habilita captura renderizada. O modo dinâmico do console prepara o executor OCI com consentimento quando necessário e não exige flag manual. A captura dinâmica de alvo real depende dos gates de isolamento e canário do executor. Consulte o [contrato de contexto arquitetural](ARCHITECTURE_CONTEXT_CONTRACT.md) e o [roteiro de aceite](ARCHITECTURE_DISCOVERY_ACCEPTANCE.md).

Se Python 3.13 estiver ausente e `winget` não estiver disponível, o launcher não poderá instalá-lo automaticamente.

## Instalação manual

Também é possível preparar o ambiente manualmente:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

Para usar GitHub Copilot na instalação manual, instale o extra correspondente:

```powershell
python -m pip install -e ".[copilot]"
```

Para instalar todos os extras declarados sem depender do launcher, consulte os grupos atuais em `pyproject.toml`. O `abrir-rasai-console.cmd` continua sendo o caminho recomendado porque os descobre e reconcilia automaticamente.

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

Este exemplo realiza coleta real; use somente alvo autorizado. Não é smoke offline e não impede todas as integrações externas. Confira as fontes ativas e os custos antes de executar. A execução materializa `audit.db` e os artefatos disponíveis conforme o estado de coleta e publicação; `logs/audit.log` depende do logging persistente. Consulte o [guia de relatórios](REPORT_GUIDE.md) para distinguir catálogo técnico e apresentação executiva.

## Console interativo

Forma recomendada no Windows:

```cmd
abrir-rasai-console.cmd
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
abrir-rasai-console.cmd
```

Como a instalação é editável, alterações em `src/` são utilizadas diretamente. Se `pyproject.toml` mudar, o launcher detecta a alteração pelo hash e reconcilia dependências, extras e entrypoints automaticamente.

Na atualização manual, encerre as execuções do RASAi, confira a origem do repositório, a branch atual e o estado do trabalho local. Preserve auditorias, configurações e arquivos não rastreados. Se não estiver na `main` ou houver alterações rastreadas, interrompa e reconcilie antes de atualizar. Na `main` limpa, use apenas avanço rápido (`git pull --ff-only origin main`); se falhar, não prossiga com instalação nem force a integração. Para uma release específica, confira a tag e o commit publicado antes de reconciliar o ambiente. A instalação e os downloads podem acessar a rede; não são necessários a cada execução. Use o inicializador recomendado ou a instalação manual acima, conforme as dependências requeridas.

Se a instalação manual precisar de Copilot, reaplique `python -m pip install -e ".[copilot]"` após mudanças relevantes de dependências.

## Diagnóstico

Se `rasai` não for reconhecido no terminal, confirme que a `.venv` está ativada ou use `abrir-rasai-console.cmd`, que chama diretamente o executável do console dentro da `.venv`.

Se Chromium estiver ausente na instalação manual:

```powershell
python -m playwright install chromium
```

Consulte [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para falhas de provider, PageSpeed/Lighthouse, CrUX e artifacts.
