# Rede, traceroute e MaxMind - critérios de saída da #666

Escopo incremental sobre o motor #659. Este documento é um checklist de validação e
não constitui autorização de merge. #649 permanece roadmap, sem motor NDR novo.

## G0 - Contratos e fronteiras
- Contrato imutável do pacote de sonda: `rasai-network-active-probe-v1`, leitura compatível
  de pacotes históricos, SHA-256 de integridade (não autenticação do executor).
- Contrato lógico aditivo `rasai-network-logical-trace-v2`: hops numerados,
  estado, IP público (ou nulo), amostras RTT, limite, último respondente,
  destino confirmado, modo do subprocesso, método ICMP/TCP e limitações.
- Scores, `audit.db`, catálogos e evidências seladas não são reescritos.
- Falha complementar não pode degradar o status negocial da auditoria.

## G1 - Critérios de saída
- Parsing IPv4/IPv6, Windows e Linux; no máximo 16 hops; orçamento limitado.
- `TimeoutExpired.stdout` preservado; hops sem resposta não são inventados.
- `traceroute` coletado separadamente de falhas de handshake TCP/TLS.
- Pacote novo e verificável e `network.html` com todos os hops, RTT e estado.
- Configuração canônica: `RASAI_NETWORK_ACTIVE_ENABLED` (false),
  `RASAI_NETWORK_ACTIVE_HOST` (hostname público exato) e `RASAI_NETWORK_MAX_HOPS` (8).
  O atalho `PREPARAR AUDITORIA > CAT-01 > N. Rede e conectividade` extrai o
  hostname da URL da sessão, removendo `https://`, caminho, porta e query, mas
  **não concede autorização automaticamente**. O operador precisa confirmar
  expressamente a sonda ativa para o hostname exato; pode habilitar/revogar e
  escolher sessão ou persistência no INI canônico. A edição avançada de
  `RASAI_NETWORK_ACTIVE_HOST` também aceita URL HTTP(S) completa como entrada,
  mas grava somente o hostname normalizado.
- Alteração de URL/hostname **não transfere** o consentimento: divergências
  são mostradas no CAT-01 e impedem despacho automático. Além do escopo
  original na tabela de páginas, o despacho exige que o host autorizado
  corresponda ao hostname da **URL primária selada** na configuração da nova AUD;
  um redirect observado não basta. Falta de snapshot canônico ou configuração
  inválida falha fechada e não bloqueia a AUD.
- Despacho automático implementado exclusivamente após a nova AUD concluída;
  usa `network_acceptance` canônico em subprocesso independente após consentimento,
  sem aguardar traceroute no caminho crítico.
- **Pendente antes do aceite integral:** comprovar em Windows que o despacho
  foi iniciado, que a atualização posterior do HTML é íntegra e que revogação,
  RPR, CONS e replay não iniciam novas sondagens.

## G2 - Critérios de saída
- Apenas IP público realmente observado recebe enriquecimento.
- City e ASN independentes; base ausente não torna falha de conectividade.
- Legenda acessível e SVG offline com precisão, fonte, data e RTT.
- Ligações tracejadas somente para hops consecutivos com coordenadas;
  não representam caminho físico nem posicionamento real dos equipamentos.
- Verificar pacote histórico #659, casos sem MMDB e resultados de coordenadas
  por leitura exclusivamente de evidência persistida.

## G3 - Critérios de saída
- Extra `geoip` instalado na .venv pelo bootstrap canônico.
- Binário geoipupdate MaxMind baixado apenas com consentimento de aquisição;
  pacote oficial com SHA-256, metadados locais para verificação idempotente.
- Bases MaxMind **City e ASN** gerenciadas em `<RAIZ_RASAI>/data/geoip/`:
  `GeoLite2-City.mmdb` e `GeoLite2-ASN.mmdb`. A raiz da aplicação é
  determinada pelo pacote instalado em modo editável, independentemente do
  CWD, e não é `%LOCALAPPDATA%`. Os datasets ficam fora do Git, da AUD e da
  .venv. **Os nomes dos arquivos são livres**: busca-se no máximo dois
  arquivos com extensão `.mmdb` (sem distinção entre maiúsculas e minúsculas)
  e identifica-se City/ASN exclusivamente pelo campo `database_type` dos
  metadados internos válidos (p. ex., `GeoLite2-City`, `GeoIP2-ASN`), além
  de exigir `build_epoch` válido. Não se adivinha o tipo a partir do nome
  do arquivo e não há novas variáveis ou caminhos a parametrizar. Uma base
  válida pode operar independentemente da outra. Duplicidade de tipo ou
  mais de dois arquivos MMDB são tratados como ambiguidade, sem eleger um
  candidato arbitrário. O CAT-01 > N exibe os nomes efetivamente aceitos
  ou informa ausência/invalidez.
