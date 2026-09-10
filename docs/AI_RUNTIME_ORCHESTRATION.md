# Orquestração de IA em runtime

Este documento descreve o contrato operacional do RASAi para uso de provedores de IA, com foco em `AI=auto`, rastreabilidade das comunicações externas e interpretação editorial transitória de campos configurados como `auto`.

A lógica deste documento é operacional. Ela não altera a identidade pública `SARI-001`, a metodologia `SCORE-GEO-004` nem transforma respostas de IA em fatos determinísticos do website.

## 1. Princípios

1. A configuração humana/original é preservada.
2. Telemetria de IA é separada de evidência de scoring.
3. Uma falha de provider não pode produzir loop infinito.
4. `AI=auto` deve distribuir chamadas entre os providers aptos **e incluídos no pool AUTO** da execução, em vez de consumir sempre o primeiro da lista.
5. Capacidade (`APTA`) e participação no AUTO são estados diferentes: um provider pode permanecer apto e explicitamente selecionável mesmo quando o usuário o exclui do AUTO.
6. Falhas terminais retiram o provider do restante daquela execução.
7. Falhas temporárias permitem novas oportunidades, mas são limitadas por circuit breaker.
8. Requests e responses externos são auditáveis, com sanitização de segredos.
9. Interpretações YMYL/E-E-A-T de campos `auto` são informativas e transitórias: não sobrescrevem configuração nem entram no cálculo do SARI.

## 2. Elegibilidade em `AI=auto`

Ao iniciar uma auditoria com provider `auto`, o RASAi consulta o registry canônico de providers. Um provider entra no pool da execução somente quando:

- está marcado como elegível para AUTO no registry;
- possui credencial configurada;
- o modelo configurado é aceito pelo adapter;
- as demais configurações obrigatórias são válidas;
- não foi explicitamente excluído do AUTO pelo usuário.

`RASAI_AI_AUTO_EXCLUDE` contém IDs/aliases de providers separados por vírgula ou ponto e vírgula. O console oferece a mesma decisão por seleção interativa. Essa configuração é não secreta e não remove a variável de API key correspondente.

Providers sem credencial, com configuração inválida ou excluídos pelo usuário são registrados como fora da execução e não recebem chamadas externas via AUTO. Um provider excluído pelo usuário continua `APTA` quando sua chave/modelo permanecem válidos e continua disponível para seleção explícita em outra execução.

A elegibilidade é específica da execução. Uma exclusão causada por falha não altera a configuração global nem impede o uso em auditorias futuras.

## 3. Round-robin por necessidade de IA

O coordenador mantém um cursor compartilhado durante a auditoria. Cada nova necessidade de IA começa pelo próximo provider elegível após o último provider efetivamente tentado.

Exemplo com `A`, `B`, `C`, `D`, sendo `D` apto porém excluído pelo usuário do AUTO:

```text
pool efetivo -> A, B, C
necessidade 1 -> A
necessidade 2 -> B
necessidade 3 -> C
necessidade 4 -> A
```

Se `B` falhar temporariamente na necessidade 2, a mesma necessidade continua em `C`. O cursor avança depois de cada tentativa; `B` não recebe retry imediato dentro daquela necessidade e poderá voltar a ser considerado em uma necessidade posterior se continuar elegível.

Em uma mesma necessidade, cada provider é visitado no máximo uma vez. Quando todos os candidatos elegíveis foram tentados sem sucesso, a necessidade termina como indisponível. Não há ciclo de retry entre providers.

## 4. Classes de falha e circuit breaker

### 4.1 Exclusão imediata

O provider é removido do pool pelo restante da execução quando a tentativa indica uma condição terminal, incluindo:

- autenticação inválida;
- falta de crédito;
- quota classificada como terminal pelo adapter;
- permissão negada;
- modelo inexistente/inválido;
- HTTP 401, 403, 404 ou 410.

O relatório registra o motivo da exclusão.

### 4.2 Falhas temporárias

Timeout, rede, indisponibilidade de servidor, rate limit e demais falhas não terminais não excluem o provider na primeira ocorrência. A saúde é acompanhada em uma janela deslizante de até cinco observações daquele provider.

O circuit breaker abre quando existem pelo menos três falhas entre as últimas cinco observações. Enquanto não atingir o limiar, o provider continua elegível para necessidades futuras.

Uma tentativa com sucesso entra na mesma janela e reduz naturalmente a densidade de falhas. O breaker é limitado à auditoria atual.

### 4.3 Provider explicitamente selecionado

