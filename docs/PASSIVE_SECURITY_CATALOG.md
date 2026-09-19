# CAT-10 · Segurança Passiva

**Estado:** contrato de desenvolvimento/pré-produção.

O CAT-10 mede **Web Security Readiness de forma estritamente passiva**. Ele reutiliza evidências já coletadas pelo RASAi, adiciona análise determinística de segurança e, quando possível, cruza identificadores de componentes/versionamento com fontes externas de vulnerabilidade sem executar exploração.

## Princípios obrigatórios

O catálogo **não executa** pentest, exploração, brute force, fuzzing, bypass de autenticação, submissão de formulários, payloads ofensivos, enumeração agressiva, varredura de portas ou validação ativa de CVE.

A ordem causal é:

~~~text
coleta HTTP/browser já existente
  -> fontes externas governadas e não ofensivas
  -> análise determinística CAT-10
  -> sealing de evidência
  -> IA opcional/advisory pelo Improvement Intelligence
  -> projeção HTML read-only
~~~

A IA nunca decide se um header existe, se um cookie possui um atributo, se uma versão foi observada, se um CVE existe ou se uma vulnerabilidade foi explorada. Esses fatos vêm de evidência persistida ou de uma fonte externa identificada. A IA pode explicar impacto, priorização, ordem de implementação, risco de regressão e validação.

## Reuso de dados

O CAT-10 reutiliza, sem nova requisição ao alvo:

- HTTP_RESPONSE, status, URL final e cadeia de redirects;
- HTTP_HEADER;
- HTML bruto/renderizado persistido;
- scripts, recursos, formulários e iframes presentes no HTML;
- page_snapshots.browser_metadata.runtime_diagnostics;
- Lighthouse Best Practices já persistido;
- MDN HTTP Observatory pela coleta canônica de padrões web;
- dados que o Improvement Intelligence já usa no domínio SECURITY.

O relatório não duplica a coleta do MDN Observatory nem repete Lighthouse.

## Análises determinísticas

A implementação cobre:

- HTTPS e downgrade de redirect;
- HSTS;
- CSP, incluindo wildcard, unsafe-inline, unsafe-eval, data:, ausência de object-src/base-uri e framing;
- X-Content-Type-Options;
- Referrer-Policy;
- Permissions-Policy;
- COOP, COEP e CORP;
- CORS observável sem request ativo de Origin;
- atributos de cookies (Secure, HttpOnly, SameSite, Domain, Path);
- mixed content;
- scripts/stylesheet third-party e SRI;
- nonce de script persistido apenas como SHA-256 e reutilização entre snapshots;
- formulários HTTP, formulários sensíveis via GET e destinos third-party;
- iframes third-party sem sandbox;
- exposição passiva de versões em Server, X-Powered-By e meta generator;
- requestfailed, pageerror, console.error e demais diagnósticos de runtime persistidos;
- sinais fortes de detalhe interno em mensagens de runtime;
- identificação conservadora de bibliotecas/versionamento por nome de recurso.

## Vulnerability Intelligence

### OSV

Quando um recurso fornece biblioteca, ecossistema e versão explícita com confiança suficiente, o CAT-10 consulta OSV usando somente package.name, package.ecosystem e version. A URL auditada não é enviada ao OSV pelo CAT-10.

Identificação de biblioteca por filename permanece heurística. Por isso, um advisory retornado por OSV é materializado como POTENTIAL_VULNERABILITY até confirmação por inventário, build, lockfile ou SBOM.

### CISA KEV

CVEs retornados pelo OSV podem ser cruzados com o catálogo CISA Known Exploited Vulnerabilities. KEV=MATCHED aumenta a prioridade operacional, mas não prova que o código vulnerável é alcançável no site auditado.

### MDN HTTP Observatory

O resultado é reutilizado de standards_service_runs e standards_metric_observations. O CAT-10 não dispara um segundo scan.

### TLS externo e Threat Intelligence

O contrato reserva estados explícitos para essas integrações, mas elas permanecem NOT_REQUESTED enquanto não existir uma política canônica de consentimento/privacidade/provider que justifique envio adicional do alvo ou conexão específica. O relatório deve expor essa ausência como cobertura não solicitada, nunca como resultado positivo ou negativo.

## Falhas externas

Falha, timeout ou indisponibilidade de OSV/CISA KEV:

- é persistida em passive_security_integrations;
- reduz a cobertura funcional do CAT-10;
- pode tornar a execução PARTIAL;
- **não cria finding do site**;
- **não é convertida em falha do alvo**.

NO_DATA significa que a integração executada não possuía insumo aplicável, por exemplo ausência de componente com versão suficiente.

