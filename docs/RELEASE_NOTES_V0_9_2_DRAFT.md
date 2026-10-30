# Release candidate - RASAi v0.9.2 (rascunho, NÃO PUBLICADA)

**Escopo:** issues #681 e #682, única branch `feat/geo-multiquery-ai-only-rpr`.
Estas notas **não** são release e não autorizam tag, merge ou publicação.

## Recursos em implementação
- Pesquisa Perplexity com 2-5 termos e GEO por IA: consultas individuais
  fisicamente atribuíveis quando a síntese é solicitada, usando os
  adapters Search API e IA canônica existentes.
- Autorização financeira separada vinculada às queries e ao modo WEB/FAST;
  estados de lote e proteção contra reenvio após ambiguidade de cobrança.
- `geo.html` com tabela por consulta e síntese determinística das análises
  persistidas, sem nova chamada LLM somente para consolidar a apresentação.
- Prévia e pacote de reanálise consultiva offline para AUD COMPLETE ou
  COMPLETE_WITH_LIMITATIONS encerrada:
  `rasai ai-reanalysis AUD_DIR [--write-local-replay]`. Não altera a
  auditoria original, não executa pesquisa nem modelos comerciais.
- Ledger #304 reaproveitado como operação offline adicional, com
  abstinência N/D; menu CAT-05 > Perplexity > A para prévia consultiva.
- Reapresentação offline de interpretação GEO já persistida e relatório
  consultivo independente de nova inferência autorizada, com modelos,
  prompts, IDs de evidência e confiança individual quando comprovados.
- Documentação de contratos, limites metodológicos e teste focado.

## Pendências de release
- [ ] Homologar a rota opcional de nova inferência GEO canônica em
      SQLite derivado, com autorização explícita e custo de IA N/D.
      A prévia/replay local nunca executa uma IA paga.
- [ ] Avaliar adapters adicionais replay-safe sob #682; integração GEO
      é o primeiro caso autorizado.
- [ ] Validar o fluxo completo multiquery em fixtures, a compatibilidade
      da renderização e os estados parciais/falhas.
- [ ] Verificar CI estritamente relevante no SHA final e integridade dos
      motores homologados; nenhum novo workflow necessário.
- [ ] Homologação humana mínima quando estritamente necessária, após
      atualização local de `main` e checkout da branch candidata.
- [ ] Merge único em `main` apenas verde; publicar v0.9.2 somente
      em gate de release posterior e separadamente autorizado.

## Garantias exigidas
Sem alteração de scores SARI/SCORE-GEO, captura HTTP/DOM/browser,
Apdex, PSI/CrUX, motor RPR físico, CONS longitudinal, política de
preços/retries dos adapters ou reconstrução retroativa de snapshots.
Nenhuma chamada comercial em testes automatizados.
