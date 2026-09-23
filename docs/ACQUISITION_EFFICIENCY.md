# Eficiência de aquisição e integrações externas do RASAi

## Objetivo

O RASAi deve minimizar a carga sobre as origens auditadas sem enfraquecer o significado de nenhuma métrica. Análises posteriores, scoring, IA e geração de relatórios devem consumir evidências persistidas em vez de reabrir a URL auditada quando a informação necessária já estiver disponível.

A regra governante é:

> Uma nova aquisição física só é permitida quando a observação não puder ser derivada da evidência já persistida sem alterar a métrica ou o contexto medido.

## Classes canônicas de aquisição

### 1. Aquisição HTTP direta - escopo de URL

Para entrada `URL_SET`, a etapa de aquisição HTTP direta executa uma requisição semelhante à de crawler para cada URL normalizada do conjunto explícito. O resultado persiste status, cadeia de redirecionamento, cabeçalhos, corpo e tempo decorrido. Essa observação é intencionalmente distinta de uma observação feita por navegador real.

Recursos de domínio, como `robots.txt` e sitemaps elegíveis, têm escopo de origem e não são repetidos para cada página.

### 2. Snapshot de navegador - escopo URL/dispositivo

A etapa de captura em navegador executa uma navegação Chromium normal para cada contexto URL/dispositivo selecionado. A mesma navegação é reutilizada para:

- DOM renderizado;
- captura de tela;
- fingerprint do documento principal quando a resposta já armazenada puder ser lida com segurança;
- trace de navegação e metadados seguros de identidade de requisição;
- erros de console/página e diagnósticos de requisições com falha;
- observações limitadas de elementos do DOM;
- Open Web Metrics baseadas nas W3C Web Performance APIs já disponíveis no navegador;
- interação limitada de lazy loading quando exigida pela regra de conteúdo lazy;
- extração determinística e evidência semântica posteriores.

As Open Web Metrics são coletadas antes da interação diagnóstica de lazy loading, no mesmo documento já carregado, e registram `additional_navigation_requests=0` e `additional_external_api_calls=0`. Ficam habilitadas por padrão porque não usam provider pago, quota externa ou nova aquisição física. Permanecem consultivas e não alteram `SARI-001` nem `SCORE-GEO-004`.

A interação de lazy loading só ocorre quando o DOM inicial apresenta sinais lazy e o conteúdo essencial ainda não pode ser recuperado. A interação percorre a página já aberta no navegador e **não** navega novamente para a URL. A evidência primária de DOM/captura de tela é congelada antes da interação diagnóstica.

Nenhuma regra posterior, cálculo, adaptador de IA ou gerador de relatório pode reabrir a página apenas para reler esses fatos.

### Proteção de tempo total do navegador

O renderizador normal do navegador é controlado por um processo worker persistente e isolado. Contextos URL/dispositivo saudáveis reutilizam a mesma sessão worker/navegador. Um contexto completo possui limite de segurança de 60 s no chamador, além dos timeouts de operação do Playwright.

Se a renderização completa ultrapassar esse limite:

- o processo worker do navegador e seus descendentes Chromium são encerrados;
- o contexto URL/dispositivo com timeout é registrado como falha de renderização;
- a mesma URL **não** é repetida automaticamente;
- o contexto seguinte recebe um novo worker de navegador e a auditoria pode continuar.

O isolamento por processo é usado em vez de timeout por thread porque a API síncrona do Playwright tem afinidade de thread e uma thread excedida continuaria executando.

No Windows, em que multiprocessing usa `spawn`, o worker de navegador reinstala o contrato canônico de captura por dispositivo e o coletor de Open Web Metrics antes de criar o renderizador. Isso evita perda silenciosa de métricas de mesma sessão no caminho isolado de execução.

### 3. Medições independentes

Algumas métricas seriam inválidas se projetadas a partir do snapshot principal e, portanto, exigem aquisição própria.

#### PageSpeed Insights / Lighthouse

PageSpeed é um serviço externo de medição. O Google executa sua própria navegação Lighthouse para a estratégia URL/dispositivo. O RASAi permite uma chamada PageSpeed por contexto URL/dispositivo selecionado.

Política vigente:

- uma chamada PageSpeed por contexto selecionado;
- todas as categorias Lighthouse configuradas são solicitadas nessa única chamada;
- sem repetição automática por padrão;
- um limite de tempo total no chamador restringe a espera completa pelo provider;
- timeout/falha é tratado de forma fail-open e materializa observação indisponível/parcial explícita;
- a fase só ocorre depois de a evidência principal da auditoria já ter sido persistida.

Uma execução PageSpeed não é contabilizada como segundo snapshot local de navegador. Trata-se de medição externa independente necessária à proveniência Lighthouse.

#### CrUX

O acesso direto ao CrUX é uma consulta de API de dados e não navega na origem auditada. Em `field_source=auto`, o RASAi reutiliza primeiro dados de campo já retornados pelo PageSpeed e chama o CrUX direto apenas quando esses dados não existem e há cliente CrUX configurado. `field_source=crux` continua sendo escolha explícita do operador.

#### Synthetic Apdex

Synthetic Navigation Apdex e Synthetic User Experience Apdex exigem amostras independentes repetidas por definição. Um único snapshot principal não substitui uma população estatística de amostras.

