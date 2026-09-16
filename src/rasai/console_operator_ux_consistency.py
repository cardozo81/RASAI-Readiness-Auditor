"""Final presentation-only consistency layer for the local interactive console.

The console has several independently composed feature surfaces.  This module is the
last public-UX projection and therefore standardises only operator-facing copy, colours
and action descriptions.  It deliberately does not change routing, persistence,
validation, scoring, retries, provider selection, fulfillment or audit evidence.
"""
from __future__ import annotations

import builtins
from contextlib import contextmanager
import re
from typing import Any, Callable, Iterator

from rasai.console_ui import CYAN, GREEN, RED, YELLOW, paint

_DEPTH = 0
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_ACTION_REWRITES = {
    "S. Definir / alterar": (
        "S. Definir / alterar valor — depois escolha sessão ou persistência"
    ),
    "L. Limpar override somente desta sessão": (
        "L. Limpar override da sessão — arquivo/Windows permanecem inalterados"
    ),
    "R. Restaurar estado canônico": (
        "R. Restaurar valor padrão/ausência canônica"
    ),
    "P. Gerenciar persistência Windows/User": (
        "P. Gerenciar credencial persistida no Windows/User — nunca no INI"
    ),
    "T. Detalhes técnicos": "T. Exibir detalhes técnicos desta configuração",
    "D. Documentação": "D. Abrir documentação desta configuração",
    "T. Validar / retestar integração": (
        "T. Validar / retestar esta integração agora — pode consumir quota técnica"
    ),
    "A. Ajustar dependência/parâmetro": (
        "A. Ajustar dependência/parâmetro desta integração"
    ),
    "T. Validar todas as integrações configuradas com probe seguro": (
        "T. Validar integrações configuradas — somente probes seguros; pode consumir quota"
    ),
    "1. Reprocessar somente pendências desta auditoria": (
        "1. Reprocessar somente pendências recuperáveis desta auditoria"
    ),
    "2. Carregar esta configuração para uma nova auditoria": (
        "2. Usar esta configuração como base de NOVA auditoria — AUD de origem não é alterada"
    ),
    "2. Carregar esta configuração para uma nova auditoria [INDISPONÍVEL]": (
        "2. Usar esta configuração como base de NOVA auditoria [INDISPONÍVEL]"
    ),
    "3. Mostrar caminhos de artefatos": (
        "3. Mostrar caminhos dos arquivos e artefatos desta auditoria"
    ),
    "R. Repetir limpeza física pendente": (
        "R. Tentar novamente remover arquivos físicos pendentes"
    ),
    "D. Remover este catálogo do plano": (
        "D. Remover este catálogo do plano da próxima auditoria"
    ),
    "U. Executar com IA": "U. Usar IA opcional nesta próxima auditoria",
    "U. Executar sem IA (recomendado)": (
        "U. Não usar IA opcional nesta próxima auditoria (recomendado)"
    ),
    "S. Salvar configuração no arquivo [SEM SECRETS]": (
        "S. Salvar configurações não sensíveis no arquivo [SECRETS NÃO SÃO GRAVADOS]"
    ),
    "L. Carregar configuração de AUD [NOVA EXECUÇÃO]": (
        "L. Carregar configuração de AUD como base [CRIA NOVA EXECUÇÃO]"
    ),
}

_GENERIC_ERRORS = {
    "ação inválida": "Ação não reconhecida. Use uma das opções exibidas na seção AÇÕES.",
    "opção inválida": "Opção não reconhecida. Use uma das opções exibidas nesta tela.",
    "id/ação inválido": "ID ou ação não reconhecido. Informe um ID exibido ou uma ação disponível.",
    "variável inválida": "Configuração não reconhecida. Selecione um número/ID exibido nesta tela.",
    "seleção inválida": "Seleção inválida. Use os números ou intervalos aceitos pela tela.",
}


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", str(text))


def _message(kind: str, text: str) -> str:
    normalized = kind.strip().upper()
    color = {
        "OK": GREEN,
        "INFO": CYAN,
        "ALERTA": YELLOW,
        "ERRO": RED,
    }.get(normalized, CYAN)
    label = paint(f"{normalized:<10}", color, bold=True)
    return f"{label} : {text.strip()}"


def _friendly_error(text: str) -> str:
    clean = str(text or "").strip()
    return _GENERIC_ERRORS.get(clean.casefold(), clean)


