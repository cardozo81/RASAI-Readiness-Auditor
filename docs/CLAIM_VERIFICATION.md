# Verificação documental de alegações comerciais (#603)

## Fronteira de confiança

`rasai.claim_source_verification.classify_claim` é um contrato determinístico offline de revisão, sem rede, sem alteração no audit.db e sem alegar conformidade SUSEP ou certificação. **O relatório da AUD permanece em `CLAIM_UNVERIFIED_EXTERNAL`** quando não houver comprovação independente da fonte primária. Link, título, PDF não aberto, metadados autodeclarados da página auditada ou resultado de IA **não autorizam** `CLAIM_CORROBORATED`.

Estados previstos:

- `CLAIM_OBSERVED`: afirmação presente no material observado, sem exigência de validação documental neste contexto.
- `CLAIM_UNVERIFIED_EXTERNAL`: exatidão contra fonte primária não demonstrada; **não significa que o conteúdo é falso**.
- `CLAIM_CORROBORATED`: revisão externa explicitamente atestada, fonte independente autenticada, documento físico verificado por hash, produto/claim/versão/vigência coincidentes e excerto presente.
- `CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE`: a mesma cadeia de prova, com decisão explícita de contradição do responsável revisor. Não equivale automaticamente a decisão regulatória.

A mera configuração de `independent_source_authenticity_verified=True` por entrada não confiável **não comprova** autenticidade. A flag e o identificador de recibo somente podem vir de sistema/revisor **separado**, com autorização verificável e controle de integridade. A função valida coerência estrutural e correspondência física de bytes, **não** autentica o fornecedor online nem decide semântica jurídica.

## Contrato de futura integração

Entradas indispensáveis: texto literal da afirmação observada; escopo exato do produto; data de avaliação; bytes limitados da fonte primária; URL HTTPS e emissor; versão do documento; intervalo efetivo; SHA-256 dos bytes; excerto literal recuperado; decisão; revisor/recibo; sinal de autenticação independente. Inconsistência, fonte ausente, texto incompatível, escopo divergente, data fora de vigência ou digest divergente retornam `CLAIM_UNVERIFIED_EXTERNAL`.

A integração futura deverá persistir a cadeia de autenticação, identificar o controlador/revisor e aplicar validações de autorização. Até lá, não há promoção automática desses estados no CAT-03 nem reprocessamento de alegações históricas. BR-GEO-042/043/045/047 continuam avaliando somente sinais editoriais observados sob seu contrato vigente.

## Testes

Fixtures determinísticas cobrem fonte ausente, digest divergente, claim de outro produto, vigência expirada, excerto ausente, origem sem HTTPS, recibo ausente e ausência de autenticação independente; incluem contraexemplo de revisão de contradição. Não são usados serviços pagos.


## Recibo de revisão autenticado (#603, segunda fronteira de confiança)

O módulo `claim_review_receipt.verify_claim_review_receipt` exige um recibo de revisão **assinado via HMAC-SHA256**, uma chave de verificação confiável com ao menos 32 bytes obtida exclusivamente de contexto privado do operador/revisor e uma lista de identificadores de revisores autorizados. Assina-se a serialização JSON canônica de **todos** os campos permitidos (hash do documento, escopo/produto, claim literal, data/vigência, URL, emissor, versão, trecho correspondente, decisão e revisor/recibo). Qualquer alteração, assinatura inválida, campo inesperado ou revisor não autorizado devolve `CLAIM_UNVERIFIED_EXTERNAL` sem promover o resultado.

Além do MAC, o verificador recusa identificador de revisor vazio ou composto somente por espaços,
mesmo quando uma allowlist externa estiver incorretamente configurada para aceitá-lo.
O classificador exige `datetime.date` puro em `at_date`: objetos `datetime` não são
datas de avaliação compatíveis com a vigência documental e resultam em
`CLAIM_UNVERIFIED_EXTERNAL` (fail-closed), sem exceção de comparação.
Essas proteções não substituem autenticação de fonte, autorização externa ou
homologação regulatória.
Esse módulo **somente verifica** o MAC de recibos criados por um sistema **independente e autorizado**. Ele não fornece função de assinatura pública nem extrai chave de ambientes auditados. Não deve ser chamado por código que aceite `trusted_key` ou `trusted_reviewer_ids` do website auditado, JSON de LLM ou da mesma solicitação externa. A credencial não é persistida nem exibida; a validação é local e offline. Um recibo autêntico prova apenas que o emissor confiável atestou aquela revisão; não comprova por si só legitimidade da entidade SUSEP ou conformidade jurídica. A autenticação inicial do revisor e da fonte primária permanece dependência externa antes de promover qualquer claim do relatório.

