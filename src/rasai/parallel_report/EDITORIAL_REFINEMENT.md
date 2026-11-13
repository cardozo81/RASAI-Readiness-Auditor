# Refinamento editorial PT-BR e Plano — PR #698

Lote sobre `5e1dc50072f06765596d55e4f90557b27d677d94`, exclusivamente na
apresentação paralela e seus testes. Baseline: 45 testes passaram em 10,61 s.
Nenhum arquivo existente na main base foi editado.

## Identidade e localização

A inspeção read-only da AUD real encontrou uma síntese de navegação (0,85)
em `synthetic_apdex_summaries` e duas de experiência (0,55 cada) em
`synthetic_ux_apdex_summaries`: MOBILE e POPULATION. A terceira ocorrência
é o agregado de experiência com perfil MIXED_DEVICE_POPULATION. Não existe
`synthetic_population_apdex_summaries` nessa AUD. Essa família tem adaptação
e teste sintético próprios, sem fabricar um cartão na geração real.

`presentation_labels.py` centraliza campos, valores tipados, dispositivos,
estados, criticidade, prioridade e origem. Valores brutos ficam em title ou
proveniência; evidências, textos do cliente, sugestões e payloads não sofrem
tradução. P0/P1/P2 permanecem sem equivalência inventada. HIGH em criticidade
ou prioridade é vermelho; confiança HIGH permanece neutra. INFO é azul.
SARI mantém Proposta de produto, Lighthouse e Apdex usam Contrato persistido.

Os estados públicos residuais de disponibilidade, medição e proposta foram
traduzidos após inspeção das dez páginas reais. Siglas, IDs de perfis/regras,
nomes de provedores/modelos, Search, Desktop, HTML e JSON permanecem técnicos.
O scanner de labels compara nós inteiros, ignorando pre/code; não certifica
todo texto livre nem considera evidência em inglês um defeito de interface.

## Tempo e contexto

Os dois helpers canônicos de time_contract foram inspecionados como puros.
Só recebem a configuração persistida da AUD e timezone explícito; não se usa
configured_presentation_timezone nem o ambiente atual. A AUD real persiste
America/Sao_Paulo em settings.presentation.timezone. Ausência histórica usa
o padrão canônico, com explicação de que o fuso histórico não foi persistido.
Timestamps tipados incluem segundos e IANA; datas civis e texto livre não
são convertidos. Timestamps legados sem offset seguem a interpretação UTC
do contrato canônico. O ISO bruto continua no payload/title.

O contexto reúne origins de audit_targets (fallback input_url), dispositivos
deduplicados de snapshots, estado, conclusão, criação, projeto, idioma,
mercado, modo, versão, regras e fuso com proveniência.

## Plano operacional

Cinco seções editoriais precedem Evidências e detalhe técnico: Visão geral,
Ações por prioridade, Cartões de ação, Correções técnicas propostas (código)
e Textos sugeridos por IA. A tabela técnica de arquivos fica recolhida na
última camada. Filtro, sort, links e expansão continuam disponíveis.

Agrupamento por action_id canônico, nunca por título. Nesta AUD: 60 ocorrências,
60 IDs distintos, 10 altas, 23 médias, 19 baixas, 8 sem prioridade; 6 de origem
explicitamente CONTENT_AI. Não se presume IA para DEEP_ANALYSIS. O protótipo
tem contagens diferentes, que não foram copiadas. Ocorrências sem ID não são
certificadas como ações distintas. Há 22 correções e 6 sugestões de conteúdo.

Cartões reorganizam justificativas, dimensões, confiança, implementação e
validação persistidas. Código Atual/Sugerido é escapado. Confiança declarada
não é probabilidade estatística; sugestões permanecem não aprovadas e exigem
revisão editorial, jurídica e de compliance.

## Verificação e limites

Regressão focal: tests/report_presentation, tests/test_report_presentation.py
e tests/test_report_numeric_zero.py. Novos testes cobrem identidade Apdex,
origem de réguas, enums/chips, timezone persistido e fallback, contexto,
agrupamento por ID, escape, preservação de literais e auditoria de labels.
Contraste AA dos tokens de chips é testado sobre fundos card e bg, light/dark.
Os tons claros warning e neutro foram ajustados discretamente para AA.

compare_visual.py usa o ZIP autorizado (SHA-256
6c124ecf7d5edc7b8d1f0c49afd8f8c54f45f23064340402271b27b62839180a),
dez páginas e cinco viewports: 1440×900, 1920×1080, 1280×800, 820×1180,
390×844. Produz 50 pares/100 screenshots, detalhes expandidos e tema escuro,
confere rail, filtros, teclado, details, réguas, stack, erros, rede, overflow
e impressão A4. Evidências e HTML real ficam apenas em diretório privado.

Geração real: inventários antes/depois idênticos, banco e report-catalog
preservados, paridade PASS nos campos disponíveis do snapshot. Consulte
_geracao.json de cada saída para hashes verificáveis. Isso não certifica
paridade HTML nem homologação humana. A estrutura operacional do plano foi
comparada com a referência; alturas/densidade variam com os registros reais.
As limitações visuais anteriores documentadas em VISUAL_FIDELITY.md
(ausência de série temporal adaptada/captura do ZIP e diferenças deliberadas)
continuam. Não se afirma reprodução pixel-perfect nem aceite humano.
