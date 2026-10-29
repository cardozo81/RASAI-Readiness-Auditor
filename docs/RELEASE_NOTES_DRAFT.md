# Notas de mudanças - candidata v0.9.0 não publicada

A versão pública e a versão no código continuam `0.8.0`. Estas notas reconciliam a evolução acumulada desde a tag `v0.8.0`, não apenas a PR #675. Não autorizam merge, bump, tag ou publicação.

## Referência e abrangência

Comparação local completa entre `v0.8.0` (`4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08`) e a baseline desta operação `02d2a7fb1a00abe907a5595602dbbab6bcae0603`: **1.495 commits alcançáveis, 503 na cadeia de primeiro pai, 822 entradas de diff com detecção de renomes, 112.484 inserções e 1.748 exclusões**. Contagens de commits não equivalem a número de funcionalidades.

O [inventário completo](RELEASE_CHANGE_INVENTORY.tsv) contém 289 entradas de runtime, 321 de testes, 108 documentais, 90 de CI e 14 operacionais. Foi obtido por `git diff --name-status --find-renames` entre os SHAs acima, sem o limite de 300 arquivos da API. Os renomes são contabilizados como uma entrada. Este inventário é mecânico; as notas abaixo agrupam os efeitos para o produto e não afirmam homologação física de cada capacidade. Mudanças posteriores desta operação ficam registradas separadamente na PR e na issue #674.

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

Permanecem separados: integridade histórica dos bancos fonte de CONS, paridade SQLite/HTML física, recuperação de AUD realmente interrompida, reconciliação causal da AUD econômica, avaliação da impressão CAT-07 e aceite operacional humano. A [matriz vigente](RELEASE_GATE_MATRIX.md) registra evidência e próxima ação. **NO-GO para publicação** até satisfação ou dispensa formal dos gates obrigatórios e autorização expressa. O conteúdo final de uma release futura deve ser novamente confrontado com seu SHA de publicação.
