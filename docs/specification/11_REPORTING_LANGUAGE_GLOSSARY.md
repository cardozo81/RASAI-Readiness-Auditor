# REPORTING_LANGUAGE_GLOSSARY.md

**Status:** APPROVED — extended through Web Performance externo Web Performance Evidence

## 1. Regra editorial

O relatório destinado ao usuário deverá ser prioritariamente em português.

Inglês somente quando:

- nome técnico é consagrado;
- nome oficial não deve ser traduzido;
- tradução poderia reduzir precisão;
- valor deriva diretamente de protocolo/HTML/API.

O usuário deve descobrir o resultado executivo antes de metodologia detalhada.

## 2. Tradução da interface

Overall Readiness
→ Readiness Search & AI

Technical Accessibility
→ Acessibilidade Técnica

Indexability
→ Capacidade de Indexação

Content Extractability
→ Extração de Conteúdo

Semantic Structure
→ Estrutura Semântica

Entity Clarity
→ Clareza de Entidades

Structured Data
→ Dados Estruturados

Answerability
→ Capacidade de Resposta

Citation Readiness
→ Preparação para Citação

Evidence & Trust
→ Evidências e Confiabilidade

Intent Coverage
→ Cobertura de Intenções

Finding
→ Problema Identificado

Recommendation
→ Recomendação

Remediation Recipe
→ Receita de Remediação / Remediation Recipe

Severity
→ Severidade

Impact
→ Impacto

Effort
→ Esforço

Confidence
→ Confiabilidade

Coverage
→ Cobertura da Análise

Consolidated
→ Consolidado

Partial
→ Parcial

Not Consolidated
→ Não Consolidado

Unknown
→ Não Determinado

Warning
→ Alerta

PASS
→ Aprovado

FAIL
→ Problema identificado

NOT_APPLICABLE
→ Não aplicável

ERROR
→ Erro de execução da análise

Core Web Vitals
→ Core Web Vitals (métricas de experiência real; preservar nome oficial)

Lighthouse Performance
→ Lighthouse Performance (score de laboratório; não traduzir como Score GEO)

CrUX / Chrome UX Report
→ CrUX / Chrome UX Report (dados agregados de usuários reais)

Field data
→ Dados de campo / experiência real agregada

Lab data
→ Dados de laboratório

LCP
→ Largest Contentful Paint (LCP)

INP
→ Interaction to Next Paint (INP)

CLS
→ Cumulative Layout Shift (CLS)

## 3. Estado geral quando Overall não é consolidável

Quando `OVERALL_READINESS` não possuir valor consolidado, o relatório deve usar explicitamente:

```text
COMPATIBILIDADE GEO
NÃO DETERMINADA
```

Não usar somente `—` como estado principal.

Não apresentar Coverage como substituto de Readiness Search & AI.

`NÃO DETERMINADA` significa informação insuficiente para conclusão geral; não equivale a zero, FAIL ou resultado crítico.

## 4. Semântica visual

Cores de referência:

- sucesso / aprovado / resultado forte: verde (`#16803C`);
- atenção: amarelo (`#D99A00`);
- problema relevante: laranja (`#D65A00`);
- erro / crítico: vermelho (`#C62828`);
- não determinado / informação insuficiente: cinza (`#667085`);
- informação metodológica: azul (`#2563EB`).

Todo estado visual deve incluir texto. Cor isolada nunca é suficiente.

Estados textuais possíveis incluem:

- APROVADO;
- ALERTA;
- PROBLEMA;
- CRÍTICO;
- PARCIAL;
- NÃO DETERMINADO;
- NÃO CONSOLIDADO;
- INCOMPLETO;
- INDISPONÍVEL.

## 5. Classificação textual de score válido

| Faixa | Termo |
|---:|---|
| 90–100 | Excelente |
| 75–89 | Alta |
| 60–74 | Moderada |
| 40–59 | Baixa |
| 0–39 | Crítica |
| sem resultado válido | Não Determinada |

A tabela acima é classificação interna para scores RASAI válidos. Ela não deve ser reutilizada automaticamente para classificar `Lighthouse Performance`, cujo score pertence à metodologia externa do Lighthouse.

A cor do resultado geral deve respeitar também Consolidation. Um valor não consolidável não deve receber apresentação de resultado geral válido.

## 6. Termos técnicos preservados

Exemplos:

- HTTP;
- robots.txt;
- canonical;
- noindex;
- JSON-LD;
- Googlebot;
- OAI-SearchBot;
- GPTBot;
- SPA;
- SSR;
- CSR;
- Playwright;
- Chromium;
- PageSpeed Insights;
- Lighthouse;
- CrUX;
- Core Web Vitals;
- LCP;
- INP;
- CLS;
- FCP;
- TBT;
- Speed Index.

Primeira ocorrência pode usar:

Canonical (URL canônica)

Soft 404 (página com semântica de erro sem status HTTP apropriado)

Client-Side Rendering — CSR (renderização no navegador)

