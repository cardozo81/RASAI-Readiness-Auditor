# Aceite consolidado - descoberta e contexto arquitetural

## Gate técnico automatizado

Branch: `feat/acceptance-and-architecture-governance`. A prova de aprovação deve
ser obtida nos **checks do HEAD corrente** da PR; checks verdes de commits
anteriores não homologam modificações subsequentes.

Escopos separados:

- **Menu inicial 8:** diagnóstico prévio e independente; lê URL e dispositivo
  da sessão canônica, sem gerar AUD, reprocessamento, complementação, catálogo,
  score, consumo de IA paga ou alteração da escolha AUTO/DECLARED/UNFORCED.
- **Preparar auditoria (menu 1):** define a política da nova AUD. A descoberta
  física usada pela auditoria/reprocessamento compartilha o classificador,
  não a decisão de política do operador.
- **Configuração reutilizada:** escolha explícita e proveniência preservadas,
  sem alterar AUD histórica.

## Gate de segurança da navegação

**Bloqueador de homologação externa:** `RASAI_ARCH_PROBE_EGRESS_GUARDED=1`
é somente uma asserção de implantação, não um mecanismo de segurança. O
transporte HTTP bruto já utiliza conexão com IP público fixado e verificação
TLS/SNI; isso **não valida o tráfego nativo do Chromium**.

Antes de ativar o guard e navegar a qualquer URL real, o ambiente executor
precisa demonstrar bloqueio, na **camada de rede**, de todo tráfego do processo
Chromium a loopback, RFC1918, link-local, endereços privados IPv6, metadados
de nuvem e endpoints internos, incluindo eventual troca de DNS depois do
preflight. Devem existir limites de egress efetivos também para conexões
não-HTTP (WebSocket/WebRTC) ou sua proibição. Em ambiente sem essas garantias,
**não ativar** a flag nem tentar contornar o bloqueio do menu.

A coleta deve falhar de modo seguro se o destino, conteúdo, renderização ou
identidade da URL não forem comprovados. Ter checks verdes não substitui a
prova operacional da política de rede.

## Smoke exploratório humano, após gate de segurança

1. Com a flag ausente, acessar **Início > 8**. Validar a URL e o dispositivo
   herdados do menu 1. Executar: informar diagnóstico inconclusivo e ausência
   de contato com a rede. Voltar: nenhuma nova AUD ou artefato criado.
2. Alterar URL e dispositivo pela opção 8; conferir que o mesmo valor aparece
   no menu 1, sem configuração duplicada ou reset indesejado.
3. Em executor **com proteção de rede comprovada**, usar URLs públicas
   autorizadas de páginas: conteúdo server-side, SPA client-side, híbrida
   hidratada, comportamento misto, HTML vazio, erro HTTP e redirects. Executar
   uma URL por vez em desktop e mobile. Coletar evidência de status de rede,
   comparação RAW versus renderizado, versão, limitação e motivo de abstenção.
   **Não esperar classificações conclusivas** quando recursos ou origens
   necessários forem bloqueados.
4. Verificar que o menu 8 não cria AUD/RPR/CONS, nem dispara módulos de
   auditoria, provedores faturáveis ou gravações no audit.db; comparar o estado
   e a contagem de AUDs antes e depois.
5. Em **Início > 1**, selecionar AUTO, DECLARED e UNFORCED em execuções
   separadas. Comprovar observado/declarado/efetivo, discrepância e
   proveniência por URL + device + snapshot, sem extrapolar para outra URL.
6. Carregar uma AUD legada sem escolha arquitetural: não inventar preferência.
   Carregar AUD com escolha explícita: preservar a preferência da origem.
   Cancelar/restaurar configuração inválida: manter estado da sessão original.
7. Verificar relatórios/consumidores consultivos permitidos e abstinência
   explícita dos não permitidos. Comparar scores e registros históricos para
   garantir que nenhum resultado pré-existente foi recalculado.
8. Reexecutar testes direcionados + CI do HEAD após qualquer correção.

## Registro do parecer

Preencher com: SHA exato, URL/teste sem credenciais, dispositivo, ambiente
e política de rede atestada, evidências da interface, artefatos antes/depois,
resultados por cenário, lista de defeitos, conclusão `APROVADO` ou
`REPROVADO`, responsável e data.

**Regra de merge:** manter a PR como Draft e as issues abertas até aprovação
dos critérios funcionais e de segurança, incluindo o smoke humano.

