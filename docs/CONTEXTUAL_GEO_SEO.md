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
