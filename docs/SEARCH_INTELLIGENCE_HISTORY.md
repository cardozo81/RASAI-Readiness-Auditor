# Histórico de Search Intelligence

## Objetivo

Search Intelligence History compara duas observações persistidas de Search Intelligence ao longo do tempo, preservando exatamente o contexto de medição.

Identificador metodológico atual:

```text
SEARCH-HISTORY-001
```

A capacidade é observacional. Ela não afirma que um deploy, uma alteração de conteúdo ou uma alteração técnica causou movimento de ranking em Search.

## Identidade de comparação

Um delta de posição só é calculado quando as observações baseline e atual possuem os mesmos valores de:

- query;
- mecanismo de busca;
- país;
- região;
- idioma;
- dispositivo;
- profundidade de resultados solicitada;
- domínio do cliente.

A comparação também exige proveniência compatível:

- ambas as observações devem estar com status `OBSERVED`;
- o provider deve permanecer o mesmo;
- o modo de dados deve permanecer o mesmo.

Se qualquer uma dessas condições mudar, o contexto é reportado como não comparável, em vez de produzir um delta de posição potencialmente enganoso.

## Semântica de posição

Quando o domínio do cliente está `FOUND` nas duas observações, o RASAi pode reportar:

- `POSITION_IMPROVED`;
- `POSITION_REGRESSED`;
- `POSITION_UNCHANGED`.

Dentro do mesmo contexto observado, uma posição numérica menor é melhor.

Exemplo:

```text
antes: 8
depois: 4
delta: -4 posições
status: POSITION_IMPROVED
```

O delta é apenas descritivo. Ele não constitui atribuição causal.

## Limite da profundidade observada

`NOT_FOUND_WITHIN_DEPTH` não é convertido em uma posição numérica artificial.

Se o cliente passa de `NOT_FOUND_WITHIN_DEPTH` para `FOUND`, o evento é:

```text
ENTERED_OBSERVED_DEPTH
```

Se passa de `FOUND` para `NOT_FOUND_WITHIN_DEPTH`, o evento é:

```text
LEFT_OBSERVED_DEPTH
```

Esses estados significam apenas que o domínio entrou ou saiu da janela de observação solicitada. Eles não estabelecem uma posição absoluta fora daquela profundidade.

## Histórico determinístico de conteúdo

Quando as observações baseline e atual possuem status determinístico de comparação competitiva `CONSOLIDATED`, a camada histórica também pode comparar evidências persistidas da página do cliente:

- cobertura da query no corpo visível;
- cobertura da query no título;
- cobertura da query em headings;
- contagem aproximada de palavras do texto visível;
- tipos JSON-LD observados;
- códigos determinísticos de gaps competitivos.

Classes de evento atuais incluem:

- `CONTENT_SIGNAL_CHANGED`;
- `CONTENT_VOLUME_CHANGED`;
- `STRUCTURED_DATA_CHANGED`;
- `DETERMINISTIC_GAP_ADDED`;
- `DETERMINISTIC_GAP_RESOLVED`.

Esses eventos permanecem evidência correlacional. Contagem de palavras não equivale a qualidade, diferença de markup não é recomendação automática e a resolução de um gap de conteúdo não prova por que a posição em Search mudou.

## Integração com deploy e milestone

O comando de histórico pode usar o modelo de milestone da Product Platform, que já seleciona as auditorias baseline e atual.

Isso mantém um único contrato before/after no produto, em vez de introduzir um sistema paralelo de marcadores de deploy.

A linha do tempo é interpretada assim:

```text
observação Search baseline
        |
        v
milestone / marcador de deploy
        |
        v
observação Search atual
        |
        v
diferenças observadas de Search e conteúdo
```

O marcador estabelece cronologia, não causalidade.

## CLI

### Comparação direta entre workspaces

```powershell
rasai search-history `
  --baseline-workspace audits/AUD-BASELINE `
  --current-workspace audits/AUD-CURRENT
```

