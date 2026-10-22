# #330 - Consulta HTML pública isolada, com consentimento e robots.txt

Módulo local **opcional**, separado do coletor homologado:
`python -m rasai.geo_competitor_fetch`. Não é ativado no pipeline,
não grava banco de AUD, não chama LLM nem substitui o consumidor read-only
`geo_competitor_content_provenance`.

Requer `--allow-public-html-requests`, `--consent-host` com **hostname exato**
para cada URL, query única e papel `CUSTOMER` ou `COMPETITOR_CANDIDATE`.
Consulta a política `/robots.txt` do mesmo host ANTES da página HTML;
robot inválido, inacessível, diferente de `text/plain`, sem regra aplicável
ou com `Disallow` interrompe a página. Comportamento conservador:
robots ausente ou erro de rede -> N/D, sem presumir autorização implícita.

Transporte padrão local: `PublicWebFetcher` com adaptador exclusivo
`PublicWebPinnedOpener`, revalidando os endereços DNS públicos no próprio
limite de conexão. O TCP é estabelecido para **IP numérico público fixado**
(e nunca para o hostname sujeito a nova resolução); o nome de origem continua
sendo o Host HTTP, o SNI TLS e a identidade exigida pelo certificado
(`ssl.create_default_context`, verificação habilitada). Não usa proxy
por ambiente. HTTPS/HTTP, GET único da política e no máximo um GET do HTML,
2 MiB por resposta, 10 s por request, **zero redirects**, sem retries. Redirects são
deliberadamente rejeitados em vez de visitar páginas cuja política
robots e consentimento ainda não foram checados. O programa não executa
JavaScript e não lê cookies/sessões. Sem argumento de opt-in não realiza
HTTP nem DNS.

Exemplo de diagnóstico **com rede e autorização explícita**:

```powershell
python -m rasai.geo_competitor_fetch `
  --url https://www.exemplo-publico.com/pagina `
  --query "seguro de vida" `
  --role COMPETITOR_CANDIDATE `
  --consent-host www.exemplo-publico.com `
  --allow-public-html-requests
```

A saída JSON informa resultado de robots, timestamp UTC **somente da
tentativa de HTML**, URL final efetivamente obtida, status HTTP,
hash SHA-256 do corpo e atributos HTML transitórios. Ainda NÃO são
persistidos em `audit.db`: o status `TRANSIENT_STATIC_HTML_FEATURES`
não equivale a evidência de AUD nem prova conteúdo principal.
`primary_content_proven=false` independentemente do resultado.
Menus, título e shell SPA podem apresentar termos de consulta sem conteúdo
carregado; um documento estático não prova hidratação final.
Não informa market/locale, device, sampling, ranking, qualidade ou causa.

Segurança: no transporte padrão, a segunda validação DNS imediatamente
antes de abrir o socket e a conexão ao IP numérico validado eliminam a
resolução implícita na janela DNS-rebinding entre preflight e TCP.
Respostas DNS com qualquer IP não público são recusadas; o certificado TLS
continua validado pelo hostname original. `egress_transport_status` informa
`PINNED_PUBLIC_IP_TLS_HOSTNAME_CHECK` no transporte padrão ou
`INJECTED_TRANSPORT_NOT_EGRESS_ATTESTED` para transportes injetados,
que não permitem afirmar bloqueio de rebinding.

Esta proteção **não é homologação de egress SaaS**: falta política de rede
externa de defesa em profundidade, auditoria de consentimento por finalidade,
limites de consumo acumulado e evidência operacional. Não ativar este
adaptador automaticamente no pipeline. Nenhuma utilização comercial ou HTTP
externo faz parte dos testes;
os cenários de robots, bloqueio, redirect, ausência de consentimento,
resposta SPA e limites usam fake de transporte em memória.

**Critério restante para encerrar #330:** persistência opcional versionada
de coleta segura e consentida, política temporal/cookies/localidade,
confronto renderizado com uma AUD autorizada e aceite de proveniência real.


## Consentimento específico por finalidade e operação (#330)

O fluxo live local requer, além de `--allow-public-html-requests` e
`--consent-host` com hostname exato, dois escopos explícitos:
a finalidade `--consent-purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW`
para concorrente ou `AUD_CUSTOMER_STATIC_CONTENT_REVIEW` para
a própria URL auditada; e ambas as operações individuais
`--consent-operation GET_ROBOTS_TXT` e
`--consent-operation GET_STATIC_HTML`.

Ausência de finalidade, operação, role coerente ou hostname gera
recusa antes de qualquer resolução DNS ou requisição HTTP. Não há
consentimento curinga, POST, redirect, JavaScript ou crawling adicional.
O gate abrange também o materializador opcional COBS que delega a
essa mesma função. Esta etapa **não** altera contratos versionados
de artefatos: os flags de autorização são verificados no limite de
rede, mas não constituem registro de consentimento assinado,
revogação ou governança de egress SaaS.


## CLI pública de captura HTML (12/10/2026)

