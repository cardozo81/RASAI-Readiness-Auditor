"""Final presentation-only consistency layer for the local interactive console.

The console has several independently composed feature surfaces. This module is the
last public-UX projection and therefore standardises only operator-facing copy, colours
and action descriptions. It deliberately does not change routing, persistence,
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
_LABEL_RE = re.compile(r"^(?P<label>[^:]+?)\s*:\s*(?P<detail>.*)$")

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
    "T. Validar integrações e IAs configuradas — somente probes seguros": (
        "T. Validar integrações e IAs configuradas — somente probes seguros; pode consumir quota"
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
    # Provider/credential actions. Keep storage scope in the action itself so the
    # operator does not need to infer whether session, User or Machine is affected.
    "S. Setar/alterar Key na sessão": (
        "S. Definir/alterar credencial somente nesta sessão"
    ),
    "P. Persistir/remover Key no Windows/User": (
        "P. Gerenciar credencial persistida no Windows/User — nunca no INI"
    ),
    "L. Limpar Key somente da sessão": (
        "L. Limpar credencial da sessão — Windows/User permanece inalterado"
    ),
    "X. Excluir Key da sessão e do Windows/User": (
        "X. Excluir credencial da sessão + Windows/User — Windows/Machine não é alterado"
    ),
    "A. Habilitar/desabilitar no AUTO sem apagar a Key": (
        "A. Incluir/excluir este provider do pool AUTO — não apaga a credencial"
    ),
    "U. Usar este provider nesta auditoria": (
        "U. Selecionar este provider como IA principal"
    ),
    # Older secret editor retained by the composed console for compatible paths.
    "S. Setar/alterar sessão": "S. Definir/alterar valor somente nesta sessão",
    "R. Remover da sessão": (
        "R. Remover valor somente da sessão — persistência não é alterada"
    ),
    "P. Persistir/remover credencial no Windows": (
        "P. Gerenciar credencial persistida no Windows/User — nunca no INI"
    ),
    # Consolidated report result actions.
    "I. Abrir relatório": "I. Abrir relatório consolidado gerado",
    "P. Abrir pasta": "P. Abrir pasta de arquivos deste relatório consolidado",
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
    if (
        "disponível somente no menu início" in lowered
        or "não é necessário" in lowered
        or "cancelad" in lowered
        or "ainda não disponível" in lowered
    ):
        return "INFO"
    if "expirou" in lowered or "indisponível neste estado" in lowered:
        return "ALERTA"
    return "ERRO"


def _split_label(text: str) -> tuple[str, str] | None:
    match = _LABEL_RE.match(str(text).strip())
    if match is None:
        return None
    return match.group("label").strip(), match.group("detail").strip()


def _rewrite_line(state: Any, line: str) -> str:
    raw = str(line)
    plain = _plain(raw)
    stripped = plain.strip()
    indent = plain[: len(plain) - len(plain.lstrip())]

    replacement = _ACTION_REWRITES.get(stripped)
    if replacement is not None:
        return indent + replacement

    labeled = _split_label(stripped)
    if labeled is not None:
        label, detail = labeled
        normalized_label = label.casefold()
        if normalized_label == "erro":
            friendly = _friendly_error(detail)
            return indent + _message(_error_kind(state, friendly), friendly)
        if normalized_label in {"atenção", "alerta", "aviso"}:
            return indent + _message("ALERTA", detail)
        if normalized_label in {"observação", "informação", "info"}:
            return indent + _message("INFO", detail)
        if normalized_label in {"falha", "erro técnico", "não foi possível abrir"}:
            return indent + _message("ERRO", detail)
        if normalized_label == "aberto":
            return indent + _message("OK", f"Artefato aberto: {detail}")
        if normalized_label == "configuração salva em":
            return indent + _message("OK", f"Configuração não sensível salva em {detail}")

    upper = stripped.upper()
    if upper.startswith("FALHA NA ") and ":" in stripped:
        summary, detail = stripped.split(":", 1)
        return indent + _message("ERRO", f"{summary}. Detalhe: {detail.strip()}")
    if upper.startswith("FILTRO INVÁLIDO:"):
        return indent + _message(
            "ERRO",
            "Filtro inválido. Corrija os valores informados e tente novamente. "
            + stripped.split(":", 1)[1].strip(),
        )
    if stripped == "A auditoria de referência deve ser anterior à auditoria atual.":
        return indent + _message(
            "ALERTA",
            "A auditoria de referência precisa ser anterior à auditoria atual. Selecione outro par.",
        )
    if stripped == "Nenhuma URL corresponde ao trecho informado.":
        return indent + _message(
            "INFO",
            "Nenhuma URL corresponde ao filtro informado. Volte e ajuste o filtro para continuar.",
        )
    if stripped.startswith("IA selecionada, porém indisponível:"):
        return indent + _message(
            "ALERTA",
            stripped + " O relatório seguirá sem análise especialista por IA.",
        )
    if stripped == "A análise por IA não pode ser executada com segurança; o consolidado seguirá sem IA.":
        return indent + _message(
            "ALERTA",
            "A análise especialista por IA não pode ser executada com segurança; o consolidado seguirá sem IA.",
        )
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
    if stripped == "Chaves/API tokens não são gravados no INI por segurança.":
        return indent + _message("INFO", "Credenciais e tokens não são gravados no INI por segurança.")
    if stripped == "Há alterações de configuração ainda não salvas no arquivo INI.":
        return indent + _message(
            "ALERTA",
            "Há alterações não salvas no arquivo INI. Salve ou descarte explicitamente antes de sair.",
        )
    if stripped.startswith("Uma ou mais alterações de credenciais desta sessão diferem da persistência do Windows"):
        return indent + _message(
            "ALERTA",
            "Há credenciais alteradas somente na sessão; ao sair, elas não serão persistidas como padrão de novos processos.",
        )
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

    # These functions are invoked directly by the main loop, so they must participate
    # in the same final presentation contract as nested configuration/audit menus.
    for name in (
        "_menu",
        "_configure",
        "_environment_menu",
        "_save_configuration",
        "_confirm_exit",
        "_artifact_action",
        "render_help",
        "render_m23_help",
        "run_audit_from_console",
        "_post_run_actions",
    ):
        current = getattr(console_module, name, None)
        if callable(current):
            setattr(console_module, name, _wrap(current))

    console_module._rasai_operator_ux_consistency = True