Toda comparação bem-sucedida também materializa um relatório HTML independente e um manifest em `audits/search-history/SH-*/`. Use `--report-root PATH` para substituir essa raiz de saída.

Saída JSON opcional:

```powershell
rasai search-history `
  --baseline-workspace audits/AUD-BASELINE `
  --current-workspace audits/AUD-CURRENT `
  --json search-history.json
```

### Comparação baseada em milestone

```powershell
rasai search-history `
  --milestone <milestone-id> `
  --audits-root audits
```

O comando aceita os mesmos modos de seleção de baseline usados pela Product Platform:

```text
AUTO
GOLDEN
EXPLICIT
```

Para seleção explícita:

```powershell
rasai search-history `
  --milestone <milestone-id> `
  --baseline-mode EXPLICIT `
  --baseline-audit <audit-id> `
  --current-audit <audit-id>
```

## Contrato de saída

A saída JSON/console inclui:

- ID da auditoria baseline;
- ID da auditoria atual;
- identificador metodológico;
- quantidade de contextos comparáveis;
- quantidade de contextos não comparáveis;
- observações de compatibilidade;
- lista de eventos;
- política de interpretação.

Saída independente:

```text
audits/search-history/SH-*/
├─ report.html
└─ manifest.json
```

O manifest do par registra IDs das auditorias baseline/atual, metodologia, metadados de milestone quando fornecidos, comparabilidade, contagens de eventos, eventos, política de origem, limite de scoring e política de causalidade.

Cada evento pode conter:

- chave exata de contexto;
- query;
- status;
- rótulo;
- valor anterior;
- valor posterior;
- delta numérico, quando fizer sentido;
- unidade;
- observação metodológica.

## Relação com o relatório HTML

`report/search-intelligence.html` é a superfície canônica de Search Intelligence da auditoria em um ponto no tempo.

`SEARCH-HISTORY-001` é um contrato separado de comparação temporal. Manter esses contratos separados evita que o HTML pontual sugira silenciosamente que uma observação posterior foi causada por um deploy.

`audits/search-history/SH-*/report.html` renderiza esse contrato de comparação, enquanto `manifest.json` preserva proveniência e limites metodológicos legíveis por máquina. A superfície independente pertence ao par de auditorias, não a um dos `AUD-*` de origem.

## Limite de scoring

Search Intelligence History não altera:

```text
SARI-001
SCORE-GEO-004
```

Mudanças de posição, entrada/saída da profundidade observada, alterações determinísticas de conteúdo e gaps competitivos não recebem peso automático no score de readiness.

Qualquer uso futuro em scoring exige nova metodologia explícita e contrato de validação.

## Limite de IA

A saída de Competitive AI não é atualmente convertida em score semântico before/after.

A camada histórica determinística pode comparar as evidências existentes antes e depois. Qualquer análise semântica histórica futura deve permanecer vinculada a evidências e não pode inferir causalidade privada de mecanismos de busca.

## Segurança e persistência

A camada histórica opera somente leitura sobre os workspaces de auditoria.

Ela lê evidências persistidas de `audit.db` e não:

- chama um provider de Search;
- chama um provider de IA;
- faz crawl de páginas do cliente ou de concorrentes;
- reescreve observações de Search;
- reescreve tabelas de scoring.

Isso torna a comparação histórica reproduzível a partir de evidências já persistidas.

## Limitações

- a comparação usa atualmente a observação persistida mais recente para cada contexto exato dentro de cada workspace;
- mudança de provider ou de modo de dados invalida a comparação numérica de ranking naquele contexto;
- comparação semântica histórica de recomendações de Competitive AI ainda não constitui contrato estável;
- o HTML histórico é determinístico e pertence ao par; ainda não oferece gráficos de tendência multi-run com três ou mais observações;
- volatilidade e personalização de Search continuam sendo fatores externos que devem ser considerados na interpretação das mudanças observadas.
