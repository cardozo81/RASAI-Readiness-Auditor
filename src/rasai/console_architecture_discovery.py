"""Read-only, standalone main-menu architectural preview."""
from __future__ import annotations

from typing import Any
import os

from rasai.architecture_probe import probe_architecture
from rasai.architecture_live_capture import capture_public_architecture
from rasai.domain import DeviceContext
from rasai.catalog_report_public_labels import public_label
from rasai.architecture_acquisition_preferences import STATIC, DYNAMIC, SKIP, read_mode, write_mode


def describe_architecture_assessment(result: Any) -> tuple[str, ...]:
    """Explain only observations supported by the captured RAW/rendered comparison."""
    lines = [
        f"Arquitetura observada: {result.architecture.value}",
        f"Versão do método: {result.method_version}",
        f"Limitação: {public_label(result.limitation) or result.limitation or 'Nenhuma identificada neste diagnóstico'}",
    ]
    comparison = result.comparison
    if comparison is None:
        lines.append("HTML RAW: " + ("obtido" if getattr(result, "raw_available", False) else "não comprovado"))
        lines.append("DOM renderizado: " + ("obtido" if getattr(result, "rendered_available", False) else "não comprovado"))
        lines.append("Evidência: comparação RAW/renderizada indisponível ou rejeitada.")
    else:
        lines.append(f"Conteúdo principal RAW: {'presente' if comparison.raw_main_content.strip() else 'ausente'}")
        lines.append(f"Conteúdo principal renderizado: {'presente' if comparison.rendered_main_content.strip() else 'ausente'}")
        lines.append(
            "Alterações observadas: "
            + (", ".join(comparison.changed_fields) if comparison.changed_fields else "nenhuma nos campos comparados")
        )
    raw = getattr(result, "raw_signals", None)
    if raw is not None:
        if raw.status == "RAW_STRUCTURAL_SIGNALS_OBSERVED":
            lines.append("Sinais observados somente no HTML RAW (sem executar JavaScript):")
            lines.append(
                "  Conteúdo substantivo em main/article: "
                + ("sim" if raw.raw_main_text_present else "não comprovado")
            )
            lines.append(
                "  Elemento H1: " + ("presente" if raw.h1_present else "não observado")
            )
            lines.append(
                "  Marcador de contêiner de aplicação: "
                + ("presente" if raw.app_root_marker_present else "não observado")
            )
            lines.append(
                "  Atributo estrutural de framework/hidratação: "
                + ("presente" if raw.framework_attribute_present else "não observado")
            )
            lines.append(
                "  Scripts em tags HTML: %s com src; %s inline."
                % (raw.external_script_tags, raw.inline_script_tags)
            )
            lines.append(
                "  Marcador de skeleton/placeholder: "
                + ("presente" if raw.hidden_placeholder_present else "não observado")
            )
            lines.append(
                "  Esses sinais não comprovam arquitetura SPA, SSR, hidratação "
                "real, conteúdo pós-JS ou indexação. Classe permanece UNKNOWN "
                "sem comparação com DOM renderizado."
            )
        else:
            lines.append(
                "Sinais estruturais RAW: N/D (HTML ausente ou orçamento excedido)."
            )
    if getattr(result, "redirect_hops_reported", None) is not None:
        hops = result.redirect_hops_reported
        lines.append(
            f"Transporte observado na captura: {hops} redirecionamento(s) HTTP."
        )
        if getattr(result, "protocol_transition", None) == "HTTP_TO_HTTPS":
            lines.append(
                "Mudança de protocolo observada: HTTP para HTTPS; "
                "a validade TLS depende da coleta segura por destino."
            )
        lines.append(
            "Origem da captura: "
            + {
                "PINNED_HTTP_STATIC": "HTTP público com transporte IP fixado",
                "ISOLATED_OCI_RENDER": "HTTP fixado e renderização isolada sem rede",
            }.get(getattr(result, "acquisition_transport", None), "N/D")
        )
        lines.append(
            "Cadeia e destino foram reportados pelo transporte da captura; "
            "o resumo não é certificação independente de domínio/certificado."
        )
    lines.append("Escopo: uma URL e um dispositivo; diagnóstico preliminar, não uma certificação.")
    return tuple(lines)


