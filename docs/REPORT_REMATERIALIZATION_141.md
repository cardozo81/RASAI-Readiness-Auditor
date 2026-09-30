# Rematerialização canônica e isolada — #141

## Contrato e limite de uso

Uma AUD é evidência persistida. A geração do relatório é sua **projeção** e
não pode retroativamente mudar aquisições, tentativas, custos, estado de
fulfillment, observações sidecar, hash das evidências ou a decisão de IA.
A chamada interna `catalog_report_site.materialize_catalog_report_site` não é
um entrypoint operacional independente: seus renderizadores dependem das
vinculações instaladas pelo runtime da aplicação.

O entrypoint suportado é:

```powershell
rasai rematerialize-report --audit-dir ".\audits\AUD-ID" --output-root "$env:TEMP\RASAI-REPORTS-141"
```

A saída sempre será `<output-root>/<AUD-ID>/report-catalog/index.html`.
Não há opção `--in-place`: a entrada original permanece intocada, e a
operação se recusa a sobrescrever saídas preexistentes. O caminho de saída
não pode estar dentro da AUD de origem. Para nova tentativa, use uma
pasta de saída nova, preservando a anterior como evidência.

## Garantias de fronteira

1. Ler a AUD com SQLite no modo somente leitura para validar a identidade.
2. Instalar `entrypoint._install_audit_runtime()`, o **mesmo** conjunto de hooks
   usado pelo comando `rasai audit`, sem chamar sua execução. Verificar
   `accepted_audit_refinements`, `execution_consistency_runtime`,
   `catalog_projection_consistency` e `post_smoke_alignment`, além dos
   bindings efetivos de catálogo e padrões. Falhar se houver instalação
   incompleta, sem fabricar um HTML aparentemente íntegro.
3. Calcular SHA-256 do inventário de arquivos da AUD (exceto
   `report-catalog/`, que é produto derivado); copiar a AUD inteira para
   staging sob a pasta de saída; conferir origem e staging por SHA-256.
4. Executar **apenas** `report_completion.materialize_catalog_report_projection`
   na cópia, com `socket.connect` e `socket.create_connection` bloqueados
   durante a projeção. Não executar finalizadores que consolidem/reconciliem
   ou coletores que reabram integração/IA.
5. Exigir `verify_catalog_report_package` válido, fingerprint de origem
   idêntico ao audit.db de staging, SHA-256 lógico de SQLite coerente com
   snapshot do manifesto e `manifest.freshness` **exatamente igual** à
   `execution_consistency_runtime._publication_state` da própria AUD.
   `assurance.closure_eligible` avalia somente assurance estrutural e
   nunca eleva uma AUD parcial a FINAL.
6. Revalidar inventário de entrada original e staging após a operação;
   recusar qualquer alteração de evidência e só então promover
   atomicamente a pasta com relatório para o destino definitivo.

O comando não pode garantir disponibilidade de artefatos originalmente
não persistidos; ausência real de dado na AUD deve continuar explícita.
Os hashes do pacote certificam integridade, não cobertura funcional.

## Smoke real exigido

AUD de referência: `AUD-6BB4E5EA1F7D4E8A9E9518F17DEF69AB`,
9/10 work-items resolvidos, SERP retornou 9/20 e permaneceu falha
recuperável legítima. O pacote original apresenta
`PRELIMINARY`, com W3C/CAT-01 e projeções completas da execução
original. A regeneração anterior feita pelo renderizador interno
não inicializado produziu uma falsa `FINAL` e perdeu linhas de vários
catálogos; **não usar esse pacote anterior como oráculo de cobertura**.

Validar novo comando nesta mesma AUD sem nova coleta, comparando:
- `manifest.freshness == PRELIMINARY` e estados no SQLite
  `PARTIAL_RETRYABLE/PENDING/PRELIMINARY`;
- hashes do banco e sidecar entre origem e nova cópia, sem alteração;
- integridade do pacote materializado, CAT-01/W3C, CAT-04, CAT-07,
  CAT-09 e índice versus relatório original;
- CAT-10 humaniza 71 observações de consentimento e oito tipos de
  plataforma conforme PR #140; classificação externa remanescente
  pertence à #109, não a este escopo;
- zero novas tentativas de IA, SERP, CrUX, preços ou outros providers.

Não transformar diferença legítima de HTML entre versões em suposta
divergência de dado sem conferir fonte persistida. Permanecem
independentes: #136 (smoke positivo IA) e #127/#15 (interrupção/RPR).
A #141 só fecha após CI dirigido e esta validação humana com evidência.
