# Competitive AI Content Intelligence

**Estado:** opt-in implementado sobre a arquitetura canônica de IA do RASAi.

## 1. Objetivo

Competitive AI Content Intelligence acrescenta uma camada semântica opcional sobre evidências já observadas por Search Intelligence.

A IA não escolhe concorrentes, não inventa posição SERP e não substitui a comparação determinística. O fluxo é:

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
-> contrato COMPETITIVE-AI-001
-> runtime canônico de IA
-> oportunidades e hipóteses de melhoria
```

A camada não altera `SARI-001`, `SCORE-GEO-004` ou qualquer tabela de scoring.

## 2. Contrato de análise

O contrato vigente é `COMPETITIVE-AI-001`.

A IA recebe somente evidência estruturada. HTML bruto não é enviado por este contrato.

Cada entrada recebe um identificador fechado:

- `CE-QUERY`: contexto da query e posição observada;
- `CE-CUSTOMER`: features extraídas da página do cliente;
- `CE-COMP-###`: features de cada página selecionada e observada;
- `CE-GAP-###`: diferença determinística previamente calculada pelo RASAi.

Toda oportunidade produzida pela IA deve citar pelo menos um desses IDs. Referência a ID inexistente é erro de contrato.

## 3. Elegibilidade

A IA só é executada quando a comparação determinística tem status `CONSOLIDATED`.

Isso exige:

- observação SERP utilizável;
- página do cliente observada;
- pelo menos uma página candidata observada;
- extração determinística concluída.

Estados incompletos não são preenchidos por inferência. O resultado fica `NOT_ELIGIBLE` e nenhuma chamada de IA é feita.

## 4. Categorias e saída

O schema permite oportunidades nas categorias:

- `QUERY_INTENT`;
- `TOPIC_COVERAGE`;
- `ENTITY_COVERAGE`;
- `INFORMATION_ARCHITECTURE`;
- `STRUCTURED_DATA`;
- `EEAT`;
- `YMYL`;
- `SEO_AEO_GEO`.

Prioridades: `HIGH`, `MEDIUM` e `LOW`.

Cada oportunidade contém título, recomendação, racional, `evidence_ids`, confiança entre `0` e `1` e nota explícita de limite causal.

## 5. Política de causalidade

Competitive AI pode afirmar que uma característica foi observada nas páginas analisadas e recomendar avaliação ou melhoria correspondente.

Não pode afirmar que:

- uma diferença causou a posição SERP;
- adotar uma característica garantirá ganho de ranking;
- um resultado classificado é necessariamente concorrente comercial;
- um score Lighthouse ou SARI determina ranking;
- uma entidade, experiência, autoridade ou fato não presente nas evidências existe.

As conclusões são hipóteses e oportunidades de remediação baseadas em observação.

## 6. E-E-A-T e YMYL

`--ymyl-mode` possui três modos:

- `AUTO`: avaliação cautelosa a partir das evidências;
- `ON`: cautela reforçada para contexto YMYL;
- `OFF`: impede classificação automática do conteúdo como YMYL.

Mesmo em `ON`, a IA não pode fabricar expertise, autoria, credenciais, avaliações ou autoridade.

## 7. Seleção e orquestração de IA

Competitive AI não possui cadastro próprio de provider. A seleção usa o mesmo registry e o mesmo runtime de IA do RASAi.

Seleção explícita:

```text
--ai-provider <provider-do-registry>
```

Nesse modo, o contrato Competitive AI usa o provider/modelo configurado no cadastro principal.

Seleção automática:

```text
--ai-provider auto
```

Nesse modo, a necessidade `COMPETITIVE_INTELLIGENCE` reutiliza integralmente a política canônica do core:

1. considera somente providers registrados, configurados e elegíveis ao `AUTO`;
2. respeita exclusões e estado de saúde da execução;
3. estima o custo da necessidade com o modelo/reasoning configurado para cada provider;
4. prioriza o candidato elegível de menor custo estimado conforme a política vigente;
5. registra o resultado da tentativa no mesmo `AiExecutionCoordinator`;
6. aplica a mesma quarentena/circuit breaker conforme a classe do erro;
7. faz fallback para o próximo candidato elegível quando a política permitir;
8. encerra no primeiro sucesso ou quando a cadeia elegível se esgota.

A feature não redefine thresholds, número de tentativas, classificação de erros, pricing ou política de quarentena.

`fixture` existe somente para testes/CI e não participa do cadastro de providers de produção.

Credenciais, modelos, reasoning, endpoints e elegibilidade AUTO são os definidos no provider registry e na configuração principal. Segredos nunca são incluídos no payload de evidências nem persistidos.

## 8. CLI

Exemplo com orquestração automática:

```powershell
rasai search "seguro auto" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider auto `
  --ymyl-mode AUTO
```

Exemplo com provider explícito:

```powershell
rasai search "seguro auto" `
  --domain cliente.example `
  --mode live `
  --compare-content `
  --ai-competitive `
  --ai-provider openai `
  --ymyl-mode AUTO
```

Para validar o contrato sem rede de IA:

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

Com `--ai-provider auto`, `--ai-model` e override único de reasoning não são aceitos; cada provider usa sua própria configuração canônica.

`--dry-run` não chama SERP, páginas ou IA e mostra o teto potencial de chamadas.

## 9. Persistência

Quando `--audit-workspace` é informado, a camada usa o mesmo `audit.db`.

Tabela aditiva:

```text
serp_competitive_ai_analyses
```

Ela referencia `serp_observations` e registra estado, provider/modelo efetivos, versão do contrato, prompt ID/versão, request ID quando disponível, intenção da query, avaliação YMYL, resumo, oportunidades estruturadas e referência/hash do artefato.

Artefatos:

```text
artifacts/search-intelligence/competitive-ai/<observation_id>.json
```

Nenhuma tabela de scoring é modificada.

## 10. Segurança e privacidade

A chamada de IA recebe somente features extraídas e diferenças determinísticas utilizadas no contrato.

Não são enviados por esta camada:

- HTML bruto;
- credenciais;
- cookies;
- headers da coleta;
- API key SERP;
- credenciais do provider de IA.

## 11. Falhas

Estados possíveis:

- `AVAILABLE`;
- `NOT_CONFIGURED`;
- `UNAVAILABLE`;
- `NOT_ELIGIBLE`.

Erros de schema e `evidence_ids` desconhecidos rejeitam a resposta da tentativa. Falhas técnicas são classificadas pelo mesmo contrato de diagnóstico usado pelo core de IA e alimentam o mesmo coordenador quando a seleção é `AUTO`.

Falha de Competitive AI não altera a observação SERP nem o resultado determinístico.

## 12. Testes

CI usa fixtures e transports injetados. Nenhum teste deve consumir credencial real ou realizar chamada live de IA.

Os testes devem cobrir:

- fechamento de `evidence_ids`;
- rejeição de evidência inexistente;
- ausência de HTML bruto na entrada;
- schema estruturado;
- segredos fora do body;
- ausência de chamada sem contexto consolidado;
- seleção por registry;
- `AUTO` usando o coordenador canônico;
- fallback/quarentena sem política local paralela;
- persistência e artefatos.

## 13. Limitações funcionais

- não há comparação semântica histórica entre duas execuções nesta camada;
- não há grafo de equivalência de entidade/empresa;
- não há conteúdo competitivo renderizado por browser;
- `report-catalog/cat-05.html` projeta evidência persistida e não executa IA durante a renderização;
- `SEARCH-HISTORY-001` compara evidência determinística e não transforma recomendações de IA em score temporal;
- a IA recebe features determinísticas, não o corpo integral da página;
- não existe garantia de ganho de ranking a partir das recomendações.
