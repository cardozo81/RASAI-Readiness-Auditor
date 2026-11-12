# Contexto consultivo GEO/SEO offline

Implementação da issue #690, sobre a base da #656. Não altera score,
SARI, Apdex, achados de motores ou revisão independente. Nenhuma operação
de rede, download documental, OCR ou fornecedor é oferecida por esta camada.

## Reuso e superfície alterada

| Produtor / consumidor existente | Uso e lacuna física |
|---|---|
| `PageSnapshot`, acquisition, device_context_capture, persistence | Identidade, dispositivo, instante e referências raw/DOM já capturadas; sem nova captura |
| extraction e captura canônica de FAQ | Links e blocos canônicos não retêm ancestrais, atributos e offsets necessários à classificação de ocorrências; o suplemento `contextual_content` observa apenas esses campos no mesmo HTML |
| contextual_documents, document_advisory | Reuso de hash, URL de referência, leitura limitada, proteção de paths/junctions, gate terminal e inventário completo; contrato passivo não modificado |
| document_relationships, document_text, document_advisory_html | Continuam responsáveis por documentos fornecidos e relações; este ciclo não abre documentos nem autentica referências |
| content_context, context_scope, context_reporting, context_interpretation_persistence/runtime, editorial_risk_context | Contexto editorial e escopo já existentes não são reclassificados nem persistidos por esta projeção |
| geo_extraction_quality, geo_competitor_content_provenance | Qualidade/extração competitiva existentes não viram provas de FAQ ou produto; não se duplica aquisição competitiva |
| geo_query_ledger, geo_search_alignment, geo_temporal_provenance, geo_observation | Seleção por query, cronologia, atribuição e identidade exata de URL reutilizadas; o novo consumidor não calcula score nem nova identidade de destino |
| geo_catalog_context, geo_report, catalog_report_site | Painel compartilhado nos pontos existentes, materializado uma vez; nenhuma nova rota canônica/CAT |
| geo_ai, competitive_ai_runtime, ai_canonical_orchestration e políticas de custo/consentimento | Não instanciados: GEO grava execução na AUD e Competitive AI exige comparação CONSOLIDATED de aquisição própria; não há perfil contextual autorizado para esta operação somente leitura |
| report_registry, report_rematerialization, report_completion, public_report_safety | Contratos de materialização e conclusão preservados; companheiro externo não substitui relatório selado |

Workflows existentes de regressão integral, catálogo e smoke visual são reutilizados.
O diff de produção limita-se aos módulos `contextual_*` e a um ponto de extensão
em `catalog_report_site.py`.

## Evidência contextual v1

`contextual-content-v1` conserva identidade da AUD/página/snapshot/dispositivo,
instante, superfície, referência e SHA-256 dos bytes. IDs de ocorrência incluem
versão, origem e posição estrutural. URLs repetidas conservam ocorrências;
consolidação de destino existe apenas na apresentação e nas oportunidades.

Categorias têm `category_basis` e `limitations`. Ancestrais nav/footer têm
precedência sobre palavras como regulamento. Host social identifica somente o
destino. Texto de anchor, aria-label e alt são campos distintos; nenhuma
visibilidade computada ou acessibilidade é inferida. Main/article/role main
fundamentam conteúdo principal; vocabulário comercial e documental é candidato,
nunca produto identificado, contrato coletado ou documento autenticado.

FAQ é uma hipótese editorial sobre um par físico fechado details/summary.
A resposta deriva somente dos tokens posteriores ao summary no mesmo details;
pergunta sem resposta permanece parcial. Outros widgets FAQ ou JSON-LD sem
vínculo ao texto físico não são promovidos. Entidades/produtos e lacunas de
intenção que exigiriam interpretação adicional permanecem N/D.

`text_range` usa posições no **HTML decodificado**, não bytes nem texto visível;
tags incompletas têm fim N/D e limitação de markup malformado. Texto é normalizado
por espaços, limitado a 600 caracteres, com indicação de truncamento. Contexto
é proximidade estrutural, não relação comercial comprovada.

