# Análise semântica por IA, roteamento e telemetria

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Scoring boundary:** `SARI-001` / `SCORE-GEO-004`

IA é uma extensão de análise semântica. LLM não é scoring engine, não substitui Business Rules e falha/ausência de provider não é defeito do website.

## 1. Providers

Core análise semântica por IA:

- `OPENAI`;
- `DEEPSEEK`;
- `MIMO`;
- `NONE`;
- `AUTO` sobre a cadeia core.

Extensões explícitas atuais:

- `XAI` / alias `grok`;
- `QWEN`;
- `GEMINI`;
- `ANTHROPIC` / alias `claude`.

Providers de extensão permanecem explicit-only enquanto sua qualificação é provisória. `AUTO` delega ao core e considera somente OpenAI, DeepSeek e MiMo.

## 2. Core routing policy

A política versionada do core inclui, em ordem:

1. OpenAI `gpt-5.6-sol`;
2. OpenAI `gpt-5.6-terra`;
3. DeepSeek `deepseek-v4-pro`;
4. MiMo `mimo-v2.5-pro`;
5. OpenAI `gpt-5.6-luna`;
6. DeepSeek `deepseek-v4-flash`;
7. MiMo `mimo-v2.5`.

Ranks, reasoning profiles, qualification/reliability labels e finalidade pertencem à política interna RASAi. Eles não são benchmark científico universal.

## 3. Selection and fallback

Provider explícito não faz failover cruzado para outro fornecedor. Credenciais ausentes de providers não selecionados não podem invalidar um provider explícito funcional.

`AUTO` resolve providers utilizáveis e tenta sequencialmente conforme a política. O primeiro resultado válido encerra a cadeia naquele contexto; um provider posterior não pode sobrescrever o resultado aceito.

Falhas qualificadoras podem permitir retry/fallback conforme política de resiliência. Falha de integração nunca vira finding do website.

## 4. URL/device consistency

O escopo público de dispositivo é `mobile`, `desktop` ou `both`. Somente contextos materializados podem disparar chamada de IA.

Quando a política fixa provider por URL, a consistência entre contextos da mesma URL deve ser preservada conforme o runtime. A comparação BR-GEO-052 só existe quando ambos os dispositivos fazem parte do escopo.

## 5. Contract validation

Todos os adapters convergem para um contrato normalizado. Uma resposta semântica só é aceita após validação local de:

- schema/estrutura esperada;
- conjunto de regras semânticas;
- ausência de duplicação/regra desconhecida;
- enums;
- `evidence_ids` existentes;
- completude contratual.

HTTP 200 ou JSON parseável isoladamente não significam resultado válido.

## 6. Retry and cost control

A política de resiliência limita chamadas e distingue erros elegíveis/não elegíveis a retry. Network/timeout/server/rate-limit/empty-response podem ser elegíveis; auth, permission, credit/quota, model, contract e invalid-response não devem ser repetidos indiscriminadamente.

Retry/fallback e limites existem também para evitar custo duplicado. `Retry-After` é tratado de forma bounded conforme a implementação.

## 7. Telemetry

`ai_provider_attempts` pode registrar:

- URL/device/tentativa;
- provider/model/rank/reasoning;
- timestamps/duração;
- status e diagnóstico sanitizado;
- usage reportado;
- custo estimado e versão de pricing;
- hashes/summaries bounded;
- versão do contrato semântico;
- decisão de retry/fallback/success quando aplicável.

Secrets, headers de autorização, payload sensível integral e private reasoning não são persistidos.

Tokens ausentes permanecem `NULL`. Custo estimado é telemetria operacional, não invoice e não participa do score.

## 8. Reporting

Página pública de telemetria:

```text
report/ai-usage.html
```

O report deve distinguir configuração, tentativa, sucesso, provider previsto/efetivo, fallback, status, tokens e custo estimado sem converter falha de IA em finding do website.

## 9. Scoring boundary

Invariantes:

1. IA permanece opcional;
2. `NONE` executa o auditor sem chamadas de LLM;
3. ausência/falha de IA não equivale a baixa qualidade do website;
4. LLM não calcula `SCORE-GEO-004`;
5. somente evidência persistida pode sustentar resultado aceito;
6. resultado válido não pode ser sobrescrito por tentativa posterior;
7. contexto de dispositivo limita chamadas ao escopo solicitado;
8. telemetria é separada de findings e score;
9. outcomes externos não entram em `SARI-001/SCORE-GEO-004` sem nova metodologia explícita/versionada.

`SCORE-GEO-003` é histórico e não deve ser usado como identificação do runtime atual em prompts, relatórios ou documentação operacional.
