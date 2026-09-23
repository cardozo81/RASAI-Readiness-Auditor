# Glossário e taxonomia técnica do RASAi

**Estado:** vigente.

Este documento é a referência canônica para siglas, identificadores e termos usados pelo RASAi. Identificadores persistidos mantêm sua forma técnica; interfaces humanas devem usar rótulo pt-BR e preservar o ID quando necessário para rastreabilidade.

## Identidade e metodologia

A camada de apresentação usa nomes de negócio em pt-BR e mantém os identificadores técnicos apenas para rastreabilidade. Quando um acrônimo tem expansão oficial em inglês, a documentação apresenta primeiro a forma em inglês, imediatamente seguida da tradução para pt-BR. A primeira versão pública dos conceitos metodológicos versionáveis é **001**.

| Sigla/ID técnico | Nome apresentado | Definição e responsabilidade |
|---|---|---|
| **RASAI / RASAi** | **Readiness Assessment for Search & AI - Avaliação de Prontidão para Search e IA**. `RASAi` é a grafia pública. | Nomeia a plataforma de avaliação de prontidão, evidências, diagnóstico, remediação e evolução para Search e IA. |
| **SARI-001** | **Search & AI Readiness Index - Índice de Prontidão Search & IA**. Versão pública **001**. | Identificador metodológico técnico do índice agregado do RASAi. A apresentação humana usa o nome por extenso; o ID permanece disponível para rastreabilidade. |
| **SCORE-GEO-004** | **Método de Pontuação de Prontidão**. Versão pública **001**. | Contrato técnico que define pesos, fatores, agregação, Cobertura, Confiança, Consolidação e critérios críticos. `SCORE-GEO-004` é tratado como ID técnico indivisível; o segmento `GEO` não define o escopo de negócio do método. |
| **BR-GEO-*** | **Regra de Avaliação de Prontidão**. | Identifica uma verificação individual com aplicabilidade, evidência, resultado e eventual contribuição para pontuação. O ID técnico não implica que a regra pertença exclusivamente a Generative Engine Optimization. |
| **EV-GEO-*** | **Evidência da Auditoria**. | Identifica uma observação persistida e rastreável que sustenta regra, achado, medição ou conclusão. O ID técnico não define um domínio GEO. |
| **FR-GEO-*** | **Functional Requirement - Requisito Funcional do RASAi**. | Identifica requisito funcional normativo do produto; não representa pontuação. |
| **NFR-GEO-*** | **Non-Functional Requirement - Requisito Não Funcional do RASAi**. | Identifica requisito de qualidade, segurança, desempenho, confiabilidade, operação ou outra restrição do produto. |
| **CAT-01 ... CAT-10** | **Catálogo de Análise**. | Organiza responsabilidades temáticas do relatório. O número não representa nota, severidade ou ordem de execução obrigatória. |
| **HIERARCHICAL_WEIGHTED_READINESS_V1** | **Agregação Hierárquica Ponderada de Prontidão**. Versão pública **001**. | Mantém a hierarquia escopo -> grupo -> dimensão -> resultado geral e evita que a quantidade de páginas multiplique peso metodológico. |
| **SARI_DIMENSION_WEIGHTS_V1** | **Pesos das Dimensões do Índice de Prontidão**. Versão pública **001**. | Fixa a participação de cada dimensão no índice. |
| **SARI_GROUP_WEIGHTS_V1** | **Pesos dos Grupos do Índice de Prontidão**. Versão pública **001**. | Fixa a participação dos grupos dentro de cada dimensão. |
| **SARI_CRITICAL_GATES_V1** | **Critérios Críticos de Prontidão**. Versão pública **001**. | Separa qualidade numérica de prontidão operacional crítica. |
| **WEIGHTED_MEASUREMENT_CONFIDENCE_V1** | **Modelo de Confiança da Medição**. Versão pública **001**. | Consolida a confiança das dimensões sem mascarar insuficiência crítica. |

**Regra para GEO:** a sigla **GEO** é expandida como **Generative Engine Optimization - Otimização para Mecanismos Generativos** somente quando o texto estiver tratando explicitamente dessa disciplina. Nos IDs técnicos `SCORE-GEO-004`, `BR-GEO-*`, `EV-GEO-*`, `FR-GEO-*` e `NFR-GEO-*`, o identificador é apresentado como unidade técnica e não é usado para definir o escopo de negócio.

## Identificadores de execução

| Prefixo | Significado apresentado | Propósito |
|---|---|---|
| **AUD-*** | **Audit - Auditoria**. | Identifica uma observação lógica e sua evidência persistida. |
| **RPR-*** | **Reprocessing - Reprocessamento**. | Identifica uma tentativa seletiva de completar um AUD sem criar nova observação longitudinal. |
| **CONS-*** | **Consolidated - Consolidado**. | Identifica pacote/relatório longitudinal derivado de AUDs compatíveis. |
| **CONRUN-*** | **Consolidated Run - Execução de Consolidação**. | Identifica cada tentativa de geração de CONS, inclusive quando não há relatório final. |
| **SCR-*** | **Score Record - Registro de Pontuação**. | Identifica registro persistido de pontuação. |
| **SCN-*** | **Score Contribution - Contribuição de Pontuação**. | Identifica contribuição rastreável de regra/escopo para uma dimensão. |
| **JOB-*** | **Execution Job - Trabalho de Execução**. | Identifica trabalho durável no plano de controle. |
| **ORG-*** | **Organization - Organização**. | Identifica organização/tenant. |
| **PRJ-*** | **Project - Projeto**. | Identifica projeto. |
| **PTY-*** | **Property - Propriedade**. | Identifica uma propriedade/site lógico no plano de controle. |
| **ENV-*** | **Environment - Ambiente**. | Identifica ambiente lógico. |
| **USR-*** | **User - Usuário**. | Identifica usuário interno vinculado à autorização. |