Limites: 2 MB/captura, 20 mil nós/tokens, profundidade 128, 500 ocorrências/captura,
2 mil ocorrências/AUD, 20 MB de leitura HTML/AUD, orçamento entre capturas de 30 s;
subprocesso de parsing/search com timeout 5 s, memória 256 MiB e saída até 5 MB.
O worker recusa socket.connect, DNS e novos subprocessos por audit hook.
Inventário completo reutiliza o limite de 20 mil entradas/2 GB da #656.
Excesso/ausência/falha de parsing produz N/D, nunca zero compensatório. Quando
todas as ocorrências foram contadas antes do limite de apresentação, totais e
omitidos são conhecidos; capturas sem contexto observável têm totais N/D.
Menu extenso não oculta a referência documental tardia. Mobile/desktop permanecem
contextos distintos. Raw fallback não comprova renderização tardia de SPA.

## Search: correlação e abstenção

`contextual-search-v1` consome o ledger físico da mesma AUD, sem providers.
Conserva query, IDs de observação/execução, timestamps, escopo SERP, selos e
referências de contexto local. Só reproduz contagens descritivas aprovadas pelo
ledger; uma URL de página exata é diferente de outra URL do mesmo host.

O schema atual de Perplexity Search não comprova conjuntamente mercado, idioma,
dispositivo e vínculo da intenção da consulta ao trecho local. Portanto o estado
**contextual** permanece `NOT_COMPARABLE`, mesmo com `QUERY_MATCH` e conjuntos
descritivos válidos. A janela de 24 h é entre observações persistidas, não prova
de atualidade hoje. Não se inventa comparação positiva com dados fabricados.
Fontes ausentes, run falho/antigo em relação à SERP, query diferente, atribuição
multiquery ausente, dados malformados ou outra AUD geram razões próprias N/D.
Search API não é resposta generativa: não há conclusão de citação em IA,
independência, autenticidade, causalidade ou melhoria de ranking.

## Recomendações e IA

`contextual-editorial-v1` produz oportunidades para pergunta sem resposta física,
referência documental candidata e controle/fragmento com contexto de destino não
comprovado. Inclui problema, texto/local observado, escopo, evidências, ajuste,
validação e limites. Repetições são agrupadas por página/dispositivo/categoria e
destino/pergunta, conservando todas as referências. Menu/rodapé/social não geram
oportunidades. A materialidade declarada é referência física local, sem ranking
numérico entre oportunidades. Não há percentuais arbitrários ou novos BR-GEO.

AI=none entrega a camada completa determinística. AI=requested resulta em
`NOT_AUTHORIZED`, zero chamadas/custo, sem fallback. IA ativa fica **pendente** de
perfil contextual/consentimento e integração canônica seguros, sob autorização
futura. Não existe implementação de provider fake ou live porque nenhum provider
é chamado; testes verificam o gate e os workers offline. Entradas hostis são dados,
nunca instruções, prompts ou conclusões regulatórias/revisões assinadas.

## Relatórios e privacidade

| Página existente | Projeção |
|---|---|
| index.html | Contagens sintéticas e links, sem inventário bruto |
| capture-context.html | Agrupamentos por categoria/destino e drill-down físico privado |
| cat-03.html | Conteúdo principal, sinais comerciais e pares FAQ; entidades N/D |
| cat-05.html / geo.html | Proveniência Search e limites de comparabilidade/citação |
| cat-08.html | Oportunidades locais, sem prioridade numérica inventada |
| cat-09.html | Problema/local/texto, ajuste e validação no companheiro privado |

Relatórios canônicos novos/reconstruídos recebem painéis públicos conservadores:
contagens, categorias e recomendações fixas, sem URLs/literais arbitrários/PII da
captura. A fonte HTML consultada é registrada em `catalog_source_dependencies`.
Detalhes físicos permanecem no **companheiro privado**, que usa os mesmos nomes
de páginas sob navegação isolada. Isso é uma limitação deliberada da projeção
pública; não há certificação de anonimização de texto arbitrário.

Executar somente sobre cópia/saída autorizada quando reconstruir relatório.
Para AUD selada, usar exclusivamente:

```powershell
.\.venv\Scripts\python.exe -m rasai.contextual_advisory --audit-dir C:\caminho\AUD-exemplo --output C:\privado\companheiro-novo --ai none
```

O comando não modifica `audit.db` nem `report-catalog`. Rejeita symlinks/junctions,
traversal, SQLite sidecars, AUD não terminal e saída existente/interna. Compara
SHA-256 de **todos** os arquivos da AUD antes/depois, recusa publicação se houver
mutação e registra manifest.json com inventários de origem e saída. Evidências
JSON e HTML são privados, sem links ativos para URLs capturadas, scripts ou fetch;
CSP recusa rede e há escaping HTML. Diretórios temporários e finais usam modo
privado 0700 (Python 3.13 restringe a DACL no Windows). O manifesto não é assinatura
independente nem proteção contra alteração concorrente posterior à verificação.