Quando o usuário escolhe um provider específico em vez de `auto`, permanecem válidas as regras de retry do adapter daquele provider. A política round-robin e `RASAI_AI_AUTO_EXCLUDE` são exclusivas do AUTO.

## 5. Compartilhamento da política entre módulos

O estado do coordenador AUTO é de execução, não de módulo. Sempre que o adapter é compatível, o mesmo cursor e a mesma saúde do provider são compartilhados por:

- análise semântica;
- remediação de conteúdo;
- remediação técnica;
- explicações especializadas integradas ao runtime.

Isso evita que cada módulo reinicie a cadeia pelo primeiro provider e concentre consumo em um único serviço. Tentativas que prosseguem para outro provider devem preservar `FALLBACK`/`fallback_from_provider`/`fallback_reason` na telemetria, inclusive em fluxos especializados.

## 6. Log de comunicação com IA

O RASAi registra em `ai_exchange_log` os envelopes externos sanitizados de cada chamada efetivamente realizada. O objetivo é permitir auditoria do que ocorreu na integração, sem transformar a telemetria em evidência de scoring.

Para cada exchange são registrados, quando disponíveis:

- ordem da comunicação;
- provider e modelo;
- finalidade da chamada;
- página e snapshot associados;
- endpoint sanitizado;
- início, fim e duração;
- resultado do transporte e HTTP status;
- tipo de exceção;
- payload enviado;
- envelope/resposta recebida;
- SHA-256 do payload capturado antes de eventual truncamento;
- indicação de truncamento.

O `ai-usage.html` apresenta essas comunicações em blocos expansíveis, permitindo relacionar request e response com o provider e a finalidade.

### 6.1 Sanitização

Nunca devem ser persistidos como parte do exchange log:

- header `Authorization`;
- API keys;
- access/refresh tokens;
- passwords/client secrets;
- campos reconhecidos como raciocínio privado do provider.

Segredos encontrados em campos de payload ou query string do endpoint são redigidos.

O tamanho máximo de captura é controlado por `RASAI_AI_EXCHANGE_LOG_MAX_BYTES`. O default é 512 KiB por lado da comunicação, com limite operacional entre 4 KiB e 4 MiB. Quando o payload excede o limite, o relatório indica truncamento e mantém o hash do conteúdo sanitizado completo observado pelo recorder.

O log pode conter conteúdo da página enviado ao modelo. Portanto, o `AUD-*/audit.db` e os relatórios devem receber o mesmo tratamento de acesso e retenção aplicado aos demais artefatos da auditoria.

## 7. Resposta recebida versus resposta aceita

Uma chamada externa pode ter sido concluída pelo provider e ainda assim ser rejeitada pelo contrato do RASAi. Esses estados não são equivalentes.

- **Erro de transporte/provider:** não houve resposta válida utilizável no nível de transporte.
- **Resposta recebida, rejeitada pelo contrato RASAi:** houve comunicação externa e pode haver consumo de tokens/custo, mas a resposta não satisfez os invariantes locais.
- **Resposta aceita:** a resposta passou pela validação local e foi utilizada para a finalidade permitida.

A telemetria deve preservar essa distinção. Uma resposta rejeitada pelo contrato não deve ser rotulada genericamente como “provider indisponível” quando o provider de fato respondeu.

Custos em `ai-usage.html` são somados a partir de `estimated_cost` e `cost_currency` persistidos nas tentativas. Uma chamada sem usage retornado pelo provider não recebe custo inventado, mesmo que o billing externo possa posteriormente registrar cobrança.

## 8. Projeção de JSON Schema no wire

O schema canônico/local continua sendo a fonte de verdade para validação do RASAi. Antes de uma chamada OpenAI estruturada, o runtime projeta o schema para o subconjunto aceito pelo wire format vigente do adapter.

A projeção pode retirar constraints de valor/comprimento/cardinalidade incompatíveis no wire, preservando estrutura, tipos, propriedades obrigatórias, `additionalProperties`, arrays, enums e nulabilidade. As constraints retiradas do wire continuam validadas localmente depois da resposta.

A projeção ocorre imediatamente antes do transport. Por isso, o exchange log registra o corpo efetivamente enviado, não uma versão anterior do request.

Essa separação evita enfraquecer o contrato local apenas para satisfazer diferenças entre APIs de providers.

## 9. Contexto editorial `auto`: YMYL e E-E-A-T

Os campos de contexto editorial podem permanecer configurados como `auto`. Quando IA está habilitada e há conteúdo/evidência suficiente, o RASAi solicita uma interpretação contextual somente para apresentação.

Campos elegíveis incluem:

