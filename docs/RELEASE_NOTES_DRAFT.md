# Notas de mudanças verificadas - candidata à próxima release

**Situação:** rascunho de release, não publicado. Versão pública corrente: `v0.8.0`. Versão candidata avaliada: `v0.9.0`. A abrangência deste documento é o diff da PR #675, não todo o histórico desde a versão pública.

## Funcionalidade e confiabilidade

### Consolidação longitudinal

- Regressões de integridade dos pacotes de consolidação, incluindo hashes de artefatos obrigatórios.
- Regressões de seleção das auditorias fonte e prevenção de reutilização de pacotes adulterados.
- Cobertura de pacotes com análises opcionais de IA simulada, incluindo evidência e registro de trocas.

### Reprocessamento seletivo

- Regressões de idempotência para sucessos semânticos já concluídos.
- Cobertura do fechamento de dependências sem reexecutar trabalho válido.
- Segregação de contadores e tentativas por reprocessamento, preservando a identidade da auditoria original.

### Consumo de IA e relatórios

- Validações de apresentação de tentativas, durações observadas e custo, sem atribuir duração total indevida a uma etapa.
- Regressões para dados econômicos incompletos e divergências de previsão que não comprovam falha de cálculo por si só.
- Ajustes de linguagem pública para ocultar códigos internos na documentação funcional e nas descrições de consumo do console.
- Smoke offline de relatórios do catálogo, com ressalvas visuais documentadas.

## Qualidade, testes e documentação

- Três workflows direcionados adicionados ou ajustados para regressões econômicas, contabilidade do reprocessamento e apresentação visual.
- Contratos e guias atualizados para consolidação, reprocessamento, custo de IA, nomenclatura pública e preparação da release.
- Matriz central de gates e limites das evidências em [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md).

## Compatibilidade e comportamento esperado

A candidata não foi publicada e o código permanece na versão `0.8.0`. Os testes não autorizam reescrever evidências históricas, alterar scoring ou tratar relatórios HTML como fonte primária. Instalação limpa e rollback operacional continuam pendentes de comprovação. A atualização deve seguir [INSTALLATION.md](INSTALLATION.md) após autorização de integração.

## Ressalvas e condições antes de publicar

- Homologação de consolidação e reprocessamento com auditorias físicas, incluindo integridade das fontes.
- Conciliação do caso histórico de custos com ledger e previsão disponíveis.
- Conferência de conteúdo e aparência de relatórios de auditorias reais, inclusive impressão.
- Instalação limpa, leitura de evidências antigas e rollback não destrutivo.
- Changelog público completo da tag `v0.8.0` até o SHA final: **ainda não certificado**. O histórico acumulado contém muitas mudanças fora da PR e não pode ser sintetizado de modo confiável apenas pelo recorte de arquivos da PR.
- Aprovação expressa da PR, merge, tag e release.

**GO/NO-GO:** NO-GO para publicação. A aprovação de workflows automatizados não substitui os critérios físicos nem a autorização humana.
