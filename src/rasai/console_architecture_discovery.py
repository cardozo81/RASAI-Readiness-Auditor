"""Read-only, standalone main-menu architectural preview."""
from __future__ import annotations

from typing import Any
import os

from rasai.architecture_probe import probe_architecture
from rasai.architecture_live_capture import capture_public_architecture
from rasai.domain import DeviceContext


def describe_architecture_assessment(result: Any) -> tuple[str, ...]:
    """Explain only observations supported by the captured RAW/rendered comparison."""
    lines = [
        f"Arquitetura observada: {result.architecture.value}",
        f"Versão do método: {result.method_version}",
        f"Limitação: {result.limitation or 'Nenhuma identificada neste diagnóstico'}",
    ]
    comparison = result.comparison
    if comparison is None:
        lines.append("Evidência: comparação RAW/renderizada indisponível ou rejeitada.")
    else:
        lines.append(f"Conteúdo principal RAW: {'presente' if comparison.raw_main_content.strip() else 'ausente'}")
        lines.append(f"Conteúdo principal renderizado: {'presente' if comparison.rendered_main_content.strip() else 'ausente'}")
        lines.append(
            "Alterações observadas: "
            + (", ".join(comparison.changed_fields) if comparison.changed_fields else "nenhuma nos campos comparados")
        )
    lines.append("Escopo: uma URL e um dispositivo; diagnóstico preliminar, não uma certificação.")
    return tuple(lines)


def architecture_preview_menu(console: Any, state: Any) -> None:
    while True:
        console.render_header(state)
        print("INÍCIO > DESCOBRIR ARQUITETURA")
        print("Diagnóstico preliminar. Não altera a configuração de arquitetura;")
        print("a auditoria realizará sua própria descoberta.")
        print(f"URL: {getattr(state, 'target', '') or '<não informada>'}")
        print(f"Dispositivo: {getattr(state, 'device', 'mobile')}")
        print("1. Executar descoberta")
        print("2. Alterar URL")
        print("3. Alterar dispositivo")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice in {"2", "3"}:
            print("A alteração também será utilizada na preparação da próxima auditoria.")
            console._configure(state, "1" if choice == "2" else "3")
            continue
        if choice != "1":
            continue
        url = str(getattr(state, "target", "") or "").strip()
        device = str(getattr(state, "device", "mobile") or "mobile").lower()
        if not url or device not in {"mobile", "desktop"}:
            print("Informe uma URL e um dispositivo válidos na preparação da auditoria.")
            input("ENTER para continuar...")
            continue
        if os.environ.get('RASAI_ARCH_PROBE_OFFLINE_CONTAINER') != '1':
            print('Diagnóstico inconclusivo: proteção de acesso à rede não configurada.')
            print('Nenhuma consulta ao site ou DNS foi realizada.')
            input('ENTER para voltar...')
            continue
        try:
            result = probe_architecture(
                url, DeviceContext(device.upper()), capture=capture_public_architecture,
            )
            for line in describe_architecture_assessment(result):
                print(line)
            print("Esta observação não modifica a seleção nem os índices da AUD.")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Não foi possível concluir a descoberta: {type(exc).__name__}")
            print("Nenhuma alteração foi feita na auditoria.")
        input("ENTER para voltar...")
