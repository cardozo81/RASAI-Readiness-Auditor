# Release candidate — RASAi v0.9.2 (rascunho, NÃO PUBLICADA)

**Escopo:** issues #681 e #682, única branch `feat/geo-multiquery-ai-only-rpr`.
Estas notas **não** são release e não autorizam tag, merge ou publicação.

## Recursos em implementação
- Pesquisa Perplexity com 2–5 termos e GEO por IA: consultas individuais
  fisicamente atribuíveis quando a síntese é solicitada, usando os
  adapters Search API e IA canônica existentes.
- Autorização financeira separada vinculada às queries e ao modo WEB/FAST;
  estados de lote e proteção contra reenvio após ambiguidade de cobrança.
- `geo.html` com tabela por consulta e síntese determinística das análises
  persistidas, sem nova chamada LLM somente para consolidar a apresentação.
- Prévia e pacote de reanálise consultiva offline para AUD COMPLETE:
  `rasai ai-reanalysis AUD_DIR [--write-local-replay]`. Não altera a
  auditoria original, não executa pesquisa nem modelos comerciais.
- Documentação de contratos, limites metodológicos e teste focado.

## Pendências de release
- [ ] Completar no escopo #682 a execução de nova inferência canônica
      sobre evidência histórica em namespace próprio, mediante orçamento
      e consentimento; o replay local atual **não** realiza nova IA.
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
