# #330 - Evidência competitiva persistida (somente leitura)

O módulo `rasai.geo_competitor_content_provenance_330` consome exclusivamente um
SQLite `audit.db` existente, com `PRAGMA query_only=ON`. Exige um ID de AUD,
um ID de observação SERP e contexto válido com query, data com fuso horário
e origem OBSERVED_API. Não faz chamadas HTTP, Perplexity ou IA.

A coleta de conteúdo opcional já existe em `search_intelligence/content.py`.
A nova inspeção apenas lê `serp_competitive_pages`: uma página CUSTOMER
e páginas COMPETITOR_CANDIDATE com status OBSERVED, HTTP 2xx, hash SHA-256,
tamanho maior que zero e texto substantivo. URLs inválidas, conteúdo vazio,
hash ausente, dados de outra auditoria ou snippets não constituem prova de HTML.

A diferença de número de palavras é descritiva, nunca causal, não altera
SARI, SCORE-GEO, Apdex, findings nem rankings. O instante da coleta HTTP
do conteúdo não é demonstrado pelo relógio SERP: html_fetch_timestamp=N/D.
A equivalência de contexto de Perplexity também não é inferida.

Exemplo offline:

    python -m rasai.geo_competitor_content_provenance_330 AUD-REFERENCIA/audit.db --audit-id AUD-REFERENCIA --serp-observation-id SERP-REFERENCIA

Limites restantes: novos candidatos exclusivos da Perplexity requerem
opt-in próprio, regras robots, origem/URL, locale, dispositivo, custo e
proveniência física. Esta ponte não abre novo crawler. Fixtures validam
integridade byte a byte da AUD, ausência de provider e fallback N/D.

## Gate de correspondência lexical da mesma query

Para formar um par descritivo, cada página persistida deve manter
`query_terms_json` idêntico à tokenização determinística da query
SERP e ao menos um desses termos em `query_terms_body_json`,
extraídos no mesmo processo de aquisição de HTML. JSON malformado,
ausência de termos no corpo, documento vazio e termos de outra query
abstêm com `CONTENT_EVIDENCE_NOT_COMPARABLE`. O novo gate não
aciona extração novamente nem realiza chamada de rede.

**Limite explícito:** mesmo uma correspondência lexical no corpo HTML
pode vir de menu, rodapé ou shell SPA. A evidência não comprova
conteúdo principal e o campo `primary_content_proven=false`
permanece. Comparações de contagem de palavras seguem estritamente
descritivas e não fundamentam propostas causais de GEO/SEO.


## Tipo MIME verificado no registro HTTP

Mesmo com status HTTP 200, hash e texto persistido, a comparação
consultiva só aceita o cabeçalho MIME registrado como `text/html`
ou `application/xhtml+xml` (com `charset` opcional). Respostas
`text/plain`, `application/pdf`, MIME ausente ou inválido
retornam `NOT_COMPARABLE`; schemas mais antigos sem o campo
`content_type` produzem `CONTENT_EVIDENCE_SCHEMA_ND`, sem migração
ou atribuição retroativa. A regra consome apenas o HTTP já persistido
pelo coletor original e não acrescenta requisições ao fluxo.

## Fatos lexicais adicionais sem inferência de qualidade (#330)

Quando a AUD já possui colunas modernas de `serp_competitive_pages`, a prévia
consulta também as listas persistidas de correspondência de termos da **mesma
query SERP** no `title`, na metadescrição, nos cabeçalhos e no corpo. A saída
`observed_lexical_differences` informa **quantidade de termos encontrados no
concorrente menos quantidade encontrada no alvo**. Valores positivos e negativos
não significam superioridade, lacuna causal ou recomendação de mudança de score.

Listas JSON sem prova lexical consistente, corrompidas ou colunas ausentes
resultam em `null` (N/D) **por dimensão**. `[]` validado na origem representa
zero observacional, sem se confundir com dado não coletado. A prévia ainda expõe
tipos JSON-LD como inventário, não como prova de qualidade/validade semântica.
Contagem de palavras continua descritiva e páginas SPA/menu não comprovam
conteúdo principal. O mesmo gate prévio de HTTP HTML válido, hash,
URL final, query, AUD e observação SERP é exigido antes da comparação.
A leitura continua sem produzir chamadas externas ou alterar artefatos.