- perfil de risco/YMYL;
- categoria YMYL;
- propósito da página;
- público pretendido;
- relevância de experiência associada a E-E-A-T;
- sensibilidade a atualização;
- origem do conteúdo.

A saída deve conter, quando determinável:

- configuração oficial: `AUTO`;
- interpretação da IA;
- confiança;
- justificativa curta baseada no conteúdo fornecido;
- IDs de evidência efetivamente fornecidos ao modelo.

Quando o conteúdo não sustenta uma classificação, a resposta correta é `Não determinável`.

### 9.1 Não persistência canônica

A interpretação editorial da IA:

- não sobrescreve `content_analysis_contexts`;
- não cria valor resolvido permanente no banco;
- não vira evidência determinística;
- não altera SCORE-GEO-004 ou SARI-001 por si só;
- não é reutilizada como verdade canônica em outra execução.

Ela existe em memória durante a execução e é injetada no HTML final depois que as projeções persistidas foram reconstruídas. O próprio HTML naturalmente preserva o texto exibido como artefato daquela auditoria.

Para garantir essa separação, o campo transitório é removido da resposta antes que o normalizador semântico legado prossiga. No exchange log persistido, o conteúdo dessa interpretação também é redigido; a versão legível aparece apenas na seção interpretativa do relatório.

## 10. Relatórios

### `ai-usage.html`

Deve apresentar:

- resumo de uso/custo existente;
- total de custo derivado da telemetria persistida de todas as finalidades de IA suportadas;
- estado final de elegibilidade por provider;
- tentativas, sucessos, falhas temporárias e terminais;
- motivo de exclusão/circuit breaker;
- log expansível de request/response sanitizados.

### `readiness.html`

Quando houver campos `auto`, deve manter a configuração original e, separadamente, exibir “Como a IA interpretou os campos AUTO nesta execução”.

A seção deve declarar explicitamente que a interpretação é contextual, não canônica e sem impacto direto em SARI/SCORE-GEO-004.

## 11. PageSpeed, Lighthouse e Agentic Browsing

O PageSpeed Insights API v5 passou a expor `AGENTIC_BROWSING` como categoria aceita pelo parâmetro repetível `category`. O contrato atual do RASAi solicita por default:

```text
performance,accessibility,best-practices,seo,agentic-browsing
```

O parser já preserva `lighthouseResult.categories.agentic-browsing.score` quando presente. A categoria continua experimental no Lighthouse; ausência isolada do score não deve ser transformada em zero nem invalidar as quatro categorias estáveis retornadas.

Agentic Browsing permanece evidência externa e fora de SARI-001/SCORE-GEO-004.

Referência operacional primária: discovery/API client atual do Google PageSpeed Insights v5, cujo enum de `category` inclui `AGENTIC_BROWSING` desde junho de 2026.

## 12. Search Intelligence competitivo

`--competitive` classifica deterministicamente resultados SERP sem adquirir páginas adicionais. Portanto, listas de gaps de conteúdo permanecem vazias quando `comparison_status=CONTENT_COMPARISON_DISABLED`.

`--compare-content` é opt-in e acrescenta aquisição HTTP limitada do domínio de interesse e dos candidatos selecionados. Somente depois de uma comparação `CONSOLIDATED` existe evidência para gaps de title, meta description, headings, cobertura dos termos no corpo, volume de conteúdo e structured data.

A análise semântica competitiva por IA é outro opt-in separado. Ela pode sugerir oportunidades de conteúdo apenas sobre evidências persistidas e deve evitar keyword stuffing, conteúdo search-engine-first e qualquer afirmação de que uma alteração específica causará ganho de ranking.

## 13. Critérios de regressão

A suíte deve cobrir no mínimo:

- round-robin entre necessidades;
- exclusão voluntária de provider do AUTO sem apagar sua credencial e sem impedir seleção explícita;
- fallback no mesmo contexto sem repetir provider;
- telemetria de fallback também nos fluxos especializados;
- permanência após falha temporária abaixo do limiar;
- circuit breaker com três falhas nas últimas cinco observações;
- exclusão imediata por erro terminal/HTTP 404;
- ausência de loop quando todos falham;
- sanitização de segredos no exchange log;
- truncamento/hash;
- custo agregado derivado de telemetria persistida e ausência de custo inventado sem usage;
- não persistência do contexto editorial transitório;
- projeção de schema OpenAI sem alterar o validador local;
- aceitação/transporte de `agentic-browsing` no PageSpeed v5 atual;
- Search content comparison desabilitada por default e explícita quando ativada.
