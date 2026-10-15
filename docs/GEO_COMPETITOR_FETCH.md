# #330 - Consulta HTML pública isolada, com consentimento e robots.txt

Módulo local **opcional**, separado do coletor homologado:
`python -m rasai.geo_competitor_fetch_330`. Não é ativado no pipeline,
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
python -m rasai.geo_competitor_fetch_330 `
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