O contrato de classificação anterior permanece disponível para testes e consumidores internos, **mas não deve receber diretamente dados não confiáveis com `independent_source_authenticity_verified=True`**. Integradores devem ingressar por esta etapa autenticada. Nenhum relatório atual é automaticamente enriquecido ou reescrito.


## Ferramenta operacional sem rede (leitura de recibos assinados)

`python -m rasai.claim_review_import_cli --claim-file <claim.txt> --document-file <document.txt> --receipt-file <receipt.json> --product-scope <produto> --at-date AAAA-MM-DD` lê três arquivos locais de tamanho limitado, sem criar/alterar uma AUD ou chamar qualquer serviço. A chave HMAC em hexadecimal deve ser fornecida **fora dos arquivos**, somente ao processo de verificação, via `RASAI_CLAIM_REVIEW_HMAC_KEY_HEX`, e os IDs autorizados via `RASAI_CLAIM_REVIEWER_ALLOWLIST`. Nunca fornecer segredo como argumento de shell nem dentro do recibo ou site; no ambiente operacional usar secret store apropriado e remover a variável ao concluir.

`receipt.json` deve conter exatamente `{"review": <campos revisionados>, "mac": "<HMAC SHA256 hex>" }`. Chaves JSON duplicadas, NaN, recibo truncado, arquivos simbólicos, documento de origem divergente, revisor não autorizado ou ausência de segredo ⇒ `CLAIM_UNVERIFIED_EXTERNAL`. O comando só escreve um JSON-resumo em stdout com estado, base e ressalvas fixas: `official_regulator_source_verified=false`, `legal_compliance_certified=false`, `file_writes=0`, `provider_requests=0`. Esses campos são intencionalmente separados do estado documental: a assinatura atesta revisão, **não** aprovação SUSEP.

A CLI é um adaptador para **fontes primárias já obtidas e autenticadas por um fluxo independente**; ela não deve baixar documento a partir de URL da página ou aceitar texto de LLM como verificação externa. O CAT-03 atual não é alterado automaticamente. A integração governada do fornecedor documental real e da cadeia de revisão ainda condiciona o fechamento de #603.

## Proveniência temporal opcional de coleta

Recibos assinados podem incluir `collected_on` (ISO `YYYY-MM-DD`), como dado adicional protegido pelo mesmo MAC. Quando fornecido, o classificador exige data válida e `collected_on <= reviewed_on <= at_date`; declaração posterior à revisão é rejeitada como `CLAIM_UNVERIFIED_EXTERNAL`. O campo é opcional para compatibilidade com recibos anteriores: **sua ausência não comprova data de coleta** e não supre a obrigação de cadeia documental quando exigida para o aceite externo. O conteúdo auditado e a IA não podem produzir nem autenticar esse campo. A verificação permanece documental, não regulatória.


## Revisão documental em lote com proveniência por alegação (19/10/2026)

A ferramenta offline `python -m rasai.claim_review_batch --manifest
/caminho/packet/manifest.json --format html` suporta até 50 alegações em
um único pacote de apresentação, com arquivos locais e recibos assinados
**independentemente para cada alegação**. O comando também suporta
`--format json`. Não é executado automaticamente na geração do CAT-03.

A estrutura de manifesto (não assinada e não atestada como origem de AUD)
é:

```json
{
  "audit_id": "AUD-EXEMPLO",
  "at_date": "2026-10-14",
  "claims": [
    {
      "claim_id": "C-001",
      "claim_file": "claim.txt",
      "document_file": "conditions.txt",
      "receipt_file": "receipt.json",
      "product_scope": "produto-e-versao-especificos"
    }
  ]
}
```

Cada `receipt.json` mantém o contrato de `claim_review_import_cli`, incluindo
`review` e `mac` HMAC-SHA256 validado contra **chave confiável externa ao
manifesto**. O revisor pertence à allowlist controlada pelo operador, recebida
pelas variáveis privadas `RASAI_CLAIM_REVIEW_HMAC_KEY_HEX` e
`RASAI_CLAIM_REVIEWER_ALLOWLIST`. Jamais incluir segredos no
manifesto, na árvore de auditoria, no documento ou nos logs.

Somente recibos autenticados, com escopo do produto, trecho literal, data
de revisão, versão documental, SHA-256 e vigência comprováveis podem expor
metadados de fonte e verificação documental. A apresentação separa
`CLAIM_CORROBORATED`, `CLAIM_UNVERIFIED_EXTERNAL` e
`CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE`; recibos inconsistentes
permanecem não verificados. Texto literal da alegação e chaves de
verificação não são exportados no relatório de lote.