### Mitigações do browser implementadas no processo

- A interceptação HTTP passa a ser registrada no `BrowserContext` **antes da criação da página**, cobrindo inclusive o primeiro request de popups; `page.route` não cobria essa situação.
- Recursos diferentes de GET, URLs não públicas, origens diferentes e solicitações que ultrapassem o orçamento são abortados.
- WebSockets são interceptados no contexto com `route_web_socket` e fechados sem `connect()`. Qualquer bloqueio impede classificação conclusiva.
- **Não constitui atestado de firewall/egress:** tráfego nativo do Chromium, redirecionamentos e WebRTC ainda exigem contenção verificável em camada de rede. A flag `RASAI_ARCH_PROBE_EGRESS_GUARDED` não instala essa contenção.

### Captura HTTP do navegador via transporte fixado

O navegador **não** usa `route.continue_` ou `route.fetch` para recursos HTTP.
Todo GET permitido é respondido via `route.fulfill` com bytes recuperados pelo
transporte Python `PublicWebPinnedOpener`, que fixa o IP público da conexão,
mantém SNI/certificado do host e recusa redirects. A primeira navegação usa
exatamente os bytes RAW já coletados, evitando segunda leitura com HTML divergente.
O orçamento de recursos é limitado a 30 requisições e 3 MB de corpo somado;
qualquer recurso bloqueado torna o diagnóstico inconclusivo. Cookies recebidos
não são transferidos pelo replay e recursos cross-origin são rejeitados, o que
pode impedir a classificação de sites que dependem de CDN e APIs externas.

**Permanece um bloqueio:** HTTP intermediado não prova que o processo Chromium
esteja isolado para outras pilhas nativas, especialmente WebRTC. Só executor
com restrições efetivas de rede atestadas pode realizar a captura externa.

### Executor OCI isolado, opt-in (em implementação e homologação)

