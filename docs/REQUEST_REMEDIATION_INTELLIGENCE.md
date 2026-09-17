# Remediações agrupadas de carregamento e execução

Este documento descreve a correlação entre erros determinísticos de carregamento/execução e as remediações apresentadas no CAT-09.

## Propósito

O RASAi já coleta sinais técnicos de navegação, requisições, respostas HTTP, console e JavaScript. Esta camada não cria uma segunda fonte de verdade e não transforma cada evento em uma recomendação isolada. O fluxo é:

```text
evento/evidência determinística
        ↓
normalização determinística
        ↓
problema recorrente / assinatura técnica
        ↓
grupo de solução determinístico
        ↓
orientação de remediação por IA
        ↓
CAT-09 · uma solução para N problemas / N ocorrências
```

A separação de propósito é intencional:

- **CAT-06/CAT-07**: observação, amostras e evidência do que ocorreu;
- **CAT-09**: solução consolidada para os problemas observados;
- **IA**: somente orientação de correção sobre grupos já calculados; não altera fatos, recorrência, Apdex ou scoring.

## Fontes atuais e extensibilidade

A primeira versão possui adaptadores determinísticos para:

- CAT-06 · Synthetic Navigation Apdex: `console.error`, `pageerror` e `requestfailed` persistidos por amostra;
- CAT-07 · Synthetic User Experience Apdex: `requestfailed`, respostas HTTP `>=400`, erros de console e erros JavaScript, incluindo URL, status, tipo de recurso, first/third-party e relação com `error_forced_frustrated` quando observada.

O agrupador é deliberadamente source-agnostic. Novos coletores determinísticos podem fornecer o mesmo contrato normalizado sem alterar a semântica do CAT-09. Uma nova fonte só deve ser conectada quando possuir evidência rastreável; o relatório não deve duplicar um mesmo evento apenas porque ele foi projetado por mais de uma página.

## Normalização e agrupamento

A normalização remove variações que não representam um problema técnico diferente, como query string e fragmento de uma URL de recurso. Mensagens são normalizadas de forma conservadora para reduzir identificadores voláteis.

Cada evento recebe uma família determinística, por exemplo:

- recurso ausente (`404/410`);
- acesso negado (`401/403`);
- limitação (`429`);
- erro de servidor (`5xx`);
- timeout, DNS ou conexão;
- CORS, CSP ou MIME;
- recurso bloqueado no cliente;
- exceção JavaScript;
- erro de console;
- outro erro HTTP ou de requisição.

O agrupamento de remediação considera a família técnica e o escopo first-party/third-party/indeterminado. Assim, vários assets `404` first-party podem compartilhar uma única solução, sem perder as URLs e amostras que originaram o grupo.

A assinatura detalhada do problema continua preservada. Portanto, um grupo pode informar simultaneamente:

- `N` problemas distintos;
- `M` ocorrências;
- `X/Y` amostras afetadas;
- recursos, status, dispositivos e catálogos de origem;
- ocorrências individuais para auditoria técnica.

## Recorrência

A recorrência é calculada deterministicamente sobre as amostras observadas. Os rótulos de apresentação são:

| Faixa observada | Rótulo |
|---|---|
| `>= 80%` | Recorrente |
| `>= 20%` e `< 80%` | Intermitente |
| `< 20%` | Ocasional |

Essas faixas descrevem **frequência**, não causalidade. O RASAi não declara que um erro é estrutural apenas porque se repetiu; repetição alta é um forte sinal operacional para investigação, mas causa estrutural exige contexto técnico adicional.

## Impacto observado versus risco potencial

O relatório separa fatos observados de risco potencial.

Exemplos de impacto observado:

- evento proveniente do CAT-07: experiência sintética observada;
- evento proveniente do CAT-06: navegação sintética observada;
- amostra marcada por política de erro como `error_forced_frustrated`: impacto observado no Apdex de experiência.

Riscos potenciais — como Performance, Funcionalidade ou Confiabilidade — são derivados da família técnica e aparecem explicitamente como potenciais. A IA não pode promovê-los a fatos observados.

## Papel da IA

Quando Improvement Intelligence está habilitada e existem grupos que ainda não possuem solução válida para o fingerprint atual da evidência, o RASAi consulta o mesmo provider/modelo configurado para análise profunda.

A chamada recebe somente grupos determinísticos já consolidados. Para cada `group_id`, a IA deve produzir:

