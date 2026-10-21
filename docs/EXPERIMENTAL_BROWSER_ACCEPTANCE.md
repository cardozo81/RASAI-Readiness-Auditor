# Campanha única de homologação física - FAQ e prontidão experimental

**Escopo:** #652 (clique FAQ) e #322 (prontidão de conteúdo).
**Estado:** ROTEIRO PRÉ-HOMOLOGAÇÃO. Não executar uma URL externa sem
consentimento específico, comprovação da contenção física de rede e
um ambiente de teste separado. A aprovação automatizada do código
não é aprovação da navegação física. Sem ação humana por enquanto.

## Pré-condições obrigatórias

1. Confirmar o HEAD da branch `feat/acceptance-and-architecture-governance`
   antes de qualquer execução no Windows. Executar `git fetch origin`,
   `git switch feat/acceptance-and-architecture-governance` e
   `git pull --ff-only`, verificar `git rev-parse HEAD`.
2. Escolher **uma URL e um alvo FAQ autorizados pelo proprietário**.
   Registrar URL solicitada, URL final permitida (redirects incluídos),
   ID exato de `aria-controls`, dispositivo e perfil/locale.
   Não escolher domínio de terceiros sem permissão.
3. Para a ação FAQ, usar ambiente isolado sem egress de rede para
   protocolos fora do HTTP observado. `--experimental-faq-network-boundary-ack`
   é apenas declaração humana e **não comprova** isolamento de sistema.
   Sem prova do ambiente, não executar clique real externo.
4. Chave HMAC de coletor de 32 bytes ou mais, mantida fora do Git,
   AUD e relatórios, com ACL de usuário restrita. Não reutilizar
   segredos de provider; não copiar a chave para o ticket.
5. CAT-07 deve ter medição normal habilitada via fluxo já previsto.
   `--experimental-readiness-architecture` não ativa CAT-07 sozinho.
   Não usar IA nem PageSpeed externo para gerar evidência deste escopo.
6. A execução deve criar **AUD nova descartável**, não reprocessar
   AUD histórica e não sobrescrever arquivos selados.

## Campanha A - mesma página e clique físico (#652)

Em uma única auditoria experimental, configurar o opt-in do coletor
usando os argumentos canônicos do comando `audit` e
`--experimental-faq-explicit-consent`,
`--experimental-faq-network-boundary-ack`,
`--experimental-faq-requested-url`,
`--experimental-faq-allowed-final-url`,
`--experimental-faq-device`,
`--experimental-faq-target-id`,
`--experimental-faq-collector-id` e
`--experimental-faq-trusted-key-file`.

**Critérios de PASS:** URL inicial/final e dispositivo exatos;
apenas um clique de botão elegível, sem submit/login/popup/navegação;
DOM anterior e posterior da mesma página com hashes e tempos UTC;
assinatura do coletor, ID de página e snapshot persistidos,
verificação da AUD selada em somente leitura e publicação do
sidecar em `.rasai-faq-sidecars/<AUD-ID>/`. O relatório consultivo
indica pós-clique como **declaração local**, não homologação externa.

**Recusas esperadas:** ausência de uma das duas flags de consentimento,
arquivo de chave inválido, alvo duplicado, controle dentro de formulário,
URL final diferente ou não autorizada, serviço de worker presente,
mudança do DOM capturado antes do clique, timeout ou navegação
durante o gesto. Nessas condições: zero promoção de resultado
normativo e nenhuma mutação de AUD original.

## Campanha B - baseline/sonda de prontidão (#322)

Executar um pequeno piloto pareado, com a **mesma URL, device,
browser version, network/cpu/context profile** e pelo menos cinco pares
de navegações controle e opt-in. A sonda é habilitada apenas com
`--experimental-readiness-architecture` e a janela opcional
`--experimental-readiness-window-ms`; não presumir que a
arquitetura UNKNOWN produz medição elegível.