## Isolamento de observações e leitura física (#330)

O consumidor de conteúdo competitivo só vincula conteúdo pelo
`observation_id` quando esse identificador é **único em toda a tabela
`serp_observations`**, não apenas dentro da AUD solicitada. Uma segunda
linha com o mesmo ID, inclusive pertencente a outra auditoria, resulta em
`SERP_OBSERVATION_ID_AMBIGUOUS_OR_FOREIGN` e nenhuma comparação.
Se a tabela de conteúdo possui `audit_id`, qualquer registro com
`audit_id` divergente ou nulo bloqueia a projeção com
`CROSS_AUD_CONTENT_PROVENANCE_UNVERIFIABLE`.

A leitura valida ausência de sidecars SQLite e usa snapshot local read-only
após hash físico limitado de `audit.db`. O hash é verificado após a consulta
e imediatamente antes de emitir comparação; qualquer alteração durante o
processamento retorna `AUD_SOURCE_CHANGED_DURING_READ`, sem publicar
métricas ou criar artefatos. O hash prova estabilidade dos bytes lidos, não
origem autêntica do fornecedor, captura no mesmo dispositivo, equivalência de
idioma nem conteúdo principal renderizado. Os testes são offline e isolados.


## Vinculação física da URL concorrente ao SERP (12/10/2026)

Um registro `serp_competitive_pages` com `observation_id`
e HTML atribuído não comprova, por si só, que a URL tenha aparecido
nos resultados orgânicos daquela SERP. O comparador offline exige
agora o inventário físico `serp_results(observation_id,url)` da
mesma observação (máximo 800 entradas), normaliza as identidades
por URL exata e só permite `comparisons[]` quando
`requested_url` concorrente for um membro **realmente persistido**
desse conjunto. O campo
`competitors[].serp_result_membership_proven` indica essa prova.

Um HTML com URL estrangeira, fora do conjunto, pode continuar
descrito como atributo persistido, mas **não** entra no
comparativo cliente × concorrente. Ausência/ambiguidade de
tabela/população resulta em `SERP_RESULT_URL_PROVENANCE_ND`,
sem qualquer ranking, ganho ou déficit inventado. O status
de conteúdo primário continua `false`, inclusive quando há
correspondência exata de URL; SERP não prova hidratação SPA,
readiness de conteúdo, equivalência de localidade/dispositivo,
resposta IA generativa nem causalidade.

São verificações sobre AUD SQLite **somente leitura**;
nenhum download, API comercial, score, persistência ou
contrato de coletor foi alterado.


## Vínculo do papel CUSTOMER à URL-alvo física da AUD (12/10/2026)

O valor `role='CUSTOMER'` dentro de `serp_competitive_pages`
não constitui prova de que o HTML armazenado pertença à URL
efetivamente auditada. Para entrar em uma comparação, o leitor
agora exige exatamente **um** `audit_targets.input_url` para
a mesma `audit_id`, com identidade canônica exata igual à
`requested_url` do registro CUSTOMER. O indicador observacional
`customer.aud_target_exact_url_proven` esclarece o resultado.

Um cliente rotulado com URL de outra página não entra na
comparação, mesmo com conteúdo HTML/termos válidos e concorrente
fisicamente comprovado na SERP. Tabela ausente, alvo ausente,
duplicidade ou URL inválida produzem
`AUD_TARGET_URL_PROVENANCE_ND` sem conteúdo parcial nem
conclusões positivas. A evidência de identidade da URL não é
prova de conteúdo principal, hidratação SPA, equivalência de
idioma/dispositivo ou causalidade.

O leitor é estritamente offline e utiliza apenas dados
anteriormente persistidos; nenhuma mudança de coletor,
esquema SQLite, GEO v8, score, relatório ou AUD é necessária.
