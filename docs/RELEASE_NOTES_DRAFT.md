# Notas de mudanças - candidata v0.9.0 não publicada

> **REGISTRO HISTÓRICO PRÉ-PUBLICAÇÃO:** a [release `v0.9.0`](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.0) foi publicada em 29/10/2026, `immutable=true`, sobre `5da8e6247094c20dcdbe770474ac31e7f93383b2`. As declarações `DRAFT`, `NO-GO`, branch de preparação e CI pendente abaixo descrevem decisões anteriores à publicação e são preservadas para rastreabilidade, não como status atual.

A última release pública é `v0.8.0`, mas a branch exclusiva `release/prepare-v0.9.0` já identifica o pacote Python como `0.9.0`, ainda não publicado. Estas notas são um **rascunho de GitHub Release**, não uma divulgação; não autorizam merge da branch de preparação, criação de tag, release draft no GitHub ou publicação. A aprovação para a PR #675 foi específica daquele merge e não autoriza automaticamente este novo ciclo.

## Referência e abrangência

**Referência do ciclo de release:** tag imutável `v0.8.0` -> `4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08`; `main` após a integração da PR #675 -> `810cc076052df93f1d18c6807c18e63b225d9473`. A comparação GitHub entre esses pontos registra **1.501 commits à frente, zero atrás**. O endpoint expõe somente 300 arquivos, portanto **não** é fonte do inventário integral. A versão `0.9.0` é aplicada somente na branch de preparação e ainda exige regressão integral no HEAD que for submetido à publicação.

Comparação local completa entre `v0.8.0` (`4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08`) e a baseline desta operação `02d2a7fb1a00abe907a5595602dbbab6bcae0603`: **1.495 commits alcançáveis, 503 na cadeia de primeiro pai, 822 entradas de diff com detecção de renomes, 112.484 inserções e 1.748 exclusões**. Contagens de commits não equivalem a número de funcionalidades.

O [inventário completo](RELEASE_CHANGE_INVENTORY.tsv) contém 289 entradas de runtime, 321 de testes, 108 documentais, 90 de CI e 14 operacionais. Foi obtido por `git diff --name-status --find-renames` entre os SHAs acima, sem o limite de 300 arquivos da API. Os renomes são contabilizados como uma entrada. Este inventário é mecânico; as notas abaixo agrupam os efeitos para o produto e não afirmam homologação física de cada capacidade. Mudanças posteriores desta operação ficam registradas separadamente na PR e na issue #674.

**Complemento pós-inventário:** a comparação entre `02d2a7fb1a00abe907a5595602dbbab6bcae0603` e `main@810cc076052df93f1d18c6807c18e63b225d9473` identifica **6 commits e 22 caminhos** afetados. A [matriz incremental de 22 caminhos](RELEASE_CHANGE_DELTA_V0_9_0.tsv) identifica o delta, incluindo arquivos novos de CI e documentação. Os mesmos caminhos podem já integrar o inventário de 822 entradas; **não** somar 822 + 22 como arquivos únicos. A inclusão do próprio bump e de documentos da branch `release/prepare-v0.9.0` é um recorte posterior e também não equivale a mudança publicada.

## Recursos e comportamento público

- **Consolidação e reprocessamento:** comparações consultivas de fontes do mesmo domínio, pacotes separados com proveniência e verificação de integridade; recuperação seletiva de conteúdo persistido, preservação de sucessos e contadores por tentativa. Os limites de comparabilidade e a elegibilidade das fontes continuam obrigatórios. Referências: [consolidação](CONSOLIDATED_REPORTING.md), [validação](CONSOLIDATED_REPORTING_VALIDATION.md), [reprocessamento](AUDIT_REPROCESSING.md).
- **Busca e evidência GEO:** inventários por consulta, identidade exata de URL, proveniência temporal, comparação de conteúdo concorrente e pacotes consultivos independentes. Captura opcional continua sujeita a consentimento, escopo e controles de rede. Não representa aprovação integral dos roadmaps ainda abertos. Referências: [consultas](GEO_QUERY_LEDGER.md), [conteúdo concorrente](GEO_COMPETITOR_CONTENT_PROVENANCE.md), [comparação longitudinal](GEO_LONGITUDINAL.md).
- **Arquitetura e conteúdo observado:** prévia arquitetural, observações limitadas de navegador e recursos, captura isolada, recuperação de conteúdo renderizado e distinção entre hipótese e evidência. FAQ e revisão documental exigem proveniência específica; ausência de observação não prova ausência de conteúdo. Referências: [arquitetura](ARCHITECTURE_DISCOVERY_ACCEPTANCE.md), [FAQ](FAQ_DOM_TRANSITION.md), [alegações](CLAIM_VERIFICATION.md).
- **Rede e GeoIP:** catálogo e diagnóstico de rede com proveniência, IP público observado quando disponível e GeoIP local opcional. Coordenadas ou caminho indisponíveis não são inventados; sondagens ativas exigem autorização. Referência: [aceite de rede](NETWORK_GEOIP_ACCEPTANCE.md).
- **Relatórios e experiência:** navegação canônica, painéis com escopo e cobertura explícitos, linguagem pt-BR, recomendações vinculadas a evidências e layouts responsivos. SARI, Apdex, Lighthouse e CrUX mantêm distinções de método e população; confiança de IA não é cobertura de controles. Referências: [guia](REPORT_GUIDE.md), [apresentação](REPORT_PRESENTATION.md), [SARI](SARI_READINESS_INDEX.md).
- **Economia e operação:** separação entre consumo generativo e Search, custo atribuído e forecast, operação principal e atividades opcionais; projeções de duração com coortes comparáveis e sem atribuir timers agregados a uma etapa exclusiva. Referências: [custos](CONSOLE_COST_AND_USAGE.md), [preços](AI_PRICING_CONFIGURATION.md), [previsão](PRE_EXECUTION_COST_FORECAST.md).
- **Console e configuração:** restauração tipada de configurações, prévias de escopo e custo, consentimento final explícito e cancelamento/retorno sem persistência acidental. Credenciais não são configuração pública; habilitação de biblioteca não equivale a consentimento de execução. Referências: [configuração](CONSOLE_CONFIG_PERSISTENCE.md), [instalação](INSTALLATION.md).

