"""Read-only, standalone main-menu architectural preview."""
from __future__ import annotations

from typing import Any
import os

from rasai.architecture_probe import probe_architecture
from rasai.architecture_live_capture import capture_public_architecture
from rasai.domain import DeviceContext
from rasai.catalog_report_public_labels import public_label


def describe_architecture_assessment(result: Any) -> tuple[str, ...]:
    """Explain only observations supported by the captured RAW/rendered comparison."""
    lines = [
        f"Arquitetura observada: {result.architecture.value}",
        f"Versão do método: {result.method_version}",
        f"Limitação: {public_label(result.limitation) or result.limitation or 'Nenhuma identificada neste diagnóstico'}",
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
        # Shared on-demand prerequisite API: do not launch Docker at startup,
        # set OS environment variables, or require manual build commands.
        from rasai.runtime_prerequisites import (
            ARCHITECTURE_BROWSER, prepare_prerequisite,
        )
        def request_consent(message: str) -> bool:
            print(message)
            return input("Autorizar? [S/N]: ").strip().upper() == "S"

        # Keep the existing explicit opt-in working during transition; all
        # normal interactive usage uses the same prerequisite manager.
        manual_oci = os.environ.get("RASAI_ARCH_PROBE_OFFLINE_CONTAINER") == "1"
        if not manual_oci:
            prepared = prepare_prerequisite(
                ARCHITECTURE_BROWSER, consent=request_consent,
            )
            if not prepared.ready:
                messages = {
                    "DOCKER_INSTALL_REQUIRED": (
                        "Docker Desktop não está instalado. A instalação deve ser "
                        "autorizada no instalador do sistema; o restante do RASAi "
                        "continua disponível."
                    ),
                    "PREREQUISITE_DECLINED": (
                        "Preparação recusada. Apenas a descoberta dinâmica ficará "
                        "indisponível; os demais catálogos continuam disponíveis."
                    ),
                    "OCI_BUILD_SOURCE_UNAVAILABLE": (
                        "Os arquivos locais necessários ao executor não estão disponíveis."
                    ),
                    "OCI_BUILD_FAILED": (
                        "Não foi possível preparar o navegador isolado. "
                        "Os demais recursos do RASAi permanecem disponíveis."
                    ),
                }
                print(messages.get(prepared.reason, "Pré-requisito indisponível."))
                print("Nenhuma consulta ao site ou DNS foi realizada.")
                input("ENTER para voltar...")
                continue
        try:
            if manual_oci:
                capture = capture_public_architecture
            else:
                from rasai.architecture_isolated_capture import capture_isolated_public_architecture
                capture = capture_isolated_public_architecture
            result = probe_architecture(
                url, DeviceContext(device.upper()), capture=capture,
            )
            for line in describe_architecture_assessment(result):
                print(line)
            print("Esta observação não modifica a seleção nem os índices da AUD.")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Não foi possível concluir a descoberta: {type(exc).__name__}")
            print("Nenhuma alteração foi feita na auditoria.")
        input("ENTER para voltar...")
