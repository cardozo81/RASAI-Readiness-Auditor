# Google Search Console - autenticação OAuth no RASAi

O RASAi aceita duas formas de autenticação no Google Search Console. Este documento descreve o contrato atual do produto em desenvolvimento.

## Opção recomendada: OAuth durável com renovação automática

Configure:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

O RASAi usa o Client ID, Client Secret e Refresh Token para obter um access token temporário imediatamente antes da chamada ao Google. O access token gerado permanece apenas em memória e não é gravado no INI, no audit.db, em relatórios nem no arquivo de diagnóstico.

`RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID` não é segredo e pode ser persistido como configuração. `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET` e `RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN` são segredos e seguem a política de credenciais do console: podem existir na sessão/ambiente seguro, mas não são gravados no INI.

A property continua obrigatória:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL=sc-domain:exemplo.com.br
```

ou, para uma property URL-prefix, exatamente o valor cadastrado e autorizado no Search Console.

## Alternativa: access token manual

Também é possível configurar:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

Esse modo é útil para teste pontual, mas o access token OAuth expira e precisa ser substituído manualmente. Para operação repetida, prefira o fluxo com Refresh Token.

## Credencial incompatível

Uma Google API Key, normalmente iniciada por `AIza`, não é um OAuth access token do Search Console. O diagnóstico do RASAi identifica essa incompatibilidade localmente e orienta a correção sem tratar a chave como bearer token válido.

## Diagnóstico

O teste de integração do Search Console valida, em camadas:

1. presença e consistência da configuração;
2. obtenção do access token, quando usado o modo com Refresh Token;
3. conectividade com a API do Google;
4. autenticação OAuth;
5. acesso à property configurada.

Falhas de autenticação/configuração são separadas de falhas transitórias de rede, proxy, VPN ou indisponibilidade do fornecedor. Nenhum segredo é exibido ou persistido pelo diagnóstico.

## Segurança

Não compartilhe Client Secret, Refresh Token ou Access Token em capturas de tela, tickets ou documentação. Se uma credencial OAuth for exposta, revogue/rotacione a autorização correspondente antes de continuar a operação.