O script revisável `scripts/verify_contextual_companion.ps1` atualiza apenas a
branch exclusiva por fast-forward, verifica SHA, valida AUD terminal, impõe ACL de
saída e refaz os hashes completos. **Não foi executado sobre AUD real.**

## Situação do aceite

A: entregue no subconjunto estrutural documentado; widgets FAQ sem vínculo e
entidades seguem N/D. B: entregue consumidor offline/abstenção e conjuntos
descritivos; comparação contextual positiva indisponível no schema físico atual.
C: entregue determinístico e gate; IA ativa pendente de GO/perfil. D: entregue
projeções e companheiro; homologação humana Windows com AUD real ainda pendente.
Não fechar #690 automaticamente. CI verde do HEAD e homologação continuam gates
de revisão/merge; testes sintéticos não substituem evidência privada real.

## Evidência local em 10/11/2026

Python 3.13 no Windows: **281 passed, 1 skipped**, em 62,89 s, com:

```text
python -m pytest -q -rs tests/test_contextual_content.py tests/test_contextual_advisory.py tests/test_contextual_search.py tests/test_contextual_report_integration.py tests/test_contextual_documents.py tests/test_document_advisory.py tests/test_geo_query_ledger.py tests/test_geo_query_ledger_report.py tests/test_catalog_report_site.py tests/test_catalog_report_package_integrity.py tests/test_report_section_readability.py tests/test_report_confidence_kpm_labels.py tests/test_catalog_source_dependencies.py tests/test_catalog_source_inventory.py --tb=short
```

O skip existente é `tests/test_geo_query_ledger.py:1380`: Windows SQLite pode
reter handle nativo durante `os.replace`; não foi introduzido skip nesta entrega.
Gate `python -m rasai.public_contract_gate`: PASS. Testes documentais:
`python -m pytest -q tests/test_documentation_contract.py tests/test_prepublication_documentation_contract.py tests/test_repository_filename_policy.py`: **23 passed**.

Smoke preexistente:
`python tests/report_catalog_visual_smoke.py --make-synthetic-fixture --output-dir .rasai-runtime/issue690-validation/visual`.
20 páginas, 60 screenshots nos três viewports; manifesto VERIFIED, hashes da
origem preservados, 0 requisições de coletores/provedores e 0 recálculo de score.
Baseline comparativo não fornecido; aceite visual humano PENDING. Verificação
adicional do companheiro sintético: 14 combinações página/viewport, details
abertos, JavaScript desligado, sem overflow horizontal ou requisições remotas.
Logs e screenshots locais privados em diretório de validação externo ao checkout;
não fazem parte da PR e não contêm AUD real. Nenhuma homologação em AUD real foi
executada. A solução observou 0 HTTP/IA/SerpAPI/Perplexity e custo incremental 0;
operações administrativas Git/GitHub deste desenvolvimento usam rede separadamente.

Gates finais de nomenclatura pública e traduções: **28 passed**, com
`python -m pytest -q tests/test_documentation_public_naming.py tests/test_rasai_namespace_contract.py tests/test_user_facing_language_contract.py`.
Esses gates também integram o workflow focal de catálogo existente. Não foram
alterados seus asserts ou exclusões. Artefatos sintéticos locais ficam fora do
checkout para preservar a distinção entre fonte versionada e evidência gerada.

## Correção aditiva pós-homologação: v1 + v2

O operador informou homologação física Windows do HEAD `58e8c6c` com 50/50
arquivos históricos preservados, 1 snapshot, 320 ocorrências e 7 hipóteses v1,
IA desativada, zero chamadas e comparabilidade externa N/D. Esses números são
evidência fornecida pelo operador; a correção não reabre nem modifica essa AUD
ou o companheiro já homologado. Os resultados anteriores acima são históricos.

### Compatibilidade e contratos

`contextual-content-v1` e `contextual-editorial-v1` permanecem íntegros: IDs,
ordinais, categorias estruturais, texto/href/URL, contexto, offsets, hashes,
limitações e as hipóteses originais não são renumerados, filtrados ou regravados.
O consumidor usa um trace efêmero do mesmo parser, sem segunda captura ou
segundo parsing. Esse trace não é publicado dentro dos registros v1.

