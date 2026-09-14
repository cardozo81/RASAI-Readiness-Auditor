"""Canonical preparation dashboard layout for the interactive console.

The preparation surface follows one navigation rule:

- numbers configure parameters of the next audit;
- letters execute actions or navigate;
- section headings only group related configuration.

This module is presentation-only. It translates the canonical visible numbering to the
existing configuration handlers without changing audit execution, persistence, provider
routing, quotas, reprocessing or report generation.
"""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from dataclasses import replace
import io
import sys
from types import ModuleType
from typing import Any, Callable


# Visible preparation numbering -> existing internal configuration choice.
# Keeping the translation at the presentation boundary avoids changing functional
# handlers while the UI exposes one continuous, semantic configuration sequence.
_VISIBLE_TO_INTERNAL = {
    "1": "1",   # Entrada
    "2": "2",   # Projeto
    "3": "3",   # Dispositivo
    "4": "9",   # Idioma / mercado
    "5": "12",  # Timezone de apresentação
    "6": "4",   # IA
    "7": "5",   # Remediações IA
    "8": "13",  # Análise profunda URL
    "9": "6",   # Web Performance
    "10": "7",  # Máx. páginas da auditoria
    "11": "8",  # Máx. páginas em Web Performance
    "12": "11", # Synthetic Apdex
    "13": "T",  # Termos SERP
    "14": "10", # Raiz auditorias
    "15": "F",  # Perfil da execução
}

_ROW_DEFINITIONS = (
    ("ESCOPO", (
        ("1. Entrada", "1", "Entrada"),
        ("2. Projeto", "2", "Projeto"),
        ("3. Dispositivo", "3", "Dispositivo"),
        ("9. Idioma / mercado", "4", "Idioma / mercado"),
        ("12. Timezone apresentação", "5", "Timezone apresentação"),
    )),
    ("INTELIGÊNCIA ARTIFICIAL", (
        ("4. IA", "6", "IA"),
        ("5. Remediações IA", "7", "Remediações IA"),
        ("13. Análise profunda URL", "8", "Análise profunda URL"),
    )),
    ("WEB PERFORMANCE", (
        ("6. Web Performance", "9", "Web Performance"),
        ("7. max-pages", "10", "Máx. páginas da auditoria"),
        ("8. WebPerf max-pages", "11", "Máx. páginas em Web Performance"),
        ("11. Synthetic Apdex", "12", "Synthetic Apdex"),
    )),
    ("SEARCH INTELLIGENCE", (
        ("T. Termos SERP", "13", "Termos SERP"),
    )),
    ("ARMAZENAMENTO / EXECUÇÃO", (
        ("10. Raiz auditorias", "14", "Raiz auditorias"),
    )),
    ("PERFIL DA PRÓXIMA EXECUÇÃO", (
        ("F. Perfil da execução", "15", "Perfil da execução"),
    )),
)


def _find_line(lines: list[str], prefix: str) -> tuple[int, str] | None:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            return index, line
    return None


def _relabel(line: str, number: str, label: str) -> str:
    if ":" not in line:
        return f"{number:>2}. {label}"
    _, value = line.split(":", 1)
    return f"{number:>2}. {label:<31}: {value.lstrip()}"


def _profile_continuations(lines: list[str]) -> list[str]:
    found = _find_line(lines, "F. Perfil da execução")
    if found is None:
        return []
    index, _ = found
    result: list[str] = []
    for line in lines[index + 1 :]:
        if not line.strip():
            break
        if not line.startswith("   "):
            break
        result.append(line)
    return result


def _action_line(lines: list[str], prefix: str, fallback: str) -> str:
    found = _find_line(lines, prefix)
    return found[1] if found is not None else fallback


def _standardize_output(rendered: str) -> str:
    """Recompose the detailed dashboard into the canonical preparation layout."""
    lines = rendered.splitlines()
    first_row = _find_line(lines, "1. Entrada")
    preamble = lines[: first_row[0]] if first_row is not None else lines
    while preamble and not preamble[-1].strip():
        preamble.pop()

    output = list(preamble)
    output.append("")
    output.append("Números configuram a próxima auditoria; letras executam ações ou navegam.")

    for heading, definitions in _ROW_DEFINITIONS:
        output.extend(("", f"[ {heading} ]"))
        for source_prefix, number, label in definitions:
            found = _find_line(lines, source_prefix)
            if found is None:
                output.append(f"{number:>2}. {label:<31}: <indisponível>")
                continue
            output.append(_relabel(found[1], number, label))
            if source_prefix == "T. Termos SERP":
                output.append("    Termos são transitórios da sessão; credencial/provedor/limites continuam em E.")
            elif source_prefix == "F. Perfil da execução":
                output.extend(_profile_continuations(lines))

    execute = _action_line(lines, "R. Executar", "R. Executar")
    save = _action_line(lines, "S. Salvar configuração", "S. Salvar configuração INI [SEM CHAVES]")
    load = _action_line(lines, "L. Carregar configuração", "L. Carregar configuração de AUD [NOVA EXECUÇÃO]")
    history = _action_line(lines, "C. Histórico", "C. Histórico / relatórios consolidados [OFFLINE - sem APIs]")
    help_line = _action_line(lines, "H. Ajuda", "H. Ajuda / custos")
    quit_line = _action_line(lines, "Q. Sair", "Q. Sair")

    output.extend((
        "",
        "[ AÇÕES ]",
        execute,
        save,
        load,
        "E. Integrações / credenciais",
        history,
        help_line,
        "V. Voltar ao início",
        quit_line,
    ))

    folder = _find_line(lines, "P. Abrir última pasta")
    report = _find_line(lines, "I. Abrir último relatório")
    if folder is not None or report is not None:
        output.extend(("", "[ ARTEFATOS ]"))
        if folder is not None:
            output.append(folder[1])
        if report is not None:
            output.append(report[1])

    return "\n".join(output).rstrip() + "\n"


