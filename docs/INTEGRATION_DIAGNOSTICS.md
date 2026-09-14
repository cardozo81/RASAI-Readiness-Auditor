# Diagnóstico de integrações externas

**Estado:** vigente.

## Objetivo

O RASAi possui uma superfície de diagnóstico operacional para integrações externas configuradas no console local. O objetivo é identificar antecipadamente problemas de configuração, autenticação, autorização, recurso, quota ou comunicação sem transformar o diagnóstico em uma auditoria, sem gerar findings do website e sem alterar o comportamento homologado do pipeline.

A feature é deliberadamente **aditiva e consultiva**. Nesta versão, o resultado do diagnóstico:

- não muda elegibilidade de execução;
- não muda `AI=auto`;
- não altera quarentena/circuit breaker;
- não impede processamento ou reprocessamento;
- não altera SARI, SCORE-GEO, Coverage ou Confidence;
- não grava evidência em `AUD-*/audit.db`;
- não executa reprocessamento;
- não substitui o resultado real do adapter durante uma auditoria.

## Acesso no console

O ponto de entrada continua sendo o menu já existente:

```text
INÍCIO

1. Nova auditoria / configurar e executar
2. Auditorias / histórico
3. Relatórios consolidados
4. Integrações / credenciais
5. Sistema / restaurar padrões
?. Ajuda
Q. Sair
```

Não foi criado um novo item de primeiro nível.

Ao abrir `Integrações / credenciais`, o console apresenta as integrações conhecidas, agrupadas por contexto:

```text
IA
SERP / Search Intelligence
Serviços externos
```

Cada integração pode aparecer como, por exemplo:

```text
CONFIGURAR
CONFIGURADO - NÃO VALIDADO
OPERACIONAL
OPERACIONAL COM VALIDAÇÃO LIMITADA
FALHA TEMPORÁRIA
CREDENCIAL RECUSADA
SEM AUTORIZAÇÃO
ERRO DE CONFIGURAÇÃO
RECURSO/ENDPOINT NÃO DISPONÍVEL
QUOTA / BILLING
DIAGNÓSTICO DESATUALIZADO - CONFIGURAÇÃO ALTERADA
```

## O que um teste comprova

Um probe representa somente o estado observado **no momento da validação**. Uma chamada isolada não autoriza afirmar que um fornecedor está globalmente estável.

O RASAi pode validar, conforme o contrato disponível para cada integração:

1. dependências locais obrigatórias;
2. formato/configuração conhecida pelo adapter;
3. resolução de endpoint e comunicação HTTP;
4. autenticação, quando o fornecedor oferece um probe seguro;
5. autorização/recurso, quando isso pode ser verificado sem executar a finalidade completa;
6. catálogo/modelo, quando o fornecedor expõe listagem compatível;
7. property/aplicação configurada, quando faz parte do contrato da integração.

O console usa a expressão `OPERACIONAL` como resultado pontual, não como garantia futura de disponibilidade.

## Falha determinística versus falha temporária

O diagnóstico não deve confundir indisponibilidade do fornecedor com erro do usuário ou do RASAi.

### Condições tratadas como determinísticas

Exemplos:

- dependência obrigatória ausente;
- formato de configuração inválido;
- credencial recusada;
- ausência de autorização;
- property/application ID/recurso incompatível;
- modelo configurado fora do contrato ou indisponível no catálogo acessível;
- quota, crédito ou billing quando o fornecedor explicita essa condição.

Essas condições tendem a permanecer até ocorrer alteração de configuração, permissão, credencial ou situação comercial.

### Condições tratadas como temporárias

Exemplos:

- timeout;
- erro de rede;
- HTTP `429`;
- HTTP `5xx`.

Nesses casos, o console informa que a falha **não prova erro de configuração** e recomenda reteste. Um `503`, por exemplo, não é apresentado como credencial inválida.

## Estratégia de custo mínimo

O verificador não deve executar trabalho comercial ou gerativo apenas para provar conectividade quando existe alternativa mais barata e tecnicamente suficiente.

### Providers de IA

A estratégia preferencial é consultar endpoint de autenticação/catálogo/modelos sem enviar prompt. O diagnóstico não executa análise semântica, remediação, Improvement Intelligence ou qualquer payload de AUD.

Consequências:

- nenhum conteúdo do website é enviado pelo diagnóstico;
- nenhum prompt de auditoria é usado;
- o teste não tenta medir qualidade do modelo;
- quando o fornecedor não permite comprovar toda a capacidade sem uma chamada de geração, o estado pode ser `OPERACIONAL COM VALIDAÇÃO LIMITADA` em vez de inventar uma garantia.

Para GitHub Copilot, o diagnóstico valida o token no GitHub sem criar uma sessão de chat Copilot. Portanto, entitlement/modelo do Copilot continua sendo uma capacidade que só pode ser confirmada integralmente pelo adapter em uso real.

### SERP

SerpApi usa o endpoint de conta para validar a credencial sem executar uma pesquisa de SERP.

Outros adapters usam somente probes técnicos mínimos. O diagnóstico não deve ser interpretado como medição de ranking nem virar observação SERP.

### Google Search Console

O probe consulta as propriedades acessíveis pelo OAuth e verifica se `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` está realmente entre as propriedades da conta autenticada.

Assim são diferenciados, entre outros casos:

