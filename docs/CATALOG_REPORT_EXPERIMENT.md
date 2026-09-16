# Relatório HTML por catálogos - validação paralela

## Objetivo

O RASAi mantém temporariamente duas projeções HTML independentes para a mesma AUD. `report/` continua sendo a árvore canônica atual; `report-catalog/` é a proposta por CAT-01…CAT-09 em validação. Não existe cópia de HTML entre as árvores.

`report-catalog/` é **read-only**. Sua fonte de verdade é `audit.db`, os artifacts da própria AUD e o snapshot secret-free da execução. O gerador não chama collectors, APIs, IA, scoring nem consulta a configuração atual da máquina para reconstruir decisões históricas.

## Contrato de apresentação

Todas as páginas compartilham o mesmo menu, componentes, CSS, estados e linguagem visual. A evolução do conteúdo não deve redesenhar a estrutura aprovada.

As páginas CAT preservam esta ordem:

1. Resumo;
2. Escopo solicitado;
3. Configuração efetiva;
4. Execução;
5. Resultados;
6. Evidências;
7. Análise e interpretação;
8. Remediações;
9. Detalhes técnicos.

A informação principal usa rótulos funcionais em pt-BR. Nomes físicos de tabelas, campos, variáveis, IDs internos e payloads pertencem somente a proveniência/detalhes técnicos quando forem necessários para rastreabilidade.

## Modal contextual

Modal é recurso de aprofundamento, não uma segunda página. Cada gatilho abre exclusivamente o item clicado: uma amostra, uma tentativa de integração, uma ocorrência de navegador, uma validação de JSON-LD, um finding ou uma remediação.

O padrão visual da modal é compartilhado, mas seu conteúdo continua restrito ao contexto de origem. Informações curtas permanecem na página; detalhes técnicos pequenos podem usar expansão inline; conteúdo com navegação própria deve permanecer em superfície dedicada.

## Fronteiras de responsabilidade

O relatório distingue explicitamente:

- **captura/observação:** o que foi medido ou encontrado;
- **análise/interpretação:** o que os fatos significam e como se correlacionam;
- **remediação:** o que deve ser alterado e como validar a correção.

CAT-01…CAT-07 são proprietários dos fatos e diagnósticos de seus domínios. CAT-08 consome referências desses catálogos para explicar, correlacionar e priorizar melhorias. CAT-09 concentra implementação de correções, exemplos e critérios de validação. Quando um CAT depende de dado pertencente a outro domínio, ele referencia o CAT/identificador de origem em vez de duplicar a evidência.

### CAT-01

Fundamentos técnicos e descoberta: robots, sitemap/feed, `llms.txt`, padrões web, falhas de console/JavaScript/requisições e evidências técnicas de descoberta. O snapshot bruto continua pertencendo à Governança.

### CAT-02

Acessibilidade: resultados automatizados, elementos afetados e evidências. Lighthouse é uma fonte automatizada e não equivale a certificação WCAG integral.

### CAT-03

Conteúdo, semântica e dados estruturados: entidades, avaliações semânticas e validações de JSON-LD. Sugestões de implementação de JSON-LD pertencem ao CAT-09.

### CAT-04

Web Performance: Lighthouse/PageSpeed/CrUX e métricas de laboratório/campo. Telemetria da chamada externa pertence a IA e integrações.

### CAT-05

Search & AI Intelligence: SERP, GSC, visibilidade em IA e observabilidade aplicável. Fontes independentes não são tratadas como dependências obrigatórias umas das outras.

### CAT-06 e CAT-07

Apdex de navegação e de experiência mostram o agregado e cada amostra persistida. O relatório não inventa URL individual de request quando o contrato da amostra só preservou contagens de falhas.

### CAT-08

Análise profunda: problemas, correlações, prioridades e melhorias evidence-bound, com referência ao CAT que possui a evidência original.

### CAT-09

Remediações: correções determinísticas e assistidas por IA, texto/HTML/JSON-LD sugerido e forma de revalidar, sempre vinculados ao finding/evidência de origem quando disponível.

## Governança

- `capture-context.html`: URL, página/captura, device, navegador, viewport, renderização e artifacts;
- `execution-evidence.html`: plano congelado × execução, fulfillment e integridade;
- `ai-integrations.html`: cada tentativa de IA e integração externa persistida, volumes, tokens, custos, retries/fallbacks, estados e comunicação request/response quando armazenada;
- `methodology.html`: natureza de observação, índice, análise e remediação;
- `metrics.html`: inventário transversal dos índices/métricas com referência ao catálogo proprietário.

Uma página CAT somente indica que utilizou IA/API e aponta para `ai-integrations.html`; ela não replica tokens, custo ou payloads.

## IA, integrações e segurança

`ai-integrations.html` consolida telemetria persistida de IA e serviços externos. Request/response bruto só é exibido quando existe no log da própria AUD. Ausência de payload não é reconstruída. API keys, bearer tokens, cookies, senhas e outros segredos são removidos da projeção.

Custo exibido é estimativa técnica persistida, não invoice/fatura. IA não altera score determinístico por opinião do modelo.

## Integração com o finalizador

`report_completion.finalize_audit_report_site()` materializa `report-catalog/` depois da árvore atual. A proposta continua isolada da inspeção de completude de `report/` enquanto estiver em validação. O gerador deve ser total sobre estados legais e poder ser executado novamente depois de capacidades pós-auditoria, como análise profunda, para refletir o estado final persistido.

## Critério para remoção futura

Somente após validação funcional decidir qual árvore se torna o contrato único. Até lá, não mover templates entre `report/` e `report-catalog/` e não criar uma terceira árvore.
