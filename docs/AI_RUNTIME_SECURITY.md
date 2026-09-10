# Segurança e retenção da telemetria de IA

A telemetria de comunicação com provedores de IA existe para rastreabilidade técnica da auditoria. Ela não é uma nova fonte de evidência de scoring.

## Dados registrados

`ai_exchange_log` pode conter o payload sanitizado efetivamente enviado ao provider e o envelope/resposta sanitizado recebido, além de metadados de execução, provider, modelo, finalidade, duração, status, hashes e indicação de truncamento.

Como o request pode carregar texto ou evidência da página auditada, o banco `AUD-*/audit.db` e o mini-site HTML devem ser tratados como artefatos potencialmente sensíveis do cliente.

## Dados proibidos

O recorder não deve persistir headers de autenticação. Campos identificados como API key, authorization, password, access/refresh token, client secret ou bearer são redigidos. Query parameters reconhecidos como segredo também são redigidos.

Campos reconhecidos como raciocínio privado/interno do provider não são persistidos.

## Interpretação editorial transitória

A saída `content_context_interpretation` usada para explicar campos editoriais configurados como `auto` é extraída em memória e redigida do exchange log persistido. Ela não cria classificação canônica em `audit.db`; sua forma legível é materializada apenas no HTML final da execução.

## Limite de captura

`RASAI_AI_EXCHANGE_LOG_MAX_BYTES` controla o limite por lado da comunicação. O default é 512 KiB e o runtime limita o valor entre 4 KiB e 4 MiB. Payloads maiores são truncados para apresentação/persistência, mantendo hash do conteúdo sanitizado completo observado pelo recorder.

## Governança

A retenção do log acompanha a retenção do workspace da auditoria. Em implantação SaaS, acesso ao exchange log deve obedecer ao mesmo tenant/workspace/project/property e RBAC aplicados aos demais artefatos de auditoria; ele não deve ser exposto entre organizações ou workspaces.
