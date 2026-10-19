# Propagação consultiva do contexto arquitetural por AUD

**Issue:** #646 - fase F3 somente nos consumidores já aprovados.
**Contrato:** architecture-audit-advisory-v1, resolvedor architecture-context-v1.

## Escopo implementado

O RASAi utiliza módulo arquitetural como fonte canônica de observação arquitetural. A escolha AUTO, DECLARED ou UNFORCED é obtida exclusivamente do snapshot de configuração persistido e validado da própria AUD. A preferência local de aquisição STATIC/DYNAMIC/SKIP do menu 8 é independente e não entra na resolução de histórico.

O projetor read-only `architecture_audit_projection.inspect_audit_architecture_context` consulta exclusivamente a pasta da AUD e seu SQLite fechado, com até 100 snapshots. Verifica correspondência de AUD, page_id, snapshot_id, requested_url, final_url e device, unicidade física dos IDs e recusa WAL/SHM/journal, symlinks, identidade duplicada ou fonte alterada durante a leitura. A classe em si pode continuar UNKNOWN. A origem arquitetural é a evidência persistida, não a escolha do usuário.

O resolvedor `architecture_context.resolve_architecture` é reutilizado por cada snapshot com consumer_id descriptive_report e fase POST_COLLECTION. Para modalidade AUTO, uma classe só é efetiva no contexto consultivo quando há observação módulo arquitetural inequívoca e elegível. Em DECLARED, a classificação informada é apresentada como escolha humana, em campo separado da medida módulo arquitetural. Em UNFORCED ou histórico sem escolha selada, a observação pode ser exibida, mas nenhuma classe é aplicada. Divergências são descritas, sem correção automática.

## Superfícies

- `index.html#architecture`: painel descritivo com descoberta módulo arquitetural, declaração, fonte, contexto efetivo apenas de relatório, motivos N/D e links técnicos preservados em code.
- `python -m rasai.architecture_audit_cli /caminho/AUD-ID`: JSON somente leitura com códigos por snapshot e modo do plano.
- `python -m rasai.architecture_audit_cli /caminho/AUD-ID --consumer-matrix`: acrescenta tabela de elegibilidade, sem ativar consumidor.

CAT-07 mantém seu orientador de Apdex independente. Nenhum perfil ou threshold é injetado; SARI, SCORE-GEO-004, navegação sintética/experiência sintética, registros Dynatrace, IA e motores de coleta não são alterados. A projeção não navega, não instala Docker e não consome APIs.

## Matriz de elegibilidade versionada

O inventário em `architecture_consumer_eligibility.py` registra CAT-01..CAT-10, SARI, SCORE-GEO, navegação sintética, experiência sintética, IA e Dynatrace por responsável, categoria, decisão e condição de abertura. Somente descriptive_report e m6_read_only_diagnostic são ADVISORY_SAFE, coincidindo exatamente com a allowlist fixa do resolvedor. Os demais estados INTERPRETATION_SAFE, PRE_COLLECTION_ONLY, METHOD_CHANGE_REQUIRES_ADR e INAPPLICABLE são descrições de governança, **não aprovação para propagação funcional**. Toda mudança normativa exige ADR individual, revisão de método, golden, paridade histórica e autorização.

## Aceite e limitações

Fixtures offline com dois URLs/devices comprovam AUTO, DECLARED, UNFORCED, histórico anterior sem escolha, divergência entre módulo arquitetural e escolha declarada, colisão de page_id entre AUDs, origem sem SQLite selado e imutabilidade. O teste não substitui prova de integridade de manifesto para uma AUD real. Histórico sem assinatura independente continua apenas consultivo e não é promovido a evidência normativa.

O smoke real pode ser executado na AUD existente; ausência de módulo arquitetural ou de opção congelada é resultado esperado N/D/UNFORCED, não erro ou motivo para iniciar uma nova coleta paga.

## Projeção temporal de captura e transporte seguro (#646)

A classificação na prévia não é um snapshot arbitrário da primeira pintura. O renderizador OCI reavalia o conteúdo main/article na MESMA página durante até 2,8 s depois de DOMContentLoaded; exige estabilidade textual sem skeleton/aria-busy por três amostras e observação mínima de 850 ms. Se conteúdo de SPA/hidratação ou redirect client-side ainda não se materializou, a evidência é inconclusiva, não positiva/negativa. Não altera timeout/configuração de navegação sintética/experiência sintética nem adiciona índice de prontidão de conteúdo.

A aquisição HTTP pode acompanhar dois redirecionamentos públicos, fixados por IP e validados independentemente. A classificação somente aceita cadeia final consistente no mesmo host ou variação www/ápice, sem downgrade HTTPS. Certificado TLS não validado impede a obtenção do conteúdo e NÃO é contornado. Redirect/handshake são fases de transporte; a janela de materialidade ocorre depois do DOMContentLoaded e não mascara tempo consumido em DNS, conexão ou TLS. A estabilidade observada não prova renderização global, indexação, ausência de WAF ou disponibilidade de crawler.

O modo sem Docker apresenta sinais estruturais RAW limitados como observação parcial, mas nunca substitui comparação RAW/DOM e nunca atribui CSR_SPA/STATIC_OR_SSR com HTML isolado.

## Censura de materialidade em substituições tardias (19/10/2026)

O método consultivo espera até o fim da janela máxima de 2,8 s depois de DOMContentLoaded antes de classificar o DOM, pois uma sequência inicial de texto estável poderia ser substituída por SPA/hidratação tardia. O aceite requer três amostras finais de texto material coincidente e sem loading visível. Em caso de substituição muito próxima do limite, a arquitetura permanece UNKNOWN, preservando limitação de materialidade. Somente marcadores de loading visíveis interrompem a estabilidade. Não há mudança de sample, task, threshold, Apdex ou scoring homologado.

Metadados limitados de redirecionamentos observados pela captura (quantidade, upgrade HTTP/HTTPS e transporte declarado) podem constar do console sem revelar caminhos, querystrings ou credenciais de páginas redirecionadas. Esses metadados não equivalem à certificação autônoma de TLS nem aprovação do destino por fonte externa.


## Destino efetivo por snapshot no relatório consultivo (#646, 19/10/2026)

O painel F3 somente leitura passou a separar explicitamente **URL
solicitada** e **URL final observada** na mesma amostra M6. A projeção
inclui `final_target_differs_from_requested`, informação textual de
identidade, sem inferência automática de causa ou novo classificador.
A divergência não significa, por si só, que houve redirect HTTP: pode
resultar de normalização, navegação observada ou contexto do transporte.
Também não comprova certificado, WAF, DOM final ou disponibilidade de
crawler. Não mistura URLs entre dispositivos/snapshots, não executa
nova navegação e não altera o resolver canônico nem os índices M23/M25.

Para proteção de credenciais de URL, a exibição de ambas as URLs no
HTML apresenta apenas esquema, host, porta e caminho; remove userinfo,
querystring e fragmento. O rastro físico permanece inalterado na AUD.
Um `final_url` malformado é exibido como não verificável, nunca
convertido em origem inventada. Fixtures de duas URLs com token de
consulta, destino distinto, legado UNFORCED e bytes SQLite imutáveis
cobrem a projeção. Aceite físico amplo do motor #646 continua sujeito
aos gates separados do escopo original.
