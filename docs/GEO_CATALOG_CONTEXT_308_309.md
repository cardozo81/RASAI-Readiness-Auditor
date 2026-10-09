# #308/#309 - GEO no contexto dos catálogos sem execução externa

## O que a projeção exibe

O motor `geo_snapshot_context_308.py` é um consumidor **estritamente
read-only** de `geo_observation_runs`, limitado à própria `audit_id`.
Ele não executa pesquisa, IA, análise, relatório ou RPR, não recalcula
índices e não faz alterações em `audit.db`.

Só existe correlação material quando o snapshot derivado pertence à
**última tentativa externa comprovada por cronologia UTC** da mesma AUD,
com estado `SUCCESS`. A projeção exige versão conhecida do método,
vínculo entre `analysis_id`, `input_sha256`, `perplexity_run_id` e
`audit_id`, integridade estrutural do `projection_json`, uma única
consulta atribuível e uma classificação de retorno com proveniência da
mesma execução. Esse teste de vínculo e autoconsistência não substitui
a inspeção integral de hashes/manifest de um AUD.

A última tentativa FAILED/QUOTA/CREDIT_ERROR, ausência de snapshot,
relógios empatados/sem timezone quando há múltiplas observações,
snapshot de outra AUD, método não reconhecido e JSON sem integridade
produzem **N/D**. Não se promove um sucesso antigo e não se repete
consulta paga quando o relatório é rematerializado.

| Superfície | Contexto aditivo | Limite |
|---|---|---|
| CAT-01 | associação contextual com dimensão acesso/descoberta | retorno de Search API não diagnostica crawler, renderização nem indexação |
| CAT-03 | URL exata, alternativa de domínio ou ausência de fontes da consulta persistida | não presume canonical, preferência da IA ou causa técnica |
| CAT-05 | interseção e denominadores por fonte, somente com overlap `DESCRIPTIVE_ONLY` internamente consistente | não equivale mercados, dispositivo, idioma, intenção ou citação generativa |
| CAT-08 | referência adicional para priorização humana | não altera escore, P1/P2/P3 nem cálculo de impacto/eficiência |
| CAT-09 | recomendação determinística já contida no snapshot persistido | não cria findings nem substitui recomendação canônica |
| index | status de fonte observacional | não projeta tendência ou previsão |
| directed-analysis | referência ao snapshot | não declara que o motor direcionado consumiu esta fonte |
| ai-integrations | proveniência de Search API | ledger próprio controla custo, retries e eventual billability |

CAT-02/04/06/07/10 continuam sem vínculo direto, evitando
contaminação dos motores homologados. Os links `geo.html`
mantêm a fonte principal para o analista.

## Validações automatizadas

Fixtures SQLite com duas AUDs e entidades privadas da outra AUD,
busca atual bem-sucedida, falha posterior (impede promoção de
sucesso antigo), relógio UTC empatado, snapshot com proveniência
adulterada, JSON com HTML potencialmente perigoso, schema histórico
e denominadores inconsistentes.

Testes garantem `read_bytes()` idênticos antes/depois da projeção,
nenhum provider chamado, ausência de contaminação entre auditorias,
sem novos IDs/custos/score e replay determinístico.

## Gates que permanecem

Métricas de marca/intenção/mercado, mapeamento per-query de
múltiplas consultas, consumo comprovado da fonte por síntese IA,
validação física de resultados externos reais e aceite visual do
relatório permanecem dependências de #304/#306/#308.
Não declarar êxito da IA ou inferir presença GEO por ter ocorrido
uma consulta Search API.
