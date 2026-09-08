# MODEL_ROUTING_POLICY.md

**Estado no baseline de desenvolvimento:** BASELINE OPERACIONAL
**Objetivo:** escolher IA/modelo de acordo com esforço, risco e necessidade de acesso ao repositório.

## 1. Separar dois usos de IA

### A. IA usada para desenvolver o RASAi Auditor

É a IA/agente que:

- lê especificações;
- cria ou modifica código;
- revisa arquitetura;
- executa testes;
- diagnostica problemas.

### B. IA usada pelo RASAi Auditor em runtime

É o SemanticAnalysisProvider utilizado para avaliar páginas.

As duas coisas não devem ser confundidas.

## 2. Roteamento por esforço - desenvolvimento

### Esforço baixo

Exemplos:

- correção textual;
- ajuste isolado;
- formatação;
- pequenas alterações de configuração;
- tarefas mecânicas sem impacto arquitetural.

Usar configuração rápida/default disponível.

Não consumir raciocínio avançado sem necessidade.

### Esforço médio

Exemplos:

- implementação de módulo isolado;
- revisão de código;
- testes;
- diagnóstico de bug não trivial;
- decisões técnicas locais.

Modelo recomendado atualmente:

`GPT-5.6 Sol`

ou modelo equivalente de raciocínio disponível no ambiente.

### Esforço alto / crítico

Exemplos:

- bootstrap estrutural;
- alteração transversal;
- Rules Engine;
- scoring;
- fallback de IA;
- arquitetura de persistência;
- Desktop/Mobile;
- debugging complexo;
- revisão de consistência entre múltiplos documentos;
- migração que possa alterar comportamento funcional.

Utilizar:

`GPT-5.6 Sol`

com a maior capacidade de raciocínio disponível no ambiente, ou agente de código equivalente.

Quando a tarefa exigir criar/editar arquivos no repositório local, utilizar obrigatoriamente uma ferramenta/agente com acesso real ao filesystem.

Um chat sem acesso ao filesystem não deve afirmar que gravou arquivos em:

`C:\IA-PROJETOS\github\RASAI-Readiness-Auditor`

## 3. Runtime do produto

Arquitetura:

SemanticAnalysisProvider
├── NONE
├── OPENAI
├── futuros providers

MVP:

- `NONE` obrigatório;
- `OPENAI` primeiro provider real.

O modelo específico da API não deve ser hardcoded na especificação funcional.

Ele deve ser configurável porque:

- modelos mudam;
- disponibilidade muda;
- política corporativa pode mudar;
- provider corporativo pode ser diferente.

O modelo escolhido em runtime deve possuir capacidade suficiente para:

- saída estruturada;
- interpretação semântica;
- evidence-grounded analysis;
- baixa propensão a inventar referências.

## 4. Fallback

Provider não configurado:

NO_AI

Provider configurado mas indisponível:

DEGRADED

Provider operacional:

FULL

Em NO_AI ou DEGRADED:

- deterministic analysis continua;
- safe heuristics continuam;
- semantic-only rules podem virar UNKNOWN;
- website nunca recebe penalidade por ausência de capacidade da auditoria.

## 5. Multi-provider

Adicionar outro provider deve exigir apenas adapter/provider novo.

Não deve exigir mudança em:

- Business Rules;
- Finding;
- Score;
- Report;
- Domain Model.

## 6. Política de revisão

Para mudanças críticas:

1. ler especificação pertinente;
2. implementar;
3. executar testes mínimos;
4. revisar contra requisitos;
5. quando a mudança fizer parte de um marco, cumprir todos os gates de branch, PR, merge, confirmação pós-merge e limpeza Git definidos na baseline;
6. avançar ao marco seguinte automaticamente somente quando autorizado por D-034 e após o encerramento integral exigido por D-035.

Blockers reais interrompem a cascata; problemas técnicos ordinários e solucionáveis devem ser corrigidos e revalidados sem solicitar nova aprovação humana.

## 7. Nota sobre esta política

A seleção exata de nomes comerciais/modelos pode mudar com disponibilidade do ambiente.

A regra normativa é capability-based:

- tarefa simples → modelo rápido;
- tarefa não trivial → reasoning model;
- tarefa crítica/transversal → reasoning model forte;
- escrita no repositório → agente com filesystem;
- runtime semântico → provider configurável;
- ausência de provider → fallback obrigatório.
