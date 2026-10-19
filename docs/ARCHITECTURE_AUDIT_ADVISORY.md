# Propagação consultiva do contexto arquitetural por AUD

**Issue:** #646 — fase F3 somente nos consumidores já aprovados.
**Contrato:** architecture-audit-advisory-v1, resolvedor architecture-context-v1.

## Escopo implementado

O RASAi utiliza M6 como fonte canônica de observação arquitetural. A escolha AUTO, DECLARED ou UNFORCED é obtida exclusivamente do snapshot de configuração persistido e validado da própria AUD. A preferência local de aquisição STATIC/DYNAMIC/SKIP do menu 8 é independente e não entra na resolução de histórico.

O projetor read-only `architecture_audit_projection.inspect_audit_architecture_context` consulta exclusivamente a pasta da AUD e seu SQLite fechado, com até 100 snapshots. Verifica correspondência de AUD, page_id, snapshot_id, requested_url, final_url e device, unicidade física dos IDs e recusa WAL/SHM/journal, symlinks, identidade duplicada ou fonte alterada durante a leitura. A classe em si pode continuar UNKNOWN. A origem arquitetural é a evidência persistida, não a escolha do usuário.

O resolvedor `architecture_context.resolve_architecture` é reutilizado por cada snapshot com consumer_id descriptive_report e fase POST_COLLECTION. Para modalidade AUTO, uma classe só é efetiva no contexto consultivo quando há observação M6 inequívoca e elegível. Em DECLARED, a classificação informada é apresentada como escolha humana, em campo separado da medida M6. Em UNFORCED ou histórico sem escolha selada, a observação pode ser exibida, mas nenhuma classe é aplicada. Divergências são descritas, sem correção automática.

## Superfícies

- `index.html#architecture`: painel descritivo com descoberta M6, declaração, fonte, contexto efetivo apenas de relatório, motivos N/D e links técnicos preservados em code.
- `python -m rasai.architecture_audit_cli /caminho/AUD-ID`: JSON somente leitura com códigos por snapshot e modo do plano.
- `python -m rasai.architecture_audit_cli /caminho/AUD-ID --consumer-matrix`: acrescenta tabela de elegibilidade, sem ativar consumidor.

CAT-07 mantém seu orientador de Apdex independente. Nenhum perfil ou threshold é injetado; SARI, SCORE-GEO-004, M23/M25, registros Dynatrace, IA e motores de coleta não são alterados. A projeção não navega, não instala Docker e não consome APIs.

## Matriz de elegibilidade versionada

O inventário em `architecture_consumer_eligibility.py` registra CAT-01..CAT-10, SARI, SCORE-GEO, M23, M25, IA e Dynatrace por responsável, categoria, decisão e condição de abertura. Somente descriptive_report e m6_read_only_diagnostic são ADVISORY_SAFE, coincidindo exatamente com a allowlist fixa do resolvedor. Os demais estados INTERPRETATION_SAFE, PRE_COLLECTION_ONLY, METHOD_CHANGE_REQUIRES_ADR e INAPPLICABLE são descrições de governança, **não aprovação para propagação funcional**. Toda mudança normativa exige ADR individual, revisão de método, golden, paridade histórica e autorização.

## Aceite e limitações

Fixtures offline com dois URLs/devices comprovam AUTO, DECLARED, UNFORCED, legado sem escolha, divergência entre M6 e escolha declarada, colisão de page_id entre AUDs, origem sem SQLite selado e imutabilidade. O teste não substitui prova de integridade de manifesto para uma AUD real. Histórico sem assinatura independente continua apenas consultivo e não é promovido a evidência normativa.

O smoke real pode ser executado na AUD existente; ausência de M6 ou de opção congelada é resultado esperado N/D/UNFORCED, não erro ou motivo para iniciar uma nova coleta paga.

## Projeção temporal de captura e transporte seguro (#646)

A classificação na prévia não é um snapshot arbitrário da primeira pintura. O renderizador OCI reavalia o conteúdo main/article na MESMA página durante até 2,8 s depois de DOMContentLoaded; exige estabilidade textual sem skeleton/aria-busy por três amostras e observação mínima de 850 ms. Se conteúdo de SPA/hidratação ou redirect client-side ainda não se materializou, a evidência é inconclusiva, não positiva/negativa. Não altera timeout/configuração de M23/M25 nem adiciona índice de prontidão de conteúdo.

A aquisição HTTP pode acompanhar dois redirecionamentos públicos, fixados por IP e validados independentemente. A classificação somente aceita cadeia final consistente no mesmo host ou variação www/ápice, sem downgrade HTTPS. Certificado TLS não validado impede a obtenção do conteúdo e NÃO é contornado. Redirect/handshake são fases de transporte; a janela de materialidade ocorre depois do DOMContentLoaded e não mascara tempo consumido em DNS, conexão ou TLS. A estabilidade observada não prova renderização global, indexação, ausência de WAF ou disponibilidade de crawler.

O modo sem Docker apresenta sinais estruturais RAW limitados como observação parcial, mas nunca substitui comparação RAW/DOM e nunca atribui CSR_SPA/STATIC_OR_SSR com HTML isolado.
