# Competitive AI Content Intelligence

**Estado:** POC opt-in implementada.

## 1. Objetivo

Competitive AI Content Intelligence acrescenta uma camada semântica opcional sobre evidências já observadas por Search Intelligence.

A IA não escolhe concorrentes, não inventa posição SERP e não substitui a comparação determinística. O fluxo obrigatório é:

```text
query
-> observação SERP
-> posição do domínio do cliente
-> classificação determinística dos resultados
-> seleção limitada de páginas
-> aquisição pública explícita
-> extração determinística de features
-> comparação cliente × páginas observadas à frente
-> contexto consolidado
-> IA com evidence_ids fechados
-> oportunidades e hipóteses de melhoria
```

A camada não altera `SARI-001`, `SCORE-GEO-004` ou qualquer tabela de scoring.

## 2. Contrato

O contrato vigente é:

```text
COMPETITIVE-AI-001
```

A IA recebe somente evidência estruturada. HTML bruto não é enviado pelo contrato de Competitive AI.

Cada entrada recebe um identificador fechado:

- `CE-QUERY`: contexto da query e posição observada;
- `CE-CUSTOMER`: features extraídas da página do cliente;
- `CE-COMP-###`: features de cada página selecionada e observada;
- `CE-GAP-###`: diferença determinística previamente calculada pelo RASAi.

Toda oportunidade produzida pela IA deve citar pelo menos um desses IDs. Um provider que referencie ID inexistente é rejeitado como erro de contrato.

## 3. Elegibilidade

A IA só é executada quando a comparação determinística tem status `CONSOLIDATED`.

Isso exige:

- observação SERP utilizável;
- página do cliente observada;
- pelo menos uma página candidata observada;
- extração determinística concluída.

Estados incompletos não são preenchidos por inferência. O resultado fica `NOT_ELIGIBLE` e nenhuma chamada externa de IA é feita.

## 4. Categorias de oportunidade

O schema permite oportunidades nas categorias:

- `QUERY_INTENT`;
- `TOPIC_COVERAGE`;
- `ENTITY_COVERAGE`;
- `INFORMATION_ARCHITECTURE`;
- `STRUCTURED_DATA`;
- `EEAT`;
- `YMYL`;
- `SEO_AEO_GEO`.

Prioridades permitidas:

- `HIGH`;
- `MEDIUM`;
- `LOW`.

Cada oportunidade contém:

- título;
- recomendação;
- racional;
- `evidence_ids`;
- confiança entre `0` e `1`;
- nota explícita de limite causal.

## 5. Política de causalidade

Competitive AI pode afirmar que uma característica foi observada nas páginas analisadas e pode recomendar avaliação ou melhoria correspondente.

Não pode afirmar que:

- uma diferença causou a posição SERP;
- adotar uma característica garantirá ganho de ranking;
- um resultado classificado é necessariamente concorrente comercial;
- um score Lighthouse ou SARI determina ranking;
- uma entidade, experiência, autoridade ou fato não presente nas evidências existe.

As conclusões são hipóteses e oportunidades de remediação baseadas em observação.

## 6. E-E-A-T e YMYL

A opção `--ymyl-mode` possui três modos:

- `AUTO`: permite avaliação cautelosa a partir das evidências;
- `ON`: exige cautela reforçada para contexto YMYL;
- `OFF`: impede a IA de classificar automaticamente o conteúdo como YMYL.

Mesmo em `ON`, a IA não pode fabricar expertise, autoria, credenciais, avaliações ou autoridade.

Recomendações relacionadas a E-E-A-T devem privilegiar verificabilidade, transparência, autoria real, fontes, responsabilidade editorial e clareza sobre quem oferece o conteúdo ou serviço.

## 7. Providers

A camada é independente de provider no core.

Providers disponíveis nesta fase:

| Provider | Default/estado | Valores/uso permitido | Recomendado |
|---|---|---|---|
| `none` | default seguro | nenhuma chamada de IA | manter quando Competitive AI não for necessária |
| `fixture` | sem rede | validação/testes com fixture | usar em CI, testes e smoke sem custo externo |
| `openai` | opt-in | execução live com OpenAI Responses API e BYOK | usar somente com evidência consolidada e intenção explícita de consumo |

