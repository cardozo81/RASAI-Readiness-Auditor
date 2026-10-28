# Vocabulário público e rastreabilidade técnica

## Contrato de linguagem para o usuário

O console, os relatórios HTML e a documentação funcional devem apresentar capacidades e resultados pelos seus nomes compreensíveis, em português do Brasil. Códigos internos de módulos de implementação não pertencem a títulos, resumos, instruções, legendas nem mensagens operacionais.

| Superfície | Termo público esperado | Critério de clareza |
| --- | --- | --- |
| Console e métricas de IA | Tempo e consumo das análises por IA | Diferenciar soma de durações, união de intervalos e tempo total da auditoria |
| Console e relatório de custos | Tentativas de análise por IA e remediação de conteúdo | Não confundir custo estimado, gasto registrado e faturamento |
| Configuração e arquitetura | Arquitetura identificada durante a coleta | Distinguir arquitetura declarada, observada e indisponível |
| Relatório de arquitetura | Rastreabilidade da arquitetura identificada | Preservar página, captura, dispositivo e limitações |
| Web Performance | Tempos observados de requisições web | Não confundir soma de requisições HTTP com duração de etapa |
| Acessibilidade | Acessibilidade automatizada | Separar observações disponíveis de cobertura não verificada |
| Apdex | Apdex de navegação e experiência | Separar experiência sintética de monitoramento real |
| Dynatrace | Confronto da experiência observada e configuração do Apdex | Não equiparar monitoramento real a sondagem sintética |
| Rastreamento | Rastreamento e descoberta | Expor fontes, êxitos e limitações sem códigos de implementação |
| Comando de diagnóstico de tentativas | Tentativas de IA e requisições HTTP | Mostrar a origem e a aplicabilidade das medições |

## Fronteira entre comunicação e contrato interno

Nomes de tabelas, campos de JSON, identificadores de regras, códigos de erro, nomes de arquivos, selectors CSS e namespaces de evidência são contratos técnicos. Permanecem imutáveis nos dados persistidos e em seções estritamente técnicas quando necessários à operação ou depuração.

É proibida a substituição global baseada apenas em uma sequência parecida com código de módulo. Um nome de produto ou modelo observado no website pode ter a mesma aparência de um identificador interno. Sua evidência deve ser preservada exatamente como coletada.

A normalização limita-se aos elementos de apresentação pertencentes ao RASAi. A proteção do relatório está implementada em `src/rasai/public_report_safety.py`; sua existência não certifica automaticamente todas as páginas renderizadas.

## Critério de aceite

- Mensagens e documentos voltados ao operador usam nomes funcionais, inclusive quando descrevem tentativas de IA e suas durações.
- A informação técnica necessária permanece acessível em evidências ou seções de referência, sem tomar o lugar da explicação humana.
- Estados parciais, indisponíveis, não aplicáveis e de baixa confiança não são apresentados como resultados conclusivos.
- Toda correção de apresentação deve conservar contagens, tempos, custos, moeda, intervalos, proveniência e texto de evidência.
- Testes focais de regressão não substituem o smoke visual e textual do catálogo completo.

O inventário de redações anteriores foi incorporado a este contrato por equivalência funcional, sem reproduzir identificadores de implementação na documentação pública.
