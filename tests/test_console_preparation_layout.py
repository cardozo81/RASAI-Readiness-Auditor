from types import SimpleNamespace

from rasai.console_preparation_layout import (
    _replace_menu_references,
    _standardize_output,
    _translate_choice,
)


def _sample_render() -> str:
    return """INÍCIO > PREPARAR AUDITORIA

CONFIGURAÇÃO DA AUDITORIA
Arquivo INI: rasai-console.ini | SALVO

1. Entrada               : URL única | https://example.com
2. Projeto               : <auto>
3. Dispositivo           : mobile
4. IA                    : deepseek [APTO]
5. Remediações IA        : conteúdo=ON
6. Web Performance       : ON
7. max-pages             : 1
8. WebPerf max-pages     : 10
9. Idioma / mercado      : pt-BR / BR
10. Raiz auditorias      : audits
11. Synthetic Apdex      : ON
12. Timezone apresentação: America/Sao_Paulo

AÇÕES
S. Salvar configuração INI [SEM CHAVES]
H. Ajuda / custos
E. Variáveis de ambiente / credenciais
C. Histórico / relatórios consolidados [OFFLINE - sem APIs]
R. Executar [APTO] configuração válida
Q. Sair

SEARCH INTELLIGENCE
T. Termos SERP            : sem termos nesta execução | provider mode=live
   Termos são transitórios da sessão; credencial/provider/limites continuam em E.
13. Análise profunda URL  : ON | IA principal=DEEPSEEK

CONFIGURAÇÃO DO PROGRAMA
D. Restaurar padrões do RASAi

PERFIL DA PRÓXIMA EXECUÇÃO
F. Perfil da execução     : NENHUM | disponível para URL única | sessão apenas
L. Carregar configuração de AUD [NOVA EXECUÇÃO]
"""


def test_standardized_preparation_menu_uses_continuous_numbering_and_sections() -> None:
    rendered = _standardize_output(_sample_render())

    assert "[ ESCOPO ]" in rendered
    assert " 4. Idioma / mercado" in rendered
    assert " 5. Timezone apresentação" in rendered
    assert "[ INTELIGÊNCIA ARTIFICIAL ]" in rendered
    assert " 6. IA" in rendered
    assert " 8. Análise profunda URL" in rendered
    assert "[ WEB PERFORMANCE ]" in rendered
    assert "10. Máx. páginas da auditoria" in rendered
    assert "11. Máx. páginas em Web Performance" in rendered
    assert "12. Synthetic Apdex" in rendered
    assert "[ SEARCH INTELLIGENCE ]" in rendered
    assert "13. Termos SERP" in rendered
    assert "14. Raiz auditorias" in rendered
    assert "15. Perfil da execução" in rendered


def test_standardized_preparation_menu_exposes_actions_only_as_letters() -> None:
    rendered = _standardize_output(_sample_render())

    assert "[ AÇÕES ]" in rendered
    assert "R. Executar [APTO]" in rendered
    assert "S. Salvar configuração INI [SEM CHAVES]" in rendered
    assert "L. Carregar configuração de AUD [NOVA EXECUÇÃO]" in rendered
    assert "E. Integrações / credenciais" in rendered
    assert "V. Voltar ao início" in rendered
    assert "D. Restaurar padrões do RASAi" not in rendered
    assert "CONFIGURAÇÃO DO PROGRAMA" not in rendered


def test_visible_numbering_translates_without_changing_internal_handlers() -> None:
    state = SimpleNamespace(error="")
    assert _translate_choice(state, "4") == "9"
    assert _translate_choice(state, "6") == "4"
    assert _translate_choice(state, "8") == "13"
    assert _translate_choice(state, "13") == "T"
    assert _translate_choice(state, "15") == "F"
    assert _translate_choice(state, "R") == "R"


def test_restore_defaults_is_not_available_from_preparation() -> None:
    state = SimpleNamespace(error="")
    assert _translate_choice(state, "D") == ""
    assert "INÍCIO > Sistema / restaurar padrões" in state.error


def test_old_configuration_letters_are_not_hidden_shortcuts() -> None:
    state = SimpleNamespace(error="")
    assert _translate_choice(state, "T") == ""
    assert "item 13" in state.error

    state.error = ""
    assert _translate_choice(state, "F") == ""
    assert "item 15" in state.error


def test_contextual_guidance_uses_canonical_visible_items() -> None:
    assert _replace_menu_references("configure termos no item T") == "configure termos no item 13"
    assert _replace_menu_references("habilite o item 13") == "habilite o item 8"
    assert _replace_menu_references("configure IA no item 4") == "configure IA no item 6"
    assert _replace_menu_references("retorne a F. Perfil da execução") == "retorne a 15. Perfil da execução"
