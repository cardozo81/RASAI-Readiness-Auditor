# Diagnóstico de integrações externas

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado; este documento descreve somente o comportamento atual do produto.

## Objetivo

O RASAi possui uma superfície de diagnóstico operacional para integrações externas configuradas no console local. O objetivo é identificar antecipadamente problemas de configuração, autenticação, autorização, recurso, quota, comunicação e caminho de rede sem transformar o diagnóstico em uma auditoria e sem alterar o comportamento funcional do pipeline.

A feature é deliberadamente **aditiva e consultiva**. O resultado do diagnóstico:

- não muda elegibilidade funcional de execução;
- não muda `AI=auto`;
- não altera quarentena/circuit breaker;
- não altera retry do runtime;
- não altera SARI, SCORE-GEO, Coverage ou Confidence;
- não grava evidência em `AUD-*/audit.db`;
- não substitui o resultado real do adapter durante uma auditoria;
- pode gerar uma advertência antes de processar/reprocessar quando a mesma configuração possui diagnóstico problemático registrado.

A advertência não é um bloqueio permanente. O operador pode continuar explicitamente; o runtime continua sendo a fonte definitiva de sucesso/falha.

## Acesso no console

O ponto de entrada é:

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

Em `Integrações / credenciais`, as integrações são agrupadas por:

```text
IA
SERP / Search Intelligence
Serviços externos
```

Estados possíveis incluem:

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

O diagnóstico pode validar, conforme o contrato de cada integração:

1. dependências locais obrigatórias;
2. formato/configuração conhecida pelo adapter;
3. endpoint e comunicação HTTP;
4. autenticação, quando existe probe seguro;
5. autorização/recurso;
6. catálogo/modelo;
7. property/aplicação configurada;
8. caminho de rede em DNS, TCP e TLS quando a chamada principal não produz resposta HTTP conclusiva;
9. host de runtime separado quando autenticação e execução usam destinos distintos, como no GitHub Copilot.

`OPERACIONAL` é uma observação pontual, não uma garantia futura de disponibilidade.

## Diagnóstico por camadas de rede

Quando o serviço responde HTTP, a resposta por si só comprova que o caminho de transporte foi suficiente para alcançar o endpoint. Nesses casos o RASAi **não adiciona conexões TCP/TLS redundantes** apenas para confirmar o que já foi provado.

Quando ocorre timeout/erro de rede sem resposta HTTP conclusiva, o diagnóstico pode avaliar:

```text
DNS
  ↓
TCP porta 443
  ↓
TLS
  ↓
HTTP / aplicação
```

A tela apresenta, quando aplicável:

```text
Endpoint
DNS
TCP 443
TLS
HTTP
Tentativas
Latências
Classificação
Host de controle
Indicação de proxy detectado
```

### Retentativas limitadas

Retentativas automáticas deste diagnóstico são restritas a **DNS/TCP/TLS** e usam no máximo três tentativas curtas.

Elas **não repetem**:

- prompt de IA;
- geração de tokens;
- consulta SERP comercial;
- PageSpeed/CrUX real;
- GSC;
- Data Export;
- qualquer operação que possa acrescentar custo/quota apenas para confirmar uma falha de transporte.

Assim, o diagnóstico consegue diferenciar uma oscilação momentânea de transporte sem alterar a política de retry funcional do RASAi.

## Classificações de rede

O RASAi não afirma que "a VPN bloqueou" ou "o firewall bloqueou" sem evidência direta da política de rede. O processo normalmente só consegue observar o efeito.

As classificações usam linguagem probabilística:

```text
REDE OPERACIONAL
REDE OPERACIONAL APÓS RETENTATIVA
PROVÁVEL FALHA/BLOQUEIO DNS DO DESTINO
PROVÁVEL BLOQUEIO/INACESSIBILIDADE DO DESTINO
PROVÁVEL INSPEÇÃO TLS/PROXY/POLÍTICA
FALHA TLS DO DESTINO
PROVÁVEL FALHA DE CONECTIVIDADE LOCAL/GERAL
INCONCLUSIVO - PROXY/VPN PODE ALTERAR A ROTA
TRANSPORTE OK; FALHA ACIMA DE TLS/HTTP
REDE NÃO TESTADA
```

