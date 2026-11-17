# Exportação externa candidata de `report-catalog` - Issue #717

**Estado:** implementação segregada, sujeita à CI, revisão de segurança e homologação antes da publicação externa. **Não distribuir o ZIP canônico** de `report-catalog`: ele inclui `integrity/audit-snapshot.db`, com possíveis dados opacos/restritos que não foram liberados por uma varredura de HTML.

## Perfis e limites de confiança

| Perfil | Conteúdo | Garantia legítima |
|---|---|---|
| Interno/probatório (`report-catalog`) | HTML, estilos, manifestos, assurance e snapshot SQLite completo | Integridade da fonte persistida sob o contrato do catálogo; **não** equivale à autorização de divulgação pública |
| Exportação candidata (`RASAI-PUBLIC-CATALOG-EXPORT-001`) | Somente arquivos textuais explicitamente permitidos, inventário e manifesto próprios | Pacote offline autoconsistente, com triagem automatizada; **não** alega equivalência forense, não contém banco bruto e **exige revisão de privacidade antes de distribuição** |

A exportação não transforma ou reescreve o banco da auditoria, nem altera `report-catalog`, `report-presentation`, scoring, coleta, execução de IA, retry, ledger ou evidências. A exportação é um artefato **derivado e independente** do catálogo canônico.

## Operação local (somente depois da homologação desta PR)

Exemplo Windows PowerShell, com pasta do relatório real existente e **ZIP de saída ainda inexistente fora da pasta de origem**:

```powershell
& .\.venv\Scripts\python.exe -B -m rasai.public_report_export --catalog-dir "C:\IA-PROJETOS\github\RASAI-Readiness-Auditor\audits\AUD-EXEMPLO\report-catalog" --output "$HOME\Downloads\RASAI_EXPORT_CANDIDATO_AUD_EXEMPLO.zip"
```

### Prévia parcial quando a fonte contém páginas não divulgáveis

Por padrão, o exportador continua **fail-closed**: qualquer dado sensível ou incompatibilidade HTML interrompe a exportação. Para inspeção privada, existe o modo **explicitamente opt-in**, que substitui páginas inteiras não publicáveis por avisos inertes, sem tentar limpar ou reconstruir seletivamente os dados:

```powershell
& .\.venv\Scripts\python.exe -B -m rasai.public_report_export --catalog-dir "C:\IA-PROJETOS\github\RASAI-Readiness-Auditor\audits\AUD-EXEMPLO\report-catalog" --output "$HOME\Downloads\RASAI_PREVIA_PARCIAL_AUD_EXEMPLO.zip" --withhold-unsafe-pages
```

- Somente até **cinco páginas HTML canônicas**, nunca `index.html`, podem ser retidas. CSS e demais arquivos com conteúdo inseguro mantêm bloqueio total.
- As páginas retidas **não são exportadas**: seus bytes são substituídos por avisos explícitos; âncoras locais referenciadas a partir de outras páginas elegíveis são reconstruídas apenas como destinos inertes para não quebrar a navegação.
- O arquivo `export-manifest.json` declara `export_mode=withheld-pages-review-only` e a lista nominal `withheld_pages`. Cada HTML original não retido é preservado byte a byte e continua sujeito aos mesmos gates de segurança.
- **Uma prévia parcial não é homologação de conteúdo, relatório completo nem autorização de publicação**. Mesmo que o comando produza ZIP verificável, cabe revisão humana de todos os arquivos incluídos. Para exibir fatos da página omitida, consulte somente o catálogo interno original.
- O comando não executa chamadas de IA, coleta, HTTP, reprocessamento ou escrita no AUD; o catálogo canônico e sua apresentação permanecem íntegros.

O comando **não transmite** dados e não gera nova análise nem nova auditoria. `EXPORT_CANDIDATE=READY_FOR_PRIVACY_REVIEW` significa apenas que as barreiras técnicas passam - não é uma decisão de liberação externa.

### Controles fail-closed

1. Verifica a origem pelo verificador canônico de pacote, `manifest.json`, inventário exato, digest lógico de equivalência entre fonte e snapshot final (pacotes históricos sem essa prova são recusados) e `integrity/catalog-assurance.json` com `global_output_security.passed=true`. Não considera essa flag aprovação pública por si só.
2. Rejeita links relativos quebrados, âncoras inexistentes, caminhos fora do pacote, links de recursos remotos ativos, iframes/embeds, redirecionamento automático, CSS `@import` e `srcset` sem inspeção apropriada.
3. Rejeita symlinks, caminhos ocultos/duvidosos, arquivos não inventariados, candidatos com dados não UTF-8, NUL e limites de tamanho excedidos.
4. Inclui apenas extensões textuais explicitamente permitidas: `.html`, `.css`, `.txt`, `.md` e `.json`. JavaScript externo não é exportado: cada HTML deve conter exclusivamente o script de interface original e idêntico ao código canônico de navegação/modais; scripts adicionais, atributos executáveis, formulários, SVG/embeds e importações CSS ativas são recusados. O diretório `integrity/` inteiro, o `manifest.json` interno, bancos SQLite, dumps binários e quaisquer outros formatos são **excluídos**. Se o HTML depender de um arquivo excluído, a exportação é recusada em vez de gerar um relatório quebrado.
5. Examina os arquivos incluídos com o detector canônico de segredos, marcadores de payload opaco e sinais de dados pessoais (e-mail, CPF/CNPJ formatados). **Achados bloqueiam a exportação**; não há substituição silenciosa por `[REDACTED]`, que poderia ocultar perda de contexto/prova.
6. Calcula hashes SHA-256 e tamanhos para cada arquivo incluído. Grava `export-manifest.json` com perfil, digest do manifesto de origem e declaração explícita de não equivalência forense.
7. Reabre o ZIP e valida inventário, hashes, conteúdo, referências locais e proibição de arquivos brutos antes de disponibilizar a saída. Cria o destino por operação atômica de vínculo físico, sem sobrescrever arquivo preexistente, inclusive sob concorrência. Duas exportações de fontes idênticas devem produzir bytes idênticos.

**Restrições conscientes:** o detector não garante encontrar toda forma de dado pessoal, confidencial ou segredo novo; ausência de alerta automatizado não significa desclassificação. URLs, termos competitivos, textos estratégicos e dados de clientes podem ser sensíveis mesmo quando não combinam com padrões. A revisão pelo proprietário dos dados deve examinar **todos os HTMLs e anexos do ZIP** para decidir finalidade, público destinatário e necessidade de expurgo. A implementação atual prefere **recusar** arquivos problemáticos, e não criar automaticamente uma versão editada cujo significado possa divergir do original.

## Testes direcionados

```powershell
& .\.venv\Scripts\python.exe -B -m pytest -q tests/test_public_report_export.py
```

Cobrir os casos sintéticos: segredo encapsulado no SQLite, segredo real no HTML fora de campos de payload, `encrypted_content` projetado, credencial em anexo textual, arquivo extra, ZIP com conteúdo proibido, duplicação, alteração de hashes, links quebrados, path traversal, ausência de aceite de assurance, destino dentro da origem, recusa de sobrescrita e ausência de mutação da árvore original.

**Gate para resolver #717:** testes + CI aprovados no SHA final; smoke offline em Windows com cópia isolada de uma auditoria real; inspeção dos HTMLs e anexos; evidência de que nenhum conteúdo restrito foi distribuído. Não confundir a criação deste exportador com certificação de liberação pública.