O manifesto impõe caminhos relativos seguros dentro de sua pasta; arquivos
com links simbólicos, tráfego HTTP, arquivos excessivos, assinatura adulterada
e revisor não autorizado não promovem verificação. A identificação
`AUD-...` no manifesto **é declarada pelo operador**, sem prova de vínculo
com a captura física da AUD. O relatório HTML é consultivo, autônomo e
somente retornado em stdout. Não integra status no CAT-03 por inferência,
não certifica emissor/SUSEP, não atualiza score ou auditoria histórica.

A extensão atende o fluxo operacional local de múltiplas alegações; **o
aceite integral de #603 permanece dependente** de fonte primária oficial
vigente autenticada e ligação auditável ao texto da captura real.

## Transparência documental no CAT-08 (projeção #603)

Na análise profunda, quando há **contexto YMYL ativo**, o bloco de
interpretação separa evidências e sugestões editoriais da **confirmação de
alegações comerciais**. O estado público informa explicitamente
`CLAIM_UNVERIFIED_EXTERNAL` - **não validado contra documentação oficial
vigente nesta projeção** - sem afirmar que a alegação é falsa ou que existe
descumprimento contratual/regulatório. Em contexto não YMYL, o aviso não é
inserido artificialmente.

O aviso não aceita como prova links para condições gerais sem documento
autenticado. Uma promoção independente continua exigindo versão, URL oficial,
emissor, escopo do produto, vigência, SHA-256 e recibo de revisão autenticado
com correspondência à alegação. A projeção CAT-08 **não importa
automaticamente** os recibos do lote consultivo nem altera conteúdo de AUD,
RuleExecution, score SARI, metodologia ou recomendações já persistidas.


### Identidade HTTPS literal da fonte primária (#603)

Um recibo HMAC válido só pode vincular a alegação a uma URL HTTPS
estruturalmente íntegra: espaços nas extremidades, caracteres de controle
(inclusive TAB/CR/LF descartados silenciosamente por `urlsplit`),
credenciais `userinfo` inclusive vazias (`https://@host`) e
porta inválida são recusados antes de uma classificação documental.
O verificador não faz DNS nem interpreta o host como autoridade pública:
a autenticação independente do emissor e a adequação regulatória
permanecem obrigações externas do revisor. Uma URL inválida torna
**somente aquela alegação** não verificada; não invalida decisões
autenticadas de outras alegações no pacote. Nenhum score, AUD ou CAT-03
é modificado.


## Ligação física facultativa das alegações ao texto da AUD (#603)

O comando `python -m rasai.claim_review_batch --manifest packet/manifest.json
--audit-directory audits/AUD-... --format html` acrescenta uma **verificação
offline de correspondência de texto literal na amostra física**. Com a opção,
cada item do manifesto deve identificar um `snapshot_id` persistido na AUD:

```json
{"claim_id":"C-001","claim_file":"claim.txt","document_file":"conditions.txt",
 "receipt_file":"receipt.json","product_scope":"produto-versao","snapshot_id":"SNP-EXEMPLO"}
```

A ligação exige diretório `AUD-...` idêntico ao rótulo do manifesto;
`audit.db` COMPLETED/COMPLETE sem sidecars, leitura somente imutável,
`snapshot_id` único em todo o banco e pertencente à AUD, e
`main_content_ref` fisicamente existente dentro de `artifacts/`
sem symlink. O texto da alegação deve ocorrer **literalmente** nos bytes UTF-8
do conteúdo principal daquela captura. O consumidor mede SHA-256 dos
bytes SQLite antes/depois e de cada artefato antes/depois da operação,
com limites de leitura, sem alterar os objetos. Resultado por item
`audit_binding.status=TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT` traz
`snapshot_id/page_id/main_content_sha256`; os demais dão NOT_VERIFIED.
Sem selo físico global, o lote inteiro retorna NOT_VERIFIABLE.
Uma assinatura documental válida sobre outro texto não é promovida ao
estado corroborado **daquela AUD** quando a ligação física falha.

Sem `--audit-directory` o fluxo de recibos anterior permanece compatível,
mas o ID da AUD no manifesto continua **um rótulo não autenticado**.
A associação de conteúdo literal NÃO comprova sessão/browser, indexação,
veracidade, vigência contratual, identidade do emissor ou conformidade SUSEP.
O estado assinado continua condicionado a chave privada externa e revisor
autorizado; nenhum segredo ou artefato é gravado no report-catalog e nenhuma
regra BR-GEO/SARI é recalculada. A homologação contra fonte primária vigente
permanece dependência externa da #603.



