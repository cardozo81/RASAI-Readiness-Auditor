"""Grouped and guided environment-variable configuration for the console."""
from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
import os
from pathlib import Path
from urllib.parse import urlparse

from searchgeo.console_artifacts import open_external_path
from searchgeo.console_config import ENV_NAMES as BASE_ENV_NAMES, KEY_ENV, PROVIDERS, apply_environment_defaults, is_secret
from searchgeo.console_m23 import M23_ENV_NAMES, apply_m23_environment_defaults, validate_env_value as validate_existing
from searchgeo.console_runtime import render_header
from searchgeo.console_session import clear_secret_volatile, mark_secret_volatile
from searchgeo.console_ui import CYAN, DIM, GREEN, YELLOW, paint
from searchgeo.content_context import (
    CONTENT_ORIGIN_ENV,
    CONTENT_RISK_PROFILE_ENV,
    EXPERIENCE_REQUIREMENT_ENV,
    FRESHNESS_SENSITIVITY_ENV,
    INTENDED_AUDIENCE_ENV,
    PAGE_PURPOSE_ENV,
    YMYL_CATEGORY_ENV,
)
from searchgeo.m23_cli import (
    APDEX_CONCURRENCY_ENV, APDEX_DELAY_ENV, APDEX_ENABLED_ENV, APDEX_MAX_ATTEMPTS_ENV,
    APDEX_MAX_PAGES_ENV, APDEX_SAMPLES_ENV, APDEX_THRESHOLD_ENV, APDEX_TIMEOUT_ENV,
)
from searchgeo.provider_registry import provider_registrations
from searchgeo.provider_runtime_policy import (
    AI_TIMEOUT_ENV, LOWEST_REASONING, REASONING_OPTIONS, SIMPLE_DEFAULT_MODELS,
    WEB_PERFORMANCE_TIMEOUT_ENV, provider_reasoning_env,
)
from searchgeo.windows_environment import (
    current_matches_persisted, environment_origin, machine_environment_value,
    persist_user_environment, remove_user_environment, user_environment_value,
)

ENV_NAMES = tuple(dict.fromkeys((*BASE_ENV_NAMES, *M23_ENV_NAMES)))
DOCUMENT_NAME = "ENVIRONMENT_VARIABLES.md"
CATEGORIES = (
    "Aplicação e execução",
    "IA — credenciais",
    "IA — modelos e reasoning",
    "IA — endpoints avançados",
    "IA — contexto editorial / YMYL",
    "Web Performance / Google APIs",
    "Synthetic Apdex",
    "Browser / Playwright",
)


@dataclass(frozen=True, slots=True)
class EnvironmentSpec:
    name: str
    category: str
    purpose: str
    value_type: str
    accepted: tuple[str, ...] = ()
    default: str | None = None
    required_when: str = "Nunca; override opcional."
    sensitive: bool = False
    impact: str = "Sem custo externo direto."
    example: str = ""
    source: str = "docs/ENVIRONMENT_VARIABLES.md"
    notes: str = ""


ENDPOINT_DEFAULTS = {
    "XAI": "https://api.x.ai/v1/responses",
    "QWEN": "https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions",
    "GEMINI": "https://generativelanguage.googleapis.com/v1beta/interactions",
    "ANTHROPIC": "https://api.anthropic.com/v1/messages",
}
KEY_SOURCES = {
    "OPENAI": "OpenAI Platform > API Keys — https://platform.openai.com/api-keys",
    "DEEPSEEK": "DeepSeek Platform > API Keys — https://platform.deepseek.com/api_keys",
    "MIMO": "Xiaomi MiMo Console > API Keys — docs/ENVIRONMENT_VARIABLES.md",
    "XAI": "xAI Console > API Keys — https://console.x.ai/",
    "QWEN": "Alibaba Cloud Model Studio > API Key — docs/ENVIRONMENT_VARIABLES.md",
    "GEMINI": "Google AI Studio > API Keys — https://aistudio.google.com/apikey",
    "ANTHROPIC": "Anthropic Console > API Keys — https://console.anthropic.com/",
}