O campo adicional `semantic_v2`, contrato `contextual-semantic-overlay-v2`,
contém diagnósticos ligados a `occurrence_id`, `v1_category`,
`display_category_v2`, `semantic_disposition_v2`, `basis`, `evidence_refs` e
`limitations`. Não substitui `captures` ou `recommendations`. A extensão do
manifesto declara a versão do overlay e conserva inventários/hashes completos
de origem e saída. Se o overlay exceder o orçamento de saída do worker, o pacote
v1 é preservado e somente a qualificação v2 fica N/D. Os limites v1 anteriores
continuam explícitos: o overlay não extrapola ocorrências omitidas.

| Informação homologada | Tratamento aditivo |
|---|---|
| Inventário v1 completo e IDs físicos | Conservado integralmente no JSON e no inventário técnico privado |
| Categorias FAQ v1 derivadas de details/summary | Conservadas como hipóteses estruturais no histórico; v2 informa a disposição editorial separadamente |
| Hipóteses/recomendações v1 | Todas mantidas; histórico v2 referencia seu ID, evidencia `not_actionable` ou `contextual_only`, e liga `superseded_by` aos diagnósticos que qualificam a hipótese |
| Blocos de outros motores, métricas, scores, trust, Search, custo, IA e navegação | Mantidos fora do painel contextual; comparação estrutural contra a projeção anterior cobre todas as páginas canônicas |
| Observações Search e razões de N/D | Sem alteração, inclusive `EXTERNAL_CONTEXT_EQUIVALENCE_UNPROVEN`; nenhuma citação generativa inferida |
| AUD e companheiro já homologados | Somente leitura; gerar outra saída externa privada nova |

### Qualificação conservadora de FAQ e controles

- Ancestrais/roles de navegação ou template têm precedência. Mesmo dentro de
  main, summary Menu/Produtos combinado com corpo composto por links é
  `NAVIGATION_DISCLOSURE`, sem FAQ editorial. A qualificação se propaga aos
  registros daquele disclosure, preservando o vínculo estrutural v1.
- FAQ editorial exige condições conjuntas: pergunta contextual interrogativa,
  escopo main/article ou FAQ explícito, details/summary fechado e resposta em
  prosa fisicamente vinculada. Ponto de interrogação, nome/classe FAQ ou summary
  isolados não bastam. Prosa direta só é admitida com escopo FAQ explícito;
  caso contrário exige bloco textual em prosa. Esse é um critério conservador
  de projeção, sem confiança percentual, autenticação de intenção ou mudança de
  motor. Outras estruturas/idiomas ficam N/D quando não sustentados.
- Pergunta sem resposta observável permanece `POTENTIAL_FAQ_QUESTION`, N/D.
  Ausência na captura não comprova resposta ausente no site e não gera ação.
- Fragmentos/ações são `OBSERVED_CONTROL` ou `POTENTIAL_FAQ_ANCHOR`.
  Voltar ao topo e links interrogativos não demonstram falha no painel ou
  lacuna de conteúdo. Suas hipóteses v1 ficam `not_actionable` em v2.
- Referência a regulamento/PDF continua candidata documental, sem autenticação,
  conteúdo inferido ou nova coleta. A hipótese de revisão v1 permanece
  `contextual_only`; isso não comprova problema editorial.

As contagens de observações v2 são `raw`, `qualified`, `not_actionable` e `nd`:
raw é o número de registros v1 disponíveis e é a soma das três disposições.
`qualified` significa contexto observável classificado, não oportunidade ou
melhoria. `observed_v1` conserva o total original pré-limite quando conhecido;
se indisponível, a limitação é N/D. Contagens de recomendações têm denominador
próprio: hipóteses v1 preservadas, ações v2 sustentadas, não acionáveis e somente
contextuais/N/D. Não são score nem somáveis às contagens de observações.

Este lote não inventa um novo gerador de remediações: os casos acima não
comprovam falha editorial adicional. `actionable_recommendations` fica vazio,
com razão explícita de N/D para melhoria; não é prova de ausência de melhorias.
Na fixture sintética de 320 registros e 7 hipóteses: os 320 e os 7 permanecem
íntegros, nenhuma FAQ de Menu/Produtos é promovida, seis hipóteses de controles
ficam não acionáveis e uma referência documental permanece contextual/N/D.
Isso não antecipa as contagens v2 da próxima homologação real.