### Host de controle

O host de controle só é usado depois de uma falha de DNS/TCP/TLS do destino.

Interpretação conceitual:

```text
serviço falha + controle funciona
    -> problema aparentemente específico do destino

serviço falha + controle falha
    -> problema local/geral de conectividade é mais provável
```

O controle não transforma inferência em prova de firewall. Ele apenas melhora a separação entre falha geral e falha específica do destino.

### Proxy e VPN

Quando o ambiente possui proxy configurado, uma conexão TCP/TLS direta pode não representar o caminho real da aplicação. Nesse caso, se o teste direto falhar, o estado é mantido como **inconclusivo** e a UI informa que proxy/VPN pode alterar a rota.

O RASAi não tenta identificar marcas específicas de VPN nem presume que uma interface de rede específica seja a causa.

## Falha determinística versus temporária

### Determinísticas

Exemplos:

- dependência obrigatória ausente;
- formato inválido;
- credencial recusada;
- ausência de autorização;
- property/application ID incompatível;
- modelo fora do contrato;
- quota/crédito/billing quando explicitados pelo fornecedor.

### Temporárias

Exemplos:

- timeout;
- connection reset;
- HTTP `429`;
- HTTP `5xx`.

Um `503` recebido do fornecedor é evidência de que a rede conseguiu chegar ao serviço. Portanto, ele é classificado como indisponibilidade temporária do fornecedor, e não como bloqueio de rede.

## Estratégia de custo mínimo

O verificador não executa trabalho gerativo/comercial apenas para provar conectividade quando existe alternativa mais barata.

### Providers de IA

A estratégia preferencial é endpoint de autenticação/catálogo/modelos sem prompt.

Nenhum conteúdo do website é enviado pelo diagnóstico e nenhum prompt de auditoria é usado.

### GitHub Copilot

Há duas verificações distintas:

1. a credencial é validada na API do GitHub sem criar sessão Copilot;
2. o caminho de rede do runtime é verificado contra:

```text
https://api.githubcopilot.com/_ping
```

A segunda verificação usa somente DNS/TCP/TLS. Ela não envia prompt nem gera tokens.

Isso permite detectar o cenário em que `api.github.com` funciona, mas o domínio específico do Copilot está inacessível por política de rede/VPN/proxy.

Entitlement, assinatura, modelo e funcionamento completo do SDK continuam sendo capacidades que só o adapter real pode confirmar integralmente.

### SERP

SerpApi usa endpoint de conta quando disponível; outros adapters usam probes técnicos mínimos. O diagnóstico não vira observação SERP nem medição de ranking.

### Google Search Console

O diagnóstico reconhece duas formas de autenticação:

```text
ACCESS_TOKEN manual
ou
CLIENT_ID + CLIENT_SECRET + REFRESH_TOKEN
```

No fluxo durável, o RASAi solicita um access token temporário ao endpoint OAuth do Google e usa esse token somente em memória para consultar as propriedades acessíveis. Depois verifica se `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` está entre as properties autorizadas.

São diferenciados:

```text
configuração OAuth incompleta
Google API Key usada indevidamente como access token (ex.: prefixo AIza)
refresh token/client recusado
falha temporária no endpoint OAuth
OAuth válido + property sem acesso
OAuth válido + property acessível
```

A property é obrigatória em ambos os modos. `CLIENT_SECRET`, `REFRESH_TOKEN` e `ACCESS_TOKEN` não são exibidos nem persistidos. Consulte [GSC_OAUTH.md](GSC_OAUTH.md).

### PageSpeed, CrUX e CrUX History

No console interativo, esses três diagnósticos usam como alvo fixo de teste:

```text
https://pudim.com.br
```

Esse valor existe somente no diagnóstico. Não altera URL de auditoria nem configuração global.

