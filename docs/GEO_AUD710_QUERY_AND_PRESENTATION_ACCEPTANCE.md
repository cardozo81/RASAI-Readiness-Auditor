# AUD-71091931EC2747518B9A8CCD7E76055A - diagnóstico GEO e decisões

Origem: AUD física 25/10/2026, alvo www.nytimes.com. Ações aqui não alteram a AUD selada, seu SQLite ou seus relatórios já publicados. Somente novas gerações de relatório refletem ajustes de apresentação.

## Evidências observadas, sem confundir universos

- SERP Google/SerpApi: consulta `alaska`, `OBSERVED_API`, 7 resultados orgânicos, 20 solicitados; coleta não confirmou a profundidade 20 e persiste `SERP_REQUESTED_DEPTH_INCOMPLETE`.
- Perplexity Search API FAST: consulta `seguro para família`, 1 request, HTTP 200, SUCCESS; 10/10 fontes normalizadas no `perplexity_search_sources`, com títulos, snippets e datas quando fornecidas.
- GEO persistido: `NO_EQUIVALENT_OBSERVED_SERP_QUERY`, `serp_observation_id=NULL`. Sem taxa de sobreposição. Este é o resultado metodologicamente correto; não deve virar score negativo ou alegação de erro do provider.
- Mesmo quando a string de consulta é igual, mercado, idioma, dispositivo, instante e pertinência temática ao alvo não ficam comprovados. Requests Search API com várias consultas não permitem atribuir cada fonte individualmente à consulta.
- Core da AUD concluído com limitações técnicas de sitemap/externos; fulfillment terminou com 15/15 requisitos. Não confundir COMPLETE com cobertura integral de API.
- Custo previsto USD 0.029577, observado USD 0.073825 (+149.61%), com alerta crítico já materializado. Diferença é real, mas atribuição causal e calibragem do forecast não são comprovadas apenas pela AUD. Esse tema requer análise específica de regras de preço, universo de forecast e tentativas; não criar ajuste arbitrário sem evidência.
- O log pós-finalização exibiu `EM EXECUÇÃO` quando `LOCAL:OPEN_REPORT`, com 100% e status final. Problema de projeção visual, não evidência de retomada de core.

## Implementação sem mexer nos motores

1. A projeção consultiva única `geo_configuration_view` alimenta CAT-05, editor e preparação com dois estados independentes: readiness técnico preservado e comparabilidade/contexto não comprovados.
2. A fronteira de lançamento solicita confirmação **informativa** quando duas consultas explicitamente configuradas (ou rascunho com oferta de execução) são divergentes ou múltiplas e inatribuíveis. O operador pode aceitar pesquisas independentes, omitir só Perplexity nesta AUD ou retornar para editar. Isso NÃO substitui o consentimento financeiro.
3. O HTML GEO mostra fontes da execução corrente verificável, links HTTP(S) seguros, datas fornecidas e sinalização de trecho abreviado; resultados históricos continuam no banco sem serem apresentados como sucesso atual.
4. O progresso mantém status terminal durante abertura de relatório/pasta, somente com 100% medido + estado físico terminal.
5. Regressões offline garantem não alteração de bytes do SQLite, sanitização, escopo de runs, preservação de configuração e ausência de requests cobrados.

## Issue #657

`#657` permanece ABERTA e **fora deste macrolote GEO**. A especificação é de observabilidade de arquitetura e prévia fora da AUD (fases A/B/C), não é redundante com comparação SERP/Perplexity. O próprio critério prevê executar após estabilização GEO. Nada no ZIP prova que foram implementados preview opt-in, inventário CSS/JS/subframes e topologia observada materializada; não fechar #657 sem entrega funcional e validação focal independente. Não exige smoke pago para começar fase A; exige primeiro estabilidade do contrato GEO e atenção aos gates de segurança descritos na issue.
