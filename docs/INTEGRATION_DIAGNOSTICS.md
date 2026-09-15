# Diagnóstico de integrações externas

O RASAi possui uma superfície de diagnóstico operacional para integrações externas configuradas no console local.

O diagnóstico é **consultivo**. Ele ajuda a identificar problemas de configuração, autenticação, autorização, quota, endpoint e transporte sem alterar o comportamento funcional da auditoria.

## Acesso

```text
INÍCIO > Integrações e serviços
```

Na superfície de integrações:

```text
D. Diagnóstico técnico das integrações
```

A correção de parâmetros usa os mesmos IDs e editores canônicos do catálogo de configuração.

## O que o diagnóstico não altera

O resultado do probe:

- não muda elegibilidade funcional do pipeline;
- não altera `AI=auto`;
- não muda custo/routing da IA;
- não altera quarentena ou circuit breaker;
- não altera retry funcional da auditoria;
- não altera SARI, SCORE-GEO, Coverage ou Confidence;
- não grava evidência de website em `AUD-*/audit.db`;
- não substitui o resultado do adapter durante uma auditoria.

Um diagnóstico problemático pode gerar orientação/advertência operacional. A tentativa real do adapter permanece a autoridade para sucesso ou falha de uma execução.

## Estados

A UI pode apresentar estados como:

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

O estado é acompanhado de motivo e dependências relevantes.

## O que um probe comprova

Um probe comprova somente o que foi observado no momento da validação.

Conforme a integração, ele pode verificar:

1. dependências locais obrigatórias;
2. formato/configuração conhecida pelo adapter;
3. endpoint e resposta HTTP;
4. autenticação segura quando existe endpoint apropriado;
5. autorização/recurso;
6. catálogo/modelo;
7. property/application configurada;
8. DNS/TCP/TLS quando a chamada principal não retorna evidência HTTP conclusiva;
9. host de runtime separado quando autenticação e uso efetivo dependem de destinos diferentes.

`OPERACIONAL` não é garantia de disponibilidade futura.

## Diagnóstico de rede

Quando existe resposta HTTP, o transporte já demonstrou conectividade suficiente até o endpoint. Nesse caso não é necessário criar conexões redundantes apenas para provar DNS/TCP/TLS.

Quando ocorre timeout ou erro de rede sem resposta HTTP conclusiva, o diagnóstico pode decompor:

```text
DNS
  ↓
TCP 443
  ↓
TLS
  ↓
HTTP / aplicação
```

A UI pode mostrar endpoint, DNS, TCP, TLS, HTTP, tentativas, latências, classificação, host de controle e indicação de proxy detectado.

## Retentativas de diagnóstico

Retentativas automáticas do diagnóstico ficam restritas às camadas de transporte e são curtas/limitadas.

O diagnóstico não repete trabalho gerativo ou comercial apenas para confirmar conectividade. Ele não usa retries próprios para:

- prompt de IA;
- geração de tokens;
- consulta SERP comercial;
- PageSpeed/CrUX real;
- GSC;
- Data Export;
- outra operação que possa acrescentar custo/quota sem necessidade.

Isso é independente da política de retry funcional dos adapters.

## Classificações de transporte

A linguagem do diagnóstico deve refletir evidência observável. Exemplos:

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

O RASAi não afirma que uma VPN ou firewall específico foi a causa sem evidência direta dessa política.

## Host de controle

Um host de controle pode ser usado depois de falha de transporte do destino para diferenciar um problema aparentemente específico do serviço de uma falha local/geral.

Interpretação:

```text
destino falha + controle funciona -> problema aparentemente específico do destino
destino falha + controle falha   -> problema local/geral é mais provável
```

Isso melhora o diagnóstico sem transformar inferência em prova de firewall.

## Proxy e VPN

Quando existe proxy configurado, um teste TCP/TLS direto pode não representar a rota efetiva da aplicação. A UI deve marcar esse cenário como inconclusivo quando apropriado e informar que proxy/VPN pode alterar o caminho.

## Falhas determinísticas e temporárias

Exemplos determinísticos:

- dependência obrigatória ausente;
- formato inválido;
- credencial recusada;
- falta de autorização;
- property/application incompatível;
- modelo fora do contrato;
- quota/billing explicitamente informado pelo fornecedor.

Exemplos temporários:

- timeout;
- connection reset;
- HTTP `429`;
- HTTP `5xx`.

Um HTTP `503` recebido prova que a requisição chegou a uma camada HTTP do serviço e deve ser classificado como indisponibilidade temporária, não como bloqueio de transporte.

## Estratégia de custo mínimo

O diagnóstico prefere endpoints sem geração de conteúdo quando disponíveis.

### IA

A estratégia ideal é autenticação, catálogo/modelos ou endpoint equivalente que não exija prompt gerativo. Nenhum conteúdo do website é enviado apenas para testar integração.

### GitHub Copilot

O contrato pode separar:

1. validação da credencial pela API do GitHub;
2. verificação do caminho até o runtime Copilot.

O caminho de runtime pode usar o endpoint de ping publicado pelo adapter e limitar-se a transporte quando possível, sem enviar prompt.

Entitlement completo, modelo e execução real permanecem responsabilidade do adapter funcional.

### SERP e demais APIs pagas

O diagnóstico não consome busca comercial apenas para comprovar que uma key existe quando há alternativa segura de validação/configuração.

## Staleness

O diagnóstico está associado à configuração observada. Se credencial, endpoint ou parâmetro relevante mudar, a UI pode classificar o resultado anterior como desatualizado.

Isso evita reaproveitar um estado `OPERACIONAL` de uma configuração diferente.

## Segurança

- valores secretos não são exibidos em claro;
- probes devem usar a menor permissão/operação possível;
- nenhum diagnóstico deve criar finding do website;
- falha do diagnóstico não substitui o preflight nem a tentativa real;
- o console orienta para o ID canônico da configuração quando uma correção é necessária.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
