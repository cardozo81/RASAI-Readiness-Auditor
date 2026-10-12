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


## Relógio da observação SERP (#330)

O registro `serp_observations.collected_at` precisa representar um
instante **com fuso UTC explícito**, incluindo `Z` ou offset
numérico. Data sem horário, timestamp sem offset, valores impossíveis
ou texto vazio não permitem confirmar proveniência cronológica e
bloqueiam a captura **antes de requests públicos**. Quando verificável,
o instante é serializado no manifesto COBS em ISO 8601 normalizado UTC,
sem alterar a observação SERP original.

Essa condição **não** demonstra que a captura HTML e a observação
SERP ocorreram na mesma época, no mesmo idioma, dispositivo ou
população: `temporal_equivalence_proven=false` permanece.


## Revalidação da origem até a publicação (#330)

O SHA-256 e os journals SQLite (`audit.db-wal`, `-shm`,
`-journal`) agora são conferidos **também após uma resposta
não observada** de robots/HTTP e imediatamente antes do
`rename` atômico do COBS, inclusive na reutilização de pacote
existente. Uma AUD que mudou fisicamente enquanto a captura
estava em andamento é rejeitada mesmo que a resposta externa
tenha sido `ROBOTS_DISALLOWED` ou `HTML_NOT_OBSERVED`.
Um journal que apareça depois do preflight também impede
a emissão de manifesto. O staging é descartado em caso de
falha, sem tocar AUD/CONS/RPR.

O digest local demonstra estabilidade dos bytes observados
entre verificações, mas não cria lock transacional com
processos externos. A rotina permanece estritamente
opt-in, isolada e não homologada como aquisição SaaS.


## Captura opcional da URL auditada e confronto estático (#330)

O modo existente `COMPETITOR_CANDIDATE` permanece inalterado:
somente URLs presentes no SERP da própria AUD podem gerar um
manifesto de concorrente `COBS` v1. O modo novo
`--capture-role CUSTOMER` exige **uma única URL exata** na tabela
`audit_targets` da mesma AUD COMPLETE; não exige que esse alvo
apareça nos resultados SERP, pois ausência do alvo no SERP não
impede obter sua página mediante consentimento próprio.

```powershell
python -m rasai.geo_competitor_capture_bundle_330 `
  --audit-dir .\audits\AUD-EXEMPLO `
  --serp-observation-id SERP-EXEMPLO `
  --candidate-url https://cliente.example.org/pagina `
  --capture-role CUSTOMER `
  --output-root .\evidencias-competitivas `
  --consent-host cliente.example.org `
  --allow-public-html-requests
```

O resultado do alvo possui contrato separado
`RASAI-COMPETITOR-CAPTURE-SIDECAR-330-002`, além de prova
local da identidade da URL auditada e indicação explícita se
ela constava ou não em `serp_results`. O v1 dos concorrentes,
seus IDs e manifestos previamente publicados permanecem iguais.

Com ambos os sidecars já obtidos (do alvo e de um concorrente),
uma comparação **puramente offline e descritiva** pode ser feita
sem novas consultas HTTP, IA ou alterações na AUD:

```powershell
python -m rasai.geo_competitor_pair_330 `
  --audit-dir .\audits\AUD-EXEMPLO `
  --customer-manifest .\evidencias-competitivas\COBS-ALVO\manifest.json `
  --competitor-manifest .\evidencias-competitivas\COBS-CONCORRENTE\manifest.json
```

A função recusa pares com AUD física/hash divergentes,
`observation_id`/consulta/escopo SERP diferentes, URLs do
mesmo hostname, papéis ausentes, hashes de pacote adulterados,
HTML não observado sob consentimento, relógio inválido ou
capturas separadas por mais de 24h. A saída indica
títulos, headings, tipos JSON-LD e contagem de palavras
**observadas no HTML estático**, mas não transforma diferença
de volume ou de metadados em lacuna de conteúdo principal,
recomendação comercial, diagnóstico SEO/Apdex ou causalidade
GEO. A equivalência de idioma, dispositivo, intenção,
população e renderização permanece não comprovada.

Captura HTTP exige autorização explícita e respeito a
robots.txt; **comparação de manifests não acessa a rede**.
Nenhum conteúdo HTML bruto, sessão individual ou token
de terceiros é gravado. A etapa de comparação profunda
com renderização equivalente permanece pendente e, sem
evidência, deve aparecer N/D.


## Autorização adicional no COBS live (12/10/2026)

Antes de qualquer DNS/HTTP, a captura de HTML exige a finalidade
compatível com `--capture-role` e as duas operações GET
individualmente consentidas. Exemplo para concorrente:
`--consent-purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW`
`--consent-operation GET_ROBOTS_TXT`
`--consent-operation GET_STATIC_HTML`.
Para a URL do cliente, usar
`--consent-purpose AUD_CUSTOMER_STATIC_CONTENT_REVIEW`.
Os antigos comandos sem o escopo explícito param antes da rede.

A versão do COBS não muda porque o controle se limita à autorização
pré-fetch, sem reescrever manifests ou snapshots já persistidos.
A finalidade não é evidência assinada de consentimento histórico; não
homologa coleta automática, egress SaaS ou integração com o pipeline.


## CLI pública para a captura COBS

`rasai competitor-capture` encaminha os argumentos ao
materializador versionado isolado sem acionar o motor de auditoria.
Além dos parâmetros de `python -m
rasai.geo_competitor_capture_bundle_330`, permanecem obrigatórios
`--allow-public-html-requests`, `--consent-host` exato,
`--consent-purpose` compatível com o papel, e ambas as flags
`--consent-operation`. O comando não retira as proteções de
proveniência SERP/AUD nem grava em `audit.db`.


## Identidade do concorrente versus alvo físico da AUD (12/10/2026)

A presença na SERP da mesma observação **não basta** para declarar
uma URL como fonte concorrente: quando existe um único alvo físico
`audit_targets.input_url` para esta AUD, e sua URL canônica é exatamente
a candidata, a captura `role=COMPETITOR_CANDIDATE` é recusada **antes de
qualquer DNS/HTTP**. A URL do próprio cliente somente pode ser tratada
pela trilha `role=CUSTOMER`, que mantém as verificações próprias de
identidade. URLs distintas e efetivamente observadas na SERP mantêm o
fluxo anterior; a comparação posterior ainda aplica critérios de
hostname, período e proveniência. Sem alvo único comprovado, este
controle adicional não inventa uma identidade nem homologa a
comparabilidade. Testes SQLite físicos positivos/negativos sem
requisições comerciais, banco original intacto.
