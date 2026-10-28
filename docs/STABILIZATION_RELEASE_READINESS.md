# Estabilização CONS/RPR/relatórios - matriz inicial de evidências

> Registro incremental da branch única. Não equivale a aceite de release.

- Baseline: `main@06dd1bfaafc981eb238e893ec1b37007c1948b27` (27/10/2026).
- Release publicada: `v0.8.0`; candidato `v0.9.0` ainda não decidido.
- Branch: `stabilization/cons-rpr-reports-release-readiness`; PR Draft obrigatória.
- Issue documental incremental: #674. #650 exclusivamente pós-v1.0.0.
- Restrições: offline/mocks, sem APIs pagas, sem sondagem externa, sem merge/tag/publicação sem aceite humano.

| Macrolote | Contrato ou evidência inicial | Estado atual | Próximo gate verificável |
| --- | --- | --- | --- |
| CONS-5 | `docs/CONSOLIDATED_REPORTING_VALIDATION.md`, `consolidated-reporting-ci.yml` | Implementado; homologação aprofundada pendente | Auditar fixtures, testes de proveniência/imutabilidade, políticas e comparabilidade |
| RPR | `docs/AUDIT_REPROCESSING.md`, `audit-reprocessing-ci.yml` | Implementado; homologação aprofundada pendente | Idempotência, recuperação seletiva, accounting incremental, SHA das AUDs |
| HTML | `report-catalog-visual-smoke.yml` | Análise transversal pendente | Smoke sintético + comparação com dados persistidos autorizados |
| IA/pricing | `ai-native-usage-pricing-targeted.yml`; AUD-01D61DBA30DD45D19F99401AB927580D | Desvio +320,69% reportado; causa não demonstrada | Reconciliação de escopo, retries, usage nativo e precificação sem API externa |
| Documentação | `docs/AUDIT_REPROCESSING.md` | Divergência v0.5.0 comprovada; correção iniciada | Revisão documental afetada + links + versão canônica |
| Release | `pyproject.toml` e `src/rasai/__init__.py` = 0.8.0 | Versão candidata ainda não aprovada | SemVer, changelog, gates Windows/Linux e decisão GO/NO-GO |

## Limites das evidências

- Nenhum cenário da matriz acima deve ser considerado reexecutado sem o SHA do workflow e resultado correspondente.
- Workflows por `paths` podem não disparar apenas por mudar este documento; gates ausentes exigem execução explícita segura ou status pendente.
- A execução física de IA da #668 e o aceite de rede #666 são referências históricas, não testes rodados neste ciclo.
- Não misturar confiança quantitativa da IA com cobertura de controles estruturais.

## Fronteiras protegidas

#127, #192, #311, #649, #650, #656 e #657 permanecem fora do escopo de implementação ou condicionadas aos seus próprios gates.

## Reconciliação econômica de IA - evidência sintética

- Teste: `tests/test_audit_cost_explain.py::test_large_point_deviation_is_not_a_calculation_defect_by_itself`.
- Contrato: não confundir diferença da estimativa pontual com precisão do intervalo, falha de cálculo ou fatura real.
- Cenários: desvio +320,69% integralmente coberto; chamada opcional não comparável; cobertura monetária incompleta.
- Evidência real da AUD-01D61DBA30DD45D19F99401AB927580D: comparação causal ainda pendente de inspeção de forecast/ledgers persistidos, sem nova API paga.
- Aceite: workflow econômico verde no SHA exato; cenário sintético não substitui exame financeiro real.

## Gate visual offline dos relatórios CAT/GEO

O workflow `report-catalog-visual-smoke.yml` executa, no mesmo gate, regressões de seções CAT-06/CAT-07, confiança de IA em percentual fracionário e rótulos/proveniência de KPMs Dynatrace, além de screenshots sintéticos de desktop, mobile e impressão. Os gatilhos passam a incluir esses testes e as camadas canônicas de apresentação afetadas. Este smoke usa fixture sintética; não atesta pertinência semântica de todos os relatórios reais nem a calibração estatística da confiança declarada pela IA. Artefatos visuais permanecem sujeitos à revisão humana.

## Evidências de CI da candidata (28/10/2026)

Commit de referência: `9ea28c20ae5a0da5154184f154fd273babf449d5`. A matriz abaixo documenta somente resultados efetivamente consultados no GitHub Actions; seu estado pertence ao SHA indicado, não automaticamente a commits posteriores.

| Gate | Execução | Evidência consultada | Interpretação |
| --- | --- | --- | --- |
| Relatórios CAT/GEO: smoke visual offline | [40645430058](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430058) | Job `synthetic-visual-report` concluído com sucesso; artefato `rasai-catalog-report-smoke`, ID `12797755212`, 22.346.624 bytes | Regressão sintética e geração de imagens aprovadas; inspeção visual humana pendente |
| Telemetria econômica | [40645430025](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430025) | SUCCESS | Comparação e apresentação econômicas cobertas pelos testes do workflow; discrepância da AUD física não reconciliada |
| Contrato público | [40645430105](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430105) | SUCCESS | Contrato público automatizado aprovado |
| RPR: contadores direcionados | [40645430029](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430029) | SUCCESS | Cobertura isolada dos contadores; não substitui RPR integral |
| CONS-5: pipeline completo | [40645430031](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430031) | Em execução na consulta | Sem aceite conclusivo nesta observação |
| RPR: pipeline completo | [40645430027](https://github.com/cardozo81/RASAI-Readiness-Auditor/actions/runs/40645430027) | Em execução na consulta | Sem aceite conclusivo nesta observação |

### Critérios de inspeção humana dos screenshots

Ao revisar o artefato publicado, conferir correspondência de cada seção ao relatório (CAT-06, CAT-07 e GEO), integridade de textos em pt-BR, leitura e hierarquia em mobile/desktop/impressão, duplicidades e coerência dos blocos, apresentação percentual de confiança **somente quando o dado permitir conversão válida**, proveniência e códigos das métricas Dynatrace, separação entre gravidade da regra e confiança declarada pela IA, e ausência de extrapolação causal. Divergências devem ser reproduzidas em fixtures ou relatórios de AUD com evidência rastreável antes de alterar os motores.

**Limite de aceite:** não considerar o pacote de 22 MB revisado apenas porque foi publicado. Para a release, ficam pendentes inspeção dos artefatos, análise comparativa de uma AUD real e aprovação humana explícita; não há GO automático por CI verde.