def _translate_choice(state: Any, raw: str) -> str:
    choice = raw.strip().upper()
    if choice == "D":
        state.error = (
            "Restaurar padrões está disponível somente em "
            "INÍCIO > Sistema / restaurar padrões."
        )
        return ""
    return _VISIBLE_TO_INTERNAL.get(choice, choice)


def _canonical_preparation_menu(
    console_module: ModuleType,
    state: Any,
    detailed_menu: Callable[[Any], str],
) -> str:
    """Render the canonical preparation dashboard and translate its numeric choices."""
    original_input = builtins.input
    original_header = console_module.render_header
    real_stdout = sys.stdout
    buffer = io.StringIO()
    rendered = False

    def preparation_header(current_state: Any) -> None:
        original_header(current_state)
        print("INÍCIO > PREPARAR AUDITORIA\n")

    def preparation_input(prompt: str = "") -> str:
        nonlocal rendered
        if not rendered and prompt.strip().casefold().startswith("escolha"):
            real_stdout.write(_standardize_output(buffer.getvalue()))
            real_stdout.flush()
            rendered = True
            real_stdout.write(prompt)
            real_stdout.flush()
            raw = original_input("")
            return _translate_choice(state, raw)
        return original_input(prompt)

    console_module.render_header = preparation_header
    builtins.input = preparation_input
    try:
        with redirect_stdout(buffer):
            result = detailed_menu(state)
        if not rendered:
            real_stdout.write(_standardize_output(buffer.getvalue()))
            real_stdout.flush()
        return result
    finally:
        builtins.input = original_input
        console_module.render_header = original_header


def _replace_menu_references(text: str) -> str:
    return (
        text.replace("item T", "item 13")
        .replace("item 13", "item 8")
        .replace("item 4", "item 6")
        .replace("F. Perfil da execução", "15. Perfil da execução")
    )


def _patch_contextual_guidance() -> None:
    """Keep dependency guidance aligned with the canonical visible numbering."""
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles
    from rasai import improvement_intelligence_console as improvement

    if getattr(profiles, "_rasai_canonical_preparation_guidance", False):
        return

    original_dependency_status = profiles.dependency_status

    def dependency_status(state: Any, session: Any = None):
        ready, blockers, advisories = original_dependency_status(state, session)
        return (
            ready,
            tuple(_replace_menu_references(item) for item in blockers),
            tuple(_replace_menu_references(item) for item in advisories),
        )

    profiles.dependency_status = dependency_status

    updated_modules = []
    for item in profiles.MODULES:
        updated_modules.append(
            replace(item, dependency_note=_replace_menu_references(item.dependency_note))
        )
    profiles.MODULES = tuple(updated_modules)
    profiles.MODULE_BY_ID = {item.id: item for item in profiles.MODULES}

    original_print_blocked = readiness._print_blocked

    def print_blocked(label: str, blockers: tuple[str, ...]) -> None:
        original_print = builtins.print

        def adjusted_print(*args: Any, **kwargs: Any) -> None:
            rewritten = tuple(
                _replace_menu_references(arg) if isinstance(arg, str) else arg
                for arg in args
            )
            original_print(*rewritten, **kwargs)

        builtins.print = adjusted_print
        try:
            original_print_blocked(label, blockers)
        finally:
            builtins.print = original_print

    readiness._print_blocked = print_blocked

    original_single_url_ready = improvement._single_url_ready

    def single_url_ready(state: Any):
        ready, reason = original_single_url_ready(state)
        return ready, _replace_menu_references(reason)

    improvement._single_url_ready = single_url_ready
    readiness._single_url_ready = single_url_ready

    original_improvement_configure = improvement.configure

    def improvement_configure(console_module: ModuleType, state: Any) -> None:
        original_print = builtins.print

        def adjusted_print(*args: Any, **kwargs: Any) -> None:
            rewritten = tuple(
                _replace_menu_references(arg) if isinstance(arg, str) else arg
                for arg in args
            )
            original_print(*rewritten, **kwargs)

        builtins.print = adjusted_print
        try:
            original_improvement_configure(console_module, state)
        finally:
            builtins.print = original_print

    improvement.configure = improvement_configure
    profiles._rasai_canonical_preparation_guidance = True


def install(console_module: ModuleType) -> None:
    """Install the canonical preparation layout after task navigation is available."""
    if getattr(console_module, "_rasai_canonical_preparation_layout", False):
        return
    from rasai import console_navigation as navigation

    _patch_contextual_guidance()
    navigation._preparation_menu = _canonical_preparation_menu
    console_module._rasai_canonical_preparation_layout = True