def _fixed_specs() -> tuple[EnvironmentSpec, ...]:
    context_source = "docs/CONTENT_ANALYSIS_CONTEXT.md"
    return (
        EnvironmentSpec("SEARCHGEO_CONFIG", "Aplicação e execução", "Força um arquivo TOML geral; hoje usado principalmente para logging.", "caminho de arquivo existente", default="searchgeo.toml opcional quando não há override", required_when="Somente se quiser apontar explicitamente para outro TOML.", example=r"SEARCHGEO_CONFIG=C:\searchgeo\searchgeo.toml"),
        EnvironmentSpec("SEARCHGEO_LOG_LEVEL", "Aplicação e execução", "Controla a verbosidade do log operacional.", "enum", ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"), "INFO", example="SEARCHGEO_LOG_LEVEL=INFO"),
        EnvironmentSpec("SEARCHGEO_DEVICE_CONTEXT", "Aplicação e execução", "Define o dispositivo default quando menu/CLI não fornecem valor explícito.", "enum", ("mobile", "desktop", "both"), "mobile", impact="`both` multiplica contextos e pode ampliar tempo, chamadas e custo externo.", example="SEARCHGEO_DEVICE_CONTEXT=mobile"),
        EnvironmentSpec(AI_TIMEOUT_ENV, "Aplicação e execução", "Timeout máximo de uma tentativa de IA; não é o timeout da auditoria inteira.", "número > 0 (segundos)", default="180", impact="Não cria chamadas; uma chamada expirada localmente ainda pode ter sido processada pelo provider.", example=f"{AI_TIMEOUT_ENV}=180"),
        EnvironmentSpec("SEARCHGEO_AI_CONTENT_REMEDIATION", "Aplicação e execução", "Default da remediação textual por IA.", "booleano", ("true", "false"), "false", required_when="Só tem efeito com provider de IA apto.", impact="Quando true, pode gerar chamadas/tokens adicionais de IA.", example="SEARCHGEO_AI_CONTENT_REMEDIATION=false"),
        EnvironmentSpec(CONTENT_RISK_PROFILE_ENV, "IA — contexto editorial / YMYL", "Define o perfil de risco editorial. Use YMYL explicitamente quando o conteúdo puder afetar saúde, segurança, estabilidade financeira ou bem-estar social.", "enum", ("auto", "standard", "ymyl"), "auto", impact="Não cria chamadas; condiciona o rigor da IA quando uma chamada já ocorrer.", example=f"{CONTENT_RISK_PROFILE_ENV}=ymyl", source=context_source, notes="AUTO é apenas classificação provisória da IA; para domínio claramente YMYL prefira override explícito."),
        EnvironmentSpec(YMYL_CATEGORY_ENV, "IA — contexto editorial / YMYL", "Contextualiza a natureza do risco YMYL para orientar trust, suporte factual e qualificadores.", "enum", ("auto", "none", "health-safety", "financial-security", "civic-societal", "other-significant-welfare"), "auto", impact="Não cria chamadas; altera apenas o contexto da avaliação sem criar score YMYL.", example=f"{YMYL_CATEGORY_ENV}=financial-security", source=context_source),
        EnvironmentSpec(PAGE_PURPOSE_ENV, "IA — contexto editorial / YMYL", "Informa a finalidade principal da página para evitar aplicar o mesmo padrão editorial a páginas informativas, transacionais, reviews, notícias ou documentação.", "enum", ("auto", "informational", "transactional", "product-service", "review-comparison", "news-editorial", "support-documentation", "forum-ugc", "other"), "auto", impact="Não cria chamadas; melhora a aderência das recomendações quando IA está ativa.", example=f"{PAGE_PURPOSE_ENV}=product-service", source=context_source),
        EnvironmentSpec(INTENDED_AUDIENCE_ENV, "IA — contexto editorial / YMYL", "Define se o público pretendido é geral, profissional ou misto para calibrar profundidade e explicação.", "enum", ("auto", "general", "professional", "mixed"), "auto", impact="Não cria chamadas; não autoriza inferir requisitos legais ou credenciais.", example=f"{INTENDED_AUDIENCE_ENV}=general", source=context_source),
        EnvironmentSpec(EXPERIENCE_REQUIREMENT_ENV, "IA — contexto editorial / YMYL", "Indica quando experiência em primeira mão é necessária, apenas benéfica ou não esperada; não substitui expertise técnica/profissional.", "enum", ("auto", "required", "beneficial", "not-expected"), "auto", impact="Não cria chamadas; evita exigir experiência pessoal indiscriminadamente.", example=f"{EXPERIENCE_REQUIREMENT_ENV}=beneficial", source=context_source),
        EnvironmentSpec(FRESHNESS_SENSITIVITY_ENV, "IA — contexto editorial / YMYL", "Define o quanto datas, períodos e qualificadores temporais são materiais para a página.", "enum", ("auto", "low", "medium", "high"), "auto", impact="Não cria chamadas; HIGH eleva o rigor sobre freshness sem autorizar alterar datas artificialmente.", example=f"{FRESHNESS_SENSITIVITY_ENV}=high", source=context_source),
        EnvironmentSpec(CONTENT_ORIGIN_ENV, "IA — contexto editorial / YMYL", "Distingue conteúdo próprio, de terceiro, UGC ou misto para orientar autoria, responsabilidade e atribuição.", "enum", ("auto", "first-party", "third-party", "user-generated", "mixed"), "auto", impact="Não cria chamadas; ajuda a separar criador da informação e publicador/host.", example=f"{CONTENT_ORIGIN_ENV}=first-party", source=context_source),
        EnvironmentSpec("SEARCHGEO_WEB_PERFORMANCE", "Web Performance / Google APIs", "Habilita PageSpeed/Lighthouse/CrUX por ambiente.", "booleano", ("true", "false"), "false", impact="Quando true, consome integração/quota externa.", example="SEARCHGEO_WEB_PERFORMANCE=false"),
        EnvironmentSpec("SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES", "Web Performance / Google APIs", "Limita páginas submetidas às integrações de Web Performance; 0 significa todas.", "inteiro >= 0", default="10", impact="Multiplicador direto do volume potencial de PageSpeed/CrUX.", example="SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES=10"),
        EnvironmentSpec(WEB_PERFORMANCE_TIMEOUT_ENV, "Web Performance / Google APIs", "Timeout de cada request PageSpeed/CrUX.", "número > 0 (segundos)", default="120", impact="Não cria requests adicionais; controla somente a espera do cliente.", example=f"{WEB_PERFORMANCE_TIMEOUT_ENV}=120"),
        EnvironmentSpec("SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE", "Web Performance / Google APIs", "Define a política de dados de campo CrUX.", "enum", ("auto", "pagespeed", "crux", "none"), "auto", required_when="`crux` exige SEARCHGEO_CRUX_API_KEY.", impact="Pode consumir PageSpeed e/ou CrUX conforme a opção.", example="SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE=auto"),
        EnvironmentSpec("SEARCHGEO_LIGHTHOUSE_CATEGORIES", "Web Performance / Google APIs", "Seleciona as categorias Lighthouse solicitadas numa chamada PageSpeed.", "lista CSV", ("performance", "accessibility", "best-practices", "seo"), "performance,accessibility,best-practices,seo", impact="Muda as categorias coletadas; não representa preço monetário por si só.", example="SEARCHGEO_LIGHTHOUSE_CATEGORIES=performance,accessibility,best-practices,seo", notes="Uma ou mais categorias, separadas por vírgula, sem duplicar."),
        EnvironmentSpec("SEARCHGEO_PAGESPEED_API_KEY", "Web Performance / Google APIs", "Chave Google para PageSpeed Insights API.", "segredo/API key", required_when="Opcional em uso ad hoc; recomendada para automação/gestão de quota.", sensitive=True, impact="Habilita quota autenticada no projeto Google Cloud; eventual billing pertence ao projeto.", source="docs/GOOGLE_API_KEYS.md", example="SEARCHGEO_PAGESPEED_API_KEY=<sua-chave>"),
        EnvironmentSpec("SEARCHGEO_CRUX_API_KEY", "Web Performance / Google APIs", "Chave Google para consulta direta à Chrome UX Report API.", "segredo/API key", required_when="Obrigatória quando field source=crux; pode ser usada como fallback direto em auto.", sensitive=True, impact="Consome quota da CrUX API no projeto Google Cloud.", source="docs/GOOGLE_API_KEYS.md", example="SEARCHGEO_CRUX_API_KEY=<sua-chave>"),
        EnvironmentSpec(APDEX_ENABLED_ENV, "Synthetic Apdex", "Habilita navegações sintéticas repetidas em Chromium.", "booleano", ("true", "false"), "false", impact="Sem API paga própria, mas gera carga HTTP real contra o alvo.", example=f"{APDEX_ENABLED_ENV}=false"),
        EnvironmentSpec(APDEX_THRESHOLD_ENV, "Synthetic Apdex", "Threshold T: <=T Satisfied; >T até 4T Tolerating; >4T Frustrated.", "número > 0 (segundos)", required_when="Obrigatória quando Synthetic Apdex=true.", impact="Define a classificação Apdex.", example=f"{APDEX_THRESHOLD_ENV}=1.5"),
        EnvironmentSpec(APDEX_SAMPLES_ENV, "Synthetic Apdex", "Amostras válidas alvo por URL/dispositivo.", "inteiro >= 1", default="100", impact="Multiplica navegações; 1–99 é small-group diagnóstico.", example=f"{APDEX_SAMPLES_ENV}=100"),
        EnvironmentSpec(APDEX_MAX_ATTEMPTS_ENV, "Synthetic Apdex", "Teto de tentativas para repor amostras inválidas.", "inteiro >= amostras válidas", default="ceil(1.25 × samples)", impact="Aumenta o teto de carga real no alvo.", example=f"{APDEX_MAX_ATTEMPTS_ENV}=125"),
        EnvironmentSpec(APDEX_MAX_PAGES_ENV, "Synthetic Apdex", "Máximo de páginas medidas; 0 significa todas.", "inteiro >= 0", default="1", impact="Multiplica contextos/navegações.", example=f"{APDEX_MAX_PAGES_ENV}=1"),
        EnvironmentSpec(APDEX_TIMEOUT_ENV, "Synthetic Apdex", "Timeout de cada navegação sintética.", "número > 0 e > 4T", default="max(45, 4T + 5) quando habilitado", required_when="Se sobrescrito com Apdex ativo, precisa ser >4T.", impact="Timeout baixo demais trunca artificialmente a faixa Frustrated.", example=f"{APDEX_TIMEOUT_ENV}=45"),
        EnvironmentSpec(APDEX_DELAY_ENV, "Synthetic Apdex", "Intervalo mínimo entre inícios de navegação.", "número >= 0 (segundos)", default="1", impact="Maior delay reduz pressão e aumenta duração total.", example=f"{APDEX_DELAY_ENV}=1"),
        EnvironmentSpec(APDEX_CONCURRENCY_ENV, "Synthetic Apdex", "Workers sintéticos simultâneos.", "enum inteiro", ("1", "2"), "1", impact="2 reduz tempo, mas aumenta carga concorrente.", example=f"{APDEX_CONCURRENCY_ENV}=1"),
        EnvironmentSpec("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "Browser / Playwright", "Caminho opcional para um executável Chromium específico.", "caminho de arquivo existente", required_when="Somente quando quiser substituir a descoberta/instalação padrão do Playwright.", example=r"PLAYWRIGHT_CHROMIUM_EXECUTABLE=C:\Program Files\Chromium\chrome.exe"),
    )


def _provider_specs() -> tuple[EnvironmentSpec, ...]:
    result: list[EnvironmentSpec] = []
    for reg in provider_registrations():
        name = reg.provider_name
        mimo_note = " O adapter atual exige chave PAYG `sk-...`; Token Plan `tp-...` não é compatível." if name == "MIMO" else ""
        result.append(EnvironmentSpec(reg.key_env, "IA — credenciais", f"Credencial do provider {reg.display_name}.{mimo_note}", "segredo/API key", required_when=f"Obrigatória ao selecionar `{reg.id}`; em AUTO torna o provider elegível quando aplicável.", sensitive=True, impact="Pode tornar chamadas externas executáveis e gerar cobrança conforme modelo/plano.", example=f"{reg.key_env}=<sua-chave>", source=KEY_SOURCES[name]))
        result.append(EnvironmentSpec(reg.model_env, "IA — modelos e reasoning", f"Modelo usado por {reg.display_name} sem --ai-model explícito.", "enum", tuple(reg.supported_models), SIMPLE_DEFAULT_MODELS[name], impact="Modelos podem ter preço, latência e capacidade diferentes.", example=f"{reg.model_env}={SIMPLE_DEFAULT_MODELS[name]}"))
        effort_env = provider_reasoning_env(name)
        if effort_env:
            result.append(EnvironmentSpec(effort_env, "IA — modelos e reasoning", f"Esforço/profundidade de reasoning para {reg.display_name}.", "enum", tuple(REASONING_OPTIONS[name]), LOWEST_REASONING[name], impact="Esforço maior pode elevar latência, tokens e custo.", example=f"{effort_env}={LOWEST_REASONING[name]}"))
        if reg.endpoint_env:
            result.append(EnvironmentSpec(reg.endpoint_env, "IA — endpoints avançados", f"Override do endpoint HTTP usado por {reg.display_name}.", "URL absoluta HTTP(S)", default=ENDPOINT_DEFAULTS.get(name), required_when="Nunca no uso normal; altere somente para endpoint oficialmente compatível/proxy controlado.", impact="Endpoint incorreto pode causar falha, cobrança em serviço diferente ou envio de dados a destino indevido.", example=f"{reg.endpoint_env}={ENDPOINT_DEFAULTS.get(name, '<url>')}", notes="Não altere sem necessidade operacional comprovada."))
    return tuple(result)


def environment_specs() -> tuple[EnvironmentSpec, ...]:
    known = {spec.name: spec for spec in (*_fixed_specs(), *_provider_specs())}
    return tuple(known.get(name, EnvironmentSpec(name, "Aplicação e execução", "Variável reconhecida pelo SearchGEO.", "texto", sensitive=is_secret(name), required_when="Consulte a documentação antes de definir.", impact="Impacto não classificado automaticamente.")) for name in ENV_NAMES)


SPECS = environment_specs()
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def _status(spec: EnvironmentSpec) -> str:
    value = (os.environ.get(spec.name) or "").strip()
    if value:
        if spec.sensitive or is_secret(spec.name):
            origin = environment_origin(spec.name, value)
            suffix = f" [{origin}]" if origin else ""
            return paint("[SET]" + suffix, GREEN, bold=True)
        if value.casefold() in {"true", "1", "yes", "on"}:
            return paint(value, GREEN, bold=True)
        if value.casefold() in {"false", "0", "no", "off"}:
            return paint(value, DIM)
        return paint(value[:60], CYAN)
    if spec.sensitive or is_secret(spec.name):
        origin = environment_origin(spec.name, None)
        if origin:
            return paint(f"<não ativa> [{origin}]", DIM)
    if spec.default is not None:
        return paint(f"<default efetivo: {spec.default}>", DIM)
    return paint("<não definida>", DIM)


def _docs_path() -> Path | None:
    for path in (Path.cwd() / "docs" / DOCUMENT_NAME, Path(__file__).resolve().parents[2] / "docs" / DOCUMENT_NAME):
        if path.is_file():
            return path
    return None


def _open_docs(state: object) -> None:
    path = _docs_path()
    if path is None:
        setattr(state, "error", f"documentação não encontrada: docs/{DOCUMENT_NAME}")
        return
    ok, detail = open_external_path(path)
    setattr(state, "operation", "LOCAL:OPEN_ENV_DOCUMENTATION")
    setattr(state, "error", "" if ok else detail)


def _validate(name: str, raw: str) -> str:
    value = validate_existing(name, raw)
    if name == "SEARCHGEO_LOG_LEVEL":
        value = value.upper()
        if value not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("use CRITICAL, ERROR, WARNING, INFO ou DEBUG")
    elif name == "SEARCHGEO_CONFIG":
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("arquivo TOML configurado não existe")
        value = str(path)
    elif name == "SEARCHGEO_LIGHTHOUSE_CATEGORIES":
        allowed = ("performance", "accessibility", "best-practices", "seo")
        items = [item.strip().casefold() for item in value.split(",") if item.strip()]
        if not items or any(item not in allowed for item in items):
            raise ValueError("categorias suportadas: " + ", ".join(allowed))
        if len(items) != len(set(items)):
            raise ValueError("não duplique categorias Lighthouse")
        value = ",".join(items)
    spec = SPEC_BY_NAME.get(name)
    if spec and spec.category == "IA — endpoints avançados":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("use URL absoluta http:// ou https://")
    return value


def _apply_change(state: object, name: str) -> None:
    issues = list(apply_environment_defaults(state, names={name}))
    issues.extend(apply_m23_environment_defaults(state, names={name}))
    setattr(state, "error", "; ".join(issues))
    for selection, provider in PROVIDERS.items():
        if KEY_ENV[provider] == name:
            getattr(state, "runtime_blocks", {}).pop(selection, None)


def _sync_secret_state(state: object, name: str) -> None:
    if current_matches_persisted(name):
        clear_secret_volatile(state, name)
    else:
        mark_secret_volatile(state, name)


def _prompt_choice(spec: EnvironmentSpec) -> str | None:
    print("\nValores aceitos:")
    for index, item in enumerate(spec.accepted, 1):
        marker = " [default]" if item == spec.default else ""
        print(f" {index}. {item}{marker}")
    print(" V. Voltar")
    raw = input("Escolha: ").strip().upper()
    if raw == "V":
        return None
    if raw in spec.accepted:
        return raw
    try:
        return spec.accepted[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("opção inválida") from exc


def _render_detail(spec: EnvironmentSpec) -> None:
    print(spec.name)
    print("=" * min(max(len(spec.name), 40), 100))
    print(f"Grupo          : {spec.category}")
    print(f"Para que serve : {spec.purpose}")
    print(f"Tipo           : {spec.value_type}")
    if spec.accepted:
        print(f"Valores aceitos: {', '.join(spec.accepted)}")
    print(f"Default efetivo: {spec.default if spec.default is not None else 'nenhum'}")
    print(f"Obrigatória    : {spec.required_when}")
    print(f"Sensível       : {'SIM — nunca exibida nem gravada no INI' if spec.sensitive or is_secret(spec.name) else 'não'}")
    print(f"Custo/impacto  : {spec.impact}")
    print(f"Valor ambiente : {_status(spec)}")
    if spec.example:
        print(f"Exemplo        : {spec.example}")
    if spec.source:
        print(f"Como obter/ref.: {spec.source}")
    if spec.notes:
        print(f"Observação     : {spec.notes}")
    if spec.default is not None and not (os.environ.get(spec.name) or "").strip():
        print(paint("Nota: o default já é aplicado internamente; não é necessário criar a variável só para repetir esse valor.", DIM))


def _persist_secret(state: object, spec: EnvironmentSpec) -> None:
    name = spec.name
    render_header(state)
    current = (os.environ.get(name) or "").strip()
    user_value = user_environment_value(name)
    machine_value = machine_environment_value(name)
    print("PERSISTÊNCIA DE CREDENCIAL NO WINDOWS\n")
    print(f"Variável           : {name}")
    print(f"Sessão atual       : {'[SET]' if current else '<não definida>'}")
    print(f"Windows / User     : {'[PERSISTIDA]' if user_value else '<não persistida>'}")
    print(f"Windows / Machine  : {'[PERSISTIDA]' if machine_value else '<não persistida>'}")
    print("\nP. Persistir no Windows/User o valor atual da sessão")
    print("R. Remover a persistência Windows/User (mantém a sessão atual)")
    print("V. Voltar")
    action = input("Escolha: ").strip().upper()
    if action == "V":
        return
    if os.name != "nt":
        setattr(state, "error", "persistência de credenciais no SO está disponível somente no Windows")
        return
    if action == "P":
        if not current:
            setattr(state, "error", "defina a credencial na sessão antes de persistir")
            return
        if input(f"Confirmar persistência de {name} no ambiente USER do Windows? Digite SIM: ").strip().upper() != "SIM":
            setattr(state, "error", "persistência cancelada")
            return
        persist_user_environment(name, current)
        _sync_secret_state(state, name)
        setattr(state, "error", "")
        setattr(state, "operation", "LOCAL:PERSIST_USER_SECRET")
    elif action == "R":
        if user_value is None:
            setattr(state, "error", f"{name} não possui persistência no escopo Windows/User")
            return
        if input(f"Confirmar remoção da persistência USER de {name}? Digite SIM: ").strip().upper() != "SIM":
            setattr(state, "error", "remoção cancelada")
            return
        remove_user_environment(name)
        _sync_secret_state(state, name)
        setattr(state, "error", "")
        setattr(state, "operation", "LOCAL:REMOVE_USER_SECRET")


def _variable_menu(state: object, spec: EnvironmentSpec) -> None:
    while True:
        render_header(state)
        _render_detail(spec)
        if spec.sensitive or is_secret(spec.name):
            print("\nAÇÕES")
            print("S. Setar/alterar sessão")
            print("R. Remover da sessão")
            print("P. Persistência Windows/User")
            print("D. Documentação")
            print("V. Voltar")
        else:
            print("\nAÇÕES")
            print("S. Setar/alterar")
            print("R. Remover override")
            print("D. Documentação")
            print("V. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "D":
            _open_docs(state)
            continue
        if action == "P" and (spec.sensitive or is_secret(spec.name)):
            try:
                _persist_secret(state, spec)
            except (OSError, ValueError) as exc:
                setattr(state, "error", f"falha de persistência: {type(exc).__name__}: {exc}")
            continue
        if action == "R":
            os.environ.pop(spec.name, None)
            if spec.sensitive or is_secret(spec.name):
                _sync_secret_state(state, spec.name)
            _apply_change(state, spec.name)
            continue
        if action != "S":
            continue
        try:
            if spec.accepted and spec.value_type in {"enum", "enum inteiro", "booleano"}:
                raw = _prompt_choice(spec)
                if raw is None:
                    continue
            else:
                raw = getpass(f"{spec.name}: ") if spec.sensitive or is_secret(spec.name) else input(f"{spec.name}: ")
            os.environ[spec.name] = _validate(spec.name, raw)
            if spec.sensitive or is_secret(spec.name):
                _sync_secret_state(state, spec.name)
            _apply_change(state, spec.name)
        except (ValueError, OverflowError) as exc:
            setattr(state, "error", str(exc))


def _category_menu(state: object, title: str, specs: tuple[EnvironmentSpec, ...]) -> None:
    while True:
        render_header(state)
        print(f"VARIÁVEIS DE AMBIENTE — {title}\n")
        for index, spec in enumerate(specs, 1):
            print(f"{index:2d}. {spec.name:<44} {_status(spec)}")
        print("\nAÇÕES")
        print("D. Abrir documentação detalhada")
        print("V. Voltar")
        raw = input("Selecione a variável: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            _open_docs(state)
            continue
        try:
            _variable_menu(state, specs[int(raw) - 1])
        except (ValueError, IndexError):
            setattr(state, "error", "variável inválida")


def environment_menu(state: object) -> None:
    """Show a two-level menu grouped by functional boundary."""
    grouped = {category: tuple(spec for spec in SPECS if spec.category == category) for category in CATEGORIES}
    while True:
        render_header(state)
        print("CONFIGURAÇÃO AVANÇADA — VARIÁVEIS DE AMBIENTE\n")
        print("Defaults seguros são aplicados internamente. Defina variável somente para override ou credencial.")
        print("Secrets nunca são gravados no INI; persistência Windows/User é opcional e exige confirmação.\n")
        choices: dict[str, str] = {}
        for index, category in enumerate(CATEGORIES, 1):
            specs = grouped[category]
            configured = sum(1 for spec in specs if (os.environ.get(spec.name) or "").strip())
            print(f" {index}. {category:<31} {configured}/{len(specs)} override(s) definidos")
            choices[str(index)] = category
        print("\n A. Todas as variáveis")
        print(f" D. Abrir documentação detalhada (docs/{DOCUMENT_NAME})")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            _open_docs(state)
            continue
        if raw == "A":
            _category_menu(state, "Todas", SPECS)
            continue
        category = choices.get(raw)
        if category:
            _category_menu(state, category, grouped[category])
        else:
            setattr(state, "error", "grupo inválido")
