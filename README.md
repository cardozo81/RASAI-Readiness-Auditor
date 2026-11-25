# RASAi - Search & AI Readiness Auditor

**RASAi** (Readiness Assessment for Search & AI) avalia a prontidão técnica e semântica de sites para mecanismos de busca e sistemas de IA. Combina coleta de evidências, avaliação reproduzível, relatórios HTML e recomendações rastreáveis. Não promete ranking, tráfego, conversões ou citações em respostas generativas.

**Pacote Python (última release publicada):** consulte a [GitHub Release mais recente](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/latest).  
**Pacote Python (versão no código-fonte):** `1.0.0`; a versão do código-fonte não comprova publicação. Consulte as [notas da v1.0.0](docs/RELEASE_NOTES_V1_0_0.md).
**Índice público:** `SARI-001` (Search & AI Readiness Index)  
**Método de pontuação:** versão pública `001`; contrato atual `SCORE-GEO-005`. Auditorias históricas preservam `SCORE-GEO-004`.

## Capacidades principais

- **Auditoria por URL:** aquisição HTTP/DOM, descoberta e rastreamento, semântica, dados estruturados, sinais Search e segurança passiva, com evidências persistidas.
- **Prontidão e recomendações:** SARI, cobertura e confiança separados, findings e remediações apoiadas nas evidências. Scores não são recalculados a partir de textos gerados por IA.
- **Experiência e qualidade Web:** Lighthouse/PageSpeed, CrUX, acessibilidade automatizada, padrões Web e Apdex sintético, quando habilitados ou disponíveis.
- **Search & AI Intelligence:** visibilidade observada, SERP, integrações Perplexity e interpretações por IA opcionais, com proveniência, limites de confiança e controle de custos.
- **Análise pós-auditoria:** reprocessamento seletivo, reanálise consultiva offline, verificação de correções, monitoramento e comparação longitudinal por `CONS-*`.
- **Operação:** console Windows, CLI, persistência SQLite local e recursos de plataforma/API para uso em arquitetura hospedada.

Cada auditoria pública recebe **uma URL de entrada e um contexto de dispositivo** (`mobile` ou `desktop`). Comparações entre dispositivos exigem execuções separadas.

## Requisitos e instalação

- **Python:** CPython `>=3.13,<3.14`.
- **Plataforma:** Windows para console e operação local; Linux para componentes hospedados e serviços.
- **Browser:** Chromium via Playwright quando a funcionalidade exigir navegação renderizada.

No Windows, a opção de abertura assistida é:

```cmd
abrir-rasai-console.cmd
```

