# Guia do usuário

Guia operacional do RASAi - Search & AI Readiness Auditor para execução local, configuração do console e leitura dos resultados.

## Instalação local

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

## Abrir o console

```powershell
rasai-console
```

Menu principal:

```text
1. Preparar auditoria
2. Auditorias / histórico
3. Relatórios consolidados
4. Inteligência Artificial
5. Integrações e serviços
6. Todas as configurações
7. Sistema / restaurar padrões
H. Ajuda
Q. Sair
```

## Fluxo recomendado

1. abra **Preparar auditoria**;
2. selecione um perfil quando uma URL única permitir e o preset for útil;
3. informe entrada, projeto, `Device`, idioma/mercado e timezone;
4. revise as análises/resultados que pretende obter;
5. resolva itens `CONFIGURAR` usando as dependências mostradas na própria capacidade;
6. configure IA, integrações e credenciais quando forem necessárias;
7. revise custo, quota e carga de recursos opcionais;
8. salve a configuração se quiser reutilizar os parâmetros não sensíveis;
9. execute somente quando o preflight estiver compatível com a configuração desejada;
10. leia o relatório e diferencie resultado obtido de capacidade não solicitada, parcial ou indisponível.

## Preparar auditoria

A tela usa a seguinte estrutura:

```text
PERFIL DA PRÓXIMA AUDITORIA
ESCOPO
ANÁLISES / RESULTADOS
RESULTADOS SISTÊMICOS
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

### Escopo

Os campos básicos têm IDs reservados:

```text
000002 Entrada
000003 Projeto
000004 Device
000005 Idioma / mercado
000006 Timezone apresentação
```

`Device` pode ser `mobile`, `desktop` ou `both`.

Os relatórios Mobile/Desktop são derivados desse valor e aparecem como `INCLUÍDO` ou `NÃO APLICÁVEL`; não são checkboxes separados.

### Análises/resultados

O catálogo inclui:

- Domínio e descoberta;
- Acessibilidade;
- Web Performance;
- Métricas e padrões;
- Search Intelligence / SERP;
- Google Search Console;
- Apdex de navegação;
- Apdex de experiência;
- Visibilidade em IA;
- Search & AI observados;
- Análise profunda e melhorias;
- Conteúdo e JSON-LD;
- Remediações;
- Quality & decisão.

Ao abrir uma capacidade, o console mostra estado, finalidade, parâmetros próprios e dependências relacionadas. Selecionar o ID de uma dependência abre a configuração canônica correspondente.

`H. Ajuda de contexto` explica a própria capacidade e suas configurações relacionadas; não é necessário pressionar `H` antes de digitar um ID. Dentro da ajuda também é possível abrir um dos IDs mostrados. `ENTER` ou `V` retorna sem gerar erro.

### Conteúdo e JSON-LD

Essa capacidade separa o que é determinístico do que é contexto/enriquecimento opcional:

```text
Conteúdo / estrutura   INCLUÍDO
JSON-LD                INCLUÍDO
Contexto editorial     AUTOMÁTICO / PERSONALIZADO / CONFIGURAR
Remediação por IA      NÃO SOLICITADA / APTO / CONFIGURAR
```

Valores editoriais `auto` são válidos e não representam pendência. A orientação JSON-LD determinística não depende de a remediação textual por IA estar habilitada.

As variáveis relacionadas aparecem agrupadas em **Contexto editorial** e **Enriquecimento por IA**. A linguagem de análise continua sendo uma configuração compartilhada/global de IA.

### Resultados sistêmicos

Visão geral, Readiness SARI, metodologia de scoring, contexto de captura, uso de IA e referências/metodologia pertencem ao contrato do relatório e não têm seleção independente.

## IDs e números de menu

O console usa duas classes de números:

- números curtos: escolhas da tela atual;
- IDs de 6 dígitos: identidade estável de uma configuração canônica.

O mesmo ID de variável aparece em Inteligência Artificial, Integrações, Todas as configurações ou em uma tela de capacidade quando essa dependência é relevante.

O formato de 6 dígitos reduz o ruído visual do formato anterior. O RASAi não usa apenas 4 dígitos porque o espaço de identificação seria pequeno demais para manter o contrato de identidade estável com baixo risco de colisão conforme novas variáveis forem adicionadas.

## Inteligência Artificial

Existe uma única seleção principal de IA por execução.

Opções conceituais:

```text
none       -> sem IA quando nenhuma capacidade exigir
provider   -> provider explicitamente selecionado
auto       -> orquestração canônica entre providers elegíveis
```

`AUTO` considera a política existente de custo, elegibilidade, disponibilidade, quarentena, circuit breaker, fallback e limite de tentativas.

Módulos consumidores não criam provider próprio. Improvement Intelligence, remediações e demais capacidades compatíveis reutilizam a seleção principal.

Credenciais e parâmetros do provider são configurados na macro **Inteligência Artificial** ou no catálogo técnico.

## Integrações e serviços

Use essa superfície para Google Search Console, SERP, PageSpeed/Lighthouse, CrUX, observabilidade e outros serviços externos publicados no catálogo.

Filtros disponíveis incluem owner funcional, ordem alfabética, estado, modificadas, pendentes e busca por ID/nome/finalidade.

`D. Diagnóstico técnico das integrações` executa probes consultivos de baixo impacto e não substitui a execução real da auditoria.

## Todas as configurações

Essa tela é a visão completa do catálogo técnico.

Cada variável mostra:

- finalidade;
- owner e contexto;
- quando é necessária;
- impacto;
- valor e origem;
- estado;
- tipo e domínio aceito;
- default;
- referências/documentação;
- ações de edição/restauração.

Campos enum/boolean/lista fechada são guiados. Ao escolher `S. Definir / alterar`, o console exibe as opções permitidas para seleção e solicita confirmação antes de aplicá-las. Quando um valor técnico não é autoexplicativo, como categorias YMYL, a opção mantém o texto canônico e recebe uma descrição curta em PT-BR. Listas fechadas permitem selecionar vários valores. Texto livre é usado apenas em domínios realmente abertos.

Um toggle booleano deve aparecer como booleano na UI. Por exemplo, `RASAI_GSC_ENABLED` usa seleção `true|false`; o console não deve apresentar texto livre para um domínio que o runtime valida como fechado.

## Origem dos valores

O console pode indicar:

```text
SESSÃO
ARQUIVO
WINDOWS/USER
WINDOWS/MACHINE
DEFAULT
NÃO CONFIGURADO
```

Isso ajuda a identificar por que um valor efetivo está ativo.

## Salvar configuração

`S. Salvar configuração` grava parâmetros não sensíveis no `rasai-console.ini`.

Também podem ser persistidos inputs não sensíveis da próxima execução, como os parâmetros de Search Intelligence configurados na sessão.

Secrets nunca entram no arquivo.

## Search Intelligence / SERP

Search Intelligence / SERP separa:

- termos, depth, região, device e classificação competitiva;
- provider/mode/limites SERP;
- credencial do provider.

Os inputs ficam em memória durante a sessão. Ao salvar explicitamente a configuração, são gravados no INI para reutilização local.

Search utiliza seu próprio device `mobile|desktop`, independente do `Device` geral da auditoria.

A profundidade significa a maior posição orgânica que será tentada, por exemplo `10 = Top 10` e `20 = Top 20`.

A preparação distingue intenção de configuração:

```text
SERP configurado + nenhum termo -> NÃO SOLICITADO
RASAI_SERP_MODE=disabled        -> DESABILITADO
termos + configuração válida    -> APTO
termos + dependência inválida   -> CONFIGURAR
```

Google Search Console não é dependência desta capacidade.

Consulte [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md).

## Google Search Console

Google Search Console possui capacidade própria em **Preparar auditoria**. OAuth, property e cobertura da URL são avaliados separadamente de SERP.

Estados comuns na preparação:

```text
APTO            -> OAuth/property suficientes e property cobre a URL
NÃO CONFIGURADO -> modo automático/opcional sem configuração suficiente
NÃO APLICÁVEL   -> property não cobre a URL em modo automático
DESABILITADO    -> GSC explicitamente desligado
CONFIGURAR      -> configuração inválida/incompleta ou requisito obrigatório não atendido
```

Mesmo quando a UI mostra `APTO`, validade/expiração do OAuth, scope, permissão da conta, quota e disponibilidade do Google só são confirmados pela chamada real.

Consulte [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md).

## Perfis

Perfis ficam no topo de **Preparar auditoria** e são presets da próxima execução.

Um perfil `CONFIGURAR` permanece visível, explica o que falta e não pode ser aplicado até atender às dependências obrigatórias.

Ajustes explícitos feitos depois de aplicar um perfil vencem o preset somente no domínio alterado.

O perfil não cria credenciais, termos SERP, contexto editorial específico nem provider de IA alternativo.

Consulte [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md).

## Web Performance

Quando solicitado, Web Performance usa os adapters e contratos atuais de PageSpeed/Lighthouse/CrUX.

A ausência de artifact ou resposta externa deve aparecer como limitação/indisponibilidade; não é convertida em score artificial.

Na CLI:

```powershell
rasai audit https://example.com --web-performance
```

## Apdex de navegação

Apdex de navegação executa amostras sintéticas de browser conforme os parâmetros configurados.

Exemplo CLI:

```powershell
rasai audit https://example.com `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-concurrency 1
```

Grupos pequenos permanecem diagnóstico de amostra limitada segundo o contrato Apdex.

## Apdex de experiência

Experience Apdex depende de Navigation Apdex.

Enquanto o mix estiver herdado:

```text
Device=mobile   -> 100% mobile
Device=desktop  -> 100% desktop
Device=both     -> 60% mobile + 40% desktop
Tablet          -> 0% no default herdado
```

Tablet pode ser incluído somente por override avançado do mix.

Editar amostras ou outros parâmetros não transforma o mix herdado em personalizado; somente alterar o próprio mix faz isso.

## Auditorias e histórico

A listagem recente usa colunas com `AUDITORIA`, `CONCLUSÃO LOCAL`, `SITUAÇÃO` e `REPROCESSAMENTO`.

`CONCLUSÃO LOCAL` usa o timezone configurado no programa. Auditorias ainda parciais não recebem um timestamp de conclusão artificial.

O console apresenta estados do fulfillment em PT-BR. Exemplos:

```text
COMPLETE              -> Concluída
PARTIAL_RETRYABLE     -> Parcial - pode reprocessar
PARTIAL_BLOCKED       -> Parcial - há bloqueios
FAILED_FATAL          -> Falha definitiva
EXPIRED_FOR_COMPLETION -> Expirada para conclusão
```

A coluna técnica separada `relatório=PRELIMINARY|FINAL` não é necessária na lista quando apenas repete o estado operacional já exibido.

Ao selecionar um `AUD-*`, a tela detalhada apresenta situação, conclusão local quando aplicável, score, elegibilidade para consolidação, requisitos e reprocessamentos.

Ações principais:

```text
Reprocessar somente pendências recuperáveis
Carregar configuração para uma nova auditoria
Mostrar caminhos de artefatos
```

Auditorias concluídas não oferecem reprocessamento porque já atingiram o objetivo e não possuem pendências a recuperar. O reprocessamento preserva itens já bem-sucedidos por padrão. Carregar configuração cria uma nova execução quando o usuário efetivamente executar; o AUD de origem não é alterado.

Ao escolher `I. Informar Audit ID`, digitar `V` cancela a entrada e retorna à listagem sem mensagem de Audit ID inválido.

`GERENCIAR AUDITORIAS / EXCLUSÃO SEGURA` usa estrutura tabular equivalente à do histórico, acrescentando seleção, tamanho e domínio. Os cabeçalhos são dimensionados com base no tamanho real do Audit ID para permanecer alinhados.

Credenciais não são copiadas do AUD.

## Relatórios consolidados

A consolidação usa auditorias persistidas e elegíveis. Montar a visão consolidada não deve iniciar coletas externas apenas para preencher a página histórica.

## Como ler o relatório

Comece por:

```text
AUD-*/report/index.html
```

Leia separadamente:

- Readiness/SARI;
- Score GEO;
- Coverage;
- Confidence;
- findings e recomendações;
- Web Performance;
- Acessibilidade;
- Apdex;
- Search Intelligence;
- Uso de IA;
- configuração solicitada versus resultado realmente obtido.

Estados como não solicitado, não configurado, desabilitado, não aplicável, parcial, falho ou indisponível devem ser interpretados de forma distinta de resultado bem-sucedido.

## Uso de IA no relatório

`ai-usage.html` registra provider/modelo, tentativas, tokens e custo estimado quando essas informações existem.

Custo é estimativa operacional; billing do fornecedor permanece a autoridade financeira externa.

## CLI básica

```powershell
rasai audit https://example.com --project "Exemplo"
rasai audit https://example.com --device-context desktop
rasai audit https://example.com --device-context both
```

Várias URLs:

```powershell
rasai audit `
  https://example.com/ `
  https://example.com/produto `
  --max-pages 2
```

## Segurança

- não copie API keys para issues, reports ou documentação;
- o INI não contém secrets;
- Windows/User só é alterado por ação explícita;
- Windows/Machine não é administrado automaticamente;
- key configurada não garante quota/saldo;
- Synthetic Apdex deve respeitar autorização e limites de carga;
- diagnóstico de integração é uma observação pontual, não garantia futura.

## Documentos relacionados

- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md)
- [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md)
- [INTEGRATION_DIAGNOSTICS.md](INTEGRATION_DIAGNOSTICS.md)
- [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md)
- [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md)
- [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md)
