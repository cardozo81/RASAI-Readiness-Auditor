# Aprovação metodológica: contexto arquitetural consultivo

**Decisão aprovada pelo responsável do projeto:** o contexto arquitetural
pode alimentar exclusivamente diagnósticos e relatórios descritivos, sem
alterar índices, coleta, pontuação, coortes ou fórmulas.

## Consumidores liberados
- `descriptive_report`: descrição consultiva baseada em evidência elegível.
- `m6_read_only_diagnostic`: inspeção de evidências e limitações.

A identidade física deve corresponder à URL solicitada e final,
dispositivo, página e snapshot. Declaração do usuário não é uma observação
física. Seleção não implica permissão de execução de qualquer integração.

## Superfícies não autorizadas
SARI, SCORE-GEO, Apdex, métricas, coletores, parâmetros de auditoria,
coortes e outros motores protegidos permanecem invariáveis. Qualquer
mudança de método exigirá nova ADR individual, owner, golden/parity,
versão de contrato, rollback e autorização explícita.

## Assinatura de evidência
A estratégia Ed25519 foi aprovada. Uma chave privada gerenciada pelo
operador, fora de INI e repositório, assina o par de hashes RAW/rendered
e a identidade física do snapshot. A verificação exige uma chave pública
fornecida de forma independente pelo operador. Alteração no artefato,
identidade ou chave de confiança faz a evidência assinada falhar fechada.
Sem chave configurada, o processamento dos demais catálogos continua.

Configurações optativas: `RASAI_ARCHITECTURE_SIGNING_KEY_FILE`
e `RASAI_ARCHITECTURE_VERIFY_KEY_FILE`. Não incluir os arquivos PEM no
repositório, INI ou workspace AUD. Chaves de confiança antigas devem
continuar disponíveis quando políticas de rotação determinarem validação
de capturas assinadas anteriormente.

## Limite
A autenticação é relativa à chave pública que o operador confia.
Capturas anteriores à habilitação permanecem sem assinatura, sem
elevação retroativa. Nenhum ajuste de score decorre dessa decisão.
