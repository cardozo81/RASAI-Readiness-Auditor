# Reutilização de configuração de AUD

## Objetivo

O RASAi permite iniciar **uma nova auditoria** usando como ponto de partida a configuração efetivamente registrada em outro `AUD-*`. O objetivo é repetir uma configuração de medição com menor deriva operacional e manter rastreabilidade entre observações independentes.

Este fluxo é diferente de reprocessamento:

- **Reprocessar** mantém o mesmo `AUD-*`, cria uma tentativa `RPR-*` quando existe trabalho recuperável e tenta completar a observação original sem repetir sucessos por padrão.
- **Reutilizar configuração** copia somente a configuração não secreta para a sessão atual e a próxima execução cria um **novo `AUD-*`**.

## Elegibilidade da origem

O estado analítico do AUD de origem não determina se sua configuração pode ser reutilizada.

Um `AUD-*` completo, parcial, preliminar ou bloqueado pode fornecer configuração quando:

- o diretório do AUD e `audit.db` existem;
- o Audit ID informado existe em `audit.db`;
- existe snapshot canônico de configuração para aquela execução;
- o tipo do snapshot é compatível com a superfície que está solicitando a reutilização;
- schema, estrutura e hash do snapshot são válidos.

A ausência ou corrupção do snapshot é tratada de forma **fail-closed**. O RASAi não tenta reconstruir a configuração geral a partir de HTMLs, relatórios ou efeitos indiretos da execução.

Quando o snapshot canônico existe, mas não contém o bloco dedicado de Search Intelligence, o console pode recuperar **somente os inputs SERP reproduzíveis que estejam materializados no próprio `audit.db`**, a partir de `serp_observations`. Essa recuperação é read-only, não altera o AUD de origem e não inventa termos, credenciais ou valores ausentes. O console sinaliza que esses dados foram reconstruídos e exige revisão antes da nova execução.

Essa regra é independente da consolidação. Somente AUDs que atendem ao contrato de finalização continuam elegíveis para consolidação, tendências e comparações oficiais.

## Snapshot canônico

Execuções iniciadas pelas superfícies suportadas persistem no próprio `audit.db` um snapshot não secreto da configuração efetivamente usada.

A tabela `audit_execution_configurations` registra:

- versão do schema do snapshot;
- tipo da superfície (`CONSOLE` ou `AUDIT_PAYLOAD`);
- configuração canônica em JSON;
- SHA-256 da configuração;
- `source_audit_id`, quando uma nova execução reutilizou outro AUD;
- hash da configuração de origem;
- campos efetivamente alterados;
- `execution_series_id`;
- escopo operacional necessário para validação de tenancy/SaaS;
- timestamp de criação.

O hash representa a configuração efetiva. Metadados de proveniência não alteram o fingerprint da configuração.

### Configuração do console

O snapshot do console contém a configuração não secreta necessária para reproduzir a execução, incluindo:

- targets normalizados;
- projeto, idioma, mercado e dispositivo;
- limites e timeouts;
- provider/modelo/reasoning de IA, sem credencial;
- Web Performance e suas opções;
- Synthetic Apdex e Experience Apdex;
- configurações não secretas expostas pelo catálogo de ambiente;
- configuração da análise profunda quando aplicável;
- Search Intelligence da execução.

### Search Intelligence / SERP

Termos de busca são entrada de uma execução e continuam **fora do `rasai-console.ini` geral**. Entretanto, fazem parte do snapshot do `AUD-*` porque são necessários para reproduzir aquela observação.

Quando Search Intelligence foi solicitado, o snapshot registra:

- termos pesquisados;
- profundidade;
- região/localidade;
- dispositivo SERP;
- classificação competitiva habilitada/desabilitada;
- parâmetros não secretos do provider e limites que pertencem ao contrato normal de configuração.

Ao carregar o AUD, esses dados voltam para a sessão atual e podem ser revisados antes da nova execução. Se o bloco específico de Search Intelligence não estiver no snapshot, mas existirem observações SERP persistidas no mesmo `audit.db`, o console recupera os termos e o contexto observável dessas evidências e marca a situação para revisão.

## Credenciais e secrets

Credenciais nunca são copiadas do AUD de origem.

API keys, bearer tokens, senhas, tokens OAuth e demais secrets continuam sendo resolvidos no momento atual por sessão, Windows/User, Windows/Machine observado ou mecanismo SaaS correspondente.

Depois de aplicar a configuração histórica, o console reconcilia as dependências com o ambiente atual. Se a configuração solicitar uma integração que hoje não possui credencial/configuração válida, o usuário recebe um alerta imediatamente.

Exemplos:

```text
ATENÇÃO: IA/openai: OPENAI_API_KEY não configurada
ATENÇÃO: Search Intelligence: <credencial do provider> não configurada
ATENÇÃO: Web Performance/CrUX: RASAI_CRUX_API_KEY não configurada
```

O alerta não injeta, inventa nem recupera o secret. O usuário pode corrigir a credencial/configuração e o preflight continua sendo a autoridade final antes da execução.

## Console local

Há dois caminhos equivalentes para carregar configuração:

```text
Início > Auditorias / histórico > selecionar AUD-* > Carregar esta configuração para uma nova auditoria
```

ou, dentro do dashboard completo de configuração:

```text
L. Carregar configuração de AUD [NOVA EXECUÇÃO]
```