### Projeções e nova homologação única

As sete superfícies existentes recebem uma seção v2 claramente delimitada.
O inventário e as hipóteses v1 continuam no histórico de compatibilidade,
incluindo texto/local/ajuste/validação e razões originais; cada hipótese ganha
uma explicação v2 separada. As observações Search mantêm sua apresentação e
seu estado N/D. Singular/plural natural aplica-se apenas à composição contextual.
Nenhuma rota, CSS, catálogo, workflow ou bloco de outro motor foi substituído.
Painéis canônicos omitem literais/URLs privados; detalhes permanecem no
companheiro privado com escaping/CSP e vínculos locais. IA solicitada continua
`NOT_AUTHORIZED`, sem providers, HTTP, PDFs ou OCR.

Após CI verde do novo SHA, executar **uma** homologação pelo script existente,
na mesma AUD terminal escolhida pelo operador e com outra saída privada nova:

```powershell
.\scripts\verify_contextual_companion.ps1 -ExpectedSha '<HEAD_FINAL_DE_40_CARACTERES>' -AuditDir 'C:\caminho\AUD-exemplo' -OutputDir 'C:\privado\validacao-v2-nova\companheiro'
```

O script exige diretório pai privado novo, faz atualização por fast-forward e
confere o SHA, valida a AUD terminal, verifica todos os hashes de origem antes
e depois, confere o manifesto de saída e imprime somente contagens v1/v2 e a
razão de N/D externo. Fetch Git administrativo é separado da solução offline.
Não reutilizar a saída anterior. Revisar FAQ qualificada, controles e histórico
v1, confirmar a paridade completa e decidir sobre merge posteriormente.

### Evidência focal da correção v2

Windows/Python 3.13: **154 passed em 61,17 s**, sem novos skips, com:

```text
python -m pytest -q -rs tests/test_contextual_content.py tests/test_contextual_advisory.py tests/test_contextual_search.py tests/test_contextual_report_integration.py tests/test_catalog_report_site.py tests/test_catalog_report_package_integrity.py tests/test_catalog_source_dependencies.py tests/test_catalog_source_inventory.py tests/test_report_section_readability.py tests/test_report_confidence_kpm_labels.py tests/test_documentation_contract.py tests/test_prepublication_documentation_contract.py tests/test_documentation_public_naming.py tests/test_rasai_namespace_contract.py tests/test_user_facing_language_contract.py --tb=short
```

- Fixture v1 de 320 ocorrências congelada contra o produtor `58e8c6c`: igualdade
  integral e SHA-256 JSON canônico
  `69643315f6ebacd5aa2de58ddf85e781e05999be4b9c5091c187bfb000015efb`.
- Fixture de AUD selada com 50 arquivos e companheiro anterior: todos os hashes
  preservados; 320 registros e 7 hipóteses v1 íntegros; seis hipóteses de controle
  não acionáveis e uma documental somente contextual/N/D; zero ações novas sem
  prova de lacuna. Isso é teste sintético, não nova homologação da AUD real.
- Comparação baseline/candidato do materializador: tokens estruturais, conteúdo
  e navegação fora do painel contextual idênticos nas 20 páginas; bytes do banco
  e linhas de scores preservados. Mudanças de concordância e qualificação dentro
  do próprio painel são deliberadas e não representam perda de dados v1.
- Smoke preexistente executado sobre relatório sintético com 320 ocorrências:
  20 páginas, 60 screenshots desktop/mobile/tablet, manifesto verificado, origem
  intacta e zero requests de coletores/provedores. A ferramenta visual não recebeu
  baseline integral; a paridade externa ao painel é provada pelo teste específico
  acima, não por alegação de paridade de todo texto visível do smoke.
- Companheiro privado: 14 combinações página/viewport, JavaScript desativado,
  sem overflow, sem requests remotos e com hashes preservados. Deep link v1
  de ocorrência continua revelando o histórico sem JavaScript.
- Gate público, parser PowerShell e `git diff --check` aprovados. Nenhuma execução
  manual da regressão integral; o CI existente executa os gates do novo HEAD.
