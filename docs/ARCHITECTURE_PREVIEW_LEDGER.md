# Issue #657 - Fase A - Prévia arquitetural rastreável, opt-in

## Situação e limites

Prévia arquitetural não é AUD e não é evidência M6. A classificação observada pelo motor do modo básico/dinâmico não é promovida se não existiu um par RAW/rendered íntegro. O modo OCI isolado tem entrada RAW pública protegida pelo transporte pinado; HTTP diferente de 2xx pode terminar em UNKNOWN antes de executar qualquer DOM. Isso é esperado e não autoriza contornar um bloqueio de origem.

O registro da prévia fica exclusivamente em `.rasai-runtime/architecture/previews/pv-<uuid>.json`, fora de `audits/*/audit.db`, manifest, assinatura ou scores. Padrão: não persistir. No menu 8, escolha `1` para executar a descoberta, depois `5` para salvar explicitamente o resultado da sessão. `6` consulta exclusivamente registros de URL exata/dispositivo do alvo corrente. `V` sai sem guardar. Alterar URL, dispositivo ou modo invalida o resultado pendente.

O registro guarda data UTC, dispositivo, modo, método, status, classe, código de limitação, origem HTTP pública do pedido, hash SHA-256 do alvo completo (não significa confiança criptográfica na página) e checksum da projeção JSON local. Não guarda conteúdo, query do URL, caminho, headers, cookies, identificadores internos, corpo, prompt, redes privadas ou credenciais. Um redirecionamento final sem proveniência disponível no assessment continua `NOT_VERIFIED_FROM_ASSESSMENT` e não é reconstruído.

Os estados só podem ser `PRELIMINARY_UNVERIFIED`. Integridade de JSON é necessária para leitura, não suficiente para autenticar captura. Lookup falha em caso de diferença de URL exata/dispositivo, checksum, TTL, symlink, formato ou campos obrigatórios. A retenção é de 30 dias e 20 registros válidos, aplicada em gravações; dados alheios/alterados nunca são apagados pela rotina.

## Status das fases

- **Fase A** - implementada como repositório opt-in, leitura isolada por escopo e interface interativa, protegendo UNKNOWN e AUD selada.
- **Vínculo opcional à preparação da próxima AUD** - **pendente**: não se deve chamar a leitura da fase A de associação persistida ou evidência M6. Exige uma escolha explícita na preparação, escopo e contrato separados.
- **Fase B** - pendente: CSS/JS/subframes somente com contagens observadas e orçamento.
- **Fase C** - pendente: topologia estritamente observada; rede interna, CDN, WAF e backend N/D quando não provados.

A #657 só deve ser encerrada após essas entregas independentes. Testes offline de fase A não exigem nova visita ao NYTimes ou Docker. Nenhuma configuração AUTO/DECLARED/UNFORCED, M6, M23/M25, Apdex, SARI ou SCORE-GEO é alterada.