## Política opt-in de exigência da data de coleta física (20/10/2026)

Para revisão de alegações **materialmente relevantes**, a CLI individual
`rasai.claim_review_import_cli` e a CLI de lote `rasai.claim_review_batch`
aceitam `--require-collection-date`. A opção exige que o recibo assinado
contenha `collected_on` válido (e não posterior à data da revisão).
Um documento cujo recibo omita a data é classificado
`CLAIM_UNVERIFIED_EXTERNAL`, motivo
`PRIMARY_COLLECTION_DATE_NOT_VERIFIED`, mesmo que possua HMAC válido.
Outras alegações completas permanecem independentes no lote.

O lote explicita `document_collection_date_policy=REQUIRED`; o anterior,
que preserva interoperabilidade dos recibos emitidos anteriormente, informa
`LEGACY_OPTIONAL`. **O modo anterior não comprova data de coleta**; não deve ser
usado como aceite de cadeia de custódia documental para alegações reguladas
quando a data for material. A escolha do modo e a atestação da fonte oficial
são atos do operador/revisor autorizado, nunca inferidos da página auditada,
da IA ou do nome do produto. Esta mudança não consulta SUSEP ou qualquer
provedor e não altera CAT-03, AUD, scoring, SARI nem revisão normativa.


## Separacao dos eixos de alegacao observada e revisao oficial

O vinculo opcional `--audit-directory` separa dois estados independentes
por `claim_id`: `audit_observation_state=CLAIM_OBSERVED` somente quando
o texto literal foi confirmado em artefato de snapshot fisico unico da
AUD; e `state` da revisao documental, que permanece
`CLAIM_UNVERIFIED_EXTERNAL` quando a fonte oficial ou o recibo
autenticado nao existe. A ausencia do arquivo do documento ou do recibo
nao apaga a alegacao ja extraida do arquivo local nem constitui prova
de que ela nao apareceu na pagina. Sem opt-in de vinculo a AUD, nenhum
`CLAIM_OBSERVED` fisico e emitido.

A apresentacao consultiva de lote mostra a observacao e a verificacao
em colunas distintas. O caso de snapshot sem texto literal tem
`audit_observation_state=NOT_VERIFIED` e qualquer resultado
documental para aquela AUD e rebaixado para N/D. O resultado continua
independente de CAT-03, calculos de score, M2/M3/M6, Apdex, SARI e
qualquer consulta externa; a data de coleta continua exigida
somente quando a politica `--require-collection-date` foi selecionada.
A prova final contra fonte oficial requer recibo autenticado
de revisor autorizado e permanece gate externo da issue #603.


## Consumidor executivo opt-in sem promocao da fonte primaria

O resumo independente em
`rasai.report_decision_matrix_cli --claim-review-manifest <manifest.json>`
usa o verificador ja existente de lote e a mesma AUD selada, exigindo
`audit_binding_mode=OBSERVATIONAL_BINDING_CHECKED`,
`document_collection_date_policy=REQUIRED`, SHA-256 fisico de
`audit.db` consistente e recibos HMAC por alegacao. Nao ha atalho por
flag `independent_source_authenticity_verified` diretamente aceita de
website ou LLM: somente a cadeia autenticada de revisor e consumidor de
arquivo local ja existente.

O suplemento e um **resumo das alegacoes submetidas**, separado da
matriz canonica de SARI/SEO/CrUX e do CAT-03. Um recibo assinado de
contradicao produz somente a contagem de revisao documental contraditoria
com ressalva expressa de que nao significa erro contratual provado,
descumprimento de regra da SUSEP ou obrigacao juridica. Ausencia de
fonte/recibo ou coleta datada permanece `CLAIM_UNVERIFIED_EXTERNAL`;
sem prova de AUD ou confianca da chave a saida abstem `NOT_VERIFIABLE`
e o comando retorna 2. Nenhum download, consulta paga, score, escrita ou
nova auditoria ocorre; a prova externa de fonte vigente ainda precisa
ser obtida e homologada sob autorizacao separada.


## Encaminhamento estruturado ao responsavel independente

O modelo operacional a encaminhar esta em
`docs/CLAIM_REVIEW_HANDOFF.md`: manifesto por alegacao com
AUD/snapshot/escopo, bytes reais da fonte primaria e recibo
`review` + `mac`. O exemplo vem intencionalmente **nao
assinado e nao verificavel**; a chave e a assinatura pertencem
ao revisor autorizado independente, e o software apenas verifica.
A entrega desse modelo nao fornece fonte externa oficial nem
encerra a issue #603.