- título da solução;
- solução recomendada;
- detalhamento técnico;
- exemplo de código/configuração quando tecnicamente justificável;
- procedimento reproduzível de validação/revalidação;
- confiança de aplicabilidade entre `0` e `1`;
- esforço `LOW`, `MEDIUM` ou `HIGH`.

A confiança representa a confiança de que **a solução proposta se aplica à evidência apresentada**. Ela não altera a confiança da coleta determinística.

IDs desconhecidos, confiança fora da faixa ou esforço fora do contrato são rejeitados. Respostas parciais preservam os grupos válidos e uma tentativa curta é usada somente para os grupos não respondidos.

## Referências públicas

O melhor link público exibido para entendimento do caso é selecionado deterministicamente pelo RASAi conforme a família técnica, priorizando documentação primária ou de alta autoridade, como MDN, Chrome DevTools e web.dev.

A IA não recebe liberdade para inventar URLs de referência. Isso evita que uma sugestão tecnicamente útil fique acompanhada por link inexistente ou não verificável.

## CAT-07

No CAT-07, os eventos continuam disponíveis por amostra. Acima do detalhe individual, o relatório acrescenta a visão de padrões entre amostras com:

- grupo técnico / solução possível;
- quantidade de problemas e ocorrências;
- amostras afetadas;
- taxa e classe de recorrência;
- first-party/third-party;
- impacto observado;
- recurso representativo.

Essa visão responde **o que aconteceu e com que frequência**. Ela não contém a recomendação completa de IA.

## CAT-09

O CAT-09 possui a seção **Remediações de carregamento e execução**. A unidade principal é a solução, não o erro individual.

Cada linha representa uma solução consolidada que pode resolver vários problemas. A modal detalha:

- abrangência do grupo;
- recorrência;
- impactos observados e riscos potenciais;
- catálogos de origem;
- solução ponderada pela IA;
- confiança de aplicabilidade;
- esforço;
- detalhe técnico;
- exemplo quando pertinente;
- revalidação;
- referência pública;
- problemas cobertos;
- ocorrências individuais expansíveis.

As ocorrências não são copiadas para uma nova fonte de verdade: continuam vinculadas ao grupo como evidência subordinada.

## Persistência

A camada é aditiva ao `audit.db` e usa tabelas próprias para:

- grupos determinísticos de remediação;
- evidências/ocorrências relacionadas;
- solução de IA por grupo e fingerprint da evidência.

Uma solução de IA concluída é reutilizada enquanto o fingerprint do grupo não mudar. Nova evidência invalida somente o grupo afetado para nova orientação.

## Custo e chamadas de IA

A coleta, normalização, recorrência e agrupamento não usam IA.

Quando a orientação é necessária:

- grupos são enviados em lotes limitados;
- não existe uma chamada por ocorrência;
- grupos já solucionados com o mesmo fingerprint são reutilizados;
- reparo é curto e restrito aos grupos que faltaram;
- tentativa, tokens e custo são registrados no mesmo sistema de telemetria de IA, com finalidade própria de CAT-09.

Isso evita transformar centenas de ocorrências repetidas em centenas de chamadas de modelo.

## Impacto metodológico

Esta funcionalidade é advisory e não altera:

- SARI / SCORE-GEO;
- fórmula ou classificação Apdex;
- resultados determinísticos de CAT-06/CAT-07;
- Lighthouse/Core Web Vitals;
- findings existentes.

A IA sugere uma remediação. O ganho só pode ser tratado como observado após uma nova coleta/revalidação.

## Impacto no SaaS

As novas tabelas pertencem ao `audit.db`, que continua sendo a autoridade de evidência da auditoria. Não há mudança de schema na Product Platform/PostgreSQL nem novo campo obrigatório na Web API.

No SaaS, o impacto operacional é limitado a:

- aumento pequeno do bundle do `audit.db` pelos grupos/evidências;
- chamadas adicionais de IA apenas quando Improvement Intelligence estiver habilitada, houver grupo elegível e não existir solução reaproveitável para o fingerprint;
- telemetria/custo adicional explicitamente atribuídos à remediação agrupada;
- nenhuma mudança de scoring ou contrato de estado da auditoria.

A extensão é fail-open em relação ao resultado principal: falha ao gerar a orientação agrupada não deve transformar uma coleta determinística válida ou o CAT-08 em falha de scoring. O CAT-09 pode mostrar o grupo determinístico e informar que a solução de IA está indisponível.