O caminho \`RASAI_ARCH_PROBE_OFFLINE_CONTAINER=1\` substitui o uso da variável
legada \`RASAI_ARCH_PROBE_EGRESS_GUARDED\` na opção 8. A variável legada,
isoladamente, **nunca** libera o Chromium no host. Sem opt-in, conserva-se
a abstenção sem DNS/HTTP. Com opt-in, o processo primeiro verifica que a imagem
OCI local \`rasai-architecture-offline:local\` existe (sem consultar a rede).
Somente após isso coleta HTML/recursos via \`PublicWebPinnedOpener\`. O browser
recebe somente um bundle limitado via stdin em \`docker run --network=none\`,
sem host mounts ou acesso ao Docker daemon, usuário não-root, filesystem read-only,
capabilities removidas, CPU/memória/pids limitados, imagem referenciada pelo
digest local e \`--pull=never\`. Recursos ausentes, externos e falhas abstêm.

Construção a partir do código auditado:
\`\`\`powershell
docker build -f Dockerfile.architecture-offline -t rasai-architecture-offline:local .
\`\`\`
O build baixa dependências e Chromium gratuitos, exige Docker funcional e
acesso à Internet **apenas durante o build**. Não há instalação automática,
execução de auditoria, alteração em INI, nem uso de API comercial.

**Limite de aceite:** testes unitários e CI não constituem prova física de
\`--network=none\` no host/daemon do operador. Exigir execução real da matriz
de rede, inspeção do comando efetivo e revisão do isolamento antes de permitir
uso operacional. Sites dependentes de CDN, cookies ou APIs de terceiros podem
resultar \`UNKNOWN\` por falta de recursos, sem fallback nativo.

### Passos operacionais para smoke OCI

1. Atualizar a branch e verificar que a árvore Git está limpa.
2. Conferir o Docker Desktop/Engine e o acesso a um daemon **local**. Revisar a
   política de redes do host e do Docker antes de confiar no isolamento.
3. Construir a imagem local a partir do código revisado, sem credenciais:
   \`docker build -f Dockerfile.architecture-offline -t rasai-architecture-offline:local .\`
4. Executar um diagnóstico de isolamento do daemon/container e observar que
   o container com \`--network none\` não alcança destinos públicos, privados,
   DNS, loopback do host ou metadata. O processo de browser nunca herda volume,
   rede host, docker.sock nem credenciais.
5. Em uma **sessão de homologação isolada**, definir temporariamente
   \`RASAI_ARCH_PROBE_OFFLINE_CONTAINER=1\`; manter a flag legada desativada.
   Se a imagem faltar, a execução deve ser inconclusiva **antes de DNS**.
6. Apenas depois do gate do item 4, testar uma URL pública autorizada de cada
   classe (estática, SPA, hidratada, mista e falhas), em mobile e desktop.
   Registrar versão, classificação, motivo de abstenção e ausência de AUD.
7. Ao terminar, desfazer a variável de sessão. Não gravar no INI nem autorizar
   provedores de IA. Não converter testes sintéticos em prova física.


**Comprovação física negativa (antes de liberar a opção 8):**
\`\`\`powershell
py -3.13 -m rasai.architecture_isolation_smoke
\`\`\`
A saída esperada é \`OCI_NETWORK_ISOLATION_BLOCKED\` para os onze testes
de DNS e sockets públicos/privados/metadata/loopback (IPv4 e IPv6). Se mostrar
\`OCI_NETWORK_ISOLATION_NOT_ATTESTED\`, o diagnóstico externo deve continuar
bloqueado. Executar novamente após mudanças de Docker daemon, imagem ou host.
O preflight recusa daemons remotos via DOCKER_HOST ou contexto Docker SSH/TCP;
a imagem é executada pelo digest local para evitar troca de tag.

**Gate automático obrigatório:** a opção 8 não se limita a encontrar a imagem
local. Antes de qualquer DNS/HTTP do site, executa no **mesmo digest OCI**
os onze probes negativos de rede usados pelo teste físico. Qualquer socket
ou DNS permitido, erro de daemon ou timeout impede a aquisição e retorna
`OCI_NETWORK_ISOLATION_NOT_ATTESTED`. O teste manual continua recomendado
como evidência operacional independente, mas uma flag de ambiente isolada
não suprime esse gate.

### Equivalência das políticas de resposta

O bundle offline preserva cabeçalhos de segurança relevantes para a execução
de scripts, incluindo `Content-Security-Policy`, `X-Content-Type-Options`,
`Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy`,
`Cross-Origin-Embedder-Policy` e `Referrer-Policy`. Não remover CSP do
HTML reproduzido: executar JavaScript que o servidor original proibiria pode
produzir uma classificação artificial. Cabeçalhos com CR/LF ou tamanho fora
do limite são rejeitados; cookies e cabeçalhos hop-by-hop não são importados.
A ausência de cookies e recursos de terceiros pode levar a abstenção legítima.

O diagnóstico de rede inclui agora **quatro tentativas UDP** (IPv4 público,
IPv4 privado, metadata/link-local e IPv6 privado) além de TCP e DNS. Com
`--network none` todas devem falhar por ausência de rota. Não é prova
independente contra comprometimento do daemon/host, mas evita tratar
bloqueio apenas TCP como cobertura WebRTC. O contêiner usa
`--log-driver=none` para não persistir o bundle no daemon.

### Diagnóstico de abstenção na captura externa

Após provar o bloqueio de rede, o RASAi agora executa um **canário de renderização
totalmente sintético** dentro da mesma imagem OCI e sob as mesmas restrições,
**antes de consultar o DNS do site**. O canário usa HTML local e não aciona
provedores pagos. Se não produzir DOM com marcador esperado, o diagnóstico
retorna `OCI_BROWSER_CANARY_FAILED`, separadamente da falha de rede.
O processo worker só retorna códigos de motivo conhecidos; o host agora
preserva `ISOLATED_BROWSER_UNAVAILABLE`, `ISOLATED_RESOURCES_BLOCKED`,
`ISOLATED_NAVIGATION_NOT_ATTESTED`, `ISOLATED_RENDER_LIMIT` ou
`ISOLATED_MANIFEST_INVALID`, em vez de colapsá-los sempre em uma mensagem
genérica. Nunca exibir stdout bruto, stderr, HTML, cookies ou tokens no console.
Essa diferenciação não autoriza afrouxar a proteção nem concluir a captura
real sem comparar RAW/DOM.

Para isolar o problema de Chromium sem consultar o site, execute **após atualizar
o código local**:

```powershell
.\.venv\Scripts\python.exe -m rasai.architecture_isolation_smoke --browser
```

Essa opção primeiro executa o bloqueio de rede e depois renderiza uma página
**sintética** na mesma imagem OCI. Os únicos resultados possíveis do teste
são `OCI_BROWSER_CANARY_PASSED` ou
`OCI_BROWSER_CANARY_FAILED` (eventualmente acompanhado de um código
técnico da lista fixa); nunca imprime Docker stderr, HTML externo ou secrets.
Se falhar, não executar a descoberta externa até diagnosticar o contêiner.
**A imagem não precisa ser reconstruída para esse teste se a versão do worker
não tiver mudado; o Python do host precisa estar atualizado.**

### Falha no exemplo externo após canário aprovado

Caso o operador obtenha `OCI_BROWSER_CANARY_PASSED`, mas o menu 8 retorne
`UNKNOWN` sem comparação RAW/DOM, **não** classificar como falha do
Chromium nem afirmar que o site é SPA. O Chromium sintético passou, mas a
página real pode exigir recursos inacessíveis, conter referências externas,
ultrapassar o orçamento, falhar no processo de replay ou exceder timeout.

O adaptador agora distingue no console três estágios antes ocultos pelo
motivo genérico `ISOLATED_RENDER_INCONCLUSIVE`:

- `OCI_ASSET_BUNDLE_REJECTED`: preparação segura de recursos da página
  rejeitada (pode ser recurso externo ou não disponível). Não fazer fallback
  para requisitar recursos não autorizados.
- `OCI_WORKER_TIMEOUT`: processo de renderização excedeu seu tempo total.
- `OCI_WORKER_OUTPUT_INVALID`: resposta do worker ausente, inválida ou
  incompatível. Não mostrar stdout/stderr, URLs ou HTML bruto para diagnosticar.
  
Os códigos são limitações da observação física, não classificação do
framework do site. O fluxo mantém `UNKNOWN` e não modifica AUD.
Antes de repetir um smoke real, sincronizar HEAD local da PR e manter o
mesmo digest OCI cuja integridade/isolamento passou. Não é necessário
reconstruir a imagem se o conteúdo do worker e Dockerfile não mudou.

### Favicon embutido por URI data: na observação isolada

O HTML de referência de `https://example.org/` contém um
`<link rel="icon">` com URI `data:`. Esse recurso está **embutido no
próprio documento**, não possui endpoint HTTP(S) para consulta segura e não
deve ser convertido em uma URL de rede.