Instalação manual para desenvolvimento ou execução CLI:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
rasai --version
```

Consulte [Instalação](docs/INSTALLATION.md), [Compatibilidade](docs/COMPATIBILITY.md) e [Configuração](docs/CONFIGURATION.md) antes de habilitar integrações externas.

## Primeiro uso

Uma auditoria básica pode ser iniciada **sem IA**:

```powershell
rasai audit https://example.com --device-context mobile --ai-provider none
```

Para escolher outro dispositivo, use `--device-context desktop`. O console oferece fluxo interativo de configuração, autorização de etapas e acompanhamento de custos.

A CLI documenta os demais comandos e parâmetros: [Referência CLI](docs/CLI_REFERENCE.md). Os exemplos `powershell` acima são **chamadas diretas à CLI**; já a ação `M. Ver linha de comando` do console gera atualmente um bloco Windows para **`cmd.exe`/`.cmd`**, não um script PowerShell. A fidelidade de argumentos com metacaracteres ainda é tratada na [issue #713](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/713); consulte [execução externa e agendamento](docs/EXECUTION_SCHEDULING.md).

## Resultados e integridade

| Saída | Localização / finalidade |
| --- | --- |
| Auditoria `AUD-*` | `audits/AUD-*/audit.db` + artefatos originais da execução |
| Relatório individual | `audits/AUD-*/report-catalog/index.html` e páginas temáticas CAT-01 a CAT-10 |
| Relatório de apresentação | `audits/AUD-*/report-presentation/index.html`, visão executiva derivada; `A` no console abre a apresentação e `I` mantém o catálogo técnico |
| Consolidação `CONS-*` | `audits/consolidated/CONS-*/report.html`, comparação longitudinal separada |
| Reanálise consultiva pós-AUD | `audits/.rasai-ai-reanalyses/AUD-*/`, pacotes derivados independentes |

O `audit.db` e seus artefatos são a fonte de evidência. Relatórios são projeções, não realizam coleta durante a renderização e não devem substituir medições indisponíveis por resultados estimados. Os estados `N/D`, parcial e não comparável são preservados quando aplicáveis.

### Rede e conectividade: origem, topologia e inventário de IPs

A coleta de rede diferencia a **captura passiva do navegador** da **sonda complementar autorizada**. O endereço local obtido pelo socket da sonda (quando comprovado) é o ponto inicial **lógico do processo executor**, não o IP público de saída nem, necessariamente, a origem da conexão do navegador. O IP público de saída permanece **não identificado** sem medição externa específica e autorizada; não é inferido por DNS, traceroute, GeoIP ou IP do destino.

- `report-catalog/network.html` e `report-presentation/rede.html` exibem a topologia lógica observada e o inventário de IPs com papéis distintos: origem local da sonda, peer remoto da captura, peer TCP da sonda, candidatos DNS (não equivalentes a conexões) e saltos públicos efetivamente registrados.
- O traceroute mostra a ordem dos saltos e os estados de ausência/ocultação; **não comprova** continuidade física da rota nem que o destino respondeu. Saltos privados/reservados são ocultados e endereços não observados não são inventados.
- O mapa geográfico usa somente coordenadas GeoIP persistidas e qualificadas como **aproximadas**. Um IP privado, um candidato DNS ou um endereço sem coordenadas verificadas não cria marcador geográfico.

**Descoberta externa de IP público (IPv4/IPv6) - habilitada por padrão:** depois de cada nova AUD, o processo executor consulta serviços HTTPS gratuitos para identificar o endereço público observado em suas próprias requisições. **Isso independe da autorização de sondagem TCP/TLS do domínio auditado.** No menu **Preparar auditoria > Rede e conectividade**, a opção **6. Habilitar/desabilitar descoberta externa do IP público** permite desligar essa etapa para a sessão ou salvar a preferência no `rasai-console.ini`. As opções **7. API ipify** e **8. API ident.me** permitem desativar individualmente cada fornecedor, com preferência persistida no `rasai-console.ini`. A primeira consulta usa [ipify](https://www.ipify.org/) e, somente em falha, [ident.me](https://api.ident.me/). Desabilitar ambas as APIs, ou desligar a opção geral, interrompe somente a descoberta externa, preservando DNS/TCP/TLS/traceroute e demais evidências. Essa escolha é válida na sessão e pode ser salva no INI. Os controles correspondem a `RASAI_NETWORK_EGRESS_ENABLED`, `RASAI_NETWORK_EGRESS_IPIFY_ENABLED` e `RASAI_NETWORK_EGRESS_IDENTME_ENABLED` (booleanos `true/false`).

O coletor complementar pós-AUD executa a consulta independente em processo isolado e realiza somente conexões **HTTPS diretas** a endereços fixos dos fornecedores, sem usar proxies de ambiente e sem enviar URLs auditadas, credenciais ou tokens. O serviço pode observar o IP e metadados de transporte da consulta; a política de privacidade é de cada fornecedor. São realizadas no máximo quatro consultas (IPv4/IPv6, primário/fallback), com limite de 2 segundos por tentativa e orçamento máximo de 10 segundos para o subprocesso isolado. Uma falha nunca bloqueia a AUD. Cada resultado é evidência da solicitação de eco externa, **não** comprova a origem da navegação do Chromium ou da conexão TCP ao destino. Se uma família não puder ser identificada, o catálogo e a apresentação registram o motivo resumido e preservam a auditoria original. O GeoIP local é reutilizado apenas quando há endereço público válido e base disponível. A regeneração dos relatórios permanece 100% offline.

**Regenerar relatórios históricos sem nova auditoria:** usar o entrypoint canônico para gerar um catálogo em **cópia externa**, seguido do gerador da apresentação sobre essa cópia. No PowerShell, dentro do checkout atualizado (com a `.venv` instalada):

```powershell
$AuditId = "AUD-EXEMPLO"
$Fonte = Join-Path (Get-Location) "audits\$AuditId"
$Saida = Join-Path $env:TEMP ("RASAI-REGEN-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
& .\.venv\Scripts\python.exe -B -m rasai rematerialize-report --audit-dir $Fonte --output-root $Saida
if ($LASTEXITCODE -ne 0) { throw "Falha na regeneracao do catalogo" }
$Copia = Join-Path $Saida $AuditId
& .\.venv\Scripts\python.exe -B -m rasai.parallel_report --audit-dir $Copia
if ($LASTEXITCODE -ne 0) { throw "Falha na regeneracao da apresentacao" }
```

A AUD original, seu `audit.db`, os sidecars, os custos e as pontuações não devem ser reescritos. Não executar com escritor ativo ou sem a integridade necessária; o gerador pode recusar a cópia. Saídas anteriores e novas devem ser comparadas como **projeções de versões diferentes**, não como novas evidências. Referências: [rematerialização isolada](docs/REPORT_REMATERIALIZATION.md) e [apresentação offline](src/rasai/parallel_report/README.md).

**Distribuição externa:** o ZIP canônico do `report-catalog` pode conter `integrity/audit-snapshot.db` e evidências restritas. **Não distribua esse pacote integral externamente** enquanto não houver um exportador público verificado; a separação está acompanhada na [issue #717](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/717).

**Reanálise offline de AUD encerrada**, sem chamar provedores nem alterar a auditoria original:

```powershell
rasai ai-reanalysis .\audits\AUD-EXEMPLO
rasai ai-reanalysis .\audits\AUD-EXEMPLO --write-local-replay
```

A nova inferência GEO paga e as novas pesquisas externas dependem de autorização específica; o replay local não as executa. Leia [GEO multiquery e reanálise pós-AUD](docs/GEO_AI_MULTIQUERY_AND_REANALYSIS.md) e [Saídas e artefatos](docs/OUTPUTS_AND_ARTIFACTS.md).

## IA, custos e limites metodológicos

A IA é **opcional**: o núcleo de auditoria funciona com `--ai-provider none`. Provedores e serviços externos dependem de configuração, elegibilidade, disponibilidade e, quando aplicável, consentimento de custo. A ausência de dados de IA ou de integrações não deve ser apresentada como aprovação nem como falha fictícia.

- `SARI-001` é o **índice de prontidão**, não um indicador de tráfego, visibilidade observada ou ranking.
- `SCORE-GEO-005` é o contrato de scoring para novas auditorias; `SCORE-GEO-004` permanece válido no replay histórico. Comparações incompatíveis não são convertidas silenciosamente.
- PageSpeed, CrUX, acessibilidade, Apdex, observabilidade e fontes de IA pertencem a metodologias distintas e mantêm seus limites.
- Interpretações por IA são consultivas e ligadas a evidências. Custos são estimados apenas quando há regra aplicável; provedores não são acionados implicitamente em replays offline.

Consulte [SARI](docs/SARI_READINESS_INDEX.md), [Scoring](docs/SCORE_GEO.md), [Guia de IA](docs/AI_GUIDE.md) e [Custos/uso de IA](docs/CONSOLE_COST_AND_USAGE.md).

## Documentação

A [documentação completa](docs/README.md) centraliza contratos e guias especializados. Páginas de referência:

- [Instalação e operação](docs/INSTALLATION.md) · [Referência CLI](docs/CLI_REFERENCE.md) · [Configuração](docs/CONFIGURATION.md)
- [Relatórios e catálogos](docs/CATALOG_AND_REPORT_SURFACES.md) · [Guia de relatórios](docs/REPORT_GUIDE.md)
- [Consolidação longitudinal](docs/CONSOLIDATED_REPORTING.md) · [Verificação de correções](docs/REPORT_GUIDE.md)
- [Monitoramento e observabilidade](docs/MONITORING_OBSERVABILITY.md) · [Plataforma](docs/PRODUCT_PLATFORM_ARCHITECTURE.md)
- [Versionamento](docs/VERSIONING.md) · [Notas v1.0.0](docs/RELEASE_NOTES_V1_0_0.md) · [Notas v0.10.0](docs/RELEASE_NOTES_V0_10_0.md) · [Notas v0.9.2](docs/RELEASE_NOTES_V0_9_2.md)
- [Pesquisa futura sobre runner SaaS](docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md) - proposta não implementada, rastreada na **Issue #1**.

## Segurança e responsabilidade

Coletas de rede ativas, integrações pagas, modelos externos e processamento de dados sensíveis requerem consentimento e configuração próprios. Não inclua credenciais em artefatos ou relatórios. Mantenha backups de auditorias persistidas antes de atualizar o runtime. Os relatórios distinguem evidência efetivamente observada, inferência e informação indisponível.

<!-- rasai-doc-index-20260908 -->
