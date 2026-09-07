"""Contextual help and cost-awareness for the optional interactive console."""
from __future__ import annotations

from searchgeo.console_config import State, is_secret
from searchgeo.console_cost import estimate_exposure
from searchgeo.console_ui import clear_screen, cost_color, paint

COST_NONE = "SEM CUSTO EXTERNO DIRETO"
COST_EXTERNAL = "PODE GERAR CUSTO EXTERNO"
COST_EXTRA_AI = "PODE GERAR CUSTO IA ADICIONAL"
COST_QUOTA = "CONSOME API/QUOTA EXTERNA"
COST_VOLUME = "MULTIPLICADOR DE CONSUMO"

PARAMETER_HELP: tuple[tuple[str, str, str], ...] = (
    ("1. Entrada", "Define o alvo. URL única é seed de crawl; TXT contém uma URL por linha e permite conhecer previamente a quantidade de URLs explícitas.", COST_VOLUME + ": quantidade de URLs/páginas afeta o teto de contextos e integrações."),
    ("2. Projeto", "Nome lógico para identificar/organizar a auditoria.", COST_NONE),
    ("3. Dispositivo", "Escolhe mobile, desktop ou both.", COST_VOLUME + ": both pode duplicar contextos e chamadas externas por página."),
    ("4. IA", "Seleciona none, provider explícito ou AUTO. Somente opções aptas podem executar.", COST_EXTERNAL + ": cobrança depende do provider, modelo, tokens e plano."),
    ("5. Remediação textual IA", "Ativa sugestões e remediação de conteúdo por IA para findings elegíveis; não altera score/findings.", COST_EXTRA_AI + ": pode acrescentar novas chamadas de IA por contexto elegível."),
    ("6. Web Performance", "Ativa Web Performance/Lighthouse e a fonte de field data.", COST_QUOTA + ": PageSpeed/CrUX são integrações externas; o console não presume preço monetário quando o serviço não fornece base de custo persistida."),
    ("7. max-pages", "Teto de páginas da auditoria principal.", COST_VOLUME + ": em URL seed representa o teto potencial de crawl e chamadas relacionadas."),
    ("8. WebPerf max-pages", "Teto de páginas submetidas ao Web Performance.", COST_VOLUME + ": limita diretamente o volume potencial de PageSpeed/CrUX."),
    ("9. Idioma / mercado", "Contexto linguístico e de mercado do auditor.", COST_NONE),
    ("10. Raiz auditorias", "Diretório dos workspaces AUD-*.", COST_NONE + ": apenas disco local."),
)

SPECIFIC_ENV_HELP: dict[str, tuple[str, str]] = {
    "SEARCHGEO_CONFIG": ("Caminho/configuração geral consumida pelo RASAi quando aplicável.", COST_NONE),
    "SEARCHGEO_LOG_LEVEL": ("Nível de detalhamento do log operacional.", COST_NONE),
    "SEARCHGEO_DEVICE_CONTEXT": ("Default de dispositivo: mobile, desktop ou both.", COST_VOLUME + " quando both."),
    "SEARCHGEO_AI_TIMEOUT_SECONDS": ("Timeout máximo de uma tentativa de IA; não habilita retry automático.", "Não cria custo sozinho; chamada já processada externamente pode ser faturada conforme o provider."),
    "SEARCHGEO_AI_CONTENT_REMEDIATION": ("Default da remediação textual por IA.", COST_EXTRA_AI + " quando true e houver provider/casos elegíveis."),
    "SEARCHGEO_WEB_PERFORMANCE": ("Default para Web Performance externo.", COST_QUOTA + " quando true."),
    "SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES": ("Teto de páginas do Web Performance.", COST_VOLUME),
    "SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS": ("Timeout por integração Web Performance.", "Não gera custo sozinho."),
    "SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE": ("Fonte de field data: auto, pagespeed, crux ou none.", COST_QUOTA + " quando fonte externa é consultada."),
    "SEARCHGEO_LIGHTHOUSE_CATEGORIES": ("Categorias Lighthouse solicitadas pelo Web Performance externo.", "Pode alterar trabalho externo; não representa preço monetário por si só."),
    "SEARCHGEO_PAGESPEED_API_KEY": ("Credencial Google para PageSpeed Insights API.", COST_QUOTA + "; eventual billing pertence ao projeto Google Cloud."),
    "SEARCHGEO_CRUX_API_KEY": ("Credencial para consulta direta à Chrome UX Report API.", COST_QUOTA + "; eventual billing pertence ao projeto Google Cloud."),
    "PLAYWRIGHT_CHROMIUM_EXECUTABLE": ("Caminho opcional para Chromium local.", COST_NONE),
}