Os dois caminhos usam o mesmo carregador e, quando a operação é concluída, mostram um resumo explícito da configuração efetivamente aplicada à sessão. O resumo inclui no mínimo:

```text
CONFIGURAÇÃO CARREGADA
Origem
Entrada
Alvo
Projeto
Dispositivo
Idioma / mercado

SEARCH INTELLIGENCE / SERP
Estado
Termos
Depth
Região
Dispositivo SERP
Competitive
Modo/provider/engine
Estado da credencial atual
```

O target restaurado também sincroniza o campo visual de URL do cabeçalho. Assim, o cabeçalho e o item `Entrada` do dashboard representam a mesma configuração carregada.

Credenciais do AUD nunca aparecem como valor reutilizado. A tela informa apenas a variável esperada e se existe uma credencial disponível **agora** na sessão/Windows.

Quando o carregamento pelo histórico é concluído com sucesso, a navegação faz handoff direto para:

```text
Início > Preparar auditoria
```

Esse contexto permanece ativo enquanto o usuário revisa a nova execução. Alterar campos, salvar o INI, abrir credenciais/integrações, consultar ajuda ou retornar de uma subtela leva novamente ao dashboard de preparação; somente `V. Voltar ao início` encerra explicitamente esse contexto.

O fluxo é:

1. usuário seleciona ou informa `AUD-*`;
2. RASAi valida `audit.db` e o snapshot canônico;
3. parâmetros não secretos, targets e inputs de execução reproduzíveis são carregados;
4. Search Intelligence é restaurado pelo snapshot ou, quando necessário e possível, pelas observações SERP persistidas no próprio AUD;
5. o estado visual do console é sincronizado com o target/dispositivo carregados;
6. credenciais e dependências são reconciliadas com o ambiente atual;
7. o console exibe o resumo do que foi restaurado e os alertas aplicáveis;
8. o console entra ou permanece em **Preparar auditoria**;
9. usuário pode revisar e alterar qualquer parâmetro permitido sem perder o contexto de preparação;
10. preflight normal é executado;
11. a execução cria um **novo `AUD-*`**;
12. o novo snapshot registra origem, série e diferenças.

Para uma única URL, o target volta ao modo URL. Para múltiplos targets, o console materializa um TXT operacional em `audits/.reused-inputs/` e mantém no snapshot a lista canônica de URLs, não a dependência do caminho de um arquivo anterior.

## SaaS / Web API

O backend SaaS usa o mesmo conceito de snapshot e proveniência. Ao criar um durable job `AUDIT`, a API pode receber `source_audit_id` e aplicar overrides explícitos do novo job sobre a configuração reutilizada.

O AUD de origem precisa pertencer ao mesmo escopo operacional permitido (`project_id`, `property_id` e `environment_id` quando aplicáveis). Proveniência é controlada pelo servidor e não pode ser forjada pelo payload do cliente.

`source_audit_id` é uma entrada de criação de `AUDIT`; não transforma outros tipos de job em auditoria.

## Linhagem e séries

A primeira execução com snapshot recebe um `execution_series_id`. Uma nova auditoria criada a partir dela herda esse identificador.

Exemplo:

```text
SER-ABC
  AUD-001  configuração inicial
  AUD-014  reutilizou AUD-001 sem alterações
  AUD-031  reutilizou AUD-014 com max_pages alterado
```

Cada `AUD-*` continua sendo uma observação independente. A série descreve apenas a relação metodológica entre configurações.

## Comparabilidade no consolidado

A linhagem de configuração complementa as regras de comparabilidade do consolidado. Ela não recalcula scores persistidos.

Classificações principais:

- `EXACT`: mesma série e mesmo hash de configuração;
- `PARTIAL`: mesma série, com alteração de configuração;
- `EQUIVALENT_WITHOUT_LINEAGE`: hashes equivalentes sem uma série compartilhada explícita;
- `UNRELATED`: configuração/série não estabelecem repetição controlada;
- `INSUFFICIENT_DATA`: snapshot insuficiente no par selecionado.

Campos alterados dentro da mesma série são expostos quando disponíveis.

## Relação com reprocessamento

Reutilização e reprocessamento nunca devem ser confundidos:

```text
Reprocessar
AUD-123 -> RPR-001 -> continua AUD-123

Reutilizar configuração
AUD-123 -> carregar parâmetros -> executar -> AUD-456
```

Um AUD incompleto pode simultaneamente:

- ser candidato a reprocessamento, quando possui requisitos recuperáveis;
- servir como fonte de configuração para uma nova auditoria, quando possui snapshot canônico íntegro.

Uma capacidade não depende da outra.

## Testes por sistema operacional

A validação segue a matriz operacional do produto:

- **Windows**: autoridade para console local, navegação, carregamento de configuração, materialização de targets, credenciais Windows e runtime local;
- **Linux**: autoridade para SaaS/Web API, durable jobs, control plane e integrações de servidor;
- testes puros de domínio, hash, schema e comparabilidade podem ser multiplataforma.

## Segurança e integridade

O recurso não altera:

- SARI-001;
- SCORE-GEO-004;
- pesos ou gates de readiness;
- política de quarentena/circuit breaker de providers;
- política de roteamento de IA;
- semântica do reprocessamento seletivo;
- `audit.db` como fonte de evidência da observação;
- regra de que apenas AUD final e elegível participa da consolidação geral.

Falha ou ausência de snapshot não altera o resultado analítico já persistido do AUD. Ela apenas impede que aquele AUD seja usado como fonte de configuração.