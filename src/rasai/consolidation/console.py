"""Interactive console flow for historical/consolidated reports."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import subprocess

from .index import ConsolidationIndex
from .presentation import specialist_usage_summary
from .service import generate, normalize_filter
from .specialist import SpecialistPreview, preview_specialist


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
        print("RELATÓRIOS CONSOLIDADOS - DOMÍNIO\n")
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
        print("RELATÓRIOS CONSOLIDADOS - DISPOSITIVO\n")
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


def _choose_comparison(audits: tuple[dict, ...]) -> tuple[str, str | None, str | None] | None:
    if len(audits) < 2:
        return ("FIRST_LAST", None, None)
    while True:
        _clear()
        print("RELATÓRIOS CONSOLIDADOS - COMPARAÇÃO DE EVOLUÇÃO\n")
        print("1. Primeira × última auditoria do período [recomendado]")
        print("2. Auditoria anterior × última")
        print("3. Escolher auditoria de referência e auditoria atual manualmente")
        print("V. Voltar")
        raw = input("Escolha [1]: ").strip().upper() or "1"
        if raw == "V":
            return None
        if raw == "1":
            return ("FIRST_LAST", None, None)
        if raw == "2":
            return ("LATEST_PREVIOUS", None, None)
        if raw != "3":
            continue
        print("\nAuditorias elegíveis:")
        for pos, audit in enumerate(audits, 1):
            print(f"{pos}. {audit.get('audit_id')} | {audit.get('event_time')}")
        try:
            baseline_pos = int(input("Auditoria de referência: ").strip())
            current_pos = int(input("Auditoria atual       : ").strip())
            baseline = audits[baseline_pos - 1]
            current = audits[current_pos - 1]
        except (ValueError, IndexError):
            continue
        if baseline_pos >= current_pos:
            print("A auditoria de referência deve ser anterior à auditoria atual.")
            _pause()
            continue
        return ("MANUAL", str(baseline.get("audit_id")), str(current.get("audit_id")))


def _print_preview(preview: SpecialistPreview, selection: str) -> None:
    print("\nPRÉVIA DE CUSTO - ANÁLISE ESPECIALISTA POR IA\n")
    print(f"Comparação : {preview.baseline_audit_id or '-'} → {preview.current_audit_id or '-'}")
    print(f"Mudanças   : {preview.event_count} evento(s) elegível(is)")
    print(f"Seleção IA : {selection.upper()}")
    if not preview.available or preview.selected is None:
        print(f"Status     : indisponível ({preview.reason or 'sem candidato'})")
        return
    selected = preview.selected
    cost = f"{selected.estimated_cost:.8f} {selected.currency}" if selected.estimated_cost is not None and selected.currency else "não determinável pelo catálogo atual"
    print(f"Provedor   : {selected.provider}")
    print(f"Modelo     : {selected.model}")
    print(f"Raciocínio : {selected.reasoning_profile}")
    print(f"Tokens     : entrada≈{selected.estimated_input_tokens} | saída≈{selected.estimated_output_tokens}")
    print(f"Tarifa     : {selected.pricing_context or '-'} | {selected.pricing_version}")
    print(f"Estimativa : {cost}")
    print("Observação : estimativa pré-chamada; não é fatura e pode variar com uso real, cache, fallback e política do provedor.")
    if selection.casefold() == "auto" and len(preview.candidates) > 1:
        print("\nRanking AUTO estimado para esta necessidade:")
        for pos, item in enumerate(preview.candidates, 1):
            item_cost = f"{item.estimated_cost:.8f} {item.currency}" if item.estimated_cost is not None and item.currency else "preço não catalogado"
            print(f"  {pos}. {item.provider}/{item.model} [{item.reasoning_profile}] -> {item_cost} ({item.pricing_context or '-'})")


def _print_ai_usage(report_dir: Path, *, specialist_requested: bool) -> None:
    print("\nUSO E CUSTO DA IA NESTE CONSOLIDADO")
    print("-" * 88)
    usage = specialist_usage_summary(report_dir)
    if usage is None:
        if specialist_requested:
            print("Telemetria da análise especialista não foi materializada; consulte o manifest e specialist-analysis.json.")
        else:
            print("Análise especialista por IA não executada. Custo de IA deste consolidado: 0.")
        return
    if not usage.requested:
        print("Análise especialista por IA não solicitada/executada. Custo de IA deste consolidado: 0.")
        return
    status_label = {
        "COMPLETE": "CONCLUÍDA",
        "UNAVAILABLE": "INDISPONÍVEL",
        "NO_DATA": "SEM DADOS ELEGÍVEIS",
        "NOT_REQUESTED": "NÃO SOLICITADA",
    }.get(usage.status.upper(), usage.status.upper())
    print(f"Estado              : {status_label}")
    print(f"Tentativas de IA    : {usage.attempts} (sucesso: {usage.successes})")
    print(f"Tokens de entrada   : {usage.input_tokens:,}")
    print(f"Tokens de cache     : {usage.cached_input_tokens:,}")
    print(f"Tokens de saída     : {usage.output_tokens:,}")
    print(f"Tokens de raciocínio: {usage.reasoning_tokens:,}")
    print(f"Tokens total        : {usage.total_tokens:,}")
    if usage.costs:
        print("Custo IA estimado   : " + " | ".join(f"{currency} {amount:.8f}" for currency, amount in usage.costs))
    elif usage.attempts:
        print("Custo IA estimado   : não disponível com pricing/tokens retornados")
    else:
        print("Custo IA estimado   : 0 (nenhuma chamada de IA materializada)")
    if usage.unpriced_attempts:
        print(f"Atenção             : {usage.unpriced_attempts} tentativa(s) sem custo monetário calculável.")
    print("Observação          : custo técnico estimado pelos adaptadores; não é fatura do provedor.")


def run(
    audits_root: str | Path,
    *,
    ai_provider: str = "none",
    ai_model: str | None = None,
    ai_reasoning: str | None = None,
    ai_timeout: float = 180.0,
    ai_available: bool = False,
    ai_unavailable_reason: str | None = None,
) -> None:
    root = Path(audits_root)
    index = ConsolidationIndex(root)
    _clear()
    print("RELATÓRIOS HISTÓRICOS / CONSOLIDADOS\n")
    print("A consolidação base é somente leitura dos AUD-*/audit.db e não chama APIs.")
    print("A análise especialista por IA é opcional e, quando solicitada, exige prévia de custo e confirmação explícita.")
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
    print(f"Domínios: {len(domains)} | período disponível: {date_min or '-'} → {date_max or '-'}")
    _pause()
    if not domains:
        return

    selected_domains = _choose_domain(domains)
    if selected_domains is None:
        return

    while True:
        _clear()
        scoped_dates = index.available_dates(normalize_filter(domains=selected_domains))
        print("RELATÓRIOS CONSOLIDADOS - PERÍODO\n")
        print(f"Disponível para o domínio selecionado: {scoped_dates[0] or '-'} → {scoped_dates[1] or '-'}")
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

    partial = normalize_filter(domains=selected_domains, date_from=date_from, date_to=date_to, devices=selected_devices)
    urls = index.available_urls(partial)
    _clear()
    print("RELATÓRIOS CONSOLIDADOS - URLs\n")
    print(f"URLs disponíveis no universo filtrado: {len(urls)}")
    print("Deixe vazio para todas. Informe um trecho para consolidar apenas URLs que contenham o texto.")
    token = input("Filtro de URL/caminho: ").strip()
    selected_urls = tuple(url for url in urls if token.casefold() in url.casefold()) if token else ()
    if token and not selected_urls:
        print("Nenhuma URL corresponde ao trecho informado.")
        _pause()
        return

    base_filters = normalize_filter(
        domains=selected_domains,
        date_from=date_from,
        date_to=date_to,
        devices=selected_devices,
        urls=selected_urls,
    )
    audits = index.candidate_audits(base_filters)
    comparison = _choose_comparison(audits)
    if comparison is None:
        return
    comparison_mode, baseline_audit_id, current_audit_id = comparison

    use_ai = False
    selected_ai = str(ai_provider or "none").casefold()
    can_offer_ai = len(audits) >= 2 and selected_ai != "none" and ai_available
    if can_offer_ai:
        _clear()
        print("RELATÓRIOS CONSOLIDADOS - ANÁLISE ESPECIALISTA\n")
        print(f"IA ativa no console: {selected_ai.upper()}")
        print("A análise por IA interpreta mudanças já calculadas pelo RASAi e recomenda ações por SEO, GEO, Desempenho, Infraestrutura, Segurança, Acessibilidade, Conteúdo e UX.")
        print("Ela é orientativa, não altera pontuação e não modifica SARI/SCORE-GEO.")
        use_ai = input("Incluir análise especialista por IA? [s/N]: ").strip().casefold() == "s"
    elif selected_ai != "none" and not ai_available:
        print(f"\nIA selecionada, porém indisponível: {ai_unavailable_reason or 'configuração não apta'}")
        print("O relatório será gerado sem a análise especialista por IA.")
        _pause()
    elif selected_ai != "none" and len(audits) < 2:
        print("\nIA está ativa no console, mas a análise especialista do consolidado exige pelo menos duas auditorias elegíveis.")
        print("Com apenas uma auditoria não existe par de evolução; nenhuma chamada de IA será feita e o custo de IA deste CONS será 0.")
        _pause()

    filters = normalize_filter(
        domains=selected_domains,
        date_from=date_from,
        date_to=date_to,
        devices=selected_devices,
        urls=selected_urls,
        comparison_mode=comparison_mode,
        baseline_audit_id=baseline_audit_id,
        current_audit_id=current_audit_id,
        specialist_ai=use_ai,
        ai_provider=selected_ai if use_ai else None,
        ai_model=ai_model if use_ai else None,
        ai_reasoning=ai_reasoning if use_ai else None,
        ai_timeout_seconds=ai_timeout if use_ai else None,
    )

    if use_ai:
        preview = preview_specialist(root, filters)
        _clear()
        _print_preview(preview, selected_ai)
        if not preview.available:
            print("\nA análise por IA não pode ser executada com segurança; o consolidado seguirá sem IA.")
            _pause()
            use_ai = False
        elif input("\nConfirmar custo estimado e autorizar chamada externa de IA? [s/N]: ").strip().casefold() != "s":
            use_ai = False
        if not use_ai:
            filters = normalize_filter(
                domains=selected_domains,
                date_from=date_from,
                date_to=date_to,
                devices=selected_devices,
                urls=selected_urls,
                comparison_mode=comparison_mode,
                baseline_audit_id=baseline_audit_id,
                current_audit_id=current_audit_id,
            )

    _clear()
    print("RELATÓRIOS CONSOLIDADOS - CONFIRMAÇÃO\n")
    print(f"Domínios : {', '.join(filters.domains) or 'todos'}")
    print(f"Período  : {filters.date_from or 'início'} → {filters.date_to or 'fim'}")
    print(f"Dispositivos: {', '.join(filters.devices) or 'todos (separados)'}")
    print(f"URLs     : {len(filters.urls) if filters.urls else 'todas'}")
    print(f"Evolução : {filters.comparison_mode}")
    print(f"IA       : {filters.ai_provider.upper() if filters.specialist_ai and filters.ai_provider else 'não'}")
    if filters.specialist_ai:
        print("\nA consolidação dos AUDs continua local/somente leitura; somente a seção especialista realizará a chamada de IA já autorizada.")
    else:
        print("\nO processo é local/somente leitura e utiliza somente dados já persistidos.")
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
    print(f"Resultado : {'REUTILIZADO (filtros + fontes + análise idênticos)' if result.reused else 'NOVO SNAPSHOT'}")
    _print_ai_usage(result.report_dir, specialist_requested=filters.specialist_ai)
    print("\nA. Abrir relatório")
    print("P. Abrir pasta")
    print("V. Voltar")
    action = input("Escolha: ").strip().upper()
    if action == "A":
        _open(result.report_path)
    elif action == "P":
        _open(result.report_dir)
