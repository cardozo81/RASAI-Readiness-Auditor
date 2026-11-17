"""Secret-safe command projection for external/scheduled RASAi executions."""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import json
import re
from datetime import datetime
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

SECRET_PLACEHOLDER = "**********"
# Keep the existing "windows" key for backward-compatible cmd.exe logs.
PLATFORMS = ("windows", "powershell", "linux", "macos")
LABELS = {
    "windows": "WINDOWS", "powershell": "POWERSHELL",
    "linux": "LINUX", "macos": "MACOS",
}
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
# Percent/delayed expansion, caret and embedded double quote semantics vary
# between interactive cmd.exe and batch files; use a lossless transport.
_CMD_UNSAFE = re.compile(r'[%!^"\r\n]')


@dataclass(frozen=True, slots=True)
class EnvValue:
    name: str
    value: str | None
    secret: bool


@dataclass(frozen=True, slots=True)
class CommandPlan:
    operation: str
    argv: tuple[str, ...]
    environment: tuple[EnvValue, ...]
    status: str = "PLANEJADO"
    metadata: tuple[tuple[str, str], ...] = ()


def _os() -> str:
    name = platform.system().casefold()
    return "windows" if name.startswith("win") else "macos" if name == "darwin" else "linux"


def _secret(name: str) -> bool:
    try:
        from rasai.console_config import is_secret
        return bool(is_secret(name))
    except ImportError:
        token = name.upper()
        return any(key in token for key in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))


def _names() -> tuple[str, ...]:
    try:
        from rasai.console_config import ENV_NAMES
        return tuple(dict.fromkeys(str(name) for name in ENV_NAMES))
    except ImportError:
        return ()


def _secret_names(state: Any | None, env: Mapping[str, str]) -> set[str]:
    names = {name for name in _names() if _secret(name) and str(env.get(name) or "").strip()}
    if state is None:
        return names
    provider = str(getattr(state, "ai_provider", "none") or "none").casefold()
    try:
        from rasai.provider_registry import get_provider_registration, provider_registrations
        if provider == "auto":
            names.update(item.key_env for item in provider_registrations() if str(env.get(item.key_env) or "").strip())
        elif provider not in {"", "none"}:
            item = get_provider_registration(provider)
            if item is not None:
                names.add(item.key_env)
    except (ImportError, RuntimeError, ValueError):
        pass
    try:
        from rasai.search_intelligence.config import SERP_MODE_ENV, SERP_PROVIDER_ENV, provider_key_env
        if str(env.get(SERP_MODE_ENV) or "").casefold() == "live":
            names.add(provider_key_env(str(env.get(SERP_PROVIDER_ENV) or "serpapi")))
    except (ImportError, RuntimeError, ValueError):
        pass
    if bool(getattr(state, "web_performance", False)):
        names.add("RASAI_PAGESPEED_API_KEY")
        if str(getattr(state, "field_source", "auto") or "auto").casefold() in {"auto", "crux"}:
            names.add("RASAI_CRUX_API_KEY")
    return names


def _environment(state: Any | None, env: Mapping[str, str]) -> tuple[EnvValue, ...]:
    secrets = _secret_names(state, env)
    out: list[EnvValue] = []
    for name in _names():
        value = str(env.get(name) or "")
        if _secret(name):
            if name in secrets:
                out.append(EnvValue(name, None, True))
        elif value.strip():
            out.append(EnvValue(name, value.replace("\r", " ").replace("\n", " "), False))
    existing = {item.name for item in out}
    out.extend(EnvValue(name, None, True) for name in sorted(secrets - existing))
    return tuple(sorted(out, key=lambda item: (not item.secret, item.name)))


def _meta(**items: Any) -> tuple[tuple[str, str], ...]:
    return tuple((key, str(value)) for key, value in items.items() if value not in {None, ""})


def audit_plan(state: Any, *, env: Mapping[str, str] | None = None, argv: Sequence[str] | None = None, status: str = "PLANEJADO") -> CommandPlan:
    if argv is None:
        from rasai.console_config import build_command
        argv = build_command(state)
    values = dict(os.environ if env is None else env)
    return CommandPlan("AUDITORIA", tuple(map(str, argv)), _environment(state, values), status,
                       _meta(alvo=getattr(state, "target", ""), dispositivo=getattr(state, "device", ""), ia=getattr(state, "ai_provider", "")))


