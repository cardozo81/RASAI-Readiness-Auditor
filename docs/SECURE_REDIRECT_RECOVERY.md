# Recuperação segura de redirect HTTPS → HTTP

## Objetivo

Este documento descreve a política `STRICT_TLS_SAME_SITE_HTTPS_UPGRADE_V1`, usada somente quando uma navegação pública iniciada em HTTPS falha depois que a própria cadeia de redirecionamento publicada pelo site rebaixa o tráfego para HTTP.

A política existe para evitar dois erros opostos:

1. interromper uma auditoria quando existe uma rota HTTPS pública, válida e diretamente equivalente ao hop HTTP defeituoso; e
2. mascarar uma configuração insegura do site, aceitando certificado inválido ou inventando um destino não comprovado.

A recuperação é uma observação adicional e limitada. Ela **não corrige o servidor**, não altera o redirect publicado e não desabilita TLS.

## Evidência que motivou a política

Em 2026-09-06 foi executado um smoke live sem integrações pagas ou chaves de API, em ambientes limpos Windows e Ubuntu.

URL configurada:

```text
https://mdsgroup.com/
```

A cadeia efetivamente publicada e observada por Chrome/Chromium limpos foi:

```text
https://mdsgroup.com/
  → HTTP 301 Location: http://www.mdsgroup.com/
http://www.mdsgroup.com/
  → HTTP 301 Location: https://mds.pt/
https://mds.pt/
  → falha TLS: ERR_CERT_COMMON_NAME_INVALID
```

O mesmo teste, acessando diretamente o equivalente HTTPS do hop inseguro, obteve:

```text
https://www.mdsgroup.com/
  → HTTP 301 Location: /pt/
https://www.mdsgroup.com/pt/
  → HTTP 200
```

A página retornou conteúdo HTML e o título observado foi:

```text
Global Insurance and Risk Consultants - MDS Portugal
```

A evidência demonstra que a rota HTTPS esperada existe e funciona, enquanto o hop HTTP publicado segue outra rota e termina em TLS inválido.

Não é possível afirmar, apenas com essa evidência, que um navegador específico do usuário chegou à rota correta exclusivamente por HSTS, cache de 301, cookie ou qualquer outro estado local. Esses fatores devem ser tratados como hipóteses até que o ambiente local seja inspecionado.

## Regra de elegibilidade

O SearchGEO só pode tentar a recuperação quando todas as condições abaixo forem satisfeitas:

1. a URL originalmente configurada usa `https://`;
2. a navegação Chromium normal falhou;
3. o trace real da navegação contém um hop `HTTPS → HTTP`;
4. o hostname de origem e o hostname do hop HTTP representam o mesmo site, permitindo apenas diferença de prefixo `www.`;
5. o hop não contém credenciais;
6. o hop não usa porta HTTP não padrão;
7. a tentativa adicional usa o mesmo caminho/query do hop observado, trocando somente `http` por `https`;
8. a tentativa adicional mantém validação TLS estrita.

Exemplo elegível:

```text
https://example.com/a
  → http://www.example.com/b
```

Candidato permitido:

```text
https://www.example.com/b
```

Exemplo não elegível:

```text
https://example.com/
  → http://other.example.net/
```

O SearchGEO não deve criar um candidato HTTPS para domínio não equivalente.

## Limite de tentativas

A recuperação é limitada a **uma única tentativa adicional por navegação M3 que atenda aos critérios**.

Ela não pode gerar:

- loop de tentativas;
- exploração de múltiplos hosts alternativos;
- tentativa de adivinhar paths de idioma;
- tentativa automática de `/pt/`, `/en/` ou qualquer outra rota que não tenha sido comprovada pelo servidor após o hop HTTPS seguro;
- bypass de certificado.

No caso MDSGroup, o SearchGEO testa apenas:

```text
https://www.mdsgroup.com/
```

O `/pt/` é descoberto posteriormente pelo redirect HTTP 301 legítimo retornado por esse próprio endpoint HTTPS.

## TLS

A política mantém:

```text
ignore_https_errors = false
```

ou comportamento equivalente.

Se o equivalente HTTPS também apresentar certificado inválido, a recuperação falha e o bloqueio original permanece.

Nunca é aceitável transformar:

```text
certificado inválido
```

em:

```text
medição válida
```

apenas para permitir que as etapas seguintes sejam executadas.

## Evidência preservada

Quando a tentativa ocorre, `page_snapshots.browser_metadata` registra `secure_redirect_recovery` com:

- versão da política;
- motivo do acionamento;
- URL originalmente solicitada;
- URL candidata HTTPS;
- resultado da tentativa;
- cadeia original observada;
- cadeia da tentativa segura;
- URL final recuperada;
- status HTTP final recuperado;
- confirmação de que TLS permaneceu habilitado.

A cadeia HTTP original não é substituída.

Os artifacts de qualidade da origem mantêm a distinção:

```text
artifacts/source-quality-preflight.json
```

contém a visão original da aquisição/preflight, enquanto:

```text
artifacts/source-quality.json
```

contém a classificação reconciliada usada pelo restante do pipeline.

## Classificação após recuperação

Quando a tentativa HTTPS segura funciona, o problema deixa de ser um bloqueio total e recebe a classificação:

```text
HTTPS_DOWNGRADE_SECURE_RECOVERY
```

A auditoria pode continuar usando a URL final realmente alcançada pelo navegador, mas permanece com limitação explícita porque a infraestrutura publicada continua problemática.

O report deve mostrar simultaneamente:

- URL informada;
- cadeia de redirects original;
- destino TLS defeituoso da cadeia original;
- candidato HTTPS usado na recuperação;
- URL final realmente carregada;
- status HTTP final;
- indicação de que TLS permaneceu estrito;
- recomendação de corrigir o redirect no servidor.

## Impacto nas métricas

Se a recuperação produz HTML/DOM válido:

- M3 pode persistir o snapshot renderizado;
- extração, regras e `SCORE-GEO-002` podem prosseguir;
- Web Performance, se habilitado, pode usar a `final_url` recuperada;
- Synthetic Apdex, se habilitado, pode usar a `final_url` recuperada;
- IA, se habilitada, pode analisar os fatos persistidos e complementar a explicação.

A recuperação não altera fórmulas de Score, Lighthouse, Core Web Vitals ou Apdex.

Se a recuperação falha:

- `SOURCE_QUALITY_BLOCKED` permanece;
- as etapas externas/repetitivas dependentes da URL podem ser interrompidas;
- ausência de métricas não pode ser convertida em zero.

## Recomendação de infraestrutura

A correção ideal é do site, não do auditor.

Para um caso equivalente ao observado em `mdsgroup.com`, a cadeia pública deveria evitar:

```text
HTTPS → HTTP → outro hostname
```

quando existe uma rota HTTPS válida.

A configuração preferível é redirecionar diretamente para um endpoint HTTPS válido, por exemplo conceitualmente:

```text
https://dominio-raiz/
  → https://www.dominio-raiz/
  → /rota-final/
```

ou diretamente para a URL canônica final, conforme a arquitetura definida pelo proprietário do site.

A validação deve ser feita também em sessão limpa para não depender silenciosamente de estado prévio do navegador.

## Segurança e reversibilidade

A implementação:

- não importa perfil pessoal do navegador;
- não usa cookies/cache do usuário;
- não desabilita TLS;
- não adivinha domínio alternativo;
- não modifica o website;
- não altera persistência normativa existente;
- é limitada à camada de navegação/qualidade da origem;
- preserva evidência suficiente para reproduzir e auditar a decisão.
