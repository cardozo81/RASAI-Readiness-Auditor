# Recursos de rastreamento e descoberta

Este documento define o comportamento público do RASAi para `robots.txt`, sitemaps e `llms.txt`.

## Princípio

A auditoria não presume que todo recurso de descoberta esteja na raiz e não faz varredura cega de diretórios. O RASAi segue referências explícitas e mantém a aquisição bounded/same-origin sempre que a expansão de rede não estiver contratada.

## robots.txt

O arquivo `robots.txt` é resolvido na raiz da origem, por exemplo:

```text
https://example.com/robots.txt
```

Ele é a fonte padronizada para regras de crawler e também pode declarar uma ou várias URLs de sitemap:

```text
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/catalog/sitemap-index.xml
Sitemap: https://example.com/news/sitemap.xml
```

O RASAi preserva todas as declarações observadas. Sitemaps same-origin entram na fila de aquisição; referências cross-origin são preservadas como evidência, mas não são adquiridas automaticamente apenas por estarem declaradas.

Referências:

- RFC 9309: https://www.rfc-editor.org/rfc/rfc9309.html
- Google robots.txt specification: https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec

## Sitemaps

Um domínio pode possuir múltiplos sitemaps. Eles podem estar na raiz ou em subdiretórios. O RASAi considera três caminhos explícitos de descoberta:

1. URLs `Sitemap:` declaradas no `robots.txt`;
2. `/sitemap.xml` como fallback convencional;
3. sitemaps filhos declarados por um `sitemapindex` já adquirido.

Exemplo:

```text
/robots.txt
  -> /discovery/sitemap-index.xml
       -> /discovery/products.xml
       -> /blog/sitemap.xml
       -> /news/sitemap.xml.gz
```

O pipeline suporta XML `urlset`, XML `sitemapindex`, sitemap texto, RSS, Atom e XML comprimido em gzip dentro dos limites operacionais definidos pelo coletor.

O fato de um sitemap estar em subdiretório não é tratado como erro. O endereço observado e a cadeia de descoberta são preservados no artifact/evidência.

Referência principal: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap

## llms.txt

`llms.txt` é tratado como proposta comunitária, não como web standard obrigatório e não recebe peso automático no SARI-001.

A proposta atual permite um arquivo geral na raiz e arquivos scoped em subdiretórios, por exemplo:

```text
/llms.txt
/docs/llms.txt
/support/llms.txt
/products/llms.txt
```

Quando múltiplos arquivos são aplicáveis, o arquivo associado ao caminho mais específico representa o escopo correspondente.

### Descoberta adotada pelo RASAi

O RASAi sempre pode verificar:

```text
/llms.txt
```

Arquivos adicionais não são procurados por força bruta. Eles são adquiridos quando houver referência explícita same-origin observada em uma página auditada, por exemplo:

```html
<link rel="describedby" href="/docs/llms.txt">
```

ou no cabeçalho HTTP:

```http
Link: </docs/llms.txt>; rel="describedby"
```

O coletor também reconhece, de forma deliberadamente compatível e claramente marcada como **não padronizada**, hints como:

```text
LLMS: https://example.com/docs/llms.txt
LLMS-TXT: /support/llms.txt
```

quando observados no `robots.txt`. Esse comportamento serve apenas para descoberta bounded de um endereço explicitamente fornecido. O RASAi não apresenta essa diretiva como parte do Robots Exclusion Protocol e recomenda `rel=describedby` para arquivos scoped.

Referências da proposta:

- https://llmstxt.org/
- https://llmstxt.org/changes.html

## Limites de segurança e operação

A aquisição de `llms.txt` scoped segue as seguintes regras:

- sem enumeração de diretórios;
- somente URLs HTTP(S) normalizadas;
- somente same-origin para aquisição automática;
- candidatos deduplicados;
- limite de candidatos por auditoria;
- cada arquivo adquirido possui artifact próprio e endereço de origem rastreável;
- ausência ou indisponibilidade de `llms.txt` não é transformada em falha de Search nem em penalização automática do SARI.

Essa separação é intencional: sitemap e robots possuem papéis estabelecidos para crawling/discovery; `llms.txt` continua sendo sinal experimental e complementar.