- O utilitário `geoipupdate` continua no perfil operacional do usuário e
  atualiza bases na pasta do programa após consentimento e conta/licença
  MaxMind válidos. Não instalar/capturar datasets dentro de AUD, RPR ou CONS.
  Se a pasta da aplicação não for gravável, retornar falha não bloqueante.
  A autorização para baixar o binário não fornece automaticamente credenciais
  ou licença para obter as bases.
- Manutenção independente da AUD: `python -m rasai.network_geoip_maintenance`,
  com `--license-accepted` e `--allow-install` quando autorizado.
- Agendamento Windows opcional: `--schedule --authorize-schedule`, revogável
  com `--unschedule --authorize-schedule`. Nunca persistir chave na tarefa.
- Bootstrap/reconciliação do binário integrada ao launcher oficial, apenas após
  `RASAI_GEOIP_ACQUIRE_TOOLS=true` explicitamente persistido.
- **Pendente antes do aceite integral:** homologação física do agendamento e atualização,
  retenção/licença e atomicidade de bases no ambiente Windows.

## G4 - Critérios de saída
- Registro canônico e round-trip do INI para os parâmetros de rede
  não sensíveis. Segredos nunca no INI, log ou relatório.
- `RASAI_NETWORK_GEOIP_SOURCE=LOCAL_FIRST` como padrão; `DISABLED` impede
  enriquecimento sem afetar evidência de rede.
- API remota: não habilitada por padrão; orçamento pago zero. **Deferir**
  implementações sem amostra técnica que comprove ganho líquido de cobertura,
  precisão ou custo em comparação à MMDB local.
- A AUD inicial usa host exato persistido e habilitação explícita no console;
  execução complementar é isolada e não bloqueante.
- **Pendente antes do aceite integral:** demonstração de restauração/revogação
  em sessão real, sem consultas remotas inesperadas.

## Matriz de validação automatizada
- `tests/test_network_traceroute.py`, `tests/test_network_route_g1.py`
  e `tests/test_network_active_probe.py`: captura, isolamento, orçamento,
  contrato e apresentação parcial.
- `tests/test_network_map.py`: mapa por hop, lacunas e caminhos consultivos.
- `tests/test_network_geoip_install.py`,
  `tests/test_network_geoip_operations.py`,
  `tests/test_network_geoip_bootstrap.py`,
  `tests/test_network_geoip_maintenance.py`,
  `tests/test_network_geoip_schedule.py`: manutenção local.
- `tests/test_network_active_policy.py` e
  `tests/test_operator_runtime_registry.py`: segurança e configuração.
- Workflow `Network GeoIP Focused` e todos os checks obrigatórios devem ficar
  verdes **no último HEAD** antes de liberar homologação humana.

## Aceite humano Windows (somente após liberar)
Utilize `scripts/NETWORK_GEOIP_WINDOWS_ACCEPTANCE.ps1` em modo preflight
sem `-AuthorizeTrace`; a sondagem física requer parâmetro explícito,
hostname exato e escopo previamente autorizado.

1. Manter intacta a AUD histórica Hetzner; gerar novo complemento autorizado.
2. Inspecionar seis respostas e duas ausências com fixture conhecida;
   medição física pode variar. Não presumir que o destino foi alcançado.
3. Verificar `network.html` offline, sem City/ASN e com uma ou ambas.
4. Com conta/licença válida, validar instalação do binário, verificação diária e
   revogação do agendamento; sem credencial a AUD deve continuar.
5. Verificar hash do `audit.db` original antes/depois e pacote complementar.
6. Aprovar explicitamente os resultados. Merge é decisão humana separada.
