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
  `RASAI_NETWORK_ACTIVE_HOST` (host exato) e `RASAI_NETWORK_MAX_HOPS` (8).
  Ausência, alteração ou remoção de permissão bloqueia novo tráfego automático.
- **Pendente antes do aceite integral:** comprovar agendamento automático exclusivo
  de AUD inicial (nunca RPR/CONS/replay), depois de consentimento persistente,
  sem atraso relevante no caminho crítico.

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
- Bases gerenciadas no perfil gravável do operador, fora de Git, AUD e .venv;
  somente MMDB com metadados corretos são consumidas automaticamente.
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
- **Pendente antes do aceite integral:** alinhar habilitação automática da AUD
  à autorização persistente e demonstrar restauração/revogação em sessão real.

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
1. Manter intacta a AUD histórica Hetzner; gerar novo complemento autorizado.
2. Inspecionar seis respostas e duas ausências com fixture conhecida;
   medição física pode variar. Não presumir que o destino foi alcançado.
3. Verificar `network.html` offline, sem City/ASN e com uma ou ambas.
4. Com conta/licença válida, validar instalação do binário, verificação diária e
   revogação do agendamento; sem credencial a AUD deve continuar.
5. Verificar hash do `audit.db` original antes/depois e pacote complementar.
6. Aprovar explicitamente os resultados. Merge é decisão humana separada.