**Critérios de PASS técnico:** cada sidecar corresponde exatamente
a uma linha `audit_id/sample_id/page_id/device` da AUD selada;
o estado OBSERVED possui estabilidade observada, relógios
monotônicos e delta pós-load coerentes; estados censurados
não possuem `primary_content_ms`. O relatório suplementar
contém visões CAT-06 e CAT-07, avisando que prontidão não altera
o Apdex persistido.

**Critério de PASS metodológico:** dados pareados com custo
ativo medido e orçamento explícito aprovado; leitura pelo
`python -m rasai.readiness_matched_pilot --json <pares> --budget-ms 30 --min-pairs 5`
(somente quando os pares reais forem materializados e autorizados).
A janela de 30 ms é referência do piloto, **não SLO homologado**.
Sem cinco pares, marcar NOT_EVALUABLE e não encerrar a #322.

## Verificação sem nova coleta

Após concluir as AUDs, usar o comando read-only:

```powershell
& ".\.venv\Scripts\python.exe" -m rasai.experimental_observation_report --aud-dir ".\audits\AUD-ID"
```

O arquivo de saída `.rasai-experimental-reports/<AUD-ID>/<SHA256>.html`
é separado de `report-catalog`, sem JavaScript ou serviços externos.
Ele contém estado, delta observado/N/D, recusas, situação de FAQ
sem interação/após clique declarado/não verificado, sem expor HTML
pós-clique nem segredos. O operador deve confirmar a integridade
das AUDs originais por seus manifests já existentes.

## Decisão por issue, sem falsa equivalência

**#652:** só fechar com aceite explícito da URL/alvo real,
isolamento, gesto same-session/same-snapshot atribuído e
reconciliado à AUD e prova humana de todos os limites. Hash
igual não prova Googlebot ou certificação externa.

**#322:** só fechar com execução física real, sidecar correspondente,
relatório consultivo legível e ensaio de overhead pareado aprovado.
Um reporte estático não altera a metodologia Apdex e não autoriza
reescrita de HTML/CAT-06/CAT-07 selados.

Se algum critério falhar, documentar especificamente sua causa,
repetir **somente** o cenário focal corrigido e avançar a outra issue
independente. Não executar pytest completo, reinstalar ambiente
ou repetir workflows já verdes por precaução.

## Recibo FAQ autenticado localmente: uso opcional

Sem chave autorizada, o suplemento exibe um sidecar íntegro apenas
como **Não verificado**, sem promover o digest SHA a evidência autenticada.
Após coleta autorizada, conferir ambos os MACs e o HTML persistido:

```powershell
& ".\\.venv\\Scripts\\python.exe" -m rasai.experimental_observation_report `
  --aud-dir ".\\audits\\AUD-ID" `
  --faq-trusted-key-file "C:\\CAMINHO_PRIVADO\\collector.key" `
  --faq-collector-id "COLETOR-AUTORIZADO"
```

Chave de 32 a 128 bytes, fora da AUD, sem symlink. MAC incorreto,
coletor divergente e DOM adulterado são recusados. A conferência é
**local**, não prova isolamento físico de rede, sessão histórica de
terceiros, Googlebot ou homologação humana. Não enviar segredo ao ticket.


## Decisao formal de 21/10/2026 - escopo da campanha

A metodologia experimental de **5 pares reais A/B** da #322 foi
aprovada **condicionalmente**. Os parametros indispensaveis -
ambiente de execucao, URLs e budget operacional - ainda nao foram
aprovados: **nao iniciar campanha fisica agora**, nem assumir 30 ms
do exemplo como teto sancionado. Nao alterar indices Apdex.

Para #652, a estrutura e o seletor FAQ **variam por URL**. Nao
reutilizar o alvo estatico entre paginas; primeiro inventariar
passivamente os controles do DOM de cada URL autorizada conforme
`docs/FAQ_TARGET_AUTHORIZATION.md`. O inventario **nao autoriza
clique**; sem alvo e contencao aprovados a campanha nao comeca.
