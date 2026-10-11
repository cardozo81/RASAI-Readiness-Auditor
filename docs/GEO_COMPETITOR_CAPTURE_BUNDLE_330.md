# #330 - Manifesto de captura competitiva vinculado à SERP

O adaptador `python -m rasai.geo_competitor_capture_bundle_330`
reutiliza o consumidor de HTML público com consentimento e robots.txt
da #330, mas adiciona uma **saída local versionada e separada**. Nunca
escreve na AUD original nem ativa o relatório produtivo GEO/CONS.

## Condições anteriores à coleta

- `--allow-public-html-requests`, hostname exato em `--consent-host`,
  AUD física única `COMPLETED/COMPLETE`, sem sidecars SQLite em aberto,
  e `serp_observations` de mesma AUD, `OBSERVED_API/OBSERVED`.
- Observação SERP tem `observation_id` único, query textual inequívoca,
  instante de observação e escopo `engine/country/region/language/device`.
  A URL concorrente solicitada precisa estar na própria tabela
  `serp_results` dessa observação; não basta aparecer em snippet.
- Antes de qualquer HTTP, o consumidor verifica o SHA-256 físico da
  base de AUD, limitada a 256 MiB. Depois da consulta opcional
  (robots.txt + HTML sem redirects, até 2 MiB por chamada), verifica
  novamente a base. Alteração durante a captura impede persistência.
- Bloqueio de robots, erro HTTP, URL insegura, HTML ausente, tentativa
  de gravar dentro da AUD ou qualquer falha de contexto não criam
  manifesto comparável. O diretório `--output-root` é explicitamente
  distinto da AUD; as fontes não são migradas nem regravadas.

## Artefato gerado

`output_root/COBS-<fingerprint>/manifest.json` retém somente os
metadados públicos observados, não a página HTML integral. Inclui
SHA-256 dos bytes de `audit.db`, IDs da AUD e observação SERP,
query, escopo, instante SERP, URL solicitada/final, status de robots,
instante da coleta HTML, código HTTP, hash de conteúdo, título,
atributos textuais e limitações. A publicação é feita em staging
com rename, e a mesma evidência produz o mesmo pacote; manifesto
existente divergente nunca é sobrescrito.

**Limitação obrigatória:** `content_comparison_eligible=false`,
`primary_content_proven=false`, equivalência de idioma/dispositivo/
época `false`. A consulta HTTP estática não prova renderização
JavaScript/SPA, conteúdo principal, alinhamento temporal, intenção
de negócio, presença em respostas gerativas nem relação causal de
ranking. O HASH autentica a origem local *naquele instante*, não a
veracidade da resposta do provedor externo. Dados capturados podem
requerer descarte conforme política operacional de retenção.

Exemplo opt-in, que faz requests públicos quando executado:

```powershell
python -m rasai.geo_competitor_capture_bundle_330 `
  --audit-dir .\audits\AUD-EXEMPLO `
  --serp-observation-id SERP-EXEMPLO `
  --candidate-url https://concorrente.exemplo.br/produto `
  --output-root .\evidencias-competitivas `
  --consent-host concorrente.exemplo.br `
  --allow-public-html-requests
```

A CI usa mocks; nenhum request público ou comercial foi realizado
para esta implementação. Ainda não existe integração do pacote COBS
ao schema canônico da AUD, mecanismo de consentimento auditável SaaS,
proxy de egress anti-DNS-rebinding, locale/device de renderização ou
aceite humano da comparabilidade. A issue #330 permanece OPEN.

## Isolamento transversal de pacotes (#330, correção)

O bloqueio do diretório de saída não se limita mais à AUD de origem:
`--output-root` precisa estar fora de **todas** as pastas com
identidade física `AUD-*`, `CONS-*` e `RPR-*`, inclusive quando
algum componente do caminho é relativo (`..`) ou passa por link
simbólico ancestral. Uma captura autorizada **nunca** pode escrever
em artefatos de outra auditoria ou em pacotes de consolidação/
reprocessamento. A verificação ocorre antes de qualquer chamada HTTP
e não cria diretórios quando a saída é insegura. Diretórios irmãos
dedicados à evidência `COBS-*` continuam elegíveis.
