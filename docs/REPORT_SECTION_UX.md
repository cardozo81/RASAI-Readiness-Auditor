# #328 - Hierarquia visual das evidências CAT-06 e CAT-07

## Protótipo descritivo e implementação segura

Seções de amostras de navegação, tentativas por perfil, amostras
Experience e explicação de arquitetura recebem contorno e
separação editorial discretos, sem esconder linhas ou reorganizar
o conteúdo persistido. O relatório GEO já tem cartões `.geo-view`
independentes e não foi modificado neste recorte.

O separador `.cat-apdex-readable` é estritamente de apresentação:
borda, espaçamento e título com divisor. O subbloco de arquitetura
e a ressalva metodológica permanecem dentro da mesma evidência
CAT-07, com superfície e cabeçalho próprios. Em mobile há padding
reduzido e tabelas continuam com rolagem; impressão mantém todo
conteúdo visível, sem quebra forçada por cartão.

Invariantes: nenhuma mudança de dados, agrupamentos, cálculos,
fórmulas Apdex, scores, scores GEO, redação/escaping de valores,
IDs de evidência, SQLite, RPR ou tabelas publicadas.

O aceite de apresentação humana integral permanece dependente da
visualização do HTML; testes automáticos confirmam apenas a
gramática das seções, isolamento de CSS e persistência do texto.
