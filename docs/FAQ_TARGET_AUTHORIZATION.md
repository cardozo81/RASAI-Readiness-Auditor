# Protocolo de descoberta e autorizacao FAQ por URL

**Issue:** #652. **Decisao do operador:** preparar a campanha, SEM
autorizar ou executar cliques, chamadas externas, custos ou merge.
O seletor/estrutura FAQ nao e fixo e **nao pode** ser reutilizado
automaticamente entre URLs, dominios, dispositivos ou capturas.

## 1. Preflight estritamente passivo

Somente depois que houver HTML obtido por uma captura **ja existente e
autorizada**, o operador pode inventariar os candidatos localmente,
sem navegador, rede, interacao ou escrita na AUD:

```powershell
& ".\.venv\Scripts\python.exe" -m rasai.faq_target_inventory `
    --html-file "C:\\CAPTURA_CONTROLADA\\pagina.html" `
    --requested-url "https://SITE_AUTORIZADO.example/faq" `
    --final-url "https://SITE_AUTORIZADO.example/faq" `
    --device DESKTOP
```

A ferramenta enumera ate 100 controles `button[aria-controls]`, incluindo
IDs dinamicos de cada pagina, e relata estruturas `details/summary` e
botoes sem `aria-controls` como **nao suportadas pelo worker atual**.
A saida indica `observed_dom_sha256`, digests das URLs e dispositivo.
Nao publica o HTML nem seleciona o primeiro alvo. Nao autentica a AUD.

Cada candidato recebe uma condicao: elegibilidade tecnica **na
politica atual**, ID nao semantico exigindo avaliacao de adaptador,
controle duplicado/ambiguo, ou estrutura insegura. O diagnostico
atual de clique exige que o `target_id` contenha indicacao FAQ e
que exista um `button` unico, fechado, sem submit/form/handler inline.
Nao relaxar esse limite implicitamente quando o ID real for opaco:
uma eventual extensao de estruturas requer implementacao e
regressoes separadas, sem autorizacao automatica de interagir.

## 2. Plano por alvo a ser submetido ao responsavel

Para **cada** URL, registrar e aprovar explicitamente, em entrada isolada:

| Campo | Requisito |
| --- | --- |
| requested_url e allowed_final_url | URL literal controlada, sem credenciais ou fragmentos |
| device/locale/viewport | Contexto da captura consentida |
| snapshot_id/page_id/AUD | Identidade fisica gerada pelo coletor; nao inventar antecipadamente |
| observed_dom_sha256 | Hash do HTML pre-clique, nunca identidade de outra sessao |
| FAQ candidato | ID `aria-controls` descoberto na propria captura e sem ambiguidade; caso nao suportado => bloqueio |
| Gesto | Um unico clique de disclosure sem submit, login, navegacao, popup ou pagamento |
| Orçamento | Deadline, numero maximo de gestos e requests (= zero durante o gesto), aprovados expressamente |
| Isolamento | Prova tecnica de barreira de egress real do SO/container, inclusive canais nao HTTP |
| Chave e recibo | Coletor autorizado; segredo fora da AUD/Git; MAC verificavel pelo leitor independente |
| Retencao | Politica de exclusao/protecao do sidecar sensivel com HTML pos-clique |

**Sem URL, candidato escolhido, isolamento fisico ou orcamento aprovados
separadamente: nao configurar flags opt-in e nao executar campanha.**

## 3. Execucao futura (nao autorizada nesta fase)

Na captura autorizada, comparar DOM vivo e hash pre-clique com a
mesma pagina/snapshot da AUD, refazer elegibilidade do botao **no
momento do gesto**, confirmar URL final e dispositivo, instalar bloqueios,
limitar a uma acao e coletar DOM/recibo antes/depois na mesma sessao.
Interacao que muda URL, abre popup, cria requests ou excede prazo falha
fechada; recepcao posterior pode ser `NOT_VERIFIED`. Comparar sidecar
assinado com artefato da AUD selada **em leitura**, sem modificar HTML
canonico, Apdex, SARI, SCORE-GEO, dados historicos ou IA.

A mera descoberta de candidatos e o recibo HMAC nao provam
Googlebot/indexacao nem isolamento fisico; fixtures Playwright
sinteticas so cobrem contrato tecnico. A decisao de homologacao
delegada depende de capturas fisicas verdadeiras e rastreaveis.