def architecture_preview_menu(console: Any, state: Any) -> None:
    while True:
        console.render_header(state)
        print("INÍCIO > DESCOBRIR ARQUITETURA")
        print("Diagnóstico preliminar. Não altera a configuração de arquitetura;")
        print("A execução da auditoria mantém sua configuração independente.")
        print(f"URL: {getattr(state, 'target', '') or '<não informada>'}")
        print(f"Dispositivo: {getattr(state, 'device', 'mobile')}")
        mode = read_mode()
        print("Modo de descoberta: " + ({STATIC: "Básica (sem Docker)", DYNAMIC: "Dinâmica (Docker isolado)", SKIP: "Não executar descoberta"}.get(mode, "Básica (sem Docker)")))
        print("1. Executar descoberta")
        print("2. Alterar URL")
        print("3. Alterar dispositivo")
        print("4. Alterar modo de descoberta")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice in {"2", "3"}:
            print("A alteração também será utilizada na preparação da próxima auditoria.")
            console._configure(state, "1" if choice == "2" else "3")
            continue
        if choice == "4":
            print("1. Básica: HTML público, sem Docker, classificação limitada")
            print("2. Dinâmica: HTML e navegador isolado, Docker necessário")
            print("3. Não executar descoberta neste momento")
            selection = input("Modo [1/2/3/V]: ").strip().upper()
            if selection in {"1", "2", "3"}:
                try:
                    write_mode({"1": STATIC, "2": DYNAMIC, "3": SKIP}[selection])
                except OSError:
                    print("Não foi possível salvar a preferência local.")
                else:
                    print("Modo salvo. Pode ser alterado novamente a qualquer momento.")
            continue
        if choice != "1":
            continue
        url = str(getattr(state, "target", "") or "").strip()
        device = str(getattr(state, "device", "mobile") or "mobile").lower()
        if not url or device not in {"mobile", "desktop"}:
            print("Informe uma URL e um dispositivo válidos na preparação da auditoria.")
            input("ENTER para continuar...")
            continue
        if mode == SKIP:
            print("Descoberta não executada por escolha do usuário.")
            print("Os demais catálogos e recursos permanecem disponíveis.")
            input("ENTER para voltar...")
            continue
        from rasai.architecture_acquisition_service import run_optional_discovery
        from rasai.architecture_static_capture import capture_static_public_architecture
        from rasai.architecture_isolated_capture import capture_isolated_public_architecture
        from rasai.runtime_prerequisites import prepare_prerequisite

        def request_consent(message: str) -> bool:
            print(message)
            return input("Autorizar? [S/N]: ").strip().upper() == "S"

        try:
            # Explicit test environment mode remains available for offline
            # validation, but all interactive choices use the canonical service.
            manual_oci = os.environ.get("RASAI_ARCH_PROBE_OFFLINE_CONTAINER") == "1"
            execution = run_optional_discovery(
                url, DeviceContext(device.upper()), mode=mode,
                consent=request_consent,
                probe=probe_architecture,
                static_capture=capture_static_public_architecture,
                dynamic_capture=(capture_public_architecture if manual_oci
                                 else capture_isolated_public_architecture),
                prepare=(lambda *_args, **_kwargs: type("Prepared", (), {"ready": True})())
                if manual_oci else prepare_prerequisite,
            )
            if not execution.executed:
                print("Descoberta indisponível ou recusada: " + str(execution.reason))
                print("Os demais catálogos continuam disponíveis.")
                if execution.reason not in {"OPTIONAL_DISCOVERY_UNAVAILABLE"}:
                    print("Nenhuma consulta ao site ou DNS foi realizada.")
                print("Nenhuma alteração foi feita na auditoria.")
            else:
                for line in describe_architecture_assessment(execution.assessment):
                    print(line)
                if mode == STATIC:
                    print("Modo básico: nenhum navegador executado; classificação dinâmica não comprovada.")
                print("Esta observação não modifica a seleção nem os índices da AUD.")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Não foi possível concluir a descoberta: {type(exc).__name__}")
            print("Nenhuma alteração foi feita na auditoria.")
        input("ENTER para voltar...")