def reprocess_plan(state: Any, audit_id: str, *, selected_items: Iterable[str], use_ai: bool, env: Mapping[str, str] | None = None, status: str = "PLANEJADO") -> CommandPlan:
    selected = tuple(dict.fromkeys(str(item) for item in selected_items if str(item).strip()))
    argv = [sys.executable, "-m", "rasai", "reprocess", audit_id, "--audits-root", str(state.audits_root)]
    for item in selected:
        argv += ["--item", item]
    argv.append("--use-ai" if use_ai else "--no-use-ai")
    if use_ai:
        argv += ["--ai-provider", str(getattr(state, "ai_provider", "none") or "none")]
        if getattr(state, "ai_model", None): argv += ["--ai-model", str(state.ai_model)]
        if getattr(state, "ai_reasoning", None): argv += ["--ai-reasoning", str(state.ai_reasoning)]
    values = dict(os.environ if env is None else env)
    return CommandPlan("REPROCESSAMENTO", tuple(argv), _environment(state, values), status,
                       _meta(audit_id=audit_id, itens=len(selected), ia="SIM" if use_ai else "NÃO"))


def consolidation_plan(audits_root: str | Path, selection: Any, filters: Any, *, env: Mapping[str, str] | None = None, status: str = "PLANEJADO") -> CommandPlan:
    argv = [sys.executable, "-m", "rasai", "consolidate", str(selection.baseline_audit_id), str(selection.current_audit_id),
            "--audits-root", str(audits_root), "--selection-mode", str(selection.selection_mode)]
    if str(selection.selection_mode).upper() == "MANUAL":
        for audit_id in selection.audit_ids[1:-1]: argv += ["--manual-audit-id", str(audit_id)]
    use_ai = bool(getattr(filters, "specialist_ai", False))
    argv.append("--specialist-ai" if use_ai else "--no-specialist-ai")
    if use_ai:
        argv += ["--ai-provider", str(getattr(filters, "ai_provider", None) or "none")]
        if getattr(filters, "ai_model", None): argv += ["--ai-model", str(filters.ai_model)]
        if getattr(filters, "ai_reasoning", None): argv += ["--ai-reasoning", str(filters.ai_reasoning)]
        if getattr(filters, "ai_timeout_seconds", None): argv += ["--ai-timeout-seconds", str(filters.ai_timeout_seconds)]
    values = dict(os.environ if env is None else env)
    state = SimpleNamespace(ai_provider=getattr(filters, "ai_provider", None) or "none", web_performance=False, field_source="auto")
    return CommandPlan("CONSOLIDADO", tuple(argv), _environment(state, values), status,
                       _meta(base=selection.baseline_audit_id, atual=selection.current_audit_id, selecao=selection.selection_mode, ia="SIM" if use_ai else "NÃO"))


def _valid_env_name(name: str) -> bool:
    return _ENV_NAME.fullmatch(name) is not None


def _cmd_quote(argument: str) -> str:
    """Quote a Windows CRT argv element, including trailing backslashes."""
    pieces = ['"']
    backslashes = 0
    for char in argument:
        if char == "\\":
            backslashes += 1
        elif char == '"':
            pieces.extend(("\\" * (backslashes * 2 + 1), '"'))
            backslashes = 0
        else:
            pieces.extend(("\\" * backslashes, char))
            backslashes = 0
    pieces.extend(("\\" * (backslashes * 2), '"'))
    return "".join(pieces)