`rasai competitor-html-review` despacha para este módulo **antes**
dos instaladores de auditoria, integração, provedor ou segredos.
Continua exigindo as mesmas flags explícitas de autorização:
hostname, papel, finalidade, duas operações GET e autorização de
requisições públicas. Exemplo:

```powershell
rasai competitor-html-review --url https://example.com/pagina `
  --query "seguro de vida" --role COMPETITOR_CANDIDATE `
  --consent-host example.com `
  --consent-purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW `
  --consent-operation GET_ROBOTS_TXT `
  --consent-operation GET_STATIC_HTML `
  --allow-public-html-requests
```

Não faz parte de uma AUD automática e não coleta nada se faltar
consentimento. O retorno é inventário efêmero, não prova de
renderização SPA nem autorização legal do destino.

## Consentimento local durável e revogável (20/10/2026)

O modo opt-in permanece baseado em hostname **exato**, papel, finalidade
e as duas operações GET já aprovadas. Agora o operador pode optar por
um registro local de eventos com concessão temporária de até 90 dias,
revogação expressa e verificação offline **antes de qualquer DNS/HTTP**:

```powershell
python -m rasai.geo_competitor_consent `
  --registry .\consent-cobs.json --host competitor.example.org `
  --role COMPETITOR_CANDIDATE `
  --purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW `
  --action GRANT --expires-at 2026-11-10T00:00:00+00:00 --confirm
python -m rasai.geo_competitor_consent `
  --registry .\consent-cobs.json --host competitor.example.org `
  --role COMPETITOR_CANDIDATE `
  --purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW --action REVOKE --confirm
