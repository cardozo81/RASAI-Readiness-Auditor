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

A preparacao e atualizacao da imagem ocorre pelo console, com
autorizacao do operador. Para ensaio tecnico independente e **somente
quando necessario**, o comando manual deve conter o SHA-256 do worker:
\`\`\`powershell
$WorkerSha = & ".\\.venv\\Scripts\\python.exe" -c "from rasai.architecture_image_identity import expected_source_sha256; print(expected_source_sha256())"
docker build --build-arg "RASAI_ARCHITECTURE_SOURCE_SHA256=$WorkerSha" -f Dockerfile.architecture-offline -t rasai-architecture-offline:local .
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
3. Acessar o console e autorizar a preparacao da imagem caso o RASAi
   indique que esta ausente ou desatualizada. Apenas o ensaio tecnico
   independente deve utilizar o comando manual com build-arg acima.
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

### Gerenciamento automatico de imagem OCI por identidade de codigo - 23/10/2026

Ao selecionar descoberta dinamica, o RASAi calcula uma identidade SHA-256
deterministica dos arquivos que compoem o worker OCI e das dependencias de
codigo explicitamente inventariadas em `architecture_image_identity.py`.
O valor tambem e aplicado como label da imagem no build autorizado pelo
console. O RASAi aceita a tag `rasai-architecture-offline:local` somente
quando o daemon Docker **local** retorna simultaneamente um identificador de
imagem no formato `sha256:...` e a label de origem esperada. Imagem ausente,
sem a label ou com label divergente **nao pode ser usada** na descoberta.

Com Docker local acessivel, o console pede autorizacao para construir ou
atualizar a imagem desatualizada. Sem consentimento, sem fonte local ou
diante de falha do build, a descoberta permanece indisponivel antes de
consultar o DNS/HTTP do alvo. Quando a imagem ja corresponde ao codigo,
nao ha novo build nem pergunta desnecessaria. A comprovacao independente
de isolamento de rede e o canario Chromium continuam obrigatorios **no
mesmo digest OCI**, antes de requisitar qualquer pagina real.

No Windows, o comando de build direciona stdout/stderr para
`subprocess.DEVNULL`. Como os logs Docker nao sao exibidos nem interpretados
pelo RASAi, isso evita que bytes UTF-8 de progresso sejam decodificados pelo
locale CP1252 e produzam `UnicodeDecodeError` em threads de leitura.
O resultado continua definido pelo exit code do Docker e pela identidade
revalidada da imagem. A verificacao `docker info` usa UTF-8 com substituicao
de bytes invalidos apenas para mensagens nao confiaveis; diagnosticos de
permissao conservam codigos estaveis, sem exposicao de stderr.

A label de origem identifica a revisao do **codigo local**, mas nao e
assinatura de fornecedor nem atestado independente do daemon, do build ou
das dependencias baixadas. Ela nao substitui as verificacoes de isolamento.
O usuario nao precisa executar `docker build` manualmente para atualizacoes
posteriores dentro desse fluxo: a preparacao pelo console e o caminho
normal. Se Docker nao estiver instalado/iniciado, o RASAi nao tenta
instalar ou iniciar o servico sem autorizacao. O modo basico e os demais
catalogos permanecem disponiveis.

Escopo desta entrega: apenas ciclo de vida da imagem, contrato de build,
verificacao de identidade e testes focais. Nao modifica limites da captura,
classificacao, TLS, cadeia de redirects, carregamento em iframe,
persistencia de AUD ou os indices.

#### Interpretacao dos smokes externos recebidos em 23/10/2026

- `loja.bradescoseguros.com.br/seguro-de-vida`: `OCI_ASSET_UNAVAILABLE`,
  com HTML inicial obtido mas DOM nao obtido. Uma pagina que depende de
  iframe, aplicacao embarcada ou recursos com autenticacao, redirect,
  resposta nao-2xx ou limite de tamanho pode falhar na obtencao
  controlada de recursos. Nao presumir arquitetura SPA nem modificar a
  politica de rede para forcar a captura.
- `mdsgroup.com`: `PUBLIC_TLS_FAILURE` na captura inicial, sem HTML.
  A negociacao TLS deve ser concluida antes de qualquer resposta HTTP
  de redirect. Um posterior redirecionamento observado por navegador
  externo nao legitima ignorar a falha TLS do destino solicitado.
  Conferir a cadeia TLS/SNI/WWW por salto em etapa propria, sem
  desabilitar a verificacao de certificado.
- `google.com`: `ISOLATED_CONTENT_NOT_STABLE`, com RAW e redirect HTTP
  observado. A janela temporal e os requisitos de materialidade do DOM
  impedem promover uma primeira renderizacao provisoria a classe final.
- `www.ecosistemasti.com.br`: `ISOLATED_RESOURCES_BLOCKED`, embora
  haja conteudo principal no HTML inicial. Requisicao de iframe, rede,
  recurso inexistente no bundle ou metodo nao permitido bloqueia
  uma comparacao completa, sem provar ausencia de SSR.

Os quatro motivos sao distintos e nao constituem falha da identificacao de
versao da imagem Docker. Provas por pagina, ativo e destino continuam
necessarias para ampliar cobertura real sem comprometer a seguranca.

### Alinhamento pontual do orçamento da descoberta OCI - 23/10/2026

A aquisição passa a admitir **64 recursos HTTP distintos adicionais ao HTML**,
sem alterar as verificações de destino, métodos HTTP ou o isolamento.
Para evitar que a ampliação encontre bloqueios internos anteriores,
`architecture_resource_budget.py` fornece os limites compartilhados por
coletor e worker: **65 entradas**, até **33.000.000 bytes de conteúdo**
(1 MB HTML + 64 vezes 500 KB por recurso), **52.000.000 bytes para o
manifesto JSON/base64** e **70 requisições HTTP no navegador** (com margem
restrita para repetições). Os tamanhos individuais permanecem iguais.
Uma página acima desses limites, com recurso externo inacessível, com
JavaScript dependente de API/cookies ou DOM final não atestado continua
`UNKNOWN`, sem tentativa de contorno ou download não autorizado.

A imagem OCI deve ser **reconstruída localmente** após atualizar o
repositório: o worker embutido na imagem precisa usar a mesma política do
coletor Python. A mudança não introduz medição/registro detalhado de
recursos; essa melhoria autorizada permanece uma etapa independente.
Nenhuma AUD, configuração, score ou evidência histórica é modificada.

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
reconstruir a imagem se a identidade do código OCI permanecer igual.

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

## Estabilidade temporal de conteudo e redirecionamentos na previa (#646)

Em páginas SPA/hidratadas o evento DOMContentLoaded, e mesmo o fim momentâneo da rede, podem ocorrer **antes** da materialização do conteúdo principal. A renderização OCI (rede desabilitada no container) agora aguarda no máximo 2.800 ms a partir de DOMContentLoaded para obter texto efetivo em main/article/[role=main] sem marcador aria-busy/skeleton, com três observações iguais e pelo menos 850 ms de janela. Este limite **não** equivale a garantia de que toda aplicação terminou; se houver spinner, mudança contínua, falha de asset ou conteúdo tardio além do orçamento, o resultado permanece UNKNOWN com ISOLATED_CONTENT_NOT_STABLE ou motivo de bloqueio. Não criar espera irrestrita, networkidle universal, navegação adicional ou pontuação Apdex.

No modo básico HTTP (sem Docker) o classificador permanece UNKNOWN por não existir DOM renderizado. Entretanto agora pode mostrar indícios RAW limitados a presença de main/article com texto substantivo, h1, contêiner de app, atributos estruturais, scripts e placeholders. Esses fatos não demonstram execução de script, SPA, SSR, hidratação ou indexação; texto do site não é copiado para o resumo.

HTTP aceita, no máximo, **dois hops** através do fetcher público existente e IP pinning por hop. O probe só considera cadeia válida se ela estiver completa, terminar exatamente no recurso final, não possuir loop, não trocar para domínio alheio (exceção www/ápice do mesmo host) e não realizar downgrade HTTPS para HTTP. Upgrade HTTP para HTTPS é permitido **somente** com TLS validado pelo transporte, sem ignorar certificado expirado, desconhecido ou inválido. Destinos públicos não relacionados, erros de certificado, timeout de rede, redirect truncado ou mudança dinâmica não comprovada geram motivo próprio/N/D; não deduzir bloqueio de firewall, indisponibilidade global ou classificação do destino. Redirecionar HTTP não é o mesmo que TLS tardio; handshake TLS deve terminar com verificação antes de buscar HTML.

Smoke posterior de ambiente protegido: fixture SSR com conteúdo imediato, SPA com conteúdo materializado dentro da janela, SPA que materializa após janela e permanece UNKNOWN, HTTP->HTTPS no mesmo host com certificado válido, cadeia HTTPS->www limitada, redirect cross-host, loop, timeout e certificado inválido sem fallback inseguro. Executar apenas em URLs públicas autorizadas, sem Docker/Chromium no host nem chamadas de provedores IA. O relatório NDR de #649 continua apenas roadmap e não é implementado aqui.

## Janela completa antes da decisão arquitetural (19/10/2026)

A etapa de estabilização consultiva observa agora **toda a janela máxima de 2.800 ms**, em vez de aceitar uma primeira sequência estável de 850 ms. Uma pintura de conteúdo aparentemente servidor pode ser substituída pelo JavaScript após 1.200-2.000 ms; o conjunto final de três observações materiais iguais deve pertencer à mesma página depois dessa atualização. Mudança próxima do prazo, loading persistente ou conteúdo insuficiente geram ISOLATED_CONTENT_NOT_STABLE, não uma classe estática fictícia. Este limite não promete que a SPA terminou depois do prazo. Skeleton oculto por CSS não bloqueia artificialmente a materialidade; elemento principal oculto não comprova conteúdo visível. Sem alteração do comportamento de navegação sintética/experiência sintética ou da duração de load.

A prévia de arquitetura apresenta adicionalmente **contagem de redirecionamentos** e transição HTTP para HTTPS quando a aquisição explicitamente as reportou. O console não publica URL final integral nem parâmetros sensíveis e diferencia metadados da captura de certificado independente. O registro de origem é um digest local da coleta, não certificação externa. Não executar novo request, ignorar TLS ou classificar conteúdo quando a URL final não puder ser vinculada à cadeia permitida.

## Proveniência RAW após redirecionamento e renderização inconclusiva (#646)

Se o transporte HTTP pinado comprovar um redirecionamento público admissível,
mas o bundle de recursos ou a renderização OCI falhar, o diagnóstico mantém a
URL final, os saltos, a transição HTTP→HTTPS e o digest da captura RAW.
A classificação permanece UNKNOWN, nunca inferindo DOM executado a partir de
RAW. PINNED_HTTP_STATIC atesta somente a aquisição HTTP, não o Chromium,
a indexabilidade ou a qualidade da experiência. Redirecionamentos não
verificáveis continuam recusados; o gate de F3 não foi alterado.

## #601 - FAQ JSON-LD como fonte independente do DOM

O observador offline CAT-03 examina também scripts FAQPage em
`application/ld+json` nos snapshots HTML já existentes, com orçamento
estrito, parser JSON que recusa chaves duplicadas/NaN e contagem de entradas
FAQPage/Question/acceptedAnswer sem exibir dados de terceiros. Esses números
são inventário **da marcação**, não prova de DOM visível, abertura de
acordeão, leitura pelo Googlebot, veracidade editorial ou elegibilidade a
pontuação. A ausência de acordeões com JSON-LD presente continua N/D para
**interação**; não se reescreve BR-GEO-039/049 nem AUD histórica. A captura
permanece read-only, sem browser, clique ou chamadas externas.


## Extensão de tempo exclusiva do diagnóstico arquitetural OCI

Apenas o renderizador OCI usado na descoberta arquitetural independente
(menu 8) agora observa por até **5.200 ms**, em lugar dos 2.800 ms
anteriores, depois de `DOMContentLoaded`. O padrão original de 2.800 ms
continua vigente para outros chamadores. A espera acompanha exclusivamente
o DOM da mesma página, permitindo identificar conteúdo materializado
tardiamente, inclusive substituição SPA após uma primeira pintura estática.
Três amostras finais de conteúdo principal visível e estável ainda são
necessárias. Conteúdo ausente, alterações nos instantes finais ou carregamento
contínuo continuam UNKNOWN, não uma classificação artificial.

**Invariantes:** o código de M2, M3, M6, a AUD, os timeouts HTTP/TLS,
DNS, ping, RTT, métricas de latência/load, Apdex, SARI e scoring não foram
alterados. Não há nova consulta HTTP, recaptura, retry, navegação nem
permissão de saída de rede; o contêiner continua `--network=none`.
A consulta de arquitetura isolada pode demorar até 2,4 segundos adicionais;
isso não compõe nem modifica indicadores medidos da auditoria.
O adaptador também preserva os códigos de abstenção de DOM não estável
ou não verificável, em vez de substituí-los por limitação genérica.


## Descoberta arquitetural genérica, sem conhecimento prévio de domínio

O RASAi recebe URL e device, não um cadastro de domínios e regras por site.
A identificação arquitetural deve decorrer de evidências obtidas em tempo de
execução e do escopo efetivamente observado. Sites externos usados em testes
são exemplos de mecanismos técnicos; não são entradas de classificação.

### Separação de três níveis de evidência

1. **Observada:** comparação RAW/DOM com identidade de documento, transporte
   admissível, recursos essenciais suficientes e conteúdo estabilizado.
   Essa camada permanece com o classificador canônico
   `STATIC_OR_SSR / CSR_SPA / HYDRATED / MIXED / UNKNOWN`.
2. **Hipótese consultiva:** inferência de baixa confiança, explicitamente
   não comprovada, sobre indícios do HTML inicial quando a renderização
   estiver indisponível. `architecture-hypothesis-v1` não transforma
   `UNKNOWN` em classificação observada, não altera índices, auditorias
   persistidas, roteamento de coletores ou autorização de execução.
3. **Limitação:** motivo técnico que impediu obter evidência suficiente,
   preservado separadamente da hipótese, incluindo TLS, redirect, recurso,
   iframe não materializado, captura bloqueada ou DOM instável.

### Padrões estruturais iniciais para hipótese de baixa confiança

- Contêiner de aplicação com scripts e conteúdo principal RAW não comprovado:
  `CSR_SPA` candidato, com `MIXED` como alternativa. Um marcador de root
  por si só não comprova JavaScript executado ou arquitetura SPA.
- Conteúdo principal RAW, atributo estrutural de framework e scripts:
  `HYDRATED` candidato, com outras arquiteturas explicitamente possíveis.
- Conteúdo RAW substantivo e H1, sem prova de hidratação:
  `STATIC_OR_SSR` candidato, sem descartar atualização por JavaScript.
- Presença de `iframe` no HTML inicial: identificar a **topologia composta**
  `EMBEDDED_FRAME_COMPOSITION`, mas recusar hipótese de arquitetura global
  até observar separadamente a origem e o DOM do conteúdo embutido.
- Ausência de RAW válido: não propor hipótese. Erros TLS e rede não
  autorizam deduzir arquitetura a partir da URL ou do erro.

Esses rótulos são informativos; "confiança baixa" não é probabilidade
numérica validada. Nunca confundir possíveis alternativas com prova física.

### Requisitos seguintes para cobertura de arquiteturas heterogêneas

1. Aquisição tipada e identificada por documento: URL solicitada, hops
   verificados, certificado e SNI por conexão, documento final, frames
   explícitos, recurso essencial/opcional e provenance por observação.
2. Reprodução isolada e limitada de dependências de documento, incluindo
   scripts, CSS, recursos de origem pública e frames permitidos, sempre com
   IP público fixado no transporte host e `docker run --network=none`.
   Não ignorar TLS nem simular cookies/sessões ausentes.
3. Observação temporal de estados sucessivos do DOM e de cada contexto
   incorporado; distinguir conteúdo tardio de conteúdo que não foi obtido,
   e SPA, SSR, hidratação, composição por frames e fluxos mistos.
4. Critérios explícitos de suficiência: preservar abstenção somente quando
   falta evidência essencial; recurso visual secundário bloqueado não deve
   ser automaticamente considerado prova de falha da arquitetura inteira.
5. Saída consultiva com arquitetura observada, candidatos, razões, componentes
   e limites. Scores históricos permanecem imutáveis.

Os mecanismos acima ainda não estão todos implementados. A primeira
entrega genérica acrescenta apenas o inventário estrutural RAW de iframe e
as hipóteses consultivas descritas, com testes independentes de qualquer host.
A arquitetura de documentos incorporados e o tratamento seletivo de recursos
permanecem requisitos funcionais independentes, não conclusões já obtidas.

## Diagnóstico genérico de falhas por recurso isolado

A aquisição OCI mantém a recusa segura de qualquer recurso com URL inválida,
destino privado, certificado TLS inválido, redirecionamento não permitido,
limite de tamanho ou resposta incompatível. Para evitar que falhas distintas
sejam apresentadas como uma única indisponibilidade, o RASAi distingue:

- Bloqueio de destino público, falha TLS, timeout e erro de rede.
- Redirecionamento proibido, HTTP não-2xx, URL final divergente.
- Tamanho individual excedido, tipo de conteúdo ausente e política recusada.

O diagnóstico consultivo identifica adicionalmente apenas **categoria**
(`script`, `stylesheet`, `iframe`, `image`, `source`, `preload`,
`modulepreload` ou `icon`), **etapa** e **posição ordinal** entre
os recursos únicos previamente inventariados. Não armazena nem imprime
URL do recurso, parâmetros, DOM, corpo HTTP, cookies, exceções, certificados
ou credenciais. Os números não equivalem a contagem de todos os recursos
que um navegador com Internet tentaria acessar: são somente o inventário
da captura RAW sob as regras atuais.

O registro é transitório, vinculado à tentativa de aquisição da página.
Não persiste em AUD, não altera scores, classificação v1, orçamento de
recursos, política TLS, isolamento OCI ou métodos de busca. Classificação
observada permanece `UNKNOWN` sem RAW/DOM completos; hipóteses do HTML
continuam separadas. A próxima investigação pode ser orientada pelo motivo
e tipo de falha, **nunca por cadastro ou reconhecimento de domínios**.


## Orçamento de recursos por papel arquitetural (23/10/2026)

O diagnóstico de captura real encontrou um recurso do tipo **folha de estilo**
acima do limite individual padrão de 500.000 bytes (posição 14 de 27 no
inventário RAW de uma amostra). Esse fato não informa o tamanho exato,
a relevância da folha nem comprova a arquitetura do documento.

O orçamento genérico, sem regras por domínio, mantém **64 recursos**
adicionais ao HTML, **1.000.000 bytes para o HTML inicial** e **500.000
bytes para recursos comuns** (incluindo JavaScript, imagens e mídia).
Folhas de estilo declaradas por `rel=stylesheet` ou por `rel=preload
as=style` podem ser adquiridas até **2.000.000 bytes**, mediante validação
de destino público e `Content-Type: text/css` na resposta.

**Limites globais permanecem iguais:** até 33.000.000 bytes decodificados
para HTML+recursos e 52.000.000 bytes para o manifesto JSON/Base64, com no
máximo 65 entradas no worker e 70 requisições no navegador isolado.
O coletor agora interrompe o inventário antes de entregar um pacote que
ultrapassaria o limite decodificado do worker. Exceder o total devolve
`OCI_ASSET_TOTAL_BYTES_LIMIT`, distinto de `OCI_ASSET_SIZE_LIMIT`
individual; ambos apresentam somente tipo, etapa e posição do recurso
sem URLs ou conteúdo.

A política por tipo **não presume que CSS seja dispensável**: folhas de
estilo podem determinar visibilidade, placeholders e estabilização do DOM
e não são ignoradas para obter classificação artificial. No worker, toda
entrada CSS deve respeitar seu teto de 2 MB; entradas não-CSS continuam
limitadas a 500 KB; a entrada principal continua limitada a 1 MB.
O worker aplica os limites também quando recebe um manifesto inválido,
sem depender da validação do host. A aquisição conserva
`--network=none` no Chromium, IP pinado no host, verificação TLS/SNI,
recusa de redirecionamentos de recursos e abstenção sem DOM comprovado.

A fonte da política de orçamento integra o fingerprint do código OCI.
Depois de `git pull --ff-only`, a preparação do console deve solicitar
consentimento para reconstruir a imagem desatualizada uma única vez.
Não é necessário executar `docker build` manualmente.

Esta mudança não implementa escolha de recursos opcionais nem observação
de frames dinâmicos. Essas capacidades permanecem separadas para evitar
promover um DOM incompleto a `STATIC_OR_SSR` ou `CSR_SPA`.
