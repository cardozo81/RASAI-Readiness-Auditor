# #330 - Consulta HTML pública isolada, com consentimento e robots.txt

Módulo local **opcional**, separado do coletor homologado:
`python -m rasai.geo_competitor_fetch_330`. Não é ativado no pipeline,
não grava banco de AUD, não chama LLM nem substitui o consumidor read-only
`geo_competitor_content_provenance_330`.

Requer `--allow-public-html-requests`, `--consent-host` com **hostname exato**
para cada URL, query única e papel `CUSTOMER` ou `COMPETITOR_CANDIDATE`.
Consulta a política `/robots.txt` do mesmo host ANTES da página HTML;
robot inválido, inacessível, diferente de `text/plain`, sem regra aplicável
ou com `Disallow` interrompe a página. Comportamento conservador:
robots ausente ou erro de rede -> N/D, sem presumir autorização implícita.

Transporte: `PublicWebFetcher` com preflight de DNS público, HTTPS/HTTP,
GET único da política e no máximo um GET do HTML, 2 MiB por resposta,
10 s por request, **zero redirects**, sem retries. Redirects são
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

Segurança: checagem DNS em userspace não impede DNS rebinding/TOCTOU em
ambiente servidor. NÃO oferecer este adaptador em SaaS sem proxy de egress
com binding de IP, limitação de domínios e auditoria de consentimento.
Nenhuma utilização comercial ou HTTP externo faz parte dos testes;
os cenários de robots, bloqueio, redirect, ausência de consentimento,
resposta SPA e limites usam fake de transporte em memória.

**Critério restante para encerrar #330:** persistência opcional versionada
de coleta segura e consentida, política temporal/cookies/localidade,
confronto renderizado com uma AUD autorizada e aceite de proveniência real.
