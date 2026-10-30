# RASAi v0.9.2  -  notas de distribuição (preparação; ainda não publicada)

**Natureza:** incremento compatível da linha 0.9, com funcionalidades opcionais GEO e reanálise consultiva pós-AUD, sem alterar contratos de pontuação. **Status:** candidata de publicação; não representa tag nem GitHub Release existente. Última release pública confirmada: [v0.9.1](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.1), publicada em 29/10/2026.

## Rastreabilidade
- Mudanças funcionais: [issues #681](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/681) e [#682](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/682), fechadas como `completed`, [PR #683](https://github.com/cardozo81/RASAI-Readiness-Auditor/pull/683) integrada no commit `b426e5bb8f654ee3835285094341aaa05d47e7c9`.
- A preparação da distribuição atualiza `pyproject.toml` e `rasai.__version__` de `0.9.1` para `0.9.2`. **A futura tag deve apontar para o commit de `main` posterior à integração desta preparação**, nunca para o merge funcional #683.
- Versões metodológicas `SARI-001`, `SCORE-GEO-005` (vigente) e `SCORE-GEO-004` (histórica) permanecem preservadas.

## Recursos
- **GEO multiquery por IA (opt-in):** 2 - 5 consultas Search independentes para atribuir fontes a cada termo, com consentimento econômico explícito, lote idempotente, observação individual e modelo de interpretação canônico. Sem síntese GEO solicitada, o agrupamento econômico anterior é preservado.
- **GEO HTML:** fontes e denominadores por query, recomendações e confiança percentual quando mensuradas. Comparação SERP só quando houver equivalência física demonstrada; ausência de dados é N/D, sem atribuição inventada.
- **Reanálise consultiva pós-AUD:** `rasai ai-reanalysis AUD_DIR` faz pré-voo somente leitura; `--write-local-replay` emite sidecar local versionado com manifesto/hash sem alterar `audit.db` nem o catálogo. Abrange `COMPLETE` e `COMPLETE_WITH_LIMITATIONS`; sem chamadas a provedores.
- **Reaproveitamento de evidências:** ledger GEO #304, fontes Search e interpretação já persistida, com IDs de evidência, modelo/prompt e confiança quando disponíveis. Critérios temporais e estados ambíguos falham de modo conservador.
- **Inferência nova opcional:** `--authorize-paid-geo-ai` somente mediante consentimento explícito, usando cópia derivada, consumidor canônico, reserva pré-chamada e sem repetição automática diante de custo incerto. Não é ativada por replay gratuito.

## Compatibilidade e limites
- Nenhuma alteração de fórmula, pesos, identidade pública do índice ou contrato de score; sem migração destrutiva de bancos, recomputação retroativa de AUD/CONS ou novos coletores físicos.
- Sem alegação de correlação com ranking, tráfego, citação generativa ou causalidade de fontes.
- O replay offline foi homologado; **não foram feitos testes comerciais reais de multiquery nem de inferência IA tarifada**. Sua existência no código não equivale a homologação de faturamento externo.
- Atualizações de runtime não reescrevem evidência histórica. Conservar backups operacionais; voltar ao código anterior não autoriza downgrade de bancos.

## Qualidade comprovada até a preparação
- HEAD funcional da PR #683: **52/52 checks aprovados**. Regressão integral em `314f5c42b6865c2dd18f8573501356faf320422d`: **5.664 passed, 29 skipped e 134 subtests passed**; runtime/console Windows: **208 passed e 5 subtests passed**.
- Pós-merge da PR #683 em `main@b426e5bb8f654ee3835285094341aaa05d47e7c9`: **40/40 checks aprovados**.
- Homologação local na AUD `AUD-91D408722667425E8A83F3ADBD1A8F99`: replay `PUBLISHED`, `PreviewCalls=0`, `ReplayCalls=0`, hashes SHA-256 de `audit.db` e manifesto original preservados. Evidência registrada na PR #683.
- **Bump de versão e documentação mudam o SHA:** requerem no novo HEAD da candidata os gates de versão, documentação, instalação isolada Windows/Linux e regressão aplicável. Os números acima não certificam o novo SHA.

## Distribuição  -  somente após aprovação específica
1. Preparar PR única `release/prepare-v0.9.2`, manter `main` íntegra, validar CI no HEAD, revisar diff/versionamento e solicitar aceite para merge.
2. Após merge autorizado, certificar novamente os checks relevantes em `main` e registrar o SHA exato do commit de preparação integrado.
3. Confirmar proteção **Immutable Releases** habilitada, tag `v0.9.2` inexistente e criar tag anotada/release inicialmente em **draft** no SHA de `main` aprovado.
4. **Publicar somente após autorização expressa de publicação**, verificar tag, `immutable=true`, integridade `gh release verify v0.9.2` (ou equivalente), data e assets autorizados.
5. Distribuição permitida: somente source archives automáticos do GitHub. **Não publicar** PyPI, Docker ou executáveis sem novo escopo. Não mover tags das versões `v0.9.0` e `v0.9.1`.