O adaptador de pré-coleta ignora **somente favicons com `rel=icon` e
`href=data:image/...` ou o marcador de ícone vazio `href=data:,`** na lista de requisições HTTP, preservando o conteúdo original
no HTML enviado ao Chromium sem rede. Scripts, CSS, preloads e referências
a endpoints externos continuam sujeitos às regras anteriores; uma URI
`data:` de script ou stylesheet não recebe essa exceção. Assim, evita-se
falsa rejeição de um metadado visual sem declarar que conteúdo dinâmico ou
recursos de terceiros foram reproduzidos.

Evidência da causa: o smoke OCI opt-in registrou apenas a categoria/quantidade
de referências, sem coletar logs de HTML, URL de recurso ou credenciais:
`link_icon:data = 1` e `script:https = 1`. A URI exata não deve ser
registrada em logs de CI. Classificações com recursos essenciais bloqueados
devem continuar como `UNKNOWN`, e não como `STATIC_OR_SSR`.

### Matriz física isolada de classificação (sem sites externos)

A suíte `tests/architecture_offline_classification_matrix.py` executa oito
cenários artificiais em uma imagem OCI local, após os testes negativos TCP,
UDP e DNS e o canário Chromium. São quatro classes do classificador
`architecture-observation-v1`, cada uma executada em mobile e desktop:
`STATIC_OR_SSR`, `CSR_SPA`, `HYDRATED` e `MIXED`.

A matriz entrega um bundle de HTML/JS local ao Chromium através de stdin;
não consulta DNS nem site externo e não cria AUD. Os scripts artificiais
modificam o elemento `main` de forma determinística, para verificar que
a comparação RAW/DOM realmente classifica o efeito observado. Resultado
esperado do teste físico: `OCI_MATRIX_ALL_8_PASSED`.

Execução local facultativa após construir e validar a mesma imagem:
```powershell
.\.venv\Scripts\python.exe -m tests.architecture_offline_classification_matrix
```

**Limite:** testes sintéticos provam a execução do classificador nas condições
construídas, não a arquitetura real de qualquer framework/site. Na captura
pública de referência, a classificação `HYDRATED` para `example.org` é uma
observação **do método v1**, não confirmação independente de que o site use
hydration framework. A matriz física externa com páginas reais heterogêneas
ainda exige amostras adequadas e evidências/limitações explícitas.
