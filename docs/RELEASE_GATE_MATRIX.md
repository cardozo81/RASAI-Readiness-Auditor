# Matriz consolidada de gates da candidata

**Estado:** decisão pré-release, não publicada. PR #675, branch `stabilization/cons-rpr-reports-release-readiness`. Base técnica verificada: `4b20e485eaa55b7e24348574c9f4831f8ff032c3`. Neste SHA, os 14 workflows efetivamente disparados na PR finalizaram com sucesso. A evidência não certifica outros workflows que não foram executados.

## Critério de estados

- `PASS_AUTOMATED`: contrato exercitado por regressões determinísticas no SHA indicado.
- `PASS_DOCUMENTED`: procedimento e requisito constam dos documentos inspecionados, sem execução operacional.
- `PASS_WITH_LIMITATION`: regressão aprovada, mas a evidência não sustenta todo o aceite físico ou visual.
- `NOT_VERIFIABLE`: faltam artefatos ou ambiente para demonstrar o requisito, sem prova de defeito.
- `PENDING_APPROVAL`: exige aceite humano ou autorização de publicação.
- `NO_GO`: bloqueio de promoção da candidata enquanto requisitos obrigatórios não forem satisfeitos ou formalmente decididos.

## Escopo e evidências

| Entregável macro | Gate já comprovado | Limite restante | Próxima ação objetiva | Situação |
| --- | --- | --- | --- | --- |
| Auditoria e contratos de execução | Workflows de auditoria e reprocessamento verdes | Homologação física de execução completa não repetida neste ciclo | Reutilizar evidências reais disponíveis e conferir integridade | PASS_WITH_LIMITATION |
| Consolidação longitudinal | Integridade de snapshot, política de seleção e pacote de IA simulada nos testes | Comparação entre auditorias físicas e hashes de origem | Conferir pacote real e SHA das fontes antes/depois | PASS_WITH_LIMITATION |
| Reprocessamento seletivo | Idempotência semântica, dependências, contadores isolados e workflow integral | Retomada real, histórico e total financeiro por tentativa | Executar smoke físico se ambiente disponível | PASS_WITH_LIMITATION |
| Economia de IA | Regra de contagem e apresentações econômicas cobertas por testes | Ledger/forecast da AUD histórica com desvio reportado +320,69% | Reconciliar operações, tokens, modelos, moeda e preços quando houver fonte | NOT_VERIFIABLE |
| Relatórios | Smoke offline, contratos públicos, linguagem focal e artefatos sintéticos | Dados físicos contra HTML e paginação CAT-07 | Inspeção dirigida por evidência; não reescrever CSS sem reprodução | PASS_WITH_LIMITATION |
| Segurança/configuração | Workflow específico verde | Não certifica qualquer instalação operacional não testada | Manter controle, não ampliar implementação sem falha | PASS_AUTOMATED |
| Rede e GeoIP | Contratos de configuração e regressões relacionadas | Coordenadas e rota de um ambiente físico não certificadas neste ciclo | Homologar somente quando houver evidência disponível | PASS_WITH_LIMITATION |
| Instalação | Launcher Windows e contrato no guia de instalação conferidos | Instalação limpa Windows e Linux, dependências e Chromium em ambiente alvo | Executar checklist de máquina limpa e guardar saída | PASS_DOCUMENTED |
| Rollback/compatibilidade | Procedimento conservador documentado; versão pública 0.8.0 | Execução do rollback e releitura de AUD histórica | Validar com cópia imutável de evidências | PASS_DOCUMENTED |
| Documentação | Índices, links internos, pontuação e terminologia funcional focal testados | Revisão transversal da apresentação e verificações externas | Encerrar o DoD da issue #674 sem dispensar gaps | PASS_WITH_LIMITATION |
| Changelog | Lista exata de 20 arquivos alterados pela PR #675 | Histórico pós-v0.8.0 completo, muito mais amplo que a PR | Produzir changelog final da tag ao SHA de release, por capacidades | NOT_VERIFIABLE |
| Publicação | Matriz GO/NO-GO e candidata propostas | Aceite humano, CI final e requisitos obrigatórios | Não converter PR Draft nem criar tag sem autorização | PENDING_APPROVAL |

## Mudanças verificáveis desta PR

O diff da PR #675 contém 20 caminhos: três workflows, dez documentos, um componente de apresentação de custos e seis arquivos de testes. O pacote se concentra em regressões de consolidação, reprocessamento, custos de IA, linguagem pública e preparação de release. **Não confundir o diff desta PR com o changelog integral desde a tag v0.8.0.**

## Sequência final de execução, sem recriar gates verdes

1. Fechar por inspeção todos os requisitos documentais efetivamente cobertos; registrar limites sem promover evidências sintéticas a físicas.
2. Reconciliar changelog histórico por funcionalidades e mudanças públicas, não por contagem bruta de commits.
3. Se disponíveis, verificar fontes físicas CONS/RPR, ledger econômico e relatórios reais com hashes antes/depois, sem reescrever `audit.db`.
4. Avaliar instalação limpa, rollback e leitura de artefatos históricos em ambiente descartável.
5. Após último commit material, executar ou consultar os checks aplicáveis ao SHA final e registrar falhas ou ausências separadamente.
6. Apresentar decisão final à homologação humana; só então considerar merge e publicação.

**Decisão atual: NO_GO para merge e publicação.** A CI automatizada está verde no SHA de referência, mas o conjunto completo dos critérios de aceite físico e operacional não foi certificado.