- Gates documentais finais, incluindo o contrato do launcher:
  `python -m pytest -q tests/test_console_launcher_contract.py tests/test_documentation_contract.py tests/test_prepublication_documentation_contract.py tests/test_documentation_public_naming.py tests/test_rasai_namespace_contract.py tests/test_user_facing_language_contract.py`: **41 passed em 7,19 s**.

Logs e capturas sintéticos ficam em diretório privado externo ao checkout.
Homologação única da correção na AUD real e autorização de merge permanecem
reservadas ao responsável. Não fechar #690 nem remover a branch automaticamente.

## Evolução em branch #690: análise reversa com overlays v3

A rota `geo-content-review.html` é a 21ª página do catálogo canônico e
apresenta o caminho observação - cobertura - hipótese - validação. Links
retornam ao inventário de `capture-context.html`, evidências GEO e CAT-03/CAT-09.
A versão pública mostra apenas projeções agregadas/sanitizadas; textos, URL
e referências físicas literais continuam no companheiro privado.

O overlay `contextual-faq-aria-overlay-v3` vincula controles ARIA
`role=button`, `aria-controls`, `aria-expanded` a painéis de mesmo DOM
capturado, respeitando IDs não ambíguos, limites e ancestralidade. Painel não
capturado é **NOT_OBSERVED_ND**, nunca erro comprovado do website. Painel
recolhido mas presente no DOM não prova visibilidade de crawler ou indexação.
Menus compostos por links são excluídos, mesmo em `main`.

O overlay `contextual-page-structure-v3` expõe títulos e H1-H6, posição,
escopo, hashes e categorias v1 somente quando o próprio markup foi observado;
sem dupla aquisição. Title, headings, claims, CTAs e documentos não são
autenticados por mera presença. A análise profunda por IA continua
**NOT_AUTHORIZED** sem consentimento de tarefa próprio: nenhuma chamada
faturável, comparação Search positiva nem conclusão YMYL foi implementada.

Essas projeções não alteram as ocorrências v1, a disposição v2, CATs,
escores, banco selado ou contratos de fornecedores. O novo contrato é
passível de testes sintéticos offline; homologação física Windows da AUD
real permanece condicionante para merge.

### Gate físico Windows opcional desta branch (pendente)

O script existente mantém o comportamento padrão v2 e aceita branch explícita.
No checkout limpo já posicionado na branch de entrega, usar uma saída privada
nova e nunca publicar HTML ou JSON das evidências.

```powershell
.\scripts\verify_contextual_companion.ps1 `
  -Branch 'feature/geo-reverse-content-timezone-690-692' `
  -RequireReverse `
  -ExpectedSha '<HEAD_FINAL_DE_40_CARACTERES>' `
  -AuditDir 'C:\caminho\privado\AUD-EXEMPLO' `
  -OutputDir 'C:\caminho\novo-privado\companheiro'
```

O gate exige hashes originais íntegros, saída privada externa nova,
rota estratégica disponível no companheiro, contratos de FAQ ARIA e hierarquia
v3, sem provider e sem escrita na AUD. A revisão editorial e visual dos
21 HTMLs e o GO de merge continuam humanos.


## Projeção reversa com verificação editorial condicionada - evolução #690

A camada `contextual-reverse-editorial-projection-v1` usa exclusivamente
capturas e overlays existentes, com tarefas condicionais `TITLE_H1_INTENT`,
`H1_HIERARCHY`, `COMMERCIAL_CLAIM_SUPPORT`, `FAQ_RECAPTURE` e
`DOCUMENT_CONTEXT`. Cada tarefa possui origem física, hash e validação;
não alega erro SEO, ranking, indexação ou falsidade comercial. Links documentais
são consolidados apenas na projeção, mantendo ocorrências e hashes v1.

O relatório novo apresenta a fila de revisão separada do histórico v1 de
controles não acionáveis, agrupa títulos por superfície e explica a diferença
entre os critérios FAQ v2/v3. O link interno GEO aponta para
`geo.html#contextual-semantic-v2`, âncora produzida pelo renderer existente.
A projeção pública não expõe literais privados; o companheiro restringe
trechos e URLs por CSP/escaping. O script Windows verifica o contrato da
projeção e o manifesto de saída em modo offline.

A nova projeção não supre a exigência de GO para IA contextual ativa nem prova
comparabilidade positiva de dados externos; essas pendências continuam na #690.


## Redução conservadora de verificações title/H1 - #690