## Termos de medição que não são sinônimos

| Termo | Significado no RASAi |
|---|---|
| **Score** | Qualidade medida no universo efetivamente avaliado. |
| **Coverage / Cobertura** | Fração do peso aplicável efetivamente avaliada. Mede completude, não qualidade. |
| **Confidence / Confiança** | Força da medição considerando Coverage, evidência, erros e criticidade. Não é probabilidade de a IA estar certa. |
| **Consolidation / Consolidação** | Indica se a medição é forte o suficiente para publicação analítica como consolidada, parcial ou não consolidada. |
| **Critical Readiness Gate** | Gate crítico independente do valor numérico; pode impedir que score alto seja interpretado como prontidão operacional. |
| **Finding / Achado** | Condição sustentada por RuleExecution + Evidence rastreável. |
| **Recommendation / Recomendação** | Orientação derivada da evidência; permanece separada do fato observado. |
| **Remediation / Remediação** | Ação técnica/editorial proposta para tratar um finding. |
| **Evidence / Evidência** | Dado persistido, rastreável e contextualizado que sustenta uma conclusão. |
| **Advisory** | Conteúdo orientativo; pode usar IA, mas não substitui fato determinístico nem altera score por si só. |

## Siglas técnicas externas recorrentes

| Sigla | Significado | Uso no RASAi |
|---|---|---|
| **IA / AI** | Inteligência Artificial / Artificial Intelligence. | Análise opcional/advisory com provider, modelo, tentativas, tokens e custo rastreáveis. |
| **GEO** | Generative Engine Optimization. | Disciplina ligada à compreensão, recuperação e uso de conteúdo por mecanismos generativos. |
| **SEO** | Search Engine Optimization. | Diagnóstico técnico e de conteúdo para mecanismos de busca. |
| **AEO** | Answer Engine Optimization. | Termo de mercado; não é padrão oficial nem score próprio do RASAi. |
| **SERP** | Search Engine Results Page. | Resultado observado de busca; separado de readiness. |
| **YMYL** | Your Money or Your Life. | Contexto de conteúdo sensível; não cria fórmula isolada de ranking. |
| **E-E-A-T** | Experience, Expertise, Authoritativeness, Trustworthiness. | Referência conceitual; o RASAi não produz nota oficial de E-E-A-T. |
| **WCAG** | Web Content Accessibility Guidelines. | Referência de acessibilidade; diagnóstico automatizado não equivale a certificação integral. |
| **W3C** | World Wide Web Consortium. | Padrões e validadores Web. |
| **CWV** | Core Web Vitals. | Família de métricas de experiência Web. |
| **LCP** | Largest Contentful Paint. | Métrica de carregamento. |
| **INP** | Interaction to Next Paint. | Métrica de responsividade. |
| **CLS** | Cumulative Layout Shift. | Métrica de estabilidade visual. |
| **CrUX** | Chrome User Experience Report. | Dados de campo agregados do Chrome quando disponíveis. |
| **RUM** | Real User Monitoring. | Telemetria de usuários reais; distinta de Apdex sintético. |
| **APM** | Application Performance Monitoring. | Observabilidade da aplicação. |
| **CSP** | Content Security Policy. | Política/cabeçalho analisado no CAT-10. |
| **CORS** | Cross-Origin Resource Sharing. | Política entre origens analisada no CAT-10. |
| **CVE** | Common Vulnerabilities and Exposures. | Identificador público de vulnerabilidade. |
| **OSV** | Open Source Vulnerabilities. | Fonte de correlação de pacote/ecossistema/versão. |
| **CISA KEV** | Known Exploited Vulnerabilities da CISA. | Catálogo para priorização quando CVE correlacionado consta como explorado conhecido. |
| **SBOM** | Software Bill of Materials. | Inventário que pode aumentar confiança na identificação de componente/versão. |
| **TLS** | Transport Layer Security. | Segurança de transporte. |
| **JSON-LD** | JSON for Linking Data. | Serialização de dados estruturados; sugestões permanecem advisory. |

## Taxonomia de resultado

```text
dado coletado
-> evidência persistida
-> execução de regra
-> métrica/indicador
-> score/índice quando o contrato permitir
-> classificação/estado
-> finding
-> recomendação/remediação
-> acompanhamento longitudinal
```

Regras de interpretação:

- dado ausente não é convertido automaticamente em falha;
- `UNKNOWN` e `ERROR` não significam `FAIL`;
- `NOT_APPLICABLE` legitimamente determinado sai do universo aplicável;
- Score não substitui Coverage;
- Confidence não substitui Score;
- Consolidation não mede qualidade do site;
- recomendação de IA não substitui evidência;
- correlação temporal não prova causalidade.

## Regra de apresentação

Relatórios e console devem preferir rótulos compreensíveis em pt-BR e manter IDs técnicos somente quando úteis à auditoria e rastreabilidade.

Exemplo:

```text
Pontuação de prontidão Search & AI (SARI-001)
Método de cálculo (SCORE-GEO-004)
Regra de Avaliação de Prontidão (ID técnico BR-GEO-011)
Catálogo 10 - Segurança passiva (CAT-10)
```

Não apresentar `GEO` isoladamente quando o contexto puder ser interpretado como geografia/geolocalização.