def _cmd_transport(executable: str, args: Sequence[str], env: Mapping[str, str]) -> str:
    """Lossless cmd.exe argv+env via Python, never serializing secrets."""
    payload = base64.urlsafe_b64encode(json.dumps(
        {"args": list(args), "environment": dict(env)}, ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")).decode("ascii")
    code = (
        "import base64,json,os,subprocess,sys;"
        "p=json.loads(base64.urlsafe_b64decode('"+payload+"'));"
        "e=dict(os.environ);e.update(p['environment']);"
        "sys.exit(subprocess.call([sys.executable]+p['args'],env=e))"
    )
    resolved = executable if not _CMD_UNSAFE.search(executable) else "python"
    return _cmd_quote(resolved) + ' -c "' + code + '"'


def _powershell_quote(value: str) -> str:
    """Literal single-quoted PowerShell string, valid on 5.1 and 7."""
    return "'" + value.replace("'", "''") + "'"


def render(plan: CommandPlan, target: str) -> str:
    target = target.casefold()
    if target not in PLATFORMS:
        raise ValueError(target)
    if not plan.argv:
        raise ValueError("plano de execução sem argv")
    exe = plan.argv[0] if (
        (target in {"windows", "powershell"} and _os() == "windows")
        or target == _os()
    ) else ("python" if target in {"windows", "powershell"} else "python3")
    safe_env: dict[str, str] = {}
    for item in plan.environment:
        if not _valid_env_name(item.name):
            raise ValueError("nome de variável de ambiente inválido")
        if not item.secret:
            safe_env[item.name] = item.value or ""
    if target == "windows":
        lines = [
            "REM Shell: cmd.exe / .cmd; não usar no PowerShell.",
            "REM Secrets herdados do SO; nenhum valor de credencial é gravado.",
        ]
        lines += [f'REM set "{item.name}={SECRET_PLACEHOLDER}"'
                  for item in plan.environment if item.secret]
        if any(_CMD_UNSAFE.search(v) for v in (exe, *plan.argv[1:], *safe_env.values())):
            lines += [
                "REM Caracteres de expansão cmd: argv/env não secretos",
                "REM transportados por JSON/base64 ao Python local.",
                _cmd_transport(exe, plan.argv[1:], safe_env),
            ]
        else:
            lines += [f'set "{name}={value}"' for name, value in safe_env.items()]
            lines += [" ".join(_cmd_quote(x) for x in (exe, *plan.argv[1:]))]
        return "\n".join(lines)
    if target == "powershell":
        lines = [
            "# Shell: Windows PowerShell 5.1 ou PowerShell 7.",
            "# Secrets herdados do ambiente; nenhum valor real é gravado.",
        ]
        lines += [f"# $env:{item.name} = {_powershell_quote(SECRET_PLACEHOLDER)}"
                  for item in plan.environment if item.secret]
        lines += [f"$env:{name} = {_powershell_quote(value)}"
                  for name, value in safe_env.items()]
        lines += ["& " + " ".join(_powershell_quote(v) for v in (exe, *plan.argv[1:]))]
        return "\n".join(lines)
    lines = [
        "# Shell: POSIX sh (Linux/macOS).",
        "# Secrets herdados do ambiente; nenhum placeholder executável.",
    ]
    lines += [f"# export {item.name}={shlex.quote(SECRET_PLACEHOLDER)}"
              for item in plan.environment if item.secret]
    lines += [f"export {name}={shlex.quote(value)}" for name, value in safe_env.items()]
    lines += [shlex.join([exe, *plan.argv[1:]])]
    return "\n".join(lines)

def render_log(plan: CommandPlan) -> str:
    lines = ["=" * 100, "RASAi - LINHA DE COMANDO PARA EXECUÇÃO EXTERNA / AGENDAMENTO", "=" * 100,
             f"Registrado em : {datetime.now().astimezone().isoformat(timespec='seconds')}", f"Operação      : {plan.operation}", f"Estado        : {plan.status}"]
    lines += [f"{key:<14}: {value}" for key, value in plan.metadata]
    lines += ["", "SEGURANÇA DE CREDENCIAIS", "-" * 100,
              "Valores reais de secrets nunca são gravados. ********** é somente um placeholder.",
              "Secret comentado/removido: usa o valor herdado do SO. Secret ativado: override apenas do processo; não altera o SO."]
    for target in PLATFORMS:
        label = LABELS[target]; lines += ["", f"[{label}]", render(plan, target), f"[/{label}]"]
    return "\n".join(lines) + "\n"


def _root(audits_root: str | Path) -> Path:
    try:
        from rasai.runtime_paths import runtime_directory
        return runtime_directory(audits_root) / "logs" / "execution-commands"
    except ImportError:
        return Path(audits_root) / ".rasai" / "logs" / "execution-commands"


def log_path(audits_root: str | Path, execution_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(execution_id))
    return _root(audits_root) / f"{safe}.log"


def record(plan: CommandPlan, audits_root: str | Path, execution_id: str | None = None, *, append: bool = True) -> Path:
    path = log_path(audits_root, execution_id) if execution_id else _root(audits_root) / f"preview-{plan.operation.casefold()}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if append and path.exists():
        with path.open("a", encoding="utf-8", newline="\n") as handle: handle.write("\n" + render_log(plan))
    else:
        path.write_text(render_log(plan), encoding="utf-8", newline="\n")
    return path


def _blocks(text: str) -> dict[str, str]:
    out = {}
    for target in PLATFORMS:
        label = LABELS[target]; start = text.rfind(f"[{label}]\n"); end = text.find(f"\n[/{label}]", start + 1)
        if start >= 0 and end > start: out[target] = text[start + len(label) + 3:end].strip()
    return out


def _copyable_command(text: str, target: str) -> str:
    """Return the executable command without comments or secret placeholders."""
    active = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if target == "windows" and line.upper().startswith("REM "):
            continue
        if target != "windows" and line.startswith("#"):
            continue
        active.append(line)
    # The && operator was introduced in PowerShell 7; 5.1 requires ';'.
    return ("; " if target == "powershell" else " && ").join(active)


def _copy(text: str) -> bool:
    commands = [["clip"]] if os.name == "nt" else [["pbcopy"]] if platform.system() == "Darwin" else [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for command in commands:
        if shutil.which(command[0]):
            try:
                subprocess.run(command, input=text, text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return True
            except (OSError, subprocess.CalledProcessError): pass
    return False


def _open(path: Path) -> bool:
    try:
        from rasai.console_artifacts import open_external_path
        return bool(open_external_path(path)[0])
    except ImportError:
        return False


def _menu(blocks: Mapping[str, str], path: Path, artifact_root: str | Path | None, title: str) -> None:
    preferred = "powershell" if _os() == "windows" else _os()
    selected = preferred if preferred in blocks else next(iter(blocks))
    message = ""
    while True:
        print("\n" + "=" * 100); print(title); print("=" * 100)
        print(f"Shell: {LABELS[selected]} | Log: {path}")
        print("-" * 100); print(blocks[selected]); print("-" * 100)
        if message: print(message)
        print("1. Windows cmd.exe\n2. Windows PowerShell 5.1/7\n3. Linux sh\n4. macOS sh")
        print("C. Copiar comando executável para clipboard\nO. Abrir log de comandos")
        if artifact_root is not None: print("P. Abrir pasta da execução")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V": return
        options = {"1": "windows", "2": "powershell", "3": "linux", "4": "macos"}
        if choice in options:
            if options[choice] not in blocks:
                message = "Log histórico sem esta shell; use um log novo para PowerShell."
            else:
                selected = options[choice]
                message = ""
            continue
        if choice == "C":
            command = _copyable_command(blocks[selected], selected)
            message = (
                "Comando executável copiado; placeholders de secrets não foram incluídos."
                if _copy(command)
                else "Clipboard automático indisponível; copie o comando exibido."
            )
            continue
        if choice == "O": message = "Log aberto." if _open(path) else "Não foi possível abrir o log automaticamente."; continue
        if choice == "P" and artifact_root is not None: message = "Pasta aberta." if _open(Path(artifact_root)) else "Não foi possível abrir a pasta automaticamente."; continue
        message = "Ação inválida."

def show(plan: CommandPlan, audits_root: str | Path, *, artifact_root: str | Path | None = None, execution_id: str | None = None) -> None:
    path = log_path(audits_root, execution_id) if execution_id else record(plan, audits_root, append=False)
    _menu({target: render(plan, target) for target in PLATFORMS}, path, artifact_root, f"VER LINHA DE COMANDO - {plan.operation} - {plan.status}")


def show_logged(audits_root: str | Path, execution_id: str, *, artifact_root: str | Path | None = None) -> bool:
    path = log_path(audits_root, execution_id)
    if not path.is_file(): return False
    try: blocks = _blocks(path.read_text(encoding="utf-8"))
    except OSError: return False
    if not blocks: return False
    _menu(blocks, path, artifact_root, f"VER LINHA DE COMANDO - {execution_id}"); return True


def executed(plan: CommandPlan) -> CommandPlan:
    return replace(plan, status="EXECUTADO")
