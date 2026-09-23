# Análise Direcionada

## Propósito

`report-catalog/directed-analysis.html` é a camada estratégica auditável do RASAi.

Ela não é um CAT e não produz fatos técnicos próprios. Os CATs continuam sendo os proprietários das medições, findings, evidências, métricas e remediações. A Análise Direcionada correlaciona esses dados persistidos para organizar ações, benefícios multidimensionais, prioridade, esforço, confiança, dependências e validação.

Fluxo:

```text
dados/evidências persistidos
→ análises e remediações dos CATs
→ Recommendation Governance
→ Strategic Context Builder
→ IA estratégica opcional
→ validação estrutural da resposta
→ persistência directed_analysis_*
→ report-catalog/directed-analysis.html
```

Nenhum collector, crawler, SERP, GSC, Lighthouse, Apdex, W3C, OSV, KEV ou outro provider de coleta é iniciado pela Análise Direcionada.

## Momento de execução

A análise ocorre depois dos finalizadores funcionais da auditoria e antes da projeção final de `report-catalog/`.

A renderização HTML é read-only. Se a IA estiver indisponível, a auditoria e os CATs permanecem válidos; a página explicita a limitação e não inventa estratégia ausente.

## Contexto estratégico

O contexto enviado à IA é estruturado e reduzido. HTML dos CATs não é usado como entrada.

São incluídos somente fatos já persistidos e referências validadas, incluindo:

- catálogos solicitados e seus estados finais conhecidos;
- métricas principais;
- recomendações aceitas pela Recommendation Governance;
- remediações de segurança passiva;
- evidências e limitações;
- IDs de ações e referências CAT previamente construídas pelo sistema.

A IA recebe instrução explícita para não criar fatos, ações, evidências, vulnerabilidades, causas de ranking ou links.

## Unidade de análise: ação

Cada ação persistida em `directed_analysis_actions` possui:

- `action_id` estável;
- origem e identificador do registro técnico;
- motivo;
- objetivo principal;
- dimensões afetadas e ganho esperado;
- prioridade;
- esforço;
- confiança e justificativa;
- dependências;
- orientação de implementação;
- passos de validação;
- referências de origem, evidência e remediação;
- estado da análise.

A IA pode enriquecer apenas `action_id` fornecido pelo sistema. Uma resposta que mencione ação ou dependência desconhecida é rejeitada.

Se o provider repetir o mesmo `action_id` com conteúdo normalizado idêntico, o RASAi deduplica a repetição sem criar uma segunda ação. Se o mesmo `action_id` aparecer com conteúdo conflitante, a resposta é rejeitada pelo contrato da Análise Direcionada. Assim, uma duplicação de transporte/formatação não degrada uma resposta semanticamente idêntica, mas duas versões divergentes da mesma ação nunca são combinadas silenciosamente.

## Rastreabilidade

Links são construídos deterministicamente pelo RASAi e nunca pela IA.

A referência contém, conforme aplicável:

```text
CAT
→ seção estável
→ assunto/identificador persistido
→ evidência
→ remediação
```

CAT-08, CAT-09 e CAT-10 utilizam anchors estáveis para detalhes materializados quando existe identificador técnico correspondente. Para fontes cujo contrato não possui detalhe atômico navegável, o link termina na seção estável e apresenta o identificador técnico na própria Análise Direcionada.

Links por hash para dialogs são abertos automaticamente pelo JavaScript compartilhado do `report-catalog/`.

## IA, custo e auditoria

O recurso reutiliza os providers e o contrato de tentativas já existentes no RASAi.

Contrato semântico:

```text
DIRECTED-ANALYSIS-001
```

Finalidade de comunicação:

```text
DIRECTED_ANALYSIS
```

Tentativas são registradas em `ai_provider_attempts`; requisição/resposta sanitizadas seguem `ai_exchange_log`. Tokens, custo, provider, modelo, reasoning, resultado e retries permanecem visíveis em **IA e integrações**.

O raw response persistido pela Análise Direcionada passa pela sanitização de segredos antes de ser salvo.

## Persistência

Tabelas aditivas:

- `directed_analysis_runs`
- `directed_analysis_actions`

O run registra versão de contrato/prompt, provider/model/reasoning, idioma, hash do contexto, versões/fontes dos CATs, resumo, dimensões, objetivos, roadmap, limitações, contexto estruturado e resposta IA sanitizada.

## Esforço

- **Baixo:** configuração, conteúdo pontual ou alteração isolada.
- **Médio:** múltiplos componentes ou implementação técnica relevante.
- **Alto:** alteração arquitetural, grande volume, integração ou múltiplas equipes.

A classificação estratégica só é apresentada quando materializada por análise válida; o renderer não a inventa.

## Confiança

Confiança significa **grau de sustentação da recomendação pelas evidências disponíveis na auditoria**.

- **Alta:** evidência direta, consistente e suficiente.
- **Média:** evidência relevante, porém incompleta ou indireta.
- **Baixa:** há indícios, mas dados adicionais são necessários.

Não representa probabilidade garantida de melhoria.

## Reprocessamento

O reprocessamento pode reconstruir a Análise Direcionada a partir da AUD persistida, sem nova coleta:

```text
AUD existente
→ finalizadores funcionais persistidos
→ reconstrução da Análise Direcionada
→ reconstrução de report-catalog
```

A reconstrução não implica nova chamada de IA por definição. O RASAi recalcula o hash do contexto estratégico efetivo:

- se o contexto não mudou, o resultado anterior pode ser reutilizado sem nova chamada de provider;
- se o contexto mudou e a síntese por IA é aplicável, o resultado anterior é preservado na trilha do `RPR-*` antes da nova materialização;
- a nova chamada, quando necessária, usa o mesmo contrato global de provider/modelo/reasoning, telemetria e custo da auditoria;
- alterações de evidência sem impacto no contexto consumido pela Análise Direcionada não devem provocar rerun apenas porque existe uma nova versão global de evidência.

Consulte [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md) e [GOVERNED_EVIDENCE_AI_PIPELINE.md](GOVERNED_EVIDENCE_AI_PIPELINE.md).

## Configuração humana

Não existe uma chave adicional específica para a Análise Direcionada. Isso evita duplicar governança de IA.

A camada estratégica respeita o uso de IA efetivamente solicitado para a auditoria e os providers/modelos disponíveis no contrato global. Quando a auditoria não solicita IA, a página permanece disponível como projeção das ações técnicas persistidas e informa que a síntese estratégica por IA não foi materializada.

## SaaS

A página integra o mesmo contrato `CATALOG_REPORT_PAGES` usado por `report-catalog/`. Por isso, listagem e entrega HTTP do SaaS seguem o mesmo boundary autorizado já aplicado às demais páginas.

## Relação com a Matriz de encerramento estrutural

A Análise Direcionada não é um catálogo e não participa como um CAT adicional na Matriz de encerramento estrutural.

A matriz continua avaliando CAT-01 ... CAT-10 e seus controles estruturais. A nova página não pode elevar nem reduzir artificialmente os eixos de Configurabilidade, Governança, Exposição, Confiabilidade, Integridade, Segurança ou Maturidade dos CATs.
