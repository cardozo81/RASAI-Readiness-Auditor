# CAT-10 · Segurança Passiva

**Estado:** contrato de desenvolvimento/pré-produção.

O CAT-10 mede **prontidão de segurança web de forma estritamente passiva**. Ele reutiliza evidências já coletadas pelo RASAi, adiciona análise determinística de segurança e, quando possível, cruza identificadores de componentes/versionamento com fontes externas de vulnerabilidade sem executar exploração.

## Compromisso funcional do CAT-10

O CAT-10 se compromete a **avaliar postura de segurança web observável por meios passivos**, com rastreabilidade suficiente para distinguir fato, correlação, limitação e orientação.

O contrato vigente deve:

- reutilizar HTTP, headers, HTML, navegador/runtime, recursos e demais evidências já coletadas quando aplicáveis, sem duplicar coleta desnecessariamente;
- avaliar deterministicamente transporte/redirecionamentos, headers e políticas, cookies, mixed content, formulários/iframes, recursos próprios e de terceiros e demais sinais implementados pelo contrato;
- identificar componentes/versões somente quando houver evidência observável e registrar a confiança/limitação da identificação;
- correlacionar componentes elegíveis com OSV e CISA KEV conforme o contrato de privacidade e minimização de dados;
- reutilizar MDN HTTP Observatory já persistido, sem disparar nova varredura durante a renderização;
- materializar achados com severidade/classificação, evidência, impacto, contenção/correção e forma de validação;
- expor estado e cobertura das integrações, distinguindo `NOT_REQUESTED`, indisponibilidade externa, ausência de dado e ausência de finding;
- permitir enriquecimento advisory por IA somente depois da evidência determinística estar disponível.

O CAT-10 **não se compromete** a:

- executar pentest, exploração, força bruta, fuzzing, bypass, payload ofensivo, enumeração agressiva ou varredura de portas;
- provar explorabilidade de um CVE apenas porque pacote/versão foi correlacionado;
- declarar ausência de vulnerabilidades a partir de ausência de evidência;
- tratar indisponibilidade de OSV, CISA KEV ou Observatory como vulnerabilidade do site;
- transformar sugestão de IA em fato determinístico;
- alterar `SARI-001`/`SCORE-GEO-004` por conta própria.

Portanto, **sem achados no CAT-10** significa somente que nenhum finding foi sustentado pelo universo passivamente observado e pelas integrações efetivamente disponíveis. Não significa certificação de segurança.

## Princípios obrigatórios

O catálogo **não executa** pentest, exploração, força bruta, fuzzing, bypass de autenticação, submissão de formulários, payloads ofensivos, enumeração agressiva, varredura de portas ou validação ativa de CVE.

A ordem causal é:

~~~text
coleta HTTP/browser já existente
  -> fontes externas governadas e não ofensivas
  -> análise determinística CAT-10
  -> sealing de evidência
  -> IA opcional/advisory pelo Improvement Intelligence
  -> projeção HTML read-only
~~~

A IA nunca decide se um cabeçalho existe, se um cookie possui um atributo, se uma versão foi observada, se um CVE existe ou se uma vulnerabilidade foi explorada. Esses fatos vêm de evidência persistida ou de uma fonte externa identificada. A IA pode explicar impacto, priorização, ordem de implementação, risco de regressão e validação.

## Reuso de dados

O CAT-10 reutiliza, sem nova requisição ao alvo:

- HTTP_RESPONSE, status, URL final e cadeia de redirects;
- HTTP_HEADER;
- HTML bruto/renderizado persistido;
- scripts, recursos, formulários e iframes presentes no HTML;
- page_snapshots.browser_metadata.runtime_diagnostics;
- Lighthouse Melhores Práticas já persistido;
- MDN HTTP Observatory pela coleta canônica de padrões web;
- dados que a Análise Profunda já usa no domínio técnico `SECURITY`.

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
- scripts/folhas de estilo externos e SRI;
- nonce de script persistido apenas como SHA-256 e reutilização entre snapshots;
- formulários HTTP, formulários sensíveis via GET e destinos externos;
- iframes externos sem sandbox;
- exposição passiva de versões em Server, X-Powered-By e meta generator;
- requestfailed, pageerror, console.error e demais diagnósticos de runtime persistidos;
- sinais fortes de detalhe interno em mensagens de runtime;
- identificação conservadora de bibliotecas/versionamento por nome de recurso.

## Vulnerability Intelligence

### OSV

Quando um recurso fornece biblioteca, ecossistema e versão explícita com confiança suficiente, o CAT-10 consulta OSV usando somente package.name, package.ecosystem e version. A URL auditada não é enviada ao OSV pelo CAT-10.

