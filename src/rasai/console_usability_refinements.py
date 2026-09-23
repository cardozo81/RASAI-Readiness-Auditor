"""Final console usability refinements for configuration and AUD history.

Presentation-only refinements:
- compact stable configuration IDs;
- guided closed-domain choices with short PT-BR explanations and confirmation;
- friendly audit status labels and local completion timestamps;
- no reprocess action for already-complete AUDs;
- aligned history and safe-deletion inventory tables.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from zoneinfo import ZoneInfo

from rasai.console_confirmation_contract import confirm_continue
from rasai.console_ui import DIM, GREEN, paint
from rasai.configuration_value_labels import configuration_value_choice

_CONFIGURATION_ID_MODULUS = 1_000_000

_PROCESSING_LABELS = {
    "PROCESSING": "Em processamento",
    "PARTIAL_RETRYABLE": "Parcial — pode reprocessar",
    "PARTIAL_BLOCKED": "Parcial — há bloqueios",
    "COMPLETE": "Concluída",
    "FAILED_FATAL": "Falha definitiva",
    "EXPIRED_FOR_COMPLETION": "Expirada para conclusão",
    "RUNNING": "Em execução",
    "IN_PROGRESS": "Em execução",
    "STARTED": "Iniciada",
    "COMPLETED": "Concluída",
    "SUCCESS": "Concluída",
    "FAILED": "Falha",
    "ERROR": "Erro",
    "UNKNOWN": "Estado desconhecido",
}
_SCORE_LABELS = {
    "PENDING": "Pendente",
    "FINAL": "Final",
    "UNAVAILABLE": "Indisponível",
}
_WORK_ITEM_LABELS = {
    "PENDING": "Pendente",
    "RUNNING": "Em andamento",
    "WAITING_FOR_DATA": "Aguardando dados",
    "SUCCESS": "Concluído",
    "FAILED_RETRYABLE": "Falha temporária — nova tentativa possível",
    "FAILED_PERMANENT": "Falha definitiva",
    "BLOCKED": "Bloqueado",
    "NOT_APPLICABLE": "Não aplicável",
    "DISABLED": "Desabilitado",
}

_VALUE_DESCRIPTIONS = {
    "RASAI_CONTENT_RISK_PROFILE": {
        "auto": "Infere o perfil de risco a partir do conteúdo e do contexto disponível.",
        "standard": "Trata o conteúdo como risco editorial padrão, sem regras YMYL reforçadas.",
        "ymyl": "Aplica avaliação reforçada para conteúdo que pode afetar saúde, finanças, segurança ou bem-estar.",
    },
    "RASAI_YMYL_CATEGORY": {
        "auto": "A categoria é inferida automaticamente quando houver evidência suficiente.",
        "none": "Declara que a página não pertence a uma categoria YMYL relevante.",
        "health-safety": "Saúde ou segurança física; exige maior rigor de evidência e confiança.",
        "financial-security": "Finanças ou segurança econômica; exige maior rigor de evidência e confiança.",
        "civic-societal": "Cidadania, governo ou temas sociais com impacto relevante.",
        "other-significant-welfare": "Outro tema capaz de afetar significativamente o bem-estar das pessoas.",
    },
    "RASAI_PAGE_PURPOSE": {
        "auto": "Infere a finalidade principal da página.",
        "informational": "Conteúdo criado principalmente para informar ou explicar.",
        "transactional": "Página orientada a concluir uma ação ou transação.",
        "product-service": "Apresenta, vende ou descreve um produto ou serviço.",
        "review-comparison": "Avalia ou compara produtos, serviços ou alternativas.",
        "news-editorial": "Conteúdo jornalístico, noticioso ou editorial.",
        "support-documentation": "Ajuda, documentação técnica ou suporte operacional.",
        "forum-ugc": "Fórum, comunidade ou conteúdo gerado por usuários.",
        "other": "Finalidade diferente das categorias anteriores.",
    },
    "RASAI_INTENDED_AUDIENCE": {
        "auto": "Infere o público esperado.",
        "general": "Conteúdo destinado ao público geral.",
        "professional": "Conteúdo destinado principalmente a profissionais ou especialistas.",
        "mixed": "Conteúdo destinado a público geral e profissional.",
    },
    "RASAI_EXPERIENCE_REQUIREMENT": {
        "auto": "Infere se experiência prática é necessária para avaliar o conteúdo.",
        "required": "Experiência em primeira mão é requisito relevante para a qualidade esperada.",
        "beneficial": "Experiência prática melhora a avaliação, mas não é estritamente obrigatória.",
        "not-expected": "Experiência em primeira mão não é normalmente esperada.",
    },
    "RASAI_FRESHNESS_SENSITIVITY": {
        "auto": "Infere o quanto a atualidade do conteúdo importa.",
        "low": "Mudanças temporais tendem a ter pouco impacto.",
        "medium": "Atualização periódica pode afetar a qualidade ou validade.",
        "high": "Conteúdo desatualizado pode comprometer significativamente a utilidade.",
    },
    "RASAI_CONTENT_ORIGIN": {
        "auto": "Infere a origem editorial predominante.",
        "first-party": "Conteúdo produzido pela própria organização ou responsável pelo site.",
        "third-party": "Conteúdo produzido principalmente por terceiros.",
        "user-generated": "Conteúdo produzido predominantemente por usuários.",
        "mixed": "Combina conteúdo próprio, de terceiros e/ou de usuários.",
    },
    "RASAI_CONSOLE_MODE": {
        "local": "Executa o console e as auditorias neste ambiente local.",
        "remote": "Usa o console como cliente de um control plane remoto.",
    },
    "RASAI_DEVICE_CONTEXT": {
        "mobile": "Usa contexto mobile como padrão.",
        "desktop": "Usa contexto desktop como padrão.",
        "both": "Executa ambos os contextos; aumenta tempo e volume de coleta.",
    },
    "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": {
        "auto": "Escolhe automaticamente a fonte de dados de campo disponível.",
        "pagespeed": "Usa os dados de campo retornados via PageSpeed quando disponíveis.",
        "crux": "Prioriza consulta direta ao Chrome UX Report; requer credencial quando aplicável.",
        "none": "Não coleta dados de campo; mantém apenas sinais sintéticos/laboratoriais.",
    },
    "RASAI_PLATFORM_DB_BACKEND": {
        "sqlite": "Usa SQLite local, adequado ao modo local e ambientes simples.",
        "postgresql": "Usa PostgreSQL, indicado para control plane centralizado e concorrente.",
    },
    "RASAI_API_AUTH_MODE": {
        "deny": "Nega acesso autenticado à API até que outro modo seja configurado.",
        "trusted-header": "Confia em um cabeçalho de identidade fornecido por proxy confiável.",
        "oidc": "Usa autenticação OpenID Connect.",
    },
}

_COMMON_VALUE_DESCRIPTIONS = {
    "true": "Habilita este comportamento.",
    "false": "Desabilita este comportamento.",
    "auto": "Delega a escolha ao runtime conforme configuração e evidências disponíveis.",
    "none": "Não aplica esta opção.",
    "mobile": "Usa o contexto de dispositivo móvel.",
    "desktop": "Usa o contexto de computador.",
    "both": "Inclui os dois contextos.",
    "low": "Nível baixo.",
    "medium": "Nível intermediário.",
    "high": "Nível alto.",
    "minimal": "Usa o menor nível suportado.",
    "standard": "Usa o comportamento padrão.",
    "live": "Executa contra a fonte/serviço real.",
    "fixture": "Usa dados locais de teste em vez da fonte real.",
    "disabled": "Mantém este recurso desabilitado.",
    "performance": "Mede desempenho e métricas de carregamento.",
    "accessibility": "Avalia acessibilidade segundo as verificações disponíveis.",
    "best-practices": "Avalia boas práticas técnicas do navegador.",
    "seo": "Avalia verificações técnicas de SEO do Lighthouse.",
    "agentic-browsing": "Solicita a categoria experimental de Agentic Browsing quando suportada.",
    "CRITICAL": "Registra apenas eventos críticos.",
    "ERROR": "Registra erros e eventos críticos.",
    "WARNING": "Registra avisos, erros e eventos críticos.",
    "INFO": "Nível operacional recomendado para uso normal.",
    "DEBUG": "Registra detalhes adicionais para diagnóstico; aumenta o volume de log.",
    "RS256": "OIDC com RSA e SHA-256.",
    "RS384": "OIDC com RSA e SHA-384.",
    "RS512": "OIDC com RSA e SHA-512.",
    "ES256": "OIDC com ECDSA e SHA-256.",
    "ES384": "OIDC com ECDSA e SHA-384.",
    "ES512": "OIDC com ECDSA e SHA-512.",
}


def configuration_id(name: str) -> str:
    """Return a compact, stable six-digit ID for a canonical configuration key.

    Four digits were intentionally avoided: with a growing configuration catalog the
    collision probability is too high for an identifier the operator is expected to
    learn and reuse. Six digits materially reduce visual noise while preserving a much
    safer namespace.
    """
    key = str(name).strip().upper().encode("utf-8")
    digest = hashlib.blake2s(key, digest_size=4, person=b"RASAI-CF").digest()
    return f"{int.from_bytes(digest, 'big') % _CONFIGURATION_ID_MODULUS:06d}"


def value_description(spec: Any, value: str) -> str:
    """Return one short PT-BR explanation for a closed-domain value."""
    token = str(value)
    by_name = _VALUE_DESCRIPTIONS.get(str(spec.name), {})
    if token in by_name:
        return by_name[token]
    if token in _COMMON_VALUE_DESCRIPTIONS:
        return _COMMON_VALUE_DESCRIPTIONS[token]

    name = str(spec.name).upper()
    lowered = token.casefold()
    if name.endswith("_MODEL") or "_MODEL_" in name:
        return "Seleciona este modelo no provider correspondente."
    if name.endswith("_PROVIDER") or "_PROVIDER_" in name:
        if lowered == "auto":
            return "Permite ao runtime escolher entre os providers elegíveis configurados."
        if lowered == "none":
            return "Não usa provider para esta finalidade."
        return f"Seleciona o provider {token} para esta finalidade."
    if "REASONING" in name:
        return {
            "none": "Não solicita esforço adicional de reasoning.",
            "low": "Solicita baixo esforço de reasoning, priorizando custo e latência.",
            "medium": "Equilibra reasoning, custo e latência.",
            "high": "Prioriza maior esforço de reasoning, com potencial aumento de custo/latência.",
        }.get(lowered, "Seleciona este nível de reasoning quando suportado pelo modelo.")
    if "DEVICE" in name:
        return _COMMON_VALUE_DESCRIPTIONS.get(lowered, "Seleciona este perfil de dispositivo.")
    if "MODE" in name:
        return f"Seleciona o modo operacional '{token}' para este recurso."
    if "SOURCE" in name:
        return f"Usa '{token}' como fonte ou política de origem para este recurso."
    if "CATEGORY" in name or "CATEGORIES" in name:
        return f"Inclui a categoria técnica '{token}'."
    if "SCOPE" in name:
        return f"Inclui o escopo técnico '{token}'."
    purpose = str(getattr(spec, "purpose", "") or "").strip().rstrip(".")
    if purpose:
        return f"Valor permitido para: {purpose.lower()}."
    return "Valor técnico permitido pelo contrato atual do runtime."


def _confirm_choice(
    selected: str,
    description: str,
    input_fn: Callable[[str], str],
) -> str | None:
    print(f"\nSelecionado: {selected}")
    if description:
        print(paint(f"             {description}", DIM))
    if confirm_continue(
        "Confirmar seleção",
        back_label="Voltar sem alterar",
        input_fn=input_fn,
    ):
        return selected
    return None


def _single_choice(spec: Any, input_fn: Callable[[str], str]) -> str | None:
    current = (os.environ.get(spec.name) or "").strip()
    print("\nValores válidos:")
    for index, item in enumerate(spec.accepted, 1):
        markers: list[str] = []
        if item == current:
            markers.append("atual")
        if item == spec.default:
            markers.append("default")
        label = configuration_value_choice(spec.name, item)
        if str(spec.value_type).casefold() == "booleano":
            label = paint(label, GREEN if item == "true" else DIM, bold=item == "true")
        suffix = f" [{' / '.join(markers)}]" if markers else ""
        print(f" {index}. {label}{suffix}")
        print(paint(f"    {value_description(spec, item)}", DIM))
    print(" V. Voltar")
    raw = input_fn("Escolha: ").strip()
    if raw.upper() == "V":
        return None
    if raw in spec.accepted:
        selected = raw
    else:
        try:
            selected = spec.accepted[int(raw) - 1]
        except (ValueError, IndexError) as exc:
            raise ValueError("opção inválida; selecione um dos valores apresentados") from exc
    return _confirm_choice(selected, value_description(spec, selected), input_fn)


def _multi_choice(spec: Any, input_fn: Callable[[str], str]) -> str | None:
    current_raw = (os.environ.get(spec.name) or spec.default or "").strip()
    current = {item.strip() for item in current_raw.split(",") if item.strip()}
    print("\nValores válidos (seleção múltipla):")
    for index, item in enumerate(spec.accepted, 1):
        marker = " [selecionado]" if item in current else ""
        print(f" {index}. {configuration_value_choice(spec.name, item)}{marker}")
        print(paint(f"    {value_description(spec, item)}", DIM))
    print(" Digite números ou valores separados por vírgula; 'todos' seleciona todos; V volta.")
    raw = input_fn("Escolha: ").strip()
    if raw.upper() == "V":
        return None
    if raw.casefold() in {"todos", "all", "*"}:
        selected = list(spec.accepted)
    else:
        tokens = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
        if not tokens:
            raise ValueError("selecione ao menos um valor")
        selected = []
        for token in tokens:
            if token in spec.accepted:
                value = token
            else:
                try:
                    value = spec.accepted[int(token) - 1]
                except (ValueError, IndexError) as exc:
                    raise ValueError(f"opção inválida: {token}") from exc
            if value not in selected:
                selected.append(value)
    joined = ",".join(selected)
    print("\nSelecionados:")
    for value in selected:
        print(
            f" - {configuration_value_choice(spec.name, value)}  "
            f"{paint(value_description(spec, value), DIM)}"
        )
    if confirm_continue(
        "Confirmar seleção",
        back_label="Voltar sem alterar",
        input_fn=input_fn,
    ):
        return joined
    return None


def _friendly_status(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    return _PROCESSING_LABELS.get(raw.upper(), raw.replace("_", " ").strip().capitalize())


def _friendly_score(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    return _SCORE_LABELS.get(raw.upper(), raw.replace("_", " ").strip().capitalize())


def _friendly_work_item(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    return _WORK_ITEM_LABELS.get(raw.upper(), raw.replace("_", " ").strip().capitalize())


def _local_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    try:
        from rasai.time_contract import configured_presentation_timezone, parse_timestamp

        timezone_name = configured_presentation_timezone()
        instant = parse_timestamp(value).astimezone(ZoneInfo(timezone_name))
        return instant.strftime("%d/%m/%Y %H:%M")
    except (ImportError, OSError, ValueError):
        return "-"


def _safe_summary(audit_root: Path, audit_id: str) -> dict[str, Any]:
    try:
        from rasai.audit_fulfillment import read_summary
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(audit_root)
        summary = read_summary(workspace, audit_id)
        if summary is None:
            return {}
        return {
            "processing_status": summary.processing_status,
            "score_status": summary.score_status,
            "report_status": summary.report_status,
            "consolidation_eligible": summary.consolidation_eligible,
            "required_items": summary.required_items,
            "successful_items": summary.successful_items,
            "pending_items": summary.pending_items,
            "blocked_items": summary.blocked_items,
            "expired_items": summary.expired_items,
            "reprocess_count": summary.reprocess_count,
            "last_reprocess_id": summary.last_reprocess_id,
            "completed_at": summary.completed_at,
        }
    except (OSError, ValueError, RuntimeError):
        return {}


def _can_reprocess(summary: dict[str, Any]) -> bool:
    status = str(summary.get("processing_status") or "").upper()
    if status not in {"PARTIAL_RETRYABLE", "PARTIAL_BLOCKED"}:
        return False
    return (
        int(summary.get("pending_items") or 0)
        + int(summary.get("blocked_items") or 0)
        + int(summary.get("expired_items") or 0)
    ) > 0


def _reprocess_label(summary: dict[str, Any]) -> str:
    status = str(summary.get("processing_status") or "").upper()
    if status == "COMPLETE":
        return "Não necessário"
    if _can_reprocess(summary):
        return "Disponível"
    if status in {"PROCESSING", "RUNNING", "IN_PROGRESS", "STARTED"}:
        return "Aguardar"
    if status == "EXPIRED_FOR_COMPLETION":
        return "Criar novo AUD"
    return "Indisponível"


def _history_row(index: int, audit_root: Path, audit_width: int) -> None:
    audit_id = audit_root.name
    summary = _safe_summary(audit_root, audit_id)
    status = _friendly_status(summary.get("processing_status") or "STATUS NÃO PROJETADO")
    completed = _local_timestamp(summary.get("completed_at")) if str(summary.get("processing_status") or "").upper() == "COMPLETE" else "-"
    reprocess = _reprocess_label(summary)
    print(f"{index:>2}. {audit_id:<{audit_width}}  {completed:<16}  {status:<29}  {reprocess}")


def _choose_audit_factory(console_module: ModuleType):
    def choose_audit(state: Any) -> str | None:
        from rasai import audit_management_console as management
        from rasai import console_navigation as navigation

        while True:
            audits = navigation._audit_directories(state.audits_root)
            print("\nAUDITORIAS / HISTÓRICO")
            print(f"Raiz: {state.audits_root}")
            if audits:
                recent = audits[:20]
                audit_width = max(36, min(44, max(len(item.name) for item in recent)))
                print("\nRecentes:")
                print(f"{'Nº':>3} {'AUDITORIA':<{audit_width}}  {'CONCLUSÃO LOCAL':<16}  {'SITUAÇÃO':<29}  REPROCESSAMENTO")
                print(f"{'---':>3} {'-' * audit_width}  {'-' * 16}  {'-' * 29}  {'-' * 16}")
                for index, audit_root in enumerate(recent, 1):
                    _history_row(index, audit_root, audit_width)
            else:
                print("\nNenhum AUD com audit.db encontrado nesta raiz.")
            print("\nB. Buscar por Audit ID")
            print("G. Gerenciar / excluir auditorias")
            print("V. Voltar")
            raw = input("Escolha: ").strip().upper()
            if raw == "V":
                return None
            if raw == "G":
                management._management_menu(console_module, state)
                console_module.render_header(state)
                continue
            if raw == "B":
                audit_id = input("Audit ID (AUD-*) [V=voltar]: ").strip().upper()
                if audit_id == "V":
                    state.error = ""
                    continue
                candidate = Path(state.audits_root) / audit_id
                if audit_id.startswith("AUD-") and (candidate / "audit.db").is_file():
                    return audit_id
                state.error = f"AUD não encontrado em {state.audits_root}: {audit_id or '<vazio>'}"
                continue
            try:
                selected = int(raw) - 1
            except ValueError:
                state.error = "opção de auditoria inválida"
                continue
            if 0 <= selected < min(len(audits), 20):
                return audits[selected].name
            state.error = "opção de auditoria inválida"

    return choose_audit


def _reprocess_selected(console_module: ModuleType, state: Any, audit_id: str) -> None:
    from rasai import console_navigation as navigation
    from rasai.audit_reprocess import reprocess_audit

    audit_root = Path(state.audits_root) / audit_id
    summary = _safe_summary(audit_root, audit_id)
    if summary and not _can_reprocess(summary):
        state.operation = "LOCAL:AUD_REPROCESS_SKIPPED"
        if str(summary.get("processing_status") or "").upper() == "COMPLETE":
            state.error = "Auditoria já concluída; não existem pendências que justifiquem reprocessamento."
        else:
            state.error = "O estado atual desta auditoria não permite reprocessamento seletivo."
        return

    pending, successes = navigation._work_item_preview(state, audit_id)
    console_module.render_header(state)
    print("REPROCESSAMENTO SELETIVO\n")
    print(f"AUD: {audit_id}")
    if pending or successes:
        print(f"Pendentes/bloqueados : {len(pending)}")
        print(f"Sucessos preservados : {len(successes)}")
        if pending:
            print("\nItens que ainda precisam de resolução:")
            for item in pending[:30]:
                print(f"- {item.component}/{item.scope_key}: {_friendly_work_item(item.status)}")
    else:
        print("O estado será reavaliado pelo motor de reprocessamento antes de qualquer nova tentativa.")
    print("\nItens já bem-sucedidos não são repetidos por padrão.")
    print("Chamadas externas/IA só ocorrem quando o requisito correspondente realmente precisar ser recuperado.")
    if not confirm_continue(
        "Confirmar e iniciar reprocessamento",
        back_label="Voltar sem reprocessar",
    ):
        state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
        state.error = "reprocessamento cancelado"
        return

    try:
        result = reprocess_audit(audit_id, audits_root=state.audits_root, source="CONSOLE")
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        state.status = "REPROCESS_FAILED"
        state.operation = "LOCAL:AUD_REPROCESS"
        state.error = f"{type(exc).__name__}: {exc}"
        return

    state.audit_id = audit_id
    state.status = result.processing_status
    state.operation = "LOCAL:AUD_REPROCESS"
    state.error = ""
    console_module.render_header(state)
    print("REPROCESSAMENTO CONCLUÍDO\n")
    print(f"AUD                  : {result.audit_id}")
    print(f"RPR                  : {result.reprocess_id or '<nenhum; sem trabalho pendente>'}")
    print(f"Situação             : {_friendly_status(result.processing_status)}")
    print(f"Score                : {_friendly_score(result.score_status)}")
    print(f"Consolidação elegível: {'SIM' if result.consolidation_eligible else 'NÃO'}")
    print(f"Itens tentados       : {result.attempted_items}")
    print(f"Itens resolvidos     : {result.successful_items}")
    print(f"Sucessos preservados : {result.skipped_success_items}")
    print(f"Itens restantes      : {result.remaining_items}")
    if result.temporal_expired_items:
        print(f"Itens expirados      : {result.temporal_expired_items}")
    input("\nENTER para continuar...")


def _selected_audit_menu(console_module: ModuleType, state: Any, audit_id: str) -> bool:
    from rasai import console_navigation as navigation
    from rasai.console_artifacts import open_external_path, report_entrypoint

    while True:
        audit_root = Path(state.audits_root) / audit_id
        summary = _safe_summary(audit_root, audit_id)
        reuse_available, reuse_detail = navigation._configuration_reuse_status(state, audit_id)
        report_path = report_entrypoint(audit_root)
        console_module.render_header(state)
        print("AUDITORIA SELECIONADA\n")
        print(f"AUD            : {audit_id}")
        print(f"Situação       : {_friendly_status(summary.get('processing_status', 'STATUS NÃO PROJETADO'))}")
        if str(summary.get("processing_status") or "").upper() == "COMPLETE":
            print(f"Conclusão local: {_local_timestamp(summary.get('completed_at'))}")
        print(f"Score          : {_friendly_score(summary.get('score_status', '-'))}")
        eligible = summary.get("consolidation_eligible")
        print(f"Consolidação   : {'ELEGÍVEL' if eligible is True else ('NÃO ELEGÍVEL' if eligible is False else '-')}")
        print(f"Configuração   : {'REUTILIZÁVEL' if reuse_available else 'INDISPONÍVEL'}")
        if not reuse_available:
            print(f"Motivo config. : {reuse_detail}")
        if summary:
            print(
                "Requisitos     : "
                f"{summary.get('successful_items', 0)}/{summary.get('required_items', 0)} atendidos | "
                f"pendentes={summary.get('pending_items', 0)} | bloqueados={summary.get('blocked_items', 0)}"
            )
            print(
                f"Reprocessamentos: {summary.get('reprocess_count', 0)} | "
                f"último={summary.get('last_reprocess_id') or '-'}"
            )
        print("\nAÇÕES")
        print("M. Ver linha de comando")
        print(
            "I. Abrir relatório HTML"
            + ("" if report_path is not None else " [INDISPONÍVEL]")
        )
        if _can_reprocess(summary):
            print("1. Reprocessar somente pendências desta auditoria")
        elif str(summary.get("processing_status") or "").upper() == "COMPLETE":
            print("1. Reprocessar pendências [NÃO NECESSÁRIO — AUDITORIA CONCLUÍDA]")
        else:
            print("1. Reprocessar pendências [INDISPONÍVEL NESTE ESTADO]")
        if reuse_available:
            print("2. Carregar esta configuração para uma nova auditoria")
        else:
            print("2. Carregar esta configuração para uma nova auditoria [INDISPONÍVEL]")
        print("3. Mostrar caminhos de artefatos")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return False
        if choice == "M":
            from rasai.execution_commands import show_logged

            if not show_logged(
                state.audits_root,
                audit_id,
                artifact_root=audit_root,
            ):
                state.error = "log de linha de comando não disponível para esta auditoria"
            continue
        if choice == "I":
            if report_path is None:
                state.error = "relatório HTML de catálogo não está disponível para esta auditoria"
                continue
            ok, detail = open_external_path(report_path)
            state.operation = "LOCAL:OPEN_SELECTED_AUDIT_REPORT"
            state.error = "" if ok else detail
            if not ok:
                console_module.render_header(state)
                print("NÃO FOI POSSÍVEL ABRIR O RELATÓRIO\n")
                print(detail)
                input("\nENTER para continuar...")
            continue
        if choice == "1":
            if not _can_reprocess(summary):
                if str(summary.get("processing_status") or "").upper() == "COMPLETE":
                    state.error = "Auditoria concluída; reprocessamento não é necessário."
                elif str(summary.get("processing_status") or "").upper() == "EXPIRED_FOR_COMPLETION":
                    state.error = "A janela de conclusão expirou; crie uma nova auditoria."
                else:
                    state.error = "Reprocessamento indisponível para o estado atual."
                continue
            _reprocess_selected(console_module, state, audit_id)
        elif choice == "2":
            if not reuse_available:
                state.status = "CONFIG_SOURCE_REJECTED"
                state.operation = "LOCAL:AUD_CONFIG_REUSE"
                state.error = reuse_detail
                continue
            if navigation._load_selected_configuration(console_module, state, audit_id):
                return True
        elif choice == "3":
            console_module.render_header(state)
            print("ARTEFATOS\n")
            print(f"Workspace : {audit_root}")
            print(f"audit.db  : {audit_root / 'audit.db'}")
            print(f"Relatório : {report_path if report_path is not None else '<não materializado ou pacote inválido>'}")
            input("\nENTER para continuar...")
        else:
            state.error = "ação inválida"

    return False


def _management_event_label(item: Any) -> str:
    return _local_timestamp(item.event_time or item.created_at)


def _management_status(item: Any) -> str:
    return _friendly_status(
        item.fulfillment_processing_status
        or item.completion_status
        or item.status
        or "-"
    )


def _management_menu(console_module: ModuleType, state: Any) -> None:
    from rasai import audit_management_console as management
    from rasai.audit_management import AuditInventoryFilter

    filters = AuditInventoryFilter()
    selected: set[str] = set()
    page = 0
    while True:
        all_items = management.inventory(state.audits_root)
        filtered = management.filter_inventory(all_items, filters)
        valid_ids = {item.audit_id for item in all_items}
        selected.intersection_update(valid_ids)
        pages = max(1, math.ceil(len(filtered) / management._PAGE_SIZE))
        page = min(page, pages - 1)
        start = page * management._PAGE_SIZE
        visible = filtered[start : start + management._PAGE_SIZE]

        console_module.render_header(state)
        print("GERENCIAR AUDITORIAS / EXCLUSÃO SEGURA\n")
        print(f"Raiz       : {state.audits_root}")
        print(f"AUDs       : {len(all_items)} total | {len(filtered)} no filtro | {len(selected)} selecionados")
        print(f"Espaço AUD : {management._size_label(sum(item.size_bytes for item in all_items))}")
        print(f"Filtros    : {management._render_filters(filters)}")
        print(f"Página     : {page + 1}/{pages}\n")
        if visible:
            audit_width = max(36, min(44, max(len(item.audit_id) for item in visible)))
            print(
                f"{'Nº':>3} {'SEL':<3} {'AUDITORIA':<{audit_width}}  "
                f"{'EVENTO LOCAL':<16}  {'SITUAÇÃO':<29}  {'TAMANHO':>10}  DOMÍNIO"
            )
            print(
                f"{'---':>3} {'---':<3} {'-' * audit_width}  "
                f"{'-' * 16}  {'-' * 29}  {'-' * 10}  {'-' * 20}"
            )
            for absolute_index, item in enumerate(visible, start + 1):
                marker = "[x]" if item.audit_id in selected else "[ ]"
                print(
                    f"{absolute_index:>3} {marker:<3} {item.audit_id:<{audit_width}}  "
                    f"{_management_event_label(item):<16}  {_management_status(item):<29}  "
                    f"{management._size_label(item.size_bytes):>10}  {management._domains_label(item)}"
                )
        else:
            print("Nenhum AUD atende aos filtros atuais.")

        print("\nAÇÕES")
        print("< / >. Página anterior / próxima")
        print("N. Alternar seleção informando números (ex.: 1,3,7-10)")
        print("A. Selecionar TODOS os AUDs do filtro atual")
        print("L. Limpar seleção")
        print("F. Definir filtros")
        print("X. Excluir AUDs selecionados")
        print("T. Excluir TODOS os AUDs existentes")
        print("R. Repetir limpeza física pendente")
        print("V. Voltar")
        choice = input("Escolha: ").strip().upper()
        if choice == "V":
            return
        if choice == ">":
            page = min(page + 1, pages - 1)
            continue
        if choice == "<":
            page = max(0, page - 1)
            continue
        if choice == "F":
            filters = management._configure_filters(filters)
            page = 0
            continue
        if choice == "A":
            selected.update(item.audit_id for item in filtered)
            continue
        if choice == "L":
            selected.clear()
            continue
        if choice == "N":
            raw = input("Números/intervalos [V=voltar sem alterar seleção]: ").strip()
            if raw.upper() == "V":
                continue
            try:
                management._toggle_indexes(raw, filtered, selected)
            except ValueError:
                state.error = "seleção inválida"
            continue
        if choice == "X":
            if not selected:
                state.error = "nenhum AUD selecionado"
                continue
            management._delete(console_module, state, tuple(sorted(selected)))
            selected.clear()
            continue
        if choice == "T":
            if not all_items:
                state.error = "nenhum AUD disponível para exclusão"
                continue
            management._delete(
                console_module,
                state,
                tuple(item.audit_id for item in all_items),
                all_audits=True,
            )
            selected.clear()
            continue
        if choice == "R":
            result = management.cleanup_pending(state.audits_root)
            state.operation = "LOCAL:AUDIT_DELETE_CLEANUP"
            state.status = "COMPLETED" if result.pending_batches == 0 else "PHYSICAL_CLEANUP_PENDING"
            state.error = "; ".join(result.errors)
            console_module.render_header(state)
            print("LIMPEZA FÍSICA PENDENTE\n")
            print(f"Lotes removidos : {result.removed_batches}")
            print(f"Lotes pendentes : {result.pending_batches}")
            print(f"Espaço pendente : {management._size_label(result.pending_bytes)}")
            for error in result.errors[:20]:
                print(f"- {error}")
            input("\nENTER para continuar...")
            continue
        state.error = "opção inválida"


def _install_compact_ids() -> None:
    from rasai import console_ui_catalog as catalog

    # CORE IDs are explicit because they are part of the same visual contract and must
    # remain stable independently from the environment-variable catalog.
    for key, value in tuple(catalog.CORE_IDS.items()):
        try:
            catalog.CORE_IDS[key] = f"{int(value):06d}"
        except (TypeError, ValueError):
            pass
    catalog.configuration_id = configuration_id

    # console_ui_refactor imports these symbols by value; update its bound reference too.
    try:
        from rasai import console_ui_refactor as refactor

        refactor.configuration_id = configuration_id
    except ImportError:
        pass


def _install_guided_values() -> None:
    from rasai import console_configuration_guidance as guidance

    guidance._single_choice = _single_choice
    guidance._multi_choice = _multi_choice


def _install_audit_history(console_module: ModuleType) -> None:
    from rasai import audit_management_console as management
    from rasai import console_navigation as navigation

    navigation._safe_summary = _safe_summary
    navigation._choose_audit = _choose_audit_factory(console_module)
    navigation._reprocess_selected = _reprocess_selected
    navigation._selected_audit_menu = _selected_audit_menu
    management._date_label = _management_event_label
    management._management_menu = _management_menu


def install(console_module: ModuleType) -> None:
    """Install the final presentation refinements after all other console wrappers."""
    if getattr(console_module, "_rasai_usability_refinements_installed", False):
        return
    _install_compact_ids()
    _install_guided_values()
    _install_audit_history(console_module)
    console_module._rasai_usability_refinements_installed = True
