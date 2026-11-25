# RASAi - Auditor de prontidão para busca e IA

O **RASAi (Readiness Assessment for Search & AI)** avalia a prontidão técnica e semântica de sites para mecanismos de busca e sistemas de inteligência artificial. Reúne evidências, mede indicadores e apresenta recomendações para orientar melhorias. Não garante posições em buscas, tráfego, conversões ou citações por IA.

A auditoria pode avaliar descoberta de páginas, conteúdo, dados estruturados, inteligência de busca (SERP e GEO), desempenho, acessibilidade, conectividade e segurança passiva. Integrações externas e análises por IA dependem de configuração e disponibilidade.

O **Índice de Prontidão Search & IA (SARI)** é o índice público da metodologia própria de avaliação do RASAi. Sua leitura combina a qualidade do universo medido (score de 0 a 100), cobertura, confiança, consolidação e critérios críticos de prontidão. Não mede popularidade nem representa probabilidade de ranqueamento ou citação por IA. Consulte a [metodologia do índice](docs/SARI_READINESS_INDEX.md).

**Release estável publicada:** [v1.0.0](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v1.0.0). Consulte a [GitHub Release mais recente](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/latest) para verificar novas versões; a branch `main` pode conter evoluções posteriores à publicação.  
**Pacote Python (versão no código-fonte):** `1.0.0`; a versão no código-fonte não comprova publicação. Consulte as [notas da v1.0.0](docs/RELEASE_NOTES_V1_0_0.md).

## Primeiros passos no Windows

1. Obtenha o código da [versão 1.0.0](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v1.0.0) ou de outra [versão publicada](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases).
2. Extraia os arquivos em uma pasta local e abra `abrir-rasai-console.cmd` por duplo clique ou pelo Prompt de Comando (CMD), na raiz do projeto:

   ```cmd
   abrir-rasai-console.cmd
   ```

3. O inicializador verifica Python 3.13, prepara o ambiente virtual e instala as dependências e o Chromium quando necessário. O primeiro acesso pode exigir internet e permissão de instalação.
4. No console, escolha **Preparar auditoria**, informe a URL, selecione o dispositivo e as avaliações desejadas, revise as integrações e os custos e execute.

Veja o [guia do usuário](docs/USER_GUIDE.md) e as [instruções de instalação](docs/INSTALLATION.md) para detalhes.

## Executar diretamente por comando

Na raiz do projeto, depois de preparar o ambiente, execute pelo CMD:

```cmd
.venv\Scripts\rasai.exe --version
.venv\Scripts\rasai.exe audit --help
.venv\Scripts\rasai.exe audit https://example.com --max-pages 1 --device-context mobile --ai-provider none
```

No PowerShell, use:

```powershell
& .\.venv\Scripts\rasai.exe audit https://example.com --max-pages 1 --device-context mobile --ai-provider none
```

Substitua a URL pelo site autorizado. Use `desktop` para uma avaliação de computador. Cada auditoria começa com uma URL e um contexto de dispositivo. O exemplo desabilita IA, mas não desabilita por si só todas as integrações externas; revise as preferências e variáveis de ambiente antes de executar. A descoberta externa do IP público é habilitada por padrão.

O console também permite gerar comandos para CMD ou PowerShell pela opção **Ver linha de comando**. Confira os parâmetros antes de reutilizá-los; nem toda ação interativa está representada pelo comando planejado. Consulte [referência de comandos](docs/CLI_REFERENCE.md) e [execução externa e agendamento](docs/EXECUTION_SCHEDULING.md).

## Onde consultar os resultados

Na pasta `audits/AUD-…/`:

- `report-presentation/index.html`: leitura executiva em 11 páginas temáticas, do diagnóstico ao plano de ação e custos.
- `report-catalog/index.html`: catálogo técnico em 21 páginas, com diagnósticos especializados, métricas, regras e evidências rastreáveis.
- `audit.db` e artefatos: fonte persistida da auditoria; preserve esses arquivos.

O catálogo técnico e a apresentação executiva são gerados independentemente, a partir das evidências persistidas, com finalidades complementares.

O **Relatório Consolidado Longitudinal (CONS-5)**, em `CONS-*/report.html`, compara auditorias elegíveis da mesma URL e dispositivo ao longo do tempo, respeitando a comparabilidade metodológica e de universo. Não executa nova coleta nem recalcula scores. Consulte o [guia de consolidação](docs/CONSOLIDATED_REPORTING.md).

No console, o histórico permite acessar os relatórios. Consulte o [guia de relatórios](docs/REPORT_GUIDE.md) e a [regeneração offline de relatórios](docs/REPORT_REMATERIALIZATION.md).

**Segurança:** não compartilhe o banco, os artefatos ou o ZIP técnico integral sem revisar o conteúdo e a autorização de divulgação. Configure credenciais pelo ambiente do sistema operacional, não em comandos ou arquivos compartilhados. Integrações externas podem transmitir dados e gerar custos.

## Documentação

- [Instalação e dependências](docs/INSTALLATION.md)
- [Configuração e integrações](docs/CONFIGURATION.md)
- [Índice de prontidão](docs/SARI_READINESS_INDEX.md) e [metodologia de pontuação](docs/SCORE_GEO.md)
- [Segurança de credenciais](docs/SECRET_AND_CONFIGURATION_SAFETY.md) e [dados e artefatos](docs/OUTPUTS_AND_ARTIFACTS.md)
- [Documentação completa](docs/README.md)
- [Avaliação arquitetural futura](docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md): decisão de manter pendente, registrada na [issue #1](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/1); não é capacidade disponível.

## Licenciamento

O código próprio do RASAi nesta revisão é disponibilizado sob a [PolyForm Noncommercial License 1.0.0](LICENSE.md) (`PolyForm-Noncommercial-1.0.0`), no modelo de código-fonte disponível (*Source Available*), não *Open Source*.

A utilização, modificação e redistribuição seguem as permissões e condições da licença, inclusive as permissões específicas para organizações nela previstas. Usos comerciais não abrangidos por essas permissões dependem de autorização separada do titular. Dependências e componentes de terceiros permanecem sujeitos às respectivas licenças.

O texto oficial em inglês no arquivo `LICENSE.md` prevalece sobre este resumo. Esta declaração refere-se à revisão atual do repositório e não altera os artefatos das releases anteriormente publicadas.
