"""Interactive console flow for offline historical/consolidated reports."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import subprocess

from .index import ConsolidationIndex
from .service import generate, normalize_filter


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _pause() -> None:
    input("\nENTER para continuar...")


def _open(path: Path) -> tuple[bool, str]:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.name == "posix":
            command = ["open", str(path)] if os.uname().sysname == "Darwin" else ["xdg-open", str(path)]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return False, str(path)
        return True, str(path)
    except OSError as exc:
        return False, f"{path}: {exc}"


def _parse_date(raw: str) -> date | None:
    value = raw.strip()
    if not value:
        return None
    return date.fromisoformat(value)


def _choose_domain(domains: tuple[str, ...]) -> tuple[str, ...] | None:
    while True:
        _clear()
        print("RELATÓRIOS CONSOLIDADOS — DOMÍNIO\n")
        print("0. Todos os domínios")
        for index, domain in enumerate(domains, 1):
            print(f"{index}. {domain}")
        print("V. Voltar")
        raw = input("Escolha: ").strip()
        if raw.upper() == "V":
            return None
        if raw == "0":
            return ()
        try:
            return (domains[int(raw) - 1],)
        except (ValueError, IndexError):
            continue


def _choose_devices(devices: tuple[str, ...]) -> tuple[str, ...] | None:
    while True:
        _clear()
        print("RELATÓRIOS CONSOLIDADOS — DISPOSITIVO\n")
        print("0. Todos, preservando séries separadas")
        for index, device in enumerate(devices, 1):
            print(f"{index}. {device}")
        print("V. Voltar")
        raw = input("Escolha: ").strip()
        if raw.upper() == "V":
            return None
        if raw == "0":
            return ()
        try:
            return (devices[int(raw) - 1],)
        except (ValueError, IndexError):
            continue


def run(audits_root: str | Path) -> None:
    root = Path(audits_root)
    index = ConsolidationIndex(root)
    _clear()
    print("RELATÓRIOS HISTÓRICOS / CONSOLIDADOS\n")
    print("Somente leitura dos AUD-*/audit.db. Nenhuma API é chamada e nenhuma auditoria é alterada.")
    print("Atualizando índice analítico reconstruível...")
    try:
        refresh = index.refresh()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nNão foi possível preparar o índice: {type(exc).__name__}: {exc}")
        _pause()
        return
    domains = index.available_domains()
    date_min, date_max = index.available_dates()
    print(f"AUDs encontrados: {refresh.discovered} | indexados agora: {refresh.indexed} | reutilizados: {refresh.reused} | removidos: {refresh.removed}")
    if refresh.issues:
        print(f"Atenção: {len(refresh.issues)} AUD(s) foram ignorados por problema de leitura/indexação.")
    print(f"Domínios: {len(domains)} | período disponível: {date_min or '—'} → {date_max or '—'}")
    _pause()
    if not domains:
        return

    selected_domains = _choose_domain(domains)
    if selected_domains is None:
        return

    while True:
        _clear()
        scoped_dates = index.available_dates(normalize_filter(domains=selected_domains))
        print("RELATÓRIOS CONSOLIDADOS — PERÍODO\n")
        print(f"Disponível para o domínio selecionado: {scoped_dates[0] or '—'} → {scoped_dates[1] or '—'}")
        print("Use AAAA-MM-DD. Vazio = sem limite.")
        try:
            date_from = _parse_date(input("Data inicial: "))
            date_to = _parse_date(input("Data final  : "))
            partial = normalize_filter(domains=selected_domains, date_from=date_from, date_to=date_to)
            break
        except ValueError as exc:
            print(f"Filtro inválido: {exc}")
            _pause()

    devices = index.available_devices(partial)
    selected_devices = _choose_devices(devices) if devices else ()
    if selected_devices is None:
        return

    partial = normalize_filter(
        domains=selected_domains,
        date_from=date_from,
        date_to=date_to,
        devices=selected_devices,
    )
    urls = index.available_urls(partial)
    _clear()
    print("RELATÓRIOS CONSOLIDADOS — URLs\n")
    print(f"URLs disponíveis no universo filtrado: {len(urls)}")
    print("Deixe vazio para todas. Informe um trecho para consolidar apenas URLs que contenham o texto.")
    token = input("Filtro de URL/caminho: ").strip()
    selected_urls = tuple(url for url in urls if token.casefold() in url.casefold()) if token else ()
    if token and not selected_urls:
        print("Nenhuma URL corresponde ao trecho informado.")
        _pause()
        return

    filters = normalize_filter(
        domains=selected_domains,
        date_from=date_from,
        date_to=date_to,
        devices=selected_devices,
        urls=selected_urls,
    )
    _clear()
    print("RELATÓRIOS CONSOLIDADOS — CONFIRMAÇÃO\n")
    print(f"Domínios : {', '.join(filters.domains) or 'todos'}")
    print(f"Período  : {filters.date_from or 'início'} → {filters.date_to or 'fim'}")
    print(f"Devices  : {', '.join(filters.devices) or 'todos (separados)'}")
    print(f"URLs     : {len(filters.urls) if filters.urls else 'todas'}")
    print("\nO processo é offline e utiliza somente dados já persistidos.")
    if input("Gerar relatório? [s/N]: ").strip().casefold() != "s":
        return

    try:
        result = generate(root, filters, refresh_index=False)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nFalha na consolidação: {type(exc).__name__}: {exc}")
        _pause()
        return

    _clear()
    print("RELATÓRIO CONSOLIDADO CONCLUÍDO\n")
    print(f"Relatório : {result.report_path}")
    print(f"Manifesto : {result.manifest_path}")
    print(f"Resultado : {'REUTILIZADO (filtros + fontes idênticos)' if result.reused else 'NOVO SNAPSHOT'}")
    print("\nA. Abrir relatório")
    print("P. Abrir pasta")
    print("V. Voltar")
    action = input("Escolha: ").strip().upper()
    if action == "A":
        _open(result.report_path)
    elif action == "P":
        _open(result.report_dir)