CrUX (Chrome UX Report — dados agregados de usuários reais)

Lighthouse Performance (score de laboratório do Lighthouse)

## 7. Seção de interpretação

Título deve incluir:

`Como interpretar este relatório`

Deve explicar separadamente:

### Readiness Search & AI

Quão preparado está o site segundo score consolidado RASAI.

### Cobertura da Análise

Quanto do universo aplicável pôde ser efetivamente analisado.

Baixa Coverage não significa necessariamente baixa qualidade do site.

### Confiabilidade

Grau de segurança da conclusão com base em evidence, método e limitações.

### Consolidado

Há cobertura e confiabilidade suficientes para apresentar o resultado como consolidado.

### Parcial

Parte relevante da avaliação está disponível, mas existem limitações.

### Não Consolidado / Não Determinado

Não há base suficiente para apresentar conclusão agregada. O estado não é score zero.

### Severidade

Gravidade intrínseca do problema.

### Prioridade

Ordem recomendada de ação considerando gravidade, impacto, confiabilidade e facilidade.

### Desktop e Mobile

São contextos independentes e podem apresentar resultados diferentes.

### Web Performance externo

`Core Web Vitals` e `Lighthouse` devem aparecer como evidência complementar, não como dimensões implícitas do Score GEO.

- Lighthouse = laboratório;
- CrUX/Core Web Vitals = dados de campo agregados quando disponíveis;
- `PASS` de Core Web Vitals não significa “GEO aprovado”;
- `FAIL` de Core Web Vitals não substitui `SCORE-GEO-002` nem cria finding RASAI automaticamente;
- `INCOMPLETE`/`UNAVAILABLE` significa falta de base externa suficiente, não defeito comprovado do site.

## 8. Linguagem de remediação

Correções detalhadas devem preferir a sequência:

```text
Página
Dispositivo
Regra
Severidade
Prioridade
Categoria GEO
Alvo / elemento / local
Problema encontrado
Valor observado
Correção recomendada
Critério de aceite
Como revalidar
Evidências
```

Quando o trecho HTML original não estiver persistido:

`Trecho HTML original não persistido para esta evidência.`

Quando houver código recomendado, rotular:

`Estrutura recomendada (exemplo)`

Nunca rotular exemplo como HTML observado.

Fallback deve ser explicitamente identificado como `FALLBACK DE REMEDIAÇÃO` ou equivalente.

## 9. Disclaimer de IA

Quando não houver IA:

`Algumas avaliações semânticas não foram executadas porque não havia um provedor de inteligência artificial disponível ou configurado. Essa limitação reduz a cobertura da auditoria e não representa um problema do website analisado.`

Quando IA externa for usada, o relatório deve indicar que análises semânticas utilizaram provider externo, sem revelar credenciais.

O relatório não deve sugerir que a IA “deu a nota GEO”; score oficial continua determinístico.

Web Performance externo não é telemetria de IA. PageSpeed/CrUX devem aparecer como serviços externos de medição e nunca como provider semântico.

## 10. Linguagem Web Performance externo obrigatória

Preferir:

```text
Lighthouse Performance: 91/100
Core Web Vitals: PASS
Fonte de campo: CrUX
Escopo: URL
SCORE-GEO-002: permanece independente
```

Evitar:

```text
Score GEO Lighthouse
Google confirmou o Score GEO
Core Web Vitals determinou a nota GEO
Sem dados CrUX = site reprovado
```

Quando Web Performance externo estiver desabilitado:

`A coleta externa de Web Performance foi desabilitada. Nenhuma requisição PageSpeed/CrUX foi realizada. O SCORE-GEO-002 permanece disponível normalmente.`

Quando houver falha externa:

`A coleta de Web Performance ficou incompleta por indisponibilidade/erro do serviço externo. Essa limitação não foi convertida em problema do website nem alterou o SCORE-GEO-002.`

## 11. Restrições

Nunca usar linguagem que prometa:

- ranking;
- citação;
- visibilidade;
- presença em mecanismo generativo.

Nunca recomendar ou afirmar sem base:

- canonical preferencial;
- remoção de noindex;
- structured data incompatível;
- autoria;
- data de atualização;
- fonte;
- claim factual;
- informação comercial.

Nunca representar PageSpeed, Lighthouse ou CrUX como certificação GEO/AEO oficial.

O produto mede readiness, oferece remediação evidence-backed e pode apresentar sinais Web Performance externos de forma separada.


### Linguagem orientada ao analista

A apresentação HTML é destinada a profissionais de análise de dados e SEO, não a desenvolvedores do RASAI. Termos técnicos só devem aparecer na leitura principal quando tiverem fonte pública reconhecida e uso difundido no domínio. Vocabulário interno de implementação deve permanecer fora da interface principal; quando tecnicamente necessário para suporte, deve ficar recolhido em detalhes técnicos e acompanhado de explicação humana. Identificadores históricos de etapas de entrega não fazem parte do vocabulário do produto e não devem aparecer em relatórios, console ou documentação operacional.