def current_cost_summary(state: State) -> tuple[str, ...]:
    estimate = estimate_exposure(state)
    lines = [
        f"Exposição financeira potencial: {estimate.level}.",
        f"Páginas consideradas: {estimate.min_pages}" if estimate.min_pages == estimate.max_pages else f"Páginas consideradas: {estimate.min_pages}–{estimate.max_pages} (mínimo conhecido–teto configurado).",
        f"Contextos de dispositivo por página: {estimate.device_contexts}.",
    ]
    if estimate.max_ai_attempts:
        lines.append(f"IA: {estimate.min_ai_attempts}–{estimate.max_ai_attempts} tentativa(s) potenciais no cenário configurado.")
    else:
        lines.append("IA: nenhuma tentativa externa prevista pela configuração atual.")
    if estimate.max_web_calls:
        lines.append(f"Web Performance: {estimate.min_web_calls}–{estimate.max_web_calls} chamada(s) PageSpeed/CrUX potenciais; quota externa é exibida separadamente de custo monetário.")
    else:
        lines.append("Web Performance: sem chamadas PageSpeed/CrUX configuradas.")
    lines.extend(estimate.pricing_lines)
    lines.extend(estimate.reasons)
    lines.append("A faixa NENHUM/BAIXO/MÉDIO/ALTO/EXCESSIVO é um indicador interno de exposição, não uma previsão de invoice.")
    lines.append("Antes da execução não são inventadas quantidades de tokens; o custo monetário final usa tokens/custos persistidos pelos adapters.")
    return tuple(lines)


def menu_cost_badges(state: State) -> dict[str, str]:
    return {
        "device": " [VOLUME↑]" if state.device == "both" else "",
        "ai": " [SEM CUSTO IA]" if state.ai_provider == "none" else " [CUSTO EXTERNO]",
        "remediation": " [CUSTO IA ADICIONAL]" if state.content_remediation else "",
        "web": " [QUOTA EXTERNA]" if state.web_performance else "",
        "max_pages": " [VOLUME]",
        "web_max_pages": " [LIMITE QUOTA]" if state.web_performance else "",
    }


def environment_help(name: str) -> tuple[str, str]:
    if name in SPECIFIC_ENV_HELP:
        return SPECIFIC_ENV_HELP[name]
    upper = name.upper()
    if is_secret(name):
        return (
            "Credencial/token de integração externa. O console mascara o valor e o usa somente na sessão/processos filhos.",
            COST_EXTERNAL + ": a credencial pode tornar chamadas externas executáveis conforme a configuração.",
        )
    if upper.endswith("_MODEL") or "_MODEL_" in upper:
        return ("Seleciona o modelo do provider conforme catálogo suportado.", COST_EXTERNAL + ": modelos podem ter preços diferentes.")
    if upper.endswith("_REASONING_EFFORT"):
        return ("Controla o esforço de reasoning quando suportado.", COST_EXTERNAL + ": custo/processamento pode aumentar com esforço maior conforme o provider.")
    return (
        "Variável reconhecida pelo RASAi; consulte a referência de configuração para o contrato completo.",
        "Impacto financeiro não classificado automaticamente; valide a integração associada.",
    )


def render_help(state: State) -> None:
    clear_screen()
    estimate = estimate_exposure(state)
    print("AJUDA — PARÂMETROS, CONSUMO E CUSTOS")
    print("=" * 100)
    print("Exposição financeira potencial: " + paint(estimate.level, cost_color(estimate.level), bold=True))
    print("Legenda: custo = possível cobrança; quota = limite externo; volume = multiplicador potencial.")
    for title, purpose, cost in PARAMETER_HELP:
        print(f"\n{title}")
        print(f"  Para que serve : {purpose}")
        print(f"  Custo/consumo  : {cost}")
    print("\nRESUMO DA CONFIGURAÇÃO ATUAL")
    for line in current_cost_summary(state):
        print("  - " + line)
    print("=" * 100)


def render_environment_help(name: str) -> None:
    purpose, cost = environment_help(name)
    print(f"\n{name}")
    print(f"  Para que serve : {purpose}")
    print(f"  Custo/consumo  : {cost}")
