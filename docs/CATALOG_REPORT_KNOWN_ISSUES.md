# Report-catalog - estado de validação e pendências conhecidas

Data de referência: 2026-09-16.

A estrutura visual atual é preservada. Os ajustes são de contrato de dados, linguagem, rastreabilidade e conteúdo; não constituem redesign.

## Validado após a correção do contrato de execução

A AUD `AUD-A336F323E60C4BD7BCF7662D3B390A07` confirmou que o snapshot `audit_catalog` passou a chegar ao subprocesso e foi persistido com `id`/`catalog_id`. O plano congelado contém os oito CATs selecionados e mantém CAT-05 como não selecionado. As autorizações de IA por catálogo também foram persistidas coerentemente.

A mesma AUD confirmou execução legítima do CAT-08 selecionado: `improvement_intelligence_runs` terminou `COMPLETE`, com 52 findings e 30 recomendações. CAT-07 possui `EXPERIENCE_APDEX` concluído e 20 amostras. A telemetria final possui cinco tentativas de IA, quatro bem-sucedidas, 104.383 tokens e custo técnico estimado de USD 0,07399068.

## Correções de projeção incorporadas no contrato 002

- nova página de Governança `Captura e contexto`;
- estados CAT derivados de resultados específicos, não apenas de work-items;
- ownership explícito de work-items, evitando associar `CONTENT_REMEDIATION_AI` ao CAT-03;
- CAT-01 passa a projetar arquivos/descoberta e diagnósticos de runtime;
- CAT-02 projeta evidência detalhada do Lighthouse quando o artifact persistido existe;
- CAT-03 projeta entidades e validações determinísticas de JSON-LD sem reutilizar sugestões do CAT-09 como prova do diagnóstico;
- CAT-06/CAT-07 projetam suas amostras individualmente;
- CAT-08 projeta findings/prioridades com referência ao CAT de origem;
- CAT-09 concentra correções e detalhes de implementação;
- `IA e integrações` consolida tentativas de IA, content remediation, custos, tokens, fallback e exchanges persistidos, além de integrações externas reconhecidas;
- rótulos funcionais substituem nomes de campo/tabela na apresentação principal;
- modal passa a ser contextual/atômica por item;
- nomes internos ficam restritos a detalhes técnicos/proveniência.

## Limitações de dados ainda reais

### Requests individuais do Apdex de experiência

O contrato atual de `synthetic_ux_apdex_samples` preserva contagens de XHR/fetch, recursos dinâmicos, erros de console/JavaScript, request failures e erros HTTP por amostra, mas não necessariamente a lista completa de URLs de cada request. O relatório deve mostrar tudo o que foi persistido e declarar a ausência da lista individual; nunca reconstruí-la por inferência.

### Comunicação bruta da análise profunda

Algumas tentativas de IA possuem telemetria em `ai_provider_attempts` sem entrada correspondente em `ai_exchange_log`. Nesses casos o relatório exibe provider/modelo, status, tokens, duração, custo, contrato, fallback e erro persistidos, e informa que request/response bruto não foi armazenado.

### Fontes compartilhadas

Alguns collectors servem a mais de um domínio, por exemplo PageSpeed/Lighthouse. O dado funcional pode aparecer no CAT proprietário (acessibilidade ou performance), mas a chamada externa e sua telemetria são exibidas uma única vez em `IA e integrações`.

## Invariantes

- seleção vem do plano congelado; ausência de snapshot não significa `NÃO SOLICITADO`;
- CAT desmarcado não pode iniciar chamada paga nem work-item funcional próprio;
- coleta, análise e remediação são responsabilidades distintas;
- CATs referenciam evidências de outros domínios em vez de duplicá-las;
- IA não altera scoring determinístico;
- `report-catalog/` permanece read-only;
- modais são contextuais, nunca um depósito de detalhes da página;
- componentes visuais e ordem estrutural das seções permanecem compartilhados e estáveis.
