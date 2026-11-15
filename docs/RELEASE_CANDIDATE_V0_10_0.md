# Candidata 0.10.0 - gates de decisão

**Estado: preparação, sem publicação.** Este checklist não autoriza merge,
criação de tag, GitHub Release (inclusive draft) ou distribuição externa.
A última release pública é `v0.9.2`.

## Identidade e escopo

- Base de preparo: `09ff011ba1c9d12e6a6dfa07397dc9ae37ca2a42`.
- Baseline publicada: `v0.9.2`, commit `6fcd78bc074dcf2d69253bf3cedf7bed09c384ef`.
- Versão candidata: `0.10.0` em `pyproject.toml` e `src/rasai/__init__.py`.
- Método: `SCORE-GEO-005` vigente, `SCORE-GEO-004` histórico, `SARI-001` preservado.
- [Notas da candidata](RELEASE_NOTES_V0_10_0.md).

| Mudança | Fundamento e limite |
| --- | --- |
| Recursos no wheel | Quatro assets ausentes no wheel da base; apenas declaração de empacotamento |
| Identidade 0.10.0 | Capacidades públicas compatíveis acumuladas após v0.9.2 |
| README principal | Identidade candidata verdadeira e caminho da apresentação adicional |
| Índice documental | Distinguir fonte candidata da release publicada |
| Guia do console | Retirar baseline pública v0.5.0 desatualizada; explicitar scoring vigente/histórico |
| Saídas e artefatos | Corrigir a tabela metodológica para 005 vigente/004 histórico |
| README do gerador | Substituir ressalva de wheel pela descrição do gate verificável |
| Smoke de compatibilidade | Passar v0.9.2 explicitamente sem mudar o default do script histórico |
| Teste dedicado | Build real, instalação não editável e geração offline fora do checkout |

Nenhuma alteração funcional de motor, design system ou dados históricos integra
este preparo. As restrições das issues 127, 192, 311, 703 e 650 permanecem.

## Gate da PR candidata

- [ ] Confirmar diff restrito ao escopo e HEAD exato.
- [ ] Conferir teste de wheel instalado, hashes e geração B offline.
- [ ] Conferir testes focais de versão, documentação, relatórios e navegação.
- [ ] Conferir CI aplicável no HEAD final, incluindo regressão integral.
- [ ] Conferir instalação/compatibilidade Windows e Linux com baseline v0.9.2.
- [ ] Revisão humana da PR e decisão expressa, separada, sobre eventual merge.

O teste dedicado pode ser reproduzido com Python 3.13 e Chromium já preparado:

```powershell
python -m pytest -q tests/test_wheel_distribution.py
```

O smoke histórico continua usando instalação editável e não substitui esse gate:

```powershell
./scripts/RELEASE_COMPATIBILITY_SMOKE.ps1 -Baseline v0.9.2
```

Recibos anteriores não certificam um HEAD posterior. Aprovação automatizada não
equivale a homologação física de AUD/RPR/CONS nem autoriza provider ou cobrança.

## Gate posterior de publicação

- [ ] Merge expressamente autorizado e CI do SHA integrado aprovado.
- [ ] Nova autorização específica para tag e GitHub Release draft.
- [ ] Confirmar proteção de imutabilidade, commit, inexistência da tag e assets autorizados.
- [ ] Autorização específica de publicação e verificação da release imutável.

Não criar nem mover tags neste preparo. Nenhum envio a PyPI, registry Docker,
hosting ou canal de artefatos está incluído. A sanitização documental pós-1.0.0
permanece fora do escopo.