Identificação de biblioteca por nome de arquivo permanece heurística. Por isso, um aviso de segurança retornado por OSV é materializado como POTENTIAL_VULNERABILITY até confirmação por inventário, compilação, arquivo de dependências travadas (lockfile) ou SBOM.

### CISA KEV

CVEs retornados pelo OSV podem ser cruzados com o catálogo CISA Known Exploited Vulnerabilities. KEV=MATCHED aumenta a prioridade operacional, mas não prova que o código vulnerável é alcançável no site auditado.

### MDN HTTP Observatory

O resultado é reutilizado das tabelas técnicas `standards_service_runs` e `standards_metric_observations`. O CAT-10 não dispara um segunda varredura.

### TLS externo e Threat Intelligence

O contrato reserva estados explícitos para essas integrações, mas elas permanecem NOT_REQUESTED enquanto não existir uma política canônica de consentimento/privacidade/provider que justifique envio adicional do alvo ou conexão específica. O relatório deve expor essa ausência como cobertura não solicitada, nunca como resultado positivo ou negativo.

## Falhas externas

Falha, timeout ou indisponibilidade de OSV/CISA KEV:

- é persistida em passive_security_integrations;
- reduz a cobertura funcional do CAT-10;
- pode tornar a execução PARTIAL;
- **não cria achado do site**;
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

Cada achado persiste classificação, severidade, confiança, fonte, evidências, contexto de próprio domínio/externo, impacto, contenção, correção, validação, CWE/CVEs e detalhes técnicos.

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

Nonce de script é persistido somente como SHA-256 e comprimento. O valor bruto não é materializado nos achados.

URLs duplicadas no inventário CAT-10 preservam esquema/host/path e estrutura útil, mas parâmetros de query reconhecidos como sensíveis são redigidos antes da persistência, inclusive quando o HTML usa URL relativa. A evidência canônica original permanece na fonte já coletada; o catálogo não cria uma segunda cópia de credenciais ou signed URLs.

Segredos do runtime continuam sujeitos ao secret_safety canônico.

## Improvement Intelligence

Não existe um segundo motor de security por IA.

Quando o operador habilita IA no CAT-10:

- usa a IA principal já configurada;
- usa o mesmo Improvement Intelligence;
- limita os domínios a SECURITY quando CAT-08 não foi solicitado;
- se CAT-08 também estiver ativo, preserva seus domínios e garante SECURITY;
- mantém provedor/modelo/esforço de raciocínio, custo, tentativas, tarefa/rodada e fallback no runtime canônico;
- não altera SARI/SCORE-GEO.

Os achados determinísticos do CAT-10 são projetados para o domínio SECURITY do Improvement Intelligence.

## Console

Variáveis expostas:

| Variável | Default | Finalidade |
|---|---:|---|
| RASAI_PASSIVE_SECURITY | false | ativa o CAT-10; a seleção do catálogo projeta true somente na execução |
| RASAI_SECURITY_HEADERS | true | HTTPS, redirecionamentos, cabeçalhos, CSP, CORS e políticas entre origens |
| RASAI_SECURITY_COOKIES | true | atributos de cookies |
| RASAI_SECURITY_RESOURCES | true | scripts, recursos, formulários, iframes e conteúdo misto |
| RASAI_SECURITY_THIRD_PARTY | true | classificação de próprio domínio/externo, SRI e destinos externos |
| RASAI_SECURITY_RUNTIME_CORRELATION | true | correlação de tempo de execução persistido |
| RASAI_SECURITY_OSV | true | OSV para componente/versionamento elegível |
| RASAI_SECURITY_CISA_KEV | true | cruza CVEs com KEV |
| RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS | 15 | tempo limite por chamada externa de inteligência de vulnerabilidades |

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

O report-catalog/cat-10.html apresenta resumo e estado, cobertura efetiva, achados por severidade/classificação, rastreabilidade por evidência, recursos próprios/externos, componentes/versionamento identificáveis, Lighthouse Melhores Práticas reutilizado, MDN HTTP Observatory reutilizado, estado de OSV/CISA KEV e demais integrações, e impacto/contenção/correção/validação de cada finding.

A página é projeção read-only. O HTML não executa coleta, IA ou cálculo de segurança.

## Testes direcionados

Os testes específicos ficam em tests/test_passive_security_catalog.py e cobrem:

- análise passiva sobre evidência persistida;
- ausência de varredura ativa;
- redaction de cookie/nonce no CAT-10;
- OSV/KEV com somente componente+versão;
- falha externa reduzindo cobertura sem virar achado;
- reuso do mesmo core pelo Improvement Intelligence;
- projeção do plano CAT-10 no console;
- contrato SaaS de IA limitado a SECURITY.
