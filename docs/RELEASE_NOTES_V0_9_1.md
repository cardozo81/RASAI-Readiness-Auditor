# RASAi 0.9.1 - notas de distribuição

**Natureza:** atualização PATCH compatível, aprovada para preparação após a publicação imutável de `v0.9.0`. A identidade pública `SARI-001` e os contratos metodológicos `SCORE-GEO-005` (vigente) / `SCORE-GEO-004` (histórico) permanecem inalterados.

## Baseline e rastreabilidade

- Publicação anterior: [`v0.9.0`](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.0), tag anotada apontando para `5da8e6247094c20dcdbe770474ac31e7f93383b2`. Esta tag e a release correspondente não são movimentadas nem substituídas.
- Alterações funcionais após `v0.9.0`: [Issue #657](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/657), integrada na [PR #679](https://github.com/cardozo81/RASAI-Readiness-Auditor/pull/679), merge `d6081e765c2d1d68679954b987c478129277ccda`.
- Ajustes de documentação pós-publicação incluídos pelas PRs [#677](https://github.com/cardozo81/RASAI-Readiness-Auditor/pull/677) e [#678](https://github.com/cardozo81/RASAI-Readiness-Auditor/pull/678). Esses ajustes não alteram os contratos de execução.
- Este documento e o bump do pacote pertencem à preparação da `v0.9.1`. A **tag final deve corresponder ao commit de `main` certificado após o merge da preparação**, e não ao merge funcional `d6081e76`.

## Entregas incorporadas da #657

- Prévia arquitetural opcional fora da AUD, com armazenamento isolado, retenção limitada, verificação de integridade e escopo exato de URL/dispositivo. A prévia exploratória não é persistida por padrão.
- Vínculo **explícito** de uma prévia válida à configuração selada de uma **nova** AUD. É apenas referência `PRELIMINARY_UNVERIFIED`, nunca classificação M6 nem alteração automática de `AUTO/DECLARED/UNFORCED`. Configurações históricas não restauram o opt-in.
- Inventário consultivo de scripts, CSS, XHR/Fetch e documentos de subframe baseado em observações Chromium/CDP já coletadas na navegação autorizada. Contagens por categoria, estados `OBSERVED`, `NOT_OBSERVED`, `UNKNOWN`, `BLOCKED` (somente bloqueio atestado), protocolos e ordem limitada dos eventos de resposta; a ordem não comprova causalidade.
- Projeção CAT-01 de HTTP/TLS e par remoto público **somente quando observados**. Ausência de comprovação de DNS, backend, CDN, WAF, rede interna ou topologia completa permanece `NETWORK_TOPOLOGY_NOT_DETERMINABLE`, sem inferência ou varredura adicional.
- Sanitização de metadados para impedir exposição de URLs com parâmetros sensíveis e identificadores privados no inventário.

## Compatibilidade e segurança

- Nenhuma migração de schema, reescrita de `audit.db`, alteração de AUDs/CONS históricos, mudança de scores metodológicos ou novos coletores físicos.
- A escolha de uma prévia **não** produz AUD nem transfere segredos, conteúdo de páginas ou configuração arquitetural inferida.
- Integrações de IA e serviços externos permanecem opt-in, sujeitas às configurações de cada operador. A distribuição desta release não exige testes externos pagos nem autoriza novas sondagens de rede.
- Recomendação operacional: conservar backups de bancos e artefatos antes de atualizar o ambiente; retorno ao código antigo não implica downgrade de bancos.

## Evidência de qualidade

- PR #679: **5.654 testes aprovados, 29 ignorados, 134 subtestes aprovados, zero falhas** (Full RASAi Regression, run `40941632126`), além dos cinco workflows de PR aprovados.
- Pós-merge #679 em `main@d6081e76`: **9/9 checks aprovados**.
- A mudança de versão `0.9.0 → 0.9.1` exige seus próprios checks de versão, compatibilidade de instalação e contratos aplicáveis no **SHA da candidata**; as evidências acima não substituem esses gates.
- Homologação automatizada não equivale a auditoria física em equipamento do operador, e resultados inconclusivos continuam explicitamente limitados.

## Distribuição

Canal proposto: **GitHub Release com tag anotada imutável `v0.9.1`**, associada exclusivamente ao SHA pós-merge certificado. Arquivos de código-fonte `.zip` e `.tar.gz` são gerados pelo GitHub; nenhum instalador binário próprio foi aprovado neste escopo. Não publicar em PyPI nem Docker.

A publicação requer criar a release inicialmente como draft, confirmar a identidade do commit e a proteção de imutabilidade, publicar e executar `gh release verify v0.9.1` ou verificação equivalente. Não atualizar nem deslocar a `v0.9.0`.
