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
