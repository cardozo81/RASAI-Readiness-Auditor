# #210 - Prévia metodológica de comparação de URLs do mesmo domínio

## Estado

Esta implementação é um **contrato advisory puro**, não uma extensão do
motor CONS produtivo. `selection.resolve_selection` continua exigindo
exatamente a mesma URL e o mesmo dispositivo para uma série longitudinal.
O objetivo desta fase é estabelecer um gate verificável de elegibilidade
para um eventual modo **SAME_DOMAIN_COMPARATIVE** sem confundi-lo com
**SAME_URL_LONGITUDINAL**.

## Entrada e saída

A função
`rasai.consolidation.domain_comparative_preview_210.preview_same_domain_candidates`
recebe de dois a cem `AuditCandidate` produzidos pelo índice analítico
existente e não faz descoberta, indexação, coleta, consulta externa ou
materialização. Sua saída é JSON-compatível, versão
`RASAI-CONS-DOMAIN-COMPARATIVE-ADVISORY-001`.

As condições mínimas são: AUDs distintas com estado lógico COMPLETE,
URL individual verificável, mesmo hostname exato e dispositivo, pelo
menos duas URLs diferentes e instantes offset-aware únicos e válidos.
A implementação usa deliberadamente **hostname exato**, não eTLD+1
estimado, evitando confundir subdomínios, `www.` com apex, ou
domínios de registradores públicos. Se esse critério for ampliado,
exigirá uma Public Suffix List versionada e regra explícita de
equivalência organizacional.

A prévia devolve URL normalizada de cada AUD, a hora observada em UTC,
fingerprint SHA-256 do universo de uma URL e motivos determinísticos de
rejeição. O campo `domain` declarado no candidato não substitui
a verificação a partir da URL.

## Matriz de admissibilidade de métricas

| Dimensão | SAME_URL_LONGITUDINAL homologado | SAME_DOMAIN_COMPARATIVE advisory |
| --- | --- | --- |
| Identidade da URL | Mesma URL e device | Host e device iguais; URLs distintas |
| Apdex M23/M25 | Contrato histórico do CONS atual | N/D: universos e contexto de navegador distintos |
| PageSpeed/CrUX | Contrato histórico do CONS atual | N/D: métricas de URLs distintas não formam tendência da mesma página |
| HTML, descoberta e conteúdo | Evidências da URL original | Somente evidência segmentada por URL; sem delta causal |
| SARI/SCORE-GEO | Política canônica do CONS atual | Delta N/D até prova de equivalência de universo/ruleset/configuração |
| GEO | Observar método e escopo existentes | Não inferir tendências nem citações por IA |
| Intervalo temporal | Série da mesma página | Apenas ordem das AUDs, nunca delta de desempenho da página |

Nenhum valor Apdex, CWV, score ou tendência de página é calculado
pela prévia. O mesmo hostname por si só não estabelece que as ofertas,
rotas, renderizações, intenções ou amostras sejam comparáveis.

## Próximo gate de engenharia

Antes de integrar um eventual modo no CONS, validar a composição de
universos, versões de ruleset, fontes de score audit-level, contexto de
dispositivo, cache, amostragem, arquitetura SPA/SSR e permissões.
Definir artefato CONS próprio com método e hashes sem modificar
séries CONS antigas, e preparar aceite humano da semântica dos relatórios.
A integração é uma demanda distinta de implementação produtiva;
**não é tratada como homologada por estes testes**.

Esta fase modifica apenas o módulo advisory, seus testes isolados
e a documentação. Nem o índice SQL, nem o seletor CONS homologado,
nem seus manifests, coleta, IA, SCORE-GEO ou Apdex são alterados.
