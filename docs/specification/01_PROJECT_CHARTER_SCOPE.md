# RASAi - Search & AI Readiness Auditor - Project Charter & Scope

**Estado no baseline de desenvolvimento:** APPROVED
**Versão funcional:** MVP Baseline

## 1. Visão do Produto

O RASAi - Search & AI Readiness Auditor é uma ferramenta local destinada a avaliar a preparação de websites para mecanismos tradicionais de busca e sistemas generativos baseados em IA.

O produto transforma evidências técnicas, estruturais e semânticas em:

- findings verificáveis;
- scores por dimensão;
- resultados separados para Desktop e Mobile;
- riscos;
- oportunidades;
- recomendações;
- backlog priorizado;
- relatório HTML profissional.

O produto mede:

`READINESS`

e não garante:

`VISIBILITY`

## 2. Contexto Operacional

Fase inicial:

- uma máquina;
- um operador/desenvolvedor;
- Windows;
- execução local;
- sem aplicação web;
- sem arquitetura distribuída;
- sem multiusuário;
- sem CI/CD obrigatório;
- Git/GitHub utilizados como controle de versão e repositório de desenvolvimento a partir do Bootstrap e fundação do projeto;
- GitHub não é dependência obrigatória para execução do produto;
- testes mínimos orientados a risco.

## 3. Objetivos mínimos da auditoria

A auditoria deverá responder:

1. O conteúdo pode ser descoberto e acessado?
2. As páginas estão tecnicamente aptas a serem indexadas?
3. O conteúdo principal pode ser recuperado?
4. A página apresenta estrutura semântica adequada?
5. As entidades relevantes estão claras?
6. Dados Estruturados estão presentes e coerentes quando aplicáveis?
7. O conteúdo responde aos intents relevantes?
8. As informações possuem características favoráveis à recuperação e citação?
9. Existem sinais adequados de evidência, autoria e confiança?
10. Existem diferenças materiais entre Desktop e Mobile?
11. O que deve ser corrigido primeiro?

## 4. Princípios

### Evidence First

Nenhum finding válido pode existir sem evidência rastreável.

### Deterministic First

Condições objetivamente verificáveis devem ser resolvidas deterministicamente.

Exemplos:

- HTTP;
- redirects;
- canonical;
- robots;
- noindex;
- JSON-LD parsing;
- links;
- sitemap.

### AI for Semantic Analysis

IA será utilizada para interpretação semântica quando necessário.

Exemplos:

- entidades;
- answerability;
- claims;
- intenção;
- contexto;
- evidência textual.

IA não calcula diretamente o score oficial.

### Explainable Scoring

Todo score deve ser reconstruível a partir de regras e contribuições versionadas.

### Desktop e Mobile independentes

Desktop e Mobile são contextos de auditoria distintos.

## 5. MVP

### Entrada

- domínio ou URL inicial;
- nome do projeto;
- idioma;
- mercado;
- limite de páginas.

### Limite padrão

`max_pages = 100`

Configurável.

### Descoberta

- seed;
- links internos;
- sitemap.

### Aquisição

Para cada página e dispositivo:

- HTTP;
- redirects;
- headers;
- RAW HTML;
- rendered DOM;
- canonical;
- robots;
- title;
- description;
- headings;
- links;
- Dados Estruturados;
- conteúdo principal.

### Crawlers baseline

- Googlebot;
- Googlebot Smartphone;
- Bingbot;
- OAI-SearchBot;
- GPTBot.

Os resultados devem ser interpretados separadamente.

### Arquiteturas web

O auditor deverá suportar:

- HTML tradicional;
- SSR;
- SSG;
- hydration;
- CSR;
- SPA;
- híbridos.

Nenhuma arquitetura é penalizada por si só.

### IA

IA é opcional.

Modos:

- `FULL`;
- `DEGRADED`;
- `NO_AI`.

O sistema deve continuar funcionando sem provider de IA.

### Relatório

Formato oficial:

`HTML`

Características:

- estático;
- autocontido sempre que possível;
- responsivo;
- profissional;
- navegável;
- português;
- adequado a público técnico e não técnico.

## 6. Dimensões

1. Acessibilidade Técnica
2. Capacidade de Indexação
3. Extração de Conteúdo
4. Estrutura Semântica
5. Clareza de Entidades
6. Dados Estruturados
7. Capacidade de Resposta
8. Preparação para Citação
9. Evidências e Confiabilidade
10. Cobertura de Intenções

Desktop e Mobile terão scores separados.

## 7. Fora do MVP

- alteração automática do website;
- publicação automática em CMS;
- geração automática de artigos;
- backlink crawler próprio;
- rank tracker;
- garantia de ranking;
- garantia de citação;
- previsão matemática de citação;
- benchmark de concorrentes;
- monitoramento contínuo;
- cloud obrigatória;
- multiusuário;
- autenticação corporativa;
- CI/CD;
- dependência obrigatória de GitHub para execução do produto.

Benchmark de concorrentes fica para V1.

## 8. Testes

Obrigatórios somente para comportamentos críticos:

- parsing;
- Rules Engine;
- scoring;
- severity;
- finding → evidence;
- Desktop × Mobile;
- HTML report;
- regressões críticas.

Não existe meta elevada de cobertura de código no MVP.

## 9. Critério de aceite funcional

O MVP deve:

1. receber target válido;
2. descobrir URLs;
3. respeitar `max_pages`;
4. criar snapshots Desktop e Mobile;
5. preservar RAW e rendered;
6. armazenar evidências;
7. executar regras;
8. suportar SPA e não-SPA;
9. operar com ou sem IA;
10. criar findings rastreáveis;
11. calcular scores reproduzíveis;
12. informar coverage;
13. informar confidence;
14. informar consolidation;
15. priorizar recomendações;
16. produzir HTML estático em português;
17. explicar limitações;
18. executar novamente de forma consistente, salvo análises explicitamente não determinísticas.