Quando os dois métodos Apdex usam aquisição equivalente de URL/dispositivo/perfil, o RASAi pode compartilhar uma navegação física elegível, preservando semânticas métricas separadas. Amostras repetidas exigidas metodologicamente não são tratadas como requisições redundantes.

#### Probe de interação de lazy loading

A análise de conteúdo lazy não executa uma segunda navegação por padrão. O scroll limitado é capturado dentro do contexto de navegador já existente e persistido como metadado `bounded_lazy_probe` com `additional_navigation_requests=0`. A avaliação posterior da regra consome essa observação. Um adaptador diagnóstico separado existe apenas como hook explícito de teste/integração.

#### Recursos de crawling e descoberta

Recursos de origem, como `llms.txt`, robots e diagnósticos de sitemap, são coletados no escopo de origem/recurso, e não uma vez por página auditada. Eles não devem ser multiplicados pela quantidade de URLs, salvo quando o próprio recurso for específico da página.

## Métricas sem custo adicional na mesma sessão

A regra "sem custo fica habilitado por padrão" aplica-se somente quando a métrica pode ser obtida sem criar nova dependência externa, quota, varredura pública ou aquisição adicional do alvo.

`OPEN-WEB-METRICS-001` atende a esse requisito porque lê estado nativo do navegador no `DEVICE_SNAPSHOT` existente. Pode expor Navigation Timing, Resource Timing, presença de Server-Timing, Paint/FCP/LCP observado, CLS observado, Event Timing quando houver interação, Long Tasks, Long Animation Frames, User Timing agregado e sinais básicos de documento/plataforma.

Isso **não** autoriza execução automática de qualquer serviço gratuito disponível na internet. Validadores W3C, MDN HTTP Observatory, WebPageTest e serviços semelhantes continuam sendo integrações/providers porque criam dependência ou observação externa. Browsertime/sitespeed.io também exigem runtime/dependências próprios. Datasets de compatibilidade de navegador, como Web Platform Baseline/MDN BCD, devem ser versionados e integrados de forma reproduzível antes de se tornarem evidência padrão.

## Fase de serviços externos

Serviços externos que não pertencem à aquisição principal direta são tratados como enriquecimentos posteriores sobre o workspace persistido da auditoria.

A evidência principal pode ser concluída e persistida antes do término de PageSpeed, CrUX, IA ou outros providers opcionais. Falha de provider opcional não invalida evidência principal já persistida.

Antes da coleta externa de Web Performance, o log operacional registra um plano contendo:

- contextos selecionados;
- chamadas PageSpeed planejadas;
- quantidade de retries;
- máximo de navegações do alvo acionadas por PageSpeed;
- política de fallback do CrUX;
- indicação de reuso do snapshot principal como entrada;
- indicação de que a fase do provider é externa à coleta principal.

Antes de cada espera por provider, o log operacional registra URL, dispositivo, posição/total do contexto e timeout ativo. O console interativo usa esses eventos para apresentar progresso medido, em vez de permanecer em um percentual fixo sem unidade interna observável.

## Integração com IA e economia de tokens

A IA não deve buscar novamente o website auditado. A IA semântica recebe somente evidências persistidas pelo RASAi.

O contrato semântico mantém uma chamada estruturada de provider por snapshot para o conjunto completo de regras semânticas contratadas. Snapshots de dispositivos não são fundidos quando suas identidades de evidência diferem.

Redução de tokens só é permitida quando não remove informação semântica necessária ao modelo. A política vigente sem perda:

- mantém o conteúdo principal extraído integral;
- mantém Structured Data;
- mantém IDs de evidência e valores observados;
- remove caminhos locais `artifact_reference`, pois um provider remoto não pode resolvê-los;
- remove título/excerto duplicados da entrada semântica quando título e conteúdo principal completo já estão no nível superior;
- orienta providers a não repetir evidências, texto de regras ou schema em campos de reasoning;
- gera relatórios sem chamadas adicionais de IA.

Truncamento cego de conteúdo não é otimização padrão porque pode alterar avaliações de semântica, answerability, entidades ou claims factuais. Qualquer orçamento futuro de tokens deve preservar garantias determinísticas de cobertura e expor truncamento como limitação explícita.

## Contrato de arquivo com conjunto de URLs

Arquivos TXT fornecidos pelo usuário aceitam UTF-8 com ou sem BOM. Linhas vazias e comentários iniciados por `#` são ignorados. Toda linha significativa é validada antes da execução; um alvo inválido é informado com o número exato da linha, em vez de ser removido silenciosamente das estimativas de exposição ou do escopo da auditoria.

## Resumo da política de requisições

Para uma auditoria normal com um dispositivo selecionado e recursos externos desabilitados, as observações físicas pretendidas por página são:

1. uma aquisição HTTP direta por URL;
2. uma navegação Chromium por URL/dispositivo.

Open Web Metrics reutilizam o item 2 e não criam uma terceira observação física. Uma interação limitada de lazy loading pode gerar atividade adicional de subrecursos na **mesma** página do navegador, mas não cria uma segunda navegação. Cargas adicionais do alvo só são permitidas para medições explicitamente independentes, como PageSpeed/Lighthouse e Synthetic Apdex. IA, scoring, geração de relatório, comparação e demais lógicas posteriores devem reutilizar evidência persistida.