A variável `RASAI_SEARCH_AI_PROVIDER` aceita `none`, `fixture` ou `openai`; o default efetivo é `none`.

Para OpenAI são reutilizados os contratos de configuração existentes:

```text
OPENAI_API_KEY
RASAI_OPENAI_MODEL
RASAI_OPENAI_REASONING_EFFORT
```

Defaults, modelos permitidos e valores de reasoning estão centralizados em `ENVIRONMENT_VARIABLES.md`. A chave nunca é incluída no payload de evidências nem persistida.

Novos providers devem implementar o mesmo contrato de entrada/saída; não devem alterar a camada de classificação SERP.

## 8. CLI

Competitive AI é sempre explícita:

```powershell
rasai search "seguro auto" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider openai `
  --ymyl-mode AUTO
```

Para validar sem rede de IA:

```powershell
rasai search "seguro auto" `
  --domain cliente.example `
  --mode fixture `
  --fixture tests\fixtures\serp\canonical_google.json `
  --compare-content `
  --ai-competitive `
  --ai-provider fixture `
  --ai-fixture tests\fixtures\serp\competitive_ai.json
```

`--ai-competitive` exige `--compare-content`.

`--dry-run` não chama SERP, páginas ou IA e mostra o teto potencial de chamadas da camada semântica.

## 9. Persistência

Quando `--audit-workspace` é informado, a camada usa o mesmo `audit.db`.

Tabela aditiva:

```text
serp_competitive_ai_analyses
```

Ela referencia `serp_observations` e registra:

- estado;
- provider/modelo;
- versão do contrato;
- prompt ID/versão;
- request ID, quando informado pelo provider;
- intenção da query;
- avaliação YMYL;
- resumo;
- oportunidades estruturadas;
- referência e SHA-256 do artefato.

Artefatos:

```text
artifacts/search-intelligence/competitive-ai/<observation_id>.json
```

Nenhuma tabela de scoring é modificada.

## 10. Segurança e privacidade

A chamada de IA recebe somente as features extraídas e diferenças determinísticas utilizadas no contrato.

Não são enviados por esta camada:

- HTML bruto;
- credenciais;
- cookies;
- headers da coleta;
- API key SERP;
- API key do provider de IA.

O conteúdo analisado ainda é conteúdo público obtido na etapa anterior. Em SaaS multi-tenant, políticas de retenção, egress e isolamento continuam obrigatórias.

## 11. Falhas

Estados possíveis:

- `AVAILABLE`;
- `NOT_CONFIGURED`;
- `UNAVAILABLE`;
- `NOT_ELIGIBLE`.

Erros de schema e `evidence_ids` desconhecidos tornam o provider `UNAVAILABLE` para aquela análise. O RASAi não aceita parcialmente uma resposta que viole o contrato.

Falha de Competitive AI não altera a observação SERP nem o resultado determinístico.

## 12. Testes

CI usa apenas fixtures e transports injetados.

Os testes verificam:

- fechamento de `evidence_ids`;
- rejeição de evidência inexistente;
- ausência de HTML bruto na entrada;
- schema estruturado;
- chave fora do body;
- ausência de chamada quando o contexto determinístico não está consolidado;
- persistência aditiva;
- artefato e hash;
- controles CLI.

Nenhum teste deve consumir uma chave real nem fazer chamada de IA live.

## 13. Limitações atuais

- adapter live de Competitive AI disponível inicialmente para OpenAI;
- não há comparação semântica histórica entre duas execuções nesta camada;
- não há grafo de equivalência de entidade/empresa;
- não há conteúdo competitivo renderizado por browser;
- `report/search-intelligence.html` projeta a evidência semântica persistida, mas não executa IA durante a renderização;
- `SEARCH-HISTORY-001` e seu relatório histórico comparam evidência determinística; não transformam recomendações de IA em score temporal;
- a IA não recebe o corpo integral da página, apenas features determinísticas;
- não existe garantia de ganho de ranking a partir das recomendações.

A arquitetura de plataforma reutiliza os milestones de deploy e a resolução before/after existentes. Não existe um segundo sistema de milestones para Search Intelligence.
