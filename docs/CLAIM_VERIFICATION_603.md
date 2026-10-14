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