A cobertura de Vulnerability Intelligence é derivada do estado real das integrações, não da mera existência de um componente no HTML. O relatório separa inventário de componentes, cobertura OSV e cobertura CISA KEV; OSV desabilitado ou indisponível não pode aparecer como análise de vulnerabilidade "coberta".

## Persistência

Tabelas do CAT-10:

~~~text
passive_security_runs
passive_security_resources
passive_security_components
passive_security_integrations
passive_security_advisories
passive_security_findings
passive_security_remediations
~~~

Cada finding persiste classificação, severidade, confiança, fonte, evidências, contexto first/third-party, impacto, contenção, correção, validação, CWE/CVEs e detalhes técnicos.

Tipos suportados:

~~~text
OBSERVATION
CONFIGURATION_WEAKNESS
EXPOSURE
POTENTIAL_VULNERABILITY
KNOWN_VULNERABILITY
THREAT_REPUTATION
RUNTIME_FAILURE
INFORMATION_DISCLOSURE
~~~

Severidades:

~~~text
CRITICAL
HIGH
MEDIUM
LOW
INFO
~~~

## Cookies, nonces e dados sensíveis

O CAT-10 não copia o valor dos cookies para suas tabelas. O nome do cookie é persistido somente como hash curto para correlação local.

Nonce de script é persistido somente como SHA-256 e comprimento. O valor bruto não é materializado nos findings.

URLs duplicadas no inventário CAT-10 preservam esquema/host/path e estrutura útil, mas parâmetros de query reconhecidos como sensíveis são redigidos antes da persistência, inclusive quando o HTML usa URL relativa. A evidência canônica original permanece na fonte já coletada; o catálogo não cria uma segunda cópia de credenciais ou signed URLs.

Segredos do runtime continuam sujeitos ao secret_safety canônico.

## Improvement Intelligence

Não existe um segundo motor de security por IA.

Quando o operador habilita IA no CAT-10:

- usa a IA principal já configurada;
- usa o mesmo Improvement Intelligence;
- limita os domínios a SECURITY quando CAT-08 não foi solicitado;
- se CAT-08 também estiver ativo, preserva seus domínios e garante SECURITY;
- mantém provider/model/reasoning, custo, attempts, task/round e fallback no runtime canônico;
- não altera SARI/SCORE-GEO.

Os findings determinísticos do CAT-10 são projetados para o domínio SECURITY do Improvement Intelligence.

## Console

Variáveis expostas:

| Variável | Default | Finalidade |
|---|---:|---|
| RASAI_PASSIVE_SECURITY | false | ativa o CAT-10; a seleção do catálogo projeta true somente na execução |
| RASAI_SECURITY_HEADERS | true | HTTPS, redirects, headers, CSP, CORS e cross-origin |
| RASAI_SECURITY_COOKIES | true | atributos de cookies |
| RASAI_SECURITY_RESOURCES | true | scripts, recursos, forms, iframes e mixed content |
| RASAI_SECURITY_THIRD_PARTY | true | classificação first/third-party, SRI e destinos externos |
| RASAI_SECURITY_RUNTIME_CORRELATION | true | correlação de runtime persistido |
| RASAI_SECURITY_OSV | true | OSV para componente/versionamento elegível |
| RASAI_SECURITY_CISA_KEV | true | cruza CVEs com KEV |
| RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS | 15 | timeout por chamada externa de vulnerability intelligence |

A seleção CAT-10 pertence ao plano da auditoria e ao snapshot do AUD; não é convertida em configuração global persistente por efeito colateral.

## SaaS

O contrato SaaS expõe opções secret-free equivalentes:

~~~text
passive_security
security_headers
security_cookies
security_resources
security_third_party
security_runtime_correlation
security_osv
security_cisa_kev
security_external_timeout_seconds
passive_security_ai
~~~

Nenhuma credencial é persistida no job. OSV e CISA KEV não exigem secret no contrato atual.

## HTML

O report-catalog/cat-10.html apresenta resumo e estado, cobertura efetiva, findings por severidade/classificação, rastreabilidade por evidência, recursos e first/third-party, componentes/versionamento identificáveis, Lighthouse Best Practices reutilizado, MDN HTTP Observatory reutilizado, estado de OSV/CISA KEV e demais integrações, e impacto/ contenção/correção/validação de cada finding.

A página é projeção read-only. O HTML não executa coleta, IA ou cálculo de segurança.

## Testes direcionados

Os testes específicos ficam em tests/test_passive_security_catalog.py e cobrem:

- análise passiva sobre evidência persistida;
- ausência de active scanning;
- redaction de cookie/nonce no CAT-10;
- OSV/KEV com somente componente+versão;
- falha externa reduzindo cobertura sem virar finding;
- reuso do mesmo core pelo Improvement Intelligence;
- projeção do plano CAT-10 no console;
- contrato SaaS de IA limitado a SECURITY.