A revisão de intenção não emite tarefa quando o H1 inteiro corresponde a
um segmento do title, descontando diferenças exclusivamente tipográficas
(caixa, acentos, pontuação), por exemplo H1 de produto e title com sufixo
ou prefixo de marca. Isso evita que diferença de marca no title seja
apresentada como indício de desalinhamento editorial. Outras divergências
continuam condicionais e requerem revisão humana; não provam defeito SEO.
A verificação não presume equivalência semântica por sinônimo, não altera
scoring, e não emite conclusão sobre posição ou indexação.


## Reconciliação focal da PR #694 e aceite privado

CORREÇÃO_CONFIRMADA: a comparação title/H1 descartava letras não latinas,
igualando indevidamente produtos distintos com o mesmo sufixo latino. O
normalizador agora preserva letras e números Unicode. Acentos, caixa e
pontuação continuam normalizados; não se infere sinonímia. Teste com textos
japoneses e cirílicos divergentes conserva a verificação condicional.

Os testes existentes de ARIA, estrutura, companheiro e integração cobrem
pergunta/resposta vinculada, controles N/D, navegação/rodapé, preservação
v1/v2/v3, referências documentais e separação público/privado. A lista visual
de 16 provas mantém total/omissões e o link capture-context.html#contextual-content;
o ledger integral continua em evidence.json. Isso não equivale a autenticação
documental nem conclusão editorial da AUD real. Nenhuma alteração de motor,
score, Search ou IA ativa integra este microlote. Search positivo continua N/D
sem mesma AUD/query/janela/mercado/idioma/dispositivo/intenção/origem.
AI=none usa somente evidência local; custo incremental de provedores zero.

No Windows, preparar checkout limpo no SHA final da PR, na branch existente.
O verificador não faz mais fetch ou merge: recusa branch/SHA divergentes antes
de ler a AUD. Usar .venv já preparada, sem instalação ou coleta externa.
Exemplo em PowerShell, com SHA real obtido e conferido na PR:

```powershell
Set-Location 'C:\IA-PROJETOS\github\RASAI-Readiness-Auditor'
$finalSha = git rev-parse HEAD
# Conferir $finalSha com o SHA final publicado na PR #694 antes de continuar.
$audit = Join-Path $PWD 'audits\AUD-C0475E4AF5674E93B8F8C6F257226808'
$private = Join-Path $env:LOCALAPPDATA ('RASAi-review-' + [guid]::NewGuid().ToString('N'))
.\scripts\verify_contextual_companion.ps1 `
  -ExpectedSha $finalSha `
  -Branch 'feature/finalize-contextual-geo-timezone-690-692' `
  -AuditDir $audit -OutputDir (Join-Path $private 'companion') -RequireReverse
```

Se a AUD estiver em outro local, ajustar somente $audit. O pai privado deve
ser novo; a ACL concede acesso ao operador. Não anexar seus arquivos à PR.
Companion contém evidence.json, manifest.json e HTML por superfície; o arquivo
acceptance.json fica no pai, fora do manifesto do companheiro. Registra SHA-256
de todos os arquivos antes/depois, incluindo relatórios e arquivos ocultos,
fuso/proveniência, capturas por dispositivo, ocorrências e contadores de chamadas.
SQLite com WAL/SHM/journal é recusado: não apagar sidecars nem abrir para escrita.
PASS verifica integridade/contratos locais; FAIL indica recusa, divergência ou
falha de geração. O finally registra hashes também em falha de geração;
falhas anteriores à criação do pai privado podem não produzir acceptance.json.
Homologação humana, temporal_21_pages e non_temporal_21_pages ficam N/D.
O teste executa o payload em fixture, inclusive recusa simulada, não na AUD real.

Para validar as 21 páginas completas, usar cópia controlada em diretório
privado, nunca rematerializar a origem. Conservar cópia do baseline e comparar
estrutura/atributos/blocos técnicos e texto não temporal por página antes/depois;
inspecionar mudança de dia, DST, datas civis, fontes técnicas e dispositivos.
O companheiro contextual não gera os 21 relatórios canônicos: seu PASS não
fecha #692. Enquanto faltar esse aceite, ambas as issues permanecem OPEN;
IA ativa, comparabilidade Search e validade documental dependem de decisões
humanas/provas adicionais. GO somente para executar homologação quando o CI
do SHA final estiver verde; merge exige autorização humana separada.