## Correções e estabilização da PR #675

- Contexto semântico determinístico materializado antes do selo de evidências, preservando bloqueio por divergência.
- Comparação da identidade física de página/contexto através de adaptadores próprios, comprovada pelos testes com Chromium real.
- Freshness do catálogo baseada no conteúdo lógico SQLite e nas dependências seladas; fixture usa o estado canônico de conclusão.
- Retries de consolidação distinguem repetição transitória de fallback e preservam quarentena de providers terminais.
- Relatórios e console preservam evidência bruta enquanto apresentam rótulos funcionais, estados finais e dependências legíveis.
- Testes restauram os catálogos globais de configuração, evitando contaminação entre cenários.
- Retorno de CONS e cancelamento não abrem persistência indevida de configuração. Recuperação RPR offline usa workspace temporário e schema real.
- Gate GeoIP não depende mais de testes não relacionados falharem na branch principal. Contratos documentais permanecem estritos; travessões proibidos foram corrigidos sem alterar testes.

## Compatibilidade, segurança e operação

Python continua restrito a `>=3.13,<3.14`. Os extras `attestation` e `geoip` foram adicionados desde a tag pública; o launcher descobre extras declarados. Configurações, bancos e relatórios históricos devem ser preservados antes de qualquer atualização autorizada. Reabrir artefatos novos com versão anterior exige evidência de compatibilidade; o smoke de troca de runtime não certifica downgrade de dados.

Os controles de origem, hashes, tamanho, JSON estrito, identidade de URL, consentimento e segredo foram reforçados nas superfícies afetadas. Isso não constitui certificação universal de segurança nem autorização para providers tarifados. Nenhum motor de scoring foi modificado nesta operação de encerramento.

## Documentação e qualidade

Guias de instalação, rede, custos, reprocessamento, consolidação e apresentação foram reconciliados com o inventário completo. A regressão integral utiliza Python 3.13 e Chromium; a certificação sempre pertence ao SHA exato. O [smoke de compatibilidade](../scripts/RELEASE_COMPATIBILITY_SMOKE.ps1) produz logs, hashes e resultados em ambiente isolado Windows/Linux. Os testes sintéticos não substituem auditorias físicas.

## Ressalvas para publicação

As homologações físicas de CONS, RPR, SQLite/HTML, economia e impressão CAT-07 foram concluídas **com limitações documentadas**, não com prova irrestrita. O RPR físico recuperou seletivamente `PASSIVE_SECURITY` (1/1), a auditoria continuou parcial; o ledger econômico interno não constitui fatura externa; PDFs históricos não equivalem aos relatórios reemitidos no novo código. Os riscos foram aceitos no ciclo #675, sem inventar evidência adicional.

A **CI do ciclo #675** encerrou 37/37 workflows e 46/46 jobs no HEAD `b72ca79253327ea1d7a58f95be9a9d72591cb2f4` (regressão: 5.649 aprovados, 29 ignorados, 134 subtestes); após o merge, 18/18 workflows acionados por `push` na `main` terminaram com sucesso. Essa evidência **não é CI da candidata com bump 0.9.0**. Consultar [matriz](RELEASE_GATE_MATRIX.md) e [checklist de publicação](RELEASE_PUBLICATION_CHECKLIST.md).

**NO-GO para publicar a v0.9.0 enquanto não houver revisão das notas finais, todos os checks obrigatórios aprovados no SHA definitivo, verificação de Immutable Releases, aceite do merge da branch de preparo e autorização posterior específica de publicação.** Nenhuma tag ou release foi criada.
