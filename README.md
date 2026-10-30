# RASAi - Search & AI Readiness Auditor

**RASAi** (Readiness Assessment for Search & AI) avalia a prontidão técnica e semântica de sites para mecanismos de busca e sistemas de IA. Combina coleta de evidências, avaliação reproduzível, relatórios HTML e recomendações rastreáveis. Não promete ranking, tráfego, conversões ou citações em respostas generativas.

**Pacote Python (última release publicada):** [consultar no GitHub](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/latest)  
**Pacote Python (versão no código-fonte):** `0.9.2` - [notas de distribuição](docs/RELEASE_NOTES_V0_9_2.md). O código não comprova publicação: verifique a tag/release no GitHub.  
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

A CLI documenta os demais comandos e parâmetros: [Referência CLI](docs/CLI_REFERENCE.md).

## Resultados e integridade

| Saída | Localização / finalidade |
| --- | --- |
| Auditoria `AUD-*` | `audits/AUD-*/audit.db` + artefatos originais da execução |
| Relatório individual | `audits/AUD-*/report-catalog/index.html` e páginas temáticas CAT-01 a CAT-10 |
| Consolidação `CONS-*` | `audits/consolidated/CONS-*/report.html`, comparação longitudinal separada |
| Reanálise consultiva pós-AUD | `audits/.rasai-ai-reanalyses/AUD-*/`, pacotes derivados independentes |

O `audit.db` e seus artefatos são a fonte de evidência. Relatórios são projeções, não realizam coleta durante a renderização e não devem substituir medições indisponíveis por resultados estimados. Os estados `N/D`, parcial e não comparável são preservados quando aplicáveis.

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
- [Versionamento](docs/VERSIONING.md) · [Notas v0.9.2](docs/RELEASE_NOTES_V0_9_2.md)
- [Pesquisa futura sobre runner SaaS](docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md) - proposta não implementada, rastreada na **Issue #1**.

## Segurança e responsabilidade

Coletas de rede ativas, integrações pagas, modelos externos e processamento de dados sensíveis requerem consentimento e configuração próprios. Não inclua credenciais em artefatos ou relatórios. Mantenha backups de auditorias persistidas antes de atualizar o runtime. Os relatórios distinguem evidência efetivamente observada, inferência e informação indisponível.

<!-- rasai-doc-index-20260908 -->
