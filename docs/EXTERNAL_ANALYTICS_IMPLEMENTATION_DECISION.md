# Decisão de implementação - External Analytics & SARI

Data de referência: 2026-09-13.

## Implementado

- CrUX History automático quando `RASAI_CRUX_API_KEY` existe;
- Microsoft Clarity Data Export opt-in;
- Common Crawl CDX History credential-free, bounded e habilitado por default;
- persistência observacional em `observability.db` e artifacts;
- configuração no console, AuditJob e `rasai-defaults.ini` sem persistir segredos;
- projeção nos relatórios temáticos relevantes;
- `BR-GEO-060` como única corroboração externa admitida no SARI.

## SARI

A inclusão de Common Crawl foi aceita porque existe relação direta com discovery/crawl e o risco metodológico foi limitado por quatro mecanismos simultâneos:

1. positive-only: ausência/erro não materializam regra;
2. bounded: 3% de `DISCOVERY_ACCESS`, máximo de 0,45 ponto no Overall;
3. não crítico: não entra em Critical Readiness Gates;
4. ratio-preserving: quando BR-GEO-060 está ausente, os grupos técnicos mantêm exatamente as proporções anteriores.

CrUX History e Clarity continuam fora do SARI.

Consulte [`SARI_EXTERNAL_CRAWL_CORROBORATION.md`](SARI_EXTERNAL_CRAWL_CORROBORATION.md).

## Não implementado nesta etapa

### Bing Webmaster Tools live

Mantida somente a capacidade/importação existente enquanto o contrato REST pós-aposentadoria SOAP/POX não estiver inequívoco e testável. Não foi criado endpoint presumido.

### IndexNow

Adiado porque é operação de escrita/submissão externa. Deve ser implementado separadamente com opt-in, ownership, dry-run, allowlist e proteção de ambiente.

### Dynatrace RUM / Cloudflare GraphQL

Permanecem candidatos enterprise/posteriores por dependerem de licença/plano e por não atenderem ao objetivo desta etapa de priorizar valor sem novo custo obrigatório.

## Revisão futura

Revisar este contrato quando ocorrer qualquer uma destas condições:

- mudança das quotas/termos das APIs utilizadas;
- mudança do contrato oficial de Bing Webmaster REST;
- disponibilidade de dados empíricos suficientes para validar associação entre SARI e outcomes reais;
- adoção de clientes/produção que exija versionamento metodológico histórico;
- mudança de `SCORE-GEO-004` ou do contrato de pesos do SARI.
