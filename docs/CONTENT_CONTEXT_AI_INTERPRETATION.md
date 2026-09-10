# Interpretação de contexto editorial pela IA

Quando um campo editorial do RASAi está configurado como `auto` e a IA está habilitada, o runtime pode pedir ao modelo uma interpretação contextual da página para ajudar o usuário a comparar sua intenção editorial com a leitura feita pela IA.

A configuração persistida continua sendo `AUTO`. A interpretação não substitui nem resolve permanentemente o valor.

## Campos elegíveis

- perfil de risco;
- categoria YMYL;
- propósito da página;
- público pretendido;
- requisito/relevância de experiência relacionado a E-E-A-T;
- sensibilidade a atualização;
- origem do conteúdo.

## Regras de interpretação

A IA deve usar somente o conteúdo/evidências fornecidos naquela requisição. Ela não pode inventar reputação, credenciais, revisão profissional, status legal, experiência pessoal, políticas ocultas ou qualquer fato não observado.

Cada classificação interpretada deve ser acompanhada, quando disponível, por confiança, justificativa curta e IDs de evidência fornecidos ao modelo. Se o conteúdo não sustentar a classificação, o estado é `Não determinável`.

## Separação de estado

A interpretação:

- não sobrescreve `content_analysis_contexts`;
- não é persistida como classificação estruturada/canônica no banco;
- não vira evidência determinística;
- não altera SARI-001 ou SCORE-GEO-004 por si só;
- não é reutilizada como verdade em outra execução.

A saída transitória é retirada da resposta antes da normalização semântica tradicional e mantida somente em memória para a projeção final do HTML. A versão legível aparece separadamente em `readiness.html`.

## Exemplo conceitual

```text
Configuração: AUTO
Interpretação da IA: YMYL — Finanças e segurança econômica
Confiança: 87%
Justificativa: o conteúdo orienta uma decisão com possível impacto financeiro relevante.
```

Esse bloco descreve a leitura contextual do modelo naquela execução; não é uma classificação oficial do website.
