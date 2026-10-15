# Verificação documental de alegações comerciais (#603)

## Fronteira de confiança

`rasai.claim_source_verification_603.classify_claim` é um contrato determinístico offline de revisão, sem rede, sem alteração no audit.db e sem alegar conformidade SUSEP ou certificação. **O relatório da AUD permanece em `CLAIM_UNVERIFIED_EXTERNAL`** quando não houver comprovação independente da fonte primária. Link, título, PDF não aberto, metadados autodeclarados da página auditada ou resultado de IA **não autorizam** `CLAIM_CORROBORATED`.

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

O módulo `claim_review_receipt_603.verify_claim_review_receipt` exige um recibo de revisão **assinado via HMAC-SHA256**, uma chave de verificação confiável com ao menos 32 bytes obtida exclusivamente de contexto privado do operador/revisor e uma lista de identificadores de revisores autorizados. Assina-se a serialização JSON canônica de **todos** os campos permitidos (hash do documento, escopo/produto, claim literal, data/vigência, URL, emissor, versão, trecho correspondente, decisão e revisor/recibo). Qualquer alteração, assinatura inválida, campo inesperado ou revisor não autorizado devolve `CLAIM_UNVERIFIED_EXTERNAL` sem promover o resultado.

Esse módulo **somente verifica** o MAC de recibos criados por um sistema **independente e autorizado**. Ele não fornece função de assinatura pública nem extrai chave de ambientes auditados. Não deve ser chamado por código que aceite `trusted_key` ou `trusted_reviewer_ids` do website auditado, JSON de LLM ou da mesma solicitação externa. A credencial não é persistida nem exibida; a validação é local e offline. Um recibo autêntico prova apenas que o emissor confiável atestou aquela revisão; não comprova por si só legitimidade da entidade SUSEP ou conformidade jurídica. A autenticação inicial do revisor e da fonte primária permanece dependência externa antes de promover qualquer claim do relatório.

O contrato de classificação anterior permanece disponível para testes e consumidores internos, **mas não deve receber diretamente dados não confiáveis com `independent_source_authenticity_verified=True`**. Integradores devem ingressar por esta etapa autenticada. Nenhum relatório atual é automaticamente enriquecido ou reescrito.
