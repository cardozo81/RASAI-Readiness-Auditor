# SERP: proveniência temporal, possível cache e profundidade incompleta (#129)

**Escopo:** mecanismo de pesquisa tradicional (Google / SerpApi) da AUD e do RPR. Não altera scoring, pedido original, elegibilidade de conclusão, gate de IA nem o teto de chamadas.

## O que os registros significam

- `provider_created_at`: horário informado na resposta pelo fornecedor, **quando disponível**. Não é o momento de reprocessamento.
- `rasai_response_received_at`: momento em que o adapter RASAi recebeu a resposta HTTP.
- `rasai_persisted_at`: momento de gravação da observação no banco.
- `serp_evidence_provenance.captured_at`: marco local já existente, mantido sem modificar a semântica `LIVE_RECOLLECTION`.
- `provider_request_id`, `raw_evidence_sha256`: identificador e hash observáveis, usados para detectar repetição **dentro da mesma AUD, query, região, idioma, dispositivo, profundidade e domínio**.
- `provider_response_repeat_status` e `previous_observation_id`: novas anotações nos metadados de qualidade de uma nova observação. Se ID e/ou SHA forem iguais, o sistema registra `POSSIBLE_PROVIDER_CACHE`. **É indício, não confirmação** de cache do fornecedor; não classificar como reutilização local nem esconder uma tentativa física.

A atualização acrescenta campos nos metadados de qualidade já persistidos, sem mudar o esquema de SQLite ou alterar arquivos RAW/hashes. Observações históricas não ganham esses novos campos retroativamente.

## Motivo de profundidade incompleta

A mensagem é derivada das flags de evidência: paginação do provedor encerrada, limite de requests ou resultados descartados durante normalização. Uma página contendo nove posições e **sem indicação de página seguinte** não comprova que Google tenha apenas nove resultados. Uma AUD que pediu 20 resultados permanece incompleta; não reduzir automaticamente a profundidade, inventar posições adicionais nem declarar ausência do domínio fora do conjunto observado.

## Atualização sem cache: autorização explícita e aviso de quota

A SerpApi informa cache por até uma hora para parâmetros idênticos e disponibiliza `no_cache=true`. A opção pode consumir quota e **não garante** resposta com mais resultados ou a indicação de nova página. Referência: https://serpapi.com/search-api.

**Padrão: permitir cache do fornecedor**, sem chamadas extras e sem alterações em auditorias anteriores.

Para pedir atualização na **próxima tentativa seletiva RPR**, o operador pode iniciar o mesmo console na sessão PowerShell em que habilitou temporariamente:

```powershell
$env:RASAI_SERP_NO_CACHE_RPR = "true"
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
.\abrir-rasai-console.cmd
```

No histórico, selecione somente as pendências desejadas e execute o RPR. A variável exige valor verdadeiro explícito, não é persistida no contrato original; não autoriza IA, não altera profundidade nem aumenta `max_requests`. Depois, remova o opt-in da sessão: `Remove-Item Env:\RASAI_SERP_NO_CACHE_RPR`. Se não houver autorização para possível quota, **não definir a variável** e não repetir imediatamente uma resposta já detectada como idêntica.

Para uso isolado do CLI de busca:
```powershell
rasai search "seguro de vida" --domain example.com --mode live --provider serpapi --depth 20 --no-cache
```
`--no-cache` é aceito exclusivamente em modo live com o adapter Google SerpApi. Ambos os caminhos preservam o mesmo `max_requests` e o orçamento de requisições configurado. Não usar o parâmetro em conjunto com `async` (o adapter não habilita async).

## Aceite e limites

Fixtures dirigidas devem comprovar: repetição de request ID/hash com timestamps separados; mensagem correta para paginação encerrada sem `next` e sem descarte; resposta diferente não marcada repetida; opção no-cache exclusivamente explícita; ausência de ampliação do orçamento; resultado incompleto ainda bloqueando IA. A homologação do comportamento do fornecedor real depende de um novo RPR do operador, com ZIP completo e sem assumir que o provedor disponibilizará a profundidade requerida.

Esta entrega é um tratamento pontual da issue #129; a convergência de todos os motores AUD/RPR (#110), o restante da linguagem pública (#109) e o gate geral (#92) são trabalhos separados.