PageSpeed executa consulta mínima real. CrUX e CrUX History consultam a origem padrão. O probe continua `LIGHT_QUOTA`.

Ausência de dados CrUX para o alvo não é erro de credencial; quando API e credencial respondem corretamente, o estado é `OPERACIONAL COM VALIDAÇÃO LIMITADA / NO_FIELD_DATA`.

### Microsoft Clarity

O diagnóstico evita Data Export para preservar quota escassa. O Clarity não participa do probe em lote seguro quando isso puder consumir quota relevante.

### Dynatrace

O diagnóstico usa:

```text
DYNATRACE_API_TOKEN
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
```

A URL deve ser HTTPS e o application ID precisa estar acessível pelo token.

## Dependências e correção na própria tela

A tela oferece:

```text
T. Validar / retestar integração
A. Ajustar dependência/parâmetro
C. Abrir catálogo completo de configuração
V. Voltar
```

`A` reutiliza o editor canônico de variáveis. Não existe um segundo mecanismo de persistência.

Secrets continuam fora do `rasai-console.ini`.

## Validação em lote

A ação:

```text
T. Validar todas as integrações configuradas com probe seguro
```

considera apenas integrações com dependências obrigatórias presentes e omite probes deliberadamente marcados como inadequados para lote.

As retentativas de rede não repetem a API do fornecedor; somente transporte DNS/TCP/TLS pode ser testado mais de uma vez depois de uma falha inconclusiva.

## Persistência

O resultado funcional permanece em:

```text
<audits_root>/.rasai/integration-diagnostics.json
```

A evidência de transporte é armazenada separadamente em:

```text
<audits_root>/.rasai/integration-network-diagnostics.json
```

A persistência de rede pode conter apenas metadados sanitizados:

```text
integration_id
checked_at
endpoint sem query/credencial
host
port
dns_status
tcp_status
tls_status
http_status
attempt_count
latencies_ms
classification
error_code/error_detail sanitizado
control_host/control_status
proxy_configured
```

Não são persistidos API keys, bearer tokens, passwords, client secrets, refresh tokens, payloads de AUD ou respostas completas do fornecedor.

O diagnóstico funcional continua usando `configuration_fingerprint` para detectar alteração de credencial/configuração sem persistir o valor original.

## Advertência antes de processar

Quando o usuário escolhe executar uma auditoria e existe diagnóstico anterior problemático de uma integração relevante para a configuração atual, o console apresenta advertência antes da execução.

Exemplo conceitual:

```text
ATENÇÃO - DIAGNÓSTICO ANTERIOR DE INTEGRAÇÃO

GitHub Copilot
Testado em : 14/09/2026 ...
Estado API : OPERACIONAL COM VALIDAÇÃO LIMITADA
Rede       : PROVÁVEL BLOQUEIO/INACESSIBILIDADE DO DESTINO
DNS/TCP/TLS: OK / FALHA / NÃO ALCANÇADO

C. Continuar mesmo assim
V. Voltar sem executar
```

A advertência só usa diagnóstico cuja configuração ainda corresponde ao fingerprint atual. Se a configuração mudou, o resultado anterior não é usado como alerta equivalente.

Diagnósticos antigos podem ser exibidos como alerta histórico, explicitando que não provam estado atual.

## Advertência antes de reprocessar

O mesmo princípio é aplicado ao reprocessamento seletivo. O RASAi lê a configuração canônica persistida do AUD de origem para determinar quais integrações eram relevantes e compara com os diagnósticos disponíveis na configuração atual.

A advertência ocorre **antes** do comando textual de confirmação do reprocessamento e não modifica os itens de fulfillment, retryability, temporal mode ou quarentena.

## Fronteira arquitetural

O diagnóstico permanece separado do motor de auditoria:

```text
configuração/diagnóstico consultivo
        !=
resultado factual da auditoria
```

Uma falha de integração externa não vira finding do website.

A feature não altera adapters nem políticas funcionais de rede/IA/SERP. O runtime continua sendo autoridade para decidir sucesso, retry e fulfillment durante a execução real.