```text
OAuth recusado
OAuth válido + property sem acesso
OAuth válido + property acessível
```

A propriedade continua sendo configuração não secreta; o bearer token continua sendo secret.

### PageSpeed, CrUX e CrUX History

Na superfície do **console interativo**, esses três diagnósticos usam por padrão o alvo fixo:

```text
https://pudim.com.br
```

Esse valor existe somente para o teste de integração. Ele:

- não altera a URL da auditoria;
- não é gravado como configuração global do projeto;
- não interfere no processamento ou reprocessamento;
- não substitui as URLs selecionadas pelo usuário durante uma auditoria.

PageSpeed executa uma consulta mínima real para essa URL com a API key configurada. CrUX e CrUX History consultam a origem `https://pudim.com.br`. Dessa forma o console pode validar o caminho `credencial + endpoint + consulta real` em vez de depender apenas de uma requisição deliberadamente incompleta.

O probe continua classificado como `LIGHT_QUOTA`, pois a validação pode consumir quota técnica das APIs Google.

Para CrUX e CrUX History, ausência de dados de campo para o alvo padrão não é confundida com falha de autenticação. Quando a API e a credencial respondem corretamente, mas não existe registro para a origem, o estado é apresentado como `OPERACIONAL COM VALIDAÇÃO LIMITADA` com categoria `NO_FIELD_DATA`.

### Microsoft Clarity

A integração possui quota diária particularmente restrita. O diagnóstico evita Data Export apenas para validar a configuração. O console pode confirmar comunicabilidade do endpoint, mas não deve gastar uma chamada de exportação para produzir um `OK` cosmético.

Por esse motivo o Clarity é omitido da ação em lote de probes seguros e permanece disponível para diagnóstico individual limitado.

### Dynatrace

O diagnóstico usa a Config API já compatível com o adapter, verificando:

```text
DYNATRACE_API_TOKEN
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
```

A URL deve ser HTTPS e o application ID precisa ser acessível pelo token configurado.

## Dependências e correção pelo próprio diagnóstico

Cada integração declara as variáveis obrigatórias, opcionais e relacionadas ao seu contrato.

Exemplo conceitual:

```text
Google Search Console

RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN   obrigatória / secret
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL       obrigatória / configuração
RASAI_GSC_ENABLED                          relacionada
```

A tela oferece:

```text
T. Validar / retestar integração
A. Ajustar dependência/parâmetro
C. Abrir catálogo completo de configuração
V. Voltar
```

`A. Ajustar dependência/parâmetro` reutiliza o editor canônico de variáveis do console. Não existe um segundo mecanismo de gravação de configuração.

Depois da alteração, o usuário retorna para a mesma integração e escolhe:

```text
S. Salvar configuração não secreta no INI e retestar
T. Retestar agora sem salvar o INI
V. Voltar sem retestar
```

Secrets continuam fora do `rasai-console.ini`. Persistência de credencial no Windows/User continua exigindo a ação explícita já existente no editor de credenciais.

## Validação em lote

A tela oferece:

```text
T. Validar todas as integrações configuradas com probe seguro
```

Somente integrações com dependências obrigatórias presentes são candidatas. Uma integração marcada como inadequada para probe em lote por quota/custo é omitida e informada ao operador.

A execução do diagnóstico não utiliza retry agressivo. Repetir automaticamente uma chamada poderia aumentar consumo e mascarar uma condição temporária.

## Persistência do último diagnóstico

O resultado é metadado operacional local, fora dos workspaces imutáveis:

```text
<audits_root>/.rasai/integration-diagnostics.json
```

São persistidos somente dados sanitizados, como:

```text
integration_id
checked_at
status
category
http_status
latency_ms
probe_cost
validated_facets
configuration_fingerprint
```

Não são persistidos:

- API keys;
- OAuth access tokens;
- passwords;
- client secrets;
- payloads de AUD;
- respostas completas potencialmente sensíveis do fornecedor.

`configuration_fingerprint` é um hash não reversível dos valores relevantes. Quando key, token, modelo, endpoint, property, região ou outro parâmetro relacionado muda, o diagnóstico anterior passa a ser apresentado como desatualizado.

Também existe validade temporal: um diagnóstico antigo é histórico, não uma afirmação sobre o estado atual do fornecedor.

## Uso futuro antes de processar/reprocessar

A persistência foi desenhada para permitir posteriormente um warning consultivo antes de uma execução ou reexecução, por exemplo:

```text
Gemini apresentou FALHA TEMPORÁRIA em 14/09/2026 10:37.
A configuração usada pelo próximo processamento é a mesma.
Continuar pode resultar em nova falha desta etapa.

1. Validar novamente
2. Continuar mesmo assim
V. Voltar
```

Esse warning **não faz parte do bloqueio da execução nesta versão**. O pipeline real continua sendo a fonte definitiva de sucesso/falha. Uma falha temporária registrada anteriormente não autoriza o RASAi a concluir que o serviço continua indisponível.

## Segurança e fronteira arquitetural

O diagnóstico é instalado somente na superfície local de integrações do console. O core de processamento não consulta o arquivo de diagnóstico nesta versão.

Isso preserva o princípio:

```text
configuração/diagnóstico do console
        !=
resultado factual da auditoria
```

Uma falha de integração externa também não deve ser convertida em finding do website.