```

Para aplicar essa política local ao diagnóstico/captura, informar
`--consent-registry .\consent-cobs.json` **além de**
`--allow-public-html-requests`, `--consent-host`,
`--consent-purpose` e ambas as `--consent-operation`. A opção
`--consent-registry` é opt-in; sem ela, os flags explícitos já existentes
continuam válidos, e um registro de consentimento não é imposto
retroativamente. Quando informada, registro ausente, expirado, corrupto,
com chave JSON duplicada ou revogado nega a coleta. A política é
revalidada após robots e antes do GET de HTML; a captura COBS valida
novamente antes de publicar um pacote derivado. Revogação não apaga
artefatos capturados anteriormente e não cancela requisições já iniciadas.

O arquivo JSON v1 é limitado a 512 eventos e 256 KiB, inclui sequência,
papel, finalidade, tempo UTC, expiração e encadeamento de SHA-256, com
gravação atômica e lock exclusivo local. O hash detecta alterações sem
recomputação, mas **não autentica o operador**: quem pode reescrever
o registro pode reencadear os hashes. Não equivale a licença, assinatura,
consentimento jurídico ou enforcement SaaS multi-instância.
Não armazenar o arquivo dentro de AUD/CONS/RPR. Coleta de HTML JS,
SPA hidratada, cookie/login e egress gerenciado continuam **não
implementados**, logo nenhum resultado estático pode ser promovido
a prova de conteúdo principal. Não executar URL externa sem autorização
independente do proprietário.


## Replay OCI opcional para JavaScript inline, sem rede adicional

O inspetor de HTML consentido e o materializador COBS aceitam as flags
--offline-inline-js-replay e --replay-device desktop|mobile. Permanecem
obrigatorios hostname exato, finalidade, GET_ROBOTS_TXT, GET_STATIC_HTML
e --allow-public-html-requests. O replay so recebe a resposta HTML
previamente autorizada; nao autoriza downloads de JavaScript, CSS,
imagens nem novas requisicoes HTTP. Scripts externos nao fornecidos,
redirecionamentos, falta de materialidade e instabilidade geram N/D.

O Chromium reutiliza o worker OCI arquitetural sem modificacao do
seu contrato: imagem local identificada por digest, canarios de isolamento
e browser, --network=none, sem mounts, sem privilegios, com CPU/memoria
limitadas, root read-only e timeout. CSP original e preservada.
Instalar Docker nao e requisito do fluxo HTTP estatico existente; sem
imagem local o suplemento retorna OCI_IMAGE_NOT_AVAILABLE.

O campo opcional capture.offline_js_advisory contem versao
RASAI-COBS-NETWORKLESS-INLINE-REPLAY-1, hashes da resposta HTML
original e do DOM isolado quando estabilizado, device, motivo de
abstencao, additional_public_http_requests=0 e audit_writes=0.
Mesmo INLINE_DOM_STABLE_IN_OCI significa apenas que o HTML coletado
pode materializar DOM no replay offline com os recursos ja disponiveis.
Nao comprova hidratacao live, conteudo editorial real, equivalencia
a SERP por device/mercado/tempo, ranking, indexacao ou citacao gerativa.

A comparacao COBS continua exclusivamente estatica e ignora este
suplemento. primary_content_proven e content_comparison_eligible
continuam false; nao se alteram AUD, SARI, SCORE-GEO, Apdex, IA,
CONS ou relatórios selados. O aceite externo da issue permanece aberto.

Exemplo do opt-in, a executar somente com autorizacao externa
independente para os dois GET:

    python -m rasai.geo_competitor_capture_bundle
      --audit-dir .\audits\AUD-EXEMPLO
      --serp-observation-id SERP-EXEMPLO
      --candidate-url https://exemplo.org/pagina
      --output-root .\evidencias-cobs
      --consent-host exemplo.org
      --consent-purpose GEO_COMPETITOR_STATIC_CONTENT_REVIEW
      --consent-operation GET_ROBOTS_TXT
      --consent-operation GET_STATIC_HTML
      --allow-public-html-requests
      --offline-inline-js-replay --replay-device desktop

O exemplo representa parametros da mesma chamada, e nao comandos
independentes por linha.


## Bundle de recursos JS/CSS ja existente, sem novas chamadas

O replay OCI pode receber recursos locais que o operador **ja possua**
e tenha direito de usar, com --offline-resource-bundle ARQUIVO.json
em conjunto com --offline-inline-js-replay --replay-device desktop|mobile.
Nao ha descoberta HTTP automatica, bypass de robots, obtencao de
arquivos do site, acesso a CDN ou coleta de recursos por esta flag.
O bundle e lido antes do primeiro DNS/HTTP; se invalido, falha fechada.

Formato exato do arquivo local, criado fora dos pacotes AUD/CONS/RPR:

    {
      "contract_version": "RASAI-COBS-ISOLATED-ASSET-BUNDLE-1",
      "target_url": "https://example.org/catalog",
      "resources": [
        {
          "url": "https://example.org/scripts/app.js",
          "content_type": "application/javascript",
          "sha256": "<SHA256_HEXADECIMAL_64>",
          "body_b64": "<BASE64_DOS_BYTES_JA_OBTIDOS>"
        }
      ]
    }

Preencher hashes e bytes reais, nao os placeholders. A URL do bundle
deve ser a mesma URL canonica do HTML previamente consentido.
Sao aceitos somente **recursos exatos e da mesma origem HTTP(S)**,
sem credenciais, URL duplicada, redirects ou origem CDN externa.
Maximo: 16 arquivos e 2 MiB agregados, bundle JSON ate 3,2 MB,
apenas MIME permitido (JavaScript, CSS, JSON, imagens, fontes).
Base64, SHA-256, duplicidade de chaves JSON, bytes/mtime e identidade
do descritor local sao conferidos, com leitura read-only.
Recurso ausente, bloqueado pela CSP ou requisitado dinamicamente por
JavaScript continua N/D; nunca aprovar hidratacao total por inferencia.

O hash do bundle e integridade **local**, nao assinatura de origem,
autenticacao do provedor ou atestado de consentimento anterior.
O suplemento nunca promove fonte nao autenticada:
offline_asset_provenance_attested=false,
live_site_hydration_proven=false,
live_primary_content_proven=false e
same_serp_device_or_population_proven=false.
A comparacao COBS antiga segue estritamente estatica.

A auditoria fisica em sites de terceiros, a equivalencia de locale,
device, periodo/mercado, a consulta SERP original e a verificacao
autorizada de recursos faltantes permanecem gates separados.
A ausencia de recursos da SPA gera abstencao e **nao** autorizacao
para adquiri-los por novos GETs.


## Inventario lexical offline do DOM produzido no OCI (22/10/2026)

Quando o replay de SPA ja autorizado retorna `INLINE_DOM_STABLE_IN_OCI`,
o mesmo resultado JSON inclui `offline_js_advisory.isolated_lexical_inventory`.
O processamento reutiliza os **mesmos bytes HTML** e o DOM retornado pelo
worker isolado, sem browser extra, DNS, fetch de assets, nova amostra, coleta
de provedor, escrita na AUD ou persistencia do DOM. Dois inventarios
delimitados (`static_html` e `isolated_dom`) exibem contagem de palavras
do HTML observado, title, descricao, amostra de headings e tipos JSON-LD,
com marcadores de truncamento. A diferenca `observed_word_count_delta`
representa **apenas a alteracao lexical nesta reproducao local**.

O contrato `RASAI-COBS-NETWORKLESS-LEXICAL-INVENTORY-1` retorna explicitamente
`content_readiness_proven=false`, `live_site_hydration_proven=false`,
`primary_content_proven=false`, `semantic_or_editorial_gap_proven=false`
e `same_serp_population_proven=false`. O DOM OCI nao comprova a pagina
ao vivo, o conteudo principal de crawler, equivalencia por locale/device,
ranking ou citacao gerativa. Se o replay estiver bloqueado, inconclusivo ou
nao habilitado, `isolated_lexical_inventory=null`. Os mecanismos de
consentimento, robots, no-redirect, isolamento, CSP e abstencao continuam
inalterados.

Esta entrega reduz a lacuna de **interpretacao do replay ja disponivel**;
nao encerra o requisito maior de captura SPA fisica autorizada e comparacao
de fontes em coorte externa equivalente da #330.
