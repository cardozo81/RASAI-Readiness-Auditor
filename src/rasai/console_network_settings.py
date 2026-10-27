"""#666 - contextual network controls using the canonical console registry.

This is a console-only editor: no DNS, sockets, probes or catalog mutations.
Consent is scoped to the current audit URL's exact public hostname.
"""
from __future__ import annotations

import os
from typing import Any

from rasai.network_active_policy import (
    authorized_hostname, hostname_from_audit_url, max_hops,
    validate_network_setting,
)

_ENABLED = "RASAI_NETWORK_ACTIVE_ENABLED"
_HOST = "RASAI_NETWORK_ACTIVE_HOST"
_FIELDS = (
    "RASAI_NETWORK_MAX_HOPS",
    "RASAI_NETWORK_GEOIP_SOURCE",
    "RASAI_GEOIP_ACQUIRE_TOOLS",
)


def _target_host(state: Any) -> str | None:
    try:
        return hostname_from_audit_url(getattr(state, "target", ""))
    except (TypeError, ValueError):
        return None


def _status(state: Any) -> tuple[str, str | None]:
    target = _target_host(state)
    approved = authorized_hostname()
    if target is None:
        return "ALVO INVÁLIDO OU AUSENTE — nenhuma sonda autorizável", None
    if approved is None:
        return "DESABILITADA (sem autorização ativa para este alvo)", target
    if approved != target:
        return "NÃO AUTORIZADA PARA ESTA URL (permissão anterior não transferida)", target
    return "AUTORIZADA SOMENTE PARA O HOST EXATO", target


def _apply_consent(console: Any, state: Any, *, host: str | None) -> bool:
    """One explicit, reversible user choice; never silently rebind another host."""
    from rasai.console_ui_catalog import _destination
    from rasai.console_session import is_dirty, mark_dirty

    destination = _destination(False)
    if destination == "V":
        return False
    prior = {key: os.environ.get(key) for key in (_HOST, _ENABLED)}
    was_dirty = is_dirty(state)
    try:
        if host is None:
            os.environ.pop(_HOST, None)
            os.environ[_ENABLED] = "false"
        else:
            os.environ[_HOST] = validate_network_setting(_HOST, host)
            os.environ[_ENABLED] = validate_network_setting(_ENABLED, "true")
        mark_dirty(state)
        if destination == "2" and not console._save_configuration(state):
            raise ValueError("Não foi possível persistir a autorização; alteração cancelada")
    except (OSError, ValueError, TypeError):
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        mark_dirty(state, was_dirty)
        state.error = "A configuração de rede não foi aplicada ou persistida."
        return False
    state.error = ""
    return True


def network_settings_menu(console: Any, state: Any) -> None:
    """Show audit-target-derived scope and reuse existing variable editors."""
    from rasai import console_provider_environment as env
    from rasai.console_configuration_presentation import variable_editor

    while True:
        console.render_header(state)
        status, target = _status(state)
        print("INÍCIO > PREPARAR AUDITORIA > REDE E CONECTIVIDADE\n")
        print("URL da auditoria:", getattr(state, "target", "") or "<não informada>")
        print("Hostname derivado:", target or "<não utilizável>")
        print("Sonda ativa:", status)
        print("Limite de hops:", max_hops(), "(máximo: 16)")
        print("GeoIP:", os.environ.get("RASAI_NETWORK_GEOIP_SOURCE", "LOCAL_FIRST"))
        print("Aquisição do utilitário MaxMind:", os.environ.get("RASAI_GEOIP_ACQUIRE_TOOLS", "false"))
        print("\nO hostname é extraído da URL: HTTPS, caminhos e parâmetros não são copiados.")
        print("A captura passiva não depende da autorização. Sonda ativa: destino exato,")
        print("porta 443, sem autorizar redirecionamentos ou outros domínios.")
        print("\n1. Autorizar a medição ativa para o hostname desta URL")
        print("2. Revogar a autorização de sondagem ativa")
        print("3. Configurar limite de hops")
        print("4. Configurar fonte GeoIP local")
        print("5. Configurar aquisição autorizada do utilitário MaxMind")
        print("V. Voltar (sem modificar configuração)")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice == "1":
            if target is None:
                state.error = "Informe uma URL pública HTTP(S) válida antes de autorizar a sonda."
                continue
            if authorized_hostname() == target:
                state.error = "Sonda já autorizada para o hostname desta URL."
                continue
            print(f"\nAutorizar sondagem de rede para {target}:443?")
            print("Esta medição complementar gera tráfego ICMP/TCP depois da nova AUD.")
            print("A autorização NÃO se transfere quando o domínio auditado muda.")
            if input("Confirma autorização [s/N]: ").strip().upper() != "S":
                continue
            _apply_consent(console, state, host=target)
            continue
        if choice == "2":
            if authorized_hostname() is None and not os.environ.get(_HOST):
                state.error = "Sonda já desabilitada nesta sessão."
                continue
            _apply_consent(console, state, host=None)
            continue
        if choice in {"3", "4", "5"}:
            env.refresh_specs()
            name = _FIELDS[int(choice) - 3]
            spec = env.SPEC_BY_NAME.get(name)
            if spec is None:
                state.error = "Configuração canônica de rede indisponível."
                continue
            variable_editor(console, state, spec)
            continue
        state.error = "Opção inválida em Rede e conectividade."
