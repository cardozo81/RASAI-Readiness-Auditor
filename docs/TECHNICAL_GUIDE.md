# Guia técnico

## Pipeline

Fluxo funcional simplificado:

```text
entrada/targets
→ discovery
→ aquisição HTTP
→ rendering Chromium por device
→ extração/evidências
→ regras determinísticas
→ análise semântica opcional por IA
→ comparação/scoring
→ remediação textual e JSON-LD advisory
→ Web Performance externo opcional
→ Acessibilidade projetada do artifact Lighthouse
→ Synthetic Apdex opcional
→ persistência
→ report site
→ reconciliação final de consistência/navegação
```

## Separação de domínios

O produto mantém separados:

- Score/Coverage/Confidence de RASAi;
- análise semântica e remediação por IA;
- Lighthouse/Core Web Vitals/CrUX;
- Acessibilidade automatizada;
- Synthetic Navigation Apdex.

Uma métrica de um domínio não deve ser promovida automaticamente a score de outro.

## Persistência

A fonte de verdade é o conjunto:

```text
audit.db
artifacts/
logs/audit.log
```

O HTML é projeção humana e deve ser reconciliado contra a persistência, especialmente quando integrações externas falham ou retornam dados parciais.

## Fail-open

Falha de integração complementar não deve corromper a auditoria principal. O estado deve ser persistido, sanitizado e explicado no report.

Exemplos:

- provider indisponível/quarantined;
- PageSpeed timeout;
- CrUX sem dado;
- artifact Lighthouse ausente;
- amostra Synthetic Apdex inválida por falha de ferramenta.

## Console

O console é uma camada sobre a CLI, não um segundo pipeline. Configura parâmetros, executa preflight, acompanha progresso por estado persistido/log e inicia a mesma superfície `rasai audit`.

`rasai-console.ini` guarda somente configuração não sensível. Secrets permanecem no ambiente/processo.

## Compatibilidade histórica

Nomes internos de módulos, classes, tabelas e eventos podem conservar identificadores históricos de implementação para não quebrar imports, schemas e rastreabilidade. Esses identificadores não devem ser usados como nomenclatura funcional da UI ou dos relatórios.