def _error_kind(state: Any, text: str) -> str:
    operation = str(getattr(state, "operation", "") or "").upper()
    lowered = str(text or "").casefold()
    if operation == "LOCAL:RESTORE_SYSTEM_DEFAULTS":
        return "ALERTA"
    if "disponível somente no menu início" in lowered or "não é necessário" in lowered:
        return "INFO"
    return "ERRO"


def _rewrite_line(state: Any, line: str) -> str:
    raw = str(line)
    plain = _plain(raw)
    stripped = plain.strip()
    indent = plain[: len(plain) - len(plain.lstrip())]

    replacement = _ACTION_REWRITES.get(stripped)
    if replacement is not None:
        return indent + replacement

    if stripped.startswith("Erro") and ":" in stripped:
        _, detail = stripped.split(":", 1)
        detail = _friendly_error(detail)
        return indent + _message(_error_kind(state, detail), detail)

    upper = stripped.upper()
    if upper.startswith("ATENÇÃO:"):
        return indent + _message("ALERTA", stripped.split(":", 1)[1])
    if upper.startswith("ALERTA:") or upper.startswith("AVISO:"):
        return indent + _message("ALERTA", stripped.split(":", 1)[1])
    if upper.startswith("OBSERVAÇÃO") and ":" in stripped:
        return indent + _message("INFO", stripped.split(":", 1)[1])
    if stripped == "Restauração concluída com ressalvas:":
        return indent + _message("ALERTA", "Restauração concluída com ressalvas; revise os itens abaixo.")
    if stripped == "Ainda não validado.":
        return indent + _message("INFO", "Integração ainda não validada. Use T para validar/retestar.")
    if stripped == "A alteração já está ativa nesta sessão.":
        return indent + _message("OK", "Alteração aplicada nesta sessão.")
    if stripped == "A execução foi iniciada. Esta tela será atualizada automaticamente.":
        return indent + _message("INFO", "Execução iniciada; esta tela será atualizada automaticamente.")
    if stripped == "Nenhum AUD com audit.db encontrado nesta raiz.":
        return indent + _message("INFO", "Nenhuma auditoria local foi encontrada nesta pasta.")
    if stripped == "Nenhuma integração com todas as dependências obrigatórias configuradas.":
        return indent + _message("INFO", "Nenhuma integração está pronta para validação em lote.")
    if stripped == "Nenhum requisito aplicável está pendente para nova tentativa.":
        return indent + _message("INFO", "Não há requisito aplicável pendente para nova tentativa.")
    if stripped.startswith("Opção inválida."):
        return indent + _message("ERRO", stripped)

    return raw


def _rewrite_text(state: Any, text: str) -> str:
    raw = str(text)
    if "\n" not in raw:
        return _rewrite_line(state, raw)
    lines = raw.splitlines()
    rewritten = "\n".join(_rewrite_line(state, line) for line in lines)
    if raw.endswith("\n"):
        rewritten += "\n"
    return rewritten


@contextmanager
def public_output(state: Any) -> Iterator[None]:
    """Apply the final copy/semantic-message projection to one public console flow."""
    global _DEPTH
    if _DEPTH:
        yield
        return

    original_print = builtins.print

    def ux_print(*args: Any, **kwargs: Any) -> None:
        rewritten = tuple(
            _rewrite_text(state, arg) if isinstance(arg, str) else arg
            for arg in args
        )
        original_print(*rewritten, **kwargs)

    _DEPTH += 1
    builtins.print = ux_print
    try:
        yield
    finally:
        builtins.print = original_print
        _DEPTH -= 1


def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_operator_ux_consistency", False)):
        return fn

    def wrapped(*args: Any, **kwargs: Any):
        state = next((item for item in args if hasattr(item, "error")), None)
        if state is None:
            return fn(*args, **kwargs)
        with public_output(state):
            return fn(*args, **kwargs)

    wrapped._rasai_operator_ux_consistency = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def install(console_module: Any) -> None:
    """Install after every other local-console presentation/navigation overlay."""
    if getattr(console_module, "_rasai_operator_ux_consistency", False):
        return

    for name in (
        "_menu",
        "_configure",
        "_environment_menu",
        "run_audit_from_console",
        "_post_run_actions",
    ):
        current = getattr(console_module, name, None)
        if callable(current):
            setattr(console_module, name, _wrap(current))

    console_module._rasai_operator_ux_consistency = True
