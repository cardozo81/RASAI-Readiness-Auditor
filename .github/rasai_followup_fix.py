from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8", newline="\n")


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    value = text(path)
    if old not in value:
        raise RuntimeError(f"anchor not found in {path}: {old[:120]!r}")
    value = value.replace(old, new, count)
    write(path, value)


# ---------------------------------------------------------------------------
# 1. Console configuration: one persistent contract for menu -> INI -> runtime.
# ---------------------------------------------------------------------------
replace(
    "src/rasai/console_config.py",
    '    "RASAI_AI_CONTENT_REMEDIATION", *CONTENT_CONTEXT_ENV_NAMES,\n',
    '    "RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", *CONTENT_CONTEXT_ENV_NAMES,\n',
)
replace(
    "src/rasai/console_config.py",
    '    content_remediation: bool = False\n    web_performance: bool = False\n',
    '    content_remediation: bool = False\n    technical_remediation: bool = False\n    web_performance: bool = False\n',
)
replace(
    "src/rasai/console_config.py",
    '    if active("RASAI_AI_CONTENT_REMEDIATION"): state.content_remediation = boolean("RASAI_AI_CONTENT_REMEDIATION", False)\n    if active("RASAI_WEB_PERFORMANCE"): state.web_performance = boolean("RASAI_WEB_PERFORMANCE", False)\n',
    '    if active("RASAI_AI_CONTENT_REMEDIATION"): state.content_remediation = boolean("RASAI_AI_CONTENT_REMEDIATION", False)\n    if active("RASAI_AI_TECHNICAL_REMEDIATION"): state.technical_remediation = boolean("RASAI_AI_TECHNICAL_REMEDIATION", False)\n    if active("RASAI_WEB_PERFORMANCE"): state.web_performance = boolean("RASAI_WEB_PERFORMANCE", False)\n',
)
replace(
    "src/rasai/console_config.py",
    '    if name in {"RASAI_AI_CONTENT_REMEDIATION", "RASAI_WEB_PERFORMANCE"} and value.casefold() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}: raise ValueError("booleano inválido")\n',
    '    if name in {"RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", "RASAI_WEB_PERFORMANCE"} and value.casefold() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}: raise ValueError("booleano inválido")\n',
)
replace(
    "src/rasai/console_config.py",
    '    if state.ai_provider == "none" and state.content_remediation: raise ValueError("remediação textual exige provider de IA apto")\n',
    '    if state.ai_provider == "none" and (state.content_remediation or state.technical_remediation): raise ValueError("remediações de IA exigem provider de IA apto")\n',
)
replace(
    "src/rasai/console_config.py",
    '    command += ["--ai-content-remediation" if state.content_remediation else "--no-ai-content-remediation"]\n    command += ["--web-performance" if state.web_performance else "--no-web-performance"]\n',
    '    command += ["--ai-content-remediation" if state.content_remediation else "--no-ai-content-remediation"]\n    command += ["--ai-technical-remediation" if state.technical_remediation else "--no-ai-technical-remediation"]\n    command += ["--web-performance" if state.web_performance else "--no-web-performance"]\n',
)

# Persistent environment section and complete projection of non-secret state.
replace(
    "src/rasai/console_settings.py",
    'CONFIG_VERSION = "1"\n',
    'CONFIG_VERSION = "2"\n',
)
replace(
    "src/rasai/console_settings.py",
    'def _optional(value: Any) -> str:\n    return "" if value is None else str(value)\n\n\ndef _state_values',
    '''def _optional(value: Any) -> str:\n    return "" if value is None else str(value)\n\n\ndef _known_nonsecret_environment_names() -> tuple[str, ...]:\n    # Imports are deliberately lazy: console_config imports this module indirectly\n    # through the interactive console, so the persistence layer must not create a\n    # module-import cycle.\n    from rasai.console_config import ENV_NAMES as CONSOLE_ENV_NAMES, is_secret\n    from rasai.console_m23 import M23_ENV_NAMES\n\n    names = tuple(dict.fromkeys((*CONSOLE_ENV_NAMES, *M23_ENV_NAMES, "RASAI_AI_TECHNICAL_REMEDIATION")))\n    return tuple(name for name in names if not is_secret(name))\n\n\ndef _runtime_environment_projection(state: Any) -> dict[str, str]:\n    values = {\n        "RASAI_DEVICE_CONTEXT": str(state.device),\n        AI_TIMEOUT_ENV: f"{float(state.ai_timeout):g}",\n        "RASAI_AI_CONTENT_REMEDIATION": _bool_text(bool(state.content_remediation)),\n        "RASAI_AI_TECHNICAL_REMEDIATION": _bool_text(bool(getattr(state, "technical_remediation", False))),\n        "RASAI_WEB_PERFORMANCE": _bool_text(bool(state.web_performance)),\n        "RASAI_WEB_PERFORMANCE_MAX_PAGES": str(int(state.web_max_pages)),\n        WEB_PERFORMANCE_TIMEOUT_ENV: f"{float(state.web_timeout):g}",\n        "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": str(state.field_source),\n        "RASAI_LIGHTHOUSE_CATEGORIES": str(state.lighthouse_categories),\n    }\n    if hasattr(state, "synthetic_apdex"):\n        values.update({\n            "RASAI_SYNTHETIC_APDEX": _bool_text(bool(state.synthetic_apdex)),\n            "RASAI_APDEX_SAMPLES_PER_CONTEXT": str(int(state.apdex_samples)),\n            "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT": str(int(state.apdex_max_attempts)),\n            "RASAI_APDEX_MAX_PAGES": str(int(state.apdex_max_pages)),\n            "RASAI_APDEX_TIMEOUT_SECONDS": f"{float(state.apdex_timeout):g}",\n            "RASAI_APDEX_DELAY_SECONDS": f"{float(state.apdex_delay):g}",\n            "RASAI_APDEX_CONCURRENCY": str(int(state.apdex_concurrency)),\n        })\n        if state.apdex_threshold is not None:\n            values["RASAI_APDEX_THRESHOLD_SECONDS"] = f"{float(state.apdex_threshold):g}"\n        else:\n            values.pop("RASAI_APDEX_THRESHOLD_SECONDS", None)\n    registration = get_provider_registration(str(state.ai_provider))\n    if registration is not None:\n        if getattr(state, "ai_model", None):\n            values[registration.model_env] = str(state.ai_model)\n        if getattr(state, "ai_reasoning", None):\n            variable = provider_reasoning_env(registration.provider_name)\n            if variable:\n                values[variable] = str(state.ai_reasoning).upper()\n    return values\n\n\ndef _persisted_environment_values(state: Any) -> dict[str, str]:\n    allowed = set(_known_nonsecret_environment_names())\n    projected = _runtime_environment_projection(state)\n    result: dict[str, str] = {}\n    for name in allowed:\n        value = (os.environ.get(name) or projected.get(name) or "").strip()\n        if value:\n            result[name] = value\n    return dict(sorted(result.items()))\n\n\ndef _state_values''',
)
replace(
    "src/rasai/console_settings.py",
    '            "content_remediation": _bool_text(bool(state.content_remediation)),\n',
    '            "content_remediation": _bool_text(bool(state.content_remediation)),\n            "technical_remediation": _bool_text(bool(getattr(state, "technical_remediation", False))),\n',
)
replace(
    "src/rasai/console_settings.py",
    'def configuration_fingerprint(state: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:\n    values = _state_values(state)\n    return tuple((section, tuple(sorted(items.items()))) for section, items in sorted(values.items()))\n',
    '''def configuration_fingerprint(state: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:\n    values = _state_values(state)\n    sections = [(section, tuple(sorted(items.items()))) for section, items in sorted(values.items())]\n    sections.append(("environment", tuple(sorted(_persisted_environment_values(state).items()))))\n    return tuple(sections)\n''',
)
replace(
    "src/rasai/console_settings.py",
    'def _parser_for_state(state: Any) -> ConfigParser:\n    parser = ConfigParser(interpolation=None)\n    for section, values in _state_values(state).items():\n        parser[section] = values\n    return parser\n',
    '''def _parser_for_state(state: Any) -> ConfigParser:\n    parser = ConfigParser(interpolation=None)\n    parser.optionxform = str\n    for section, values in _state_values(state).items():\n        parser[section] = values\n    parser["environment"] = _persisted_environment_values(state)\n    return parser\n''',
)
replace(
    "src/rasai/console_settings.py",
    'def save_console_config(state: Any, path: Path | None = None) -> Path:\n    destination = path or resolve_config_path()\n',
    'def save_console_config(state: Any, path: Path | None = None) -> Path:\n    sync_nonsecret_runtime_environment(state)\n    destination = path or resolve_config_path()\n',
)
replace(
    "src/rasai/console_settings.py",
    '    elif key == ("ai", "content_remediation"): state.content_remediation = _parse_bool(raw)\n    elif key == ("web_performance", "enabled"): state.web_performance = _parse_bool(raw)\n',
    '    elif key == ("ai", "content_remediation"): state.content_remediation = _parse_bool(raw)\n    elif key == ("ai", "technical_remediation"): state.technical_remediation = _parse_bool(raw)\n    elif key == ("web_performance", "enabled"): state.web_performance = _parse_bool(raw)\n',
)
replace(
    "src/rasai/console_settings.py",
    '    parser = ConfigParser(interpolation=None)\n    try:\n        with source.open("r", encoding="utf-8") as stream:\n            parser.read_file(stream)\n',
    '    parser = ConfigParser(interpolation=None)\n    parser.optionxform = str\n    try:\n        with source.open("r", encoding="utf-8") as stream:\n            parser.read_file(stream)\n',
)
replace(
    "src/rasai/console_settings.py",
    '    warnings: list[str] = []\n    for section, values in _state_values(state).items():\n',
    '''    warnings: list[str] = []\n    # Existing process/Windows values have higher precedence than the INI. The INI\n    # fills only missing non-secret variables, making Save -> close -> reopen stable.\n    if parser.has_section("environment"):\n        allowed = set(_known_nonsecret_environment_names())\n        for name, raw in parser.items("environment", raw=True):\n            if name not in allowed:\n                warnings.append(f"environment.{name}: variável não reconhecida ou não persistível")\n                continue\n            if not (os.environ.get(name) or "").strip() and raw.strip():\n                os.environ[name] = raw.strip()\n    for section, values in _state_values(state).items():\n''',
)
replace(
    "src/rasai/console_settings.py",
    'def sync_nonsecret_runtime_environment(state: Any) -> None:\n    """Project effective non-secret console settings into adapter environment."""\n    os.environ[AI_TIMEOUT_ENV] = f"{float(state.ai_timeout):g}"\n    os.environ[WEB_PERFORMANCE_TIMEOUT_ENV] = f"{float(state.web_timeout):g}"\n    registration = get_provider_registration(str(state.ai_provider))\n    if registration is not None and getattr(state, "ai_reasoning", None):\n        variable = provider_reasoning_env(registration.provider_name)\n        if variable:\n            os.environ[variable] = str(state.ai_reasoning).upper()\n',
    '''def sync_nonsecret_runtime_environment(state: Any) -> None:\n    """Project all effective non-secret console settings into adapter environment."""\n    projection = _runtime_environment_projection(state)\n    for name, value in projection.items():\n        if value:\n            os.environ[name] = value\n        else:\n            os.environ.pop(name, None)\n''',
)

# Interactive console exposes both remediations in the same stable menu item.
replace(
    "src/rasai/interactive_console.py",
    '            if value == "none":\n                state.content_remediation = False\n',
    '            if value == "none":\n                state.content_remediation = False\n                state.technical_remediation = False\n',
)
replace(
    "src/rasai/interactive_console.py",
    '    elif choice == "5":\n        capability = provider_capabilities(blocks=state.runtime_blocks)[state.ai_provider]\n        if state.ai_provider == "none" or not capability.available:\n            state.content_remediation = False\n            state.error = "opção 5 requer uma IA configurada e ativa no item 4"\n        else:\n            state.content_remediation = input("Remediação textual IA? Pode gerar chamadas/custo adicionais [s/N]: ").strip().casefold() == "s"\n            state.error = ""\n',
    '''    elif choice == "5":\n        capability = provider_capabilities(blocks=state.runtime_blocks)[state.ai_provider]\n        if state.ai_provider == "none" or not capability.available:\n            state.content_remediation = False\n            state.technical_remediation = False\n            state.error = "opção 5 requer uma IA configurada e ativa no item 4"\n        else:\n            state.content_remediation = input("Remediação de conteúdo por IA? Pode gerar chamadas/custo adicionais [s/N]: ").strip().casefold() == "s"\n            state.technical_remediation = input("Remediação técnica de crawling/discovery por IA? Advisory, pode gerar chamadas/custo adicionais [s/N]: ").strip().casefold() == "s"\n            state.error = ""\n''',
)
replace(
    "src/rasai/interactive_console.py",
    '    if remediation_available:\n        print(f"5. Remediação textual IA : {bool_badge(state.content_remediation)} [DISPONÍVEL - IA ativa no item 4]{badges[\'remediation\']}")\n    else:\n        print("5. Remediação textual IA : " + paint("INDISPONÍVEL", RED, bold=True) + " [REQUER IA CONFIGURADA E ATIVA NO ITEM 4]")\n',
    '''    if remediation_available:\n        print(f"5. Remediações IA        : conteúdo={bool_badge(state.content_remediation)} | técnica crawling={bool_badge(state.technical_remediation)} [DISPONÍVEL - IA ativa no item 4]{badges['remediation']}")\n    else:\n        print("5. Remediações IA        : " + paint("INDISPONÍVEL", RED, bold=True) + " [REQUER IA CONFIGURADA E ATIVA NO ITEM 4]")\n''',
)
replace(
    "src/rasai/interactive_console.py",
    'def _save_configuration(state: State) -> bool:\n    try:\n        path = save_console_config(state, get_config_path(state))\n',
    'def _save_configuration(state: State) -> bool:\n    try:\n        sync_nonsecret_runtime_environment(state)\n        path = save_console_config(state, get_config_path(state))\n',
)

replace(
    "src/rasai/console_help.py",
    '("5. Remediação textual IA", "Ativa sugestões e remediação de conteúdo por IA para findings elegíveis; não altera score/findings.", COST_EXTRA_AI + ": pode acrescentar novas chamadas de IA por contexto elegível."),\n',
    '("5. Remediações IA", "Controla separadamente remediação de conteúdo e remediação técnica advisory de crawling/discovery; nenhuma delas altera score por opinião.", COST_EXTRA_AI + ": cada finalidade habilitada pode acrescentar chamadas externas quando houver contexto elegível."),\n',
)
replace(
    "src/rasai/console_help.py",
    '    "RASAI_AI_CONTENT_REMEDIATION": ("Default da remediação textual por IA.", COST_EXTRA_AI + " quando true e houver provider/casos elegíveis."),\n',
    '    "RASAI_AI_CONTENT_REMEDIATION": ("Default da remediação de conteúdo por IA.", COST_EXTRA_AI + " quando true e houver provider/casos elegíveis."),\n    "RASAI_AI_TECHNICAL_REMEDIATION": ("Default da remediação técnica advisory de crawling/discovery por IA.", COST_EXTRA_AI + " quando true, provider apto e diagnósticos técnicos elegíveis."),\n',
)
replace(
    "src/rasai/console_help.py",
    '        "remediation": " [CUSTO IA ADICIONAL]" if state.content_remediation else "",\n',
    '        "remediation": " [CUSTO IA ADICIONAL]" if (state.content_remediation or getattr(state, "technical_remediation", False)) else "",\n',
)

replace(
    "src/rasai/console_environment.py",
    '        EnvironmentSpec("RASAI_AI_CONTENT_REMEDIATION", "Aplicação e execução", "Default da remediação textual por IA.", "booleano", ("true", "false"), "false", required_when="Só tem efeito com provider de IA apto.", impact="Quando true, pode gerar chamadas/tokens adicionais de IA.", example="RASAI_AI_CONTENT_REMEDIATION=false"),\n',
    '        EnvironmentSpec("RASAI_AI_CONTENT_REMEDIATION", "Aplicação e execução", "Default da remediação de conteúdo por IA.", "booleano", ("true", "false"), "false", required_when="Só tem efeito com provider de IA apto.", impact="Quando true, pode gerar chamadas/tokens adicionais de IA.", example="RASAI_AI_CONTENT_REMEDIATION=false"),\n        EnvironmentSpec("RASAI_AI_TECHNICAL_REMEDIATION", "Aplicação e execução", "Default da remediação técnica advisory de crawling/discovery por IA.", "booleano", ("true", "false"), "false", required_when="Só tem efeito com provider de IA apto e diagnósticos técnicos elegíveis.", impact="Quando true, pode gerar chamada/tokens adicionais de IA; não altera scoring por opinião.", example="RASAI_AI_TECHNICAL_REMEDIATION=false"),\n',
)

# Exposure estimate includes the audit-level technical remediation call budget.
replace(
    "src/rasai/console_cost.py",
    '        if state.content_remediation:\n            max_ai += max_pages * devices * per_context_max\n',
    '        if state.content_remediation:\n            max_ai += max_pages * devices * per_context_max\n        if getattr(state, "technical_remediation", False):\n            max_ai += per_context_max\n',
)
replace(
    "src/rasai/console_cost.py",
    '    if state.content_remediation:\n        reasons.append(\n            "A remediação de conteúdo por IA pode acrescentar tentativas apenas quando houver findings elegíveis."\n        )\n',
    '    if state.content_remediation:\n        reasons.append(\n            "A remediação de conteúdo por IA pode acrescentar tentativas apenas quando houver findings elegíveis."\n        )\n    if getattr(state, "technical_remediation", False):\n        reasons.append(\n            "A remediação técnica de crawling/discovery é audit-level e pode acrescentar tentativas quando houver diagnósticos técnicos elegíveis; permanece advisory/non-scoring."\n        )\n',
)

# ---------------------------------------------------------------------------
# 2. Make robots/sitemap contribution visible in SARI reporting.
# ---------------------------------------------------------------------------
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '        ai_attempts = _many(\n            connection,\n            "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",\n            (audit_id,),\n        )\n        return {\n',
    '        ai_attempts = _many(\n            connection,\n            "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",\n            (audit_id,),\n        )\n        discovery_executions = _many(\n            connection,\n            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN (\'BR-GEO-003\',\'BR-GEO-017\',\'BR-GEO-018\') ORDER BY rule_id,rule_execution_id",\n            (audit_id,),\n        )\n        return {\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '            "ai_attempts": ai_attempts,\n        }\n',
    '            "ai_attempts": ai_attempts,\n            "discovery_executions": discovery_executions,\n        }\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '{_content_context_block(workspace, audit_id)}\n{_provenance_block(data["contributions"])}\n',
    '{_discovery_scoring_block(data)}\n{_content_context_block(workspace, audit_id)}\n{_provenance_block(data["contributions"])}\n',
)
insert_anchor = 'def _provenance_block(contributions: list[sqlite3.Row]) -> str:\n'
insert_value = '''def _discovery_scoring_block(data: dict[str, Any]) -> str:\n    labels = {\n        "BR-GEO-003": "Sitemap disponível: aquisição e interpretação",\n        "BR-GEO-017": "robots.txt presente: interpretabilidade",\n        "BR-GEO-018": "Acesso de crawlers configurados",\n    }\n    executions = data.get("discovery_executions", [])\n    contributions = [row for row in data.get("contributions", []) if str(row["rule_id"]) in labels]\n    rows: list[str] = []\n    for rule_id, label in labels.items():\n        rule_execs = [row for row in executions if str(row["rule_id"]) == rule_id]\n        results = sorted({str(row["result"]) for row in rule_execs}) or ["NÃO EXECUTADO"]\n        represented = [row for row in contributions if str(row["rule_id"]) == rule_id]\n        if represented:\n            devices = ", ".join(sorted({str(row["device"]).upper() for row in represented}))\n            factors = ", ".join(sorted({"-" if row["result_factor"] is None else f"{float(row['result_factor']):g}" for row in represented}))\n            role = f"Contribuição persistida no score ({devices}); fator={factors}"\n        elif rule_id in {"BR-GEO-017", "BR-GEO-018"}:\n            role = "Avaliado dentro do grupo ROBOTS; SCORE-GEO-004 persiste como contribuição a regra representativa mais restritiva do grupo por dispositivo."\n        else:\n            role = "Avaliado; sem contribuição representativa persistida neste audit."\n        rows.append(\n            "<tr>"\n            f"<td><code>{rule_id}</code></td><td>{escape(label)}</td>"\n            f"<td>{escape(', '.join(results))}</td><td>Technical Accessibility</td><td>{escape(role)}</td></tr>"\n        )\n    return (\n        "<section class='panel' id='discovery-scoring-inputs'><div class='kicker'>SARI - inputs técnicos de descoberta</div>"\n        "<h2>robots.txt, sitemap e acesso de crawlers no SCORE-GEO-004</h2>"\n        "<p class='intro'>Estes sinais não são apenas diagnóstico do relatório de crawling. BR-GEO-003, BR-GEO-017 e BR-GEO-018 são avaliados deterministicamente e alimentam a dimensão Technical Accessibility. BR-GEO-017/018 compartilham o grupo de scoring ROBOTS para evitar peso duplicado do mesmo fenômeno.</p>"\n        "<div class='table-wrap'><table><thead><tr><th>Regra</th><th>Sinal</th><th>Resultado persistido</th><th>Dimensão</th><th>Papel no score</th></tr></thead><tbody>"\n        + "".join(rows) + "</tbody></table></div><p><a href='crawling-discovery.html'>Abrir diagnóstico aprofundado de rastreamento e descoberta →</a></p></section>"\n    )\n\n\n'''
replace("src/rasai/rasai_readiness_reporting.py", insert_anchor, insert_value + insert_anchor)

# M24 language: the advisory layer is outside the score, but the base deterministic rules are not.
replace(
    "src/rasai/m24_reporting.py",
    '<footer class=\'footer\'>M24-CD-001 · projeção somente de dados persistidos e artifacts; sem impacto no Search & AI Readiness Index.</footer>',
    '<footer class=\'footer\'>M24-CD-001 · os diagnósticos aprofundados desta página são advisory/non-scoring. As regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 permanecem inputs do SARI-001 via SCORE-GEO-004.</footer>',
)
replace(
    "src/rasai/m24_reporting.py",
    '<div class=\'kicker\'>Remediação técnica opcional por IA</div><h2>Telemetria e limites</h2>',
    '<div class=\'kicker\'>IA técnica de crawling/discovery (opcional)</div><h2>Telemetria e limites da remediação técnica</h2>',
)
replace(
    "src/rasai/m24_reporting.py",
    '<p><strong>Artifact:</strong> <code>{escape(artifact)}</code></p></section>',
    '<p><strong>Artifact:</strong> <code>{escape(artifact)}</code></p><p><a href=\'content-suggestions.html\'>Ver separadamente a remediação de conteúdo por IA →</a></p></section>',
)
replace(
    "src/rasai/m24_reporting.py",
    "<p class='intro'>Rastreamento, descoberta e acesso de crawlers usa referências públicas para os fenômenos técnicos, mas permanece fora do SCORE-GEO-004/SARI-001. llms.txt é explicitamente identificado como proposta comunitária.</p>",
    "<p class='intro'>Os diagnósticos M24 aprofundados permanecem advisory/non-scoring. Separadamente, as regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 já alimentam SCORE-GEO-004/SARI-001. llms.txt é explicitamente identificado como proposta comunitária.</p>",
)

# ---------------------------------------------------------------------------
# 3. Apdex browser diagnostics: per sample + grouped whole-test summary.
# ---------------------------------------------------------------------------
replace(
    "src/rasai/m23_apdex_profiles.py",
    '    network_method: str | None\n\n\nclass SyntheticNavigationGateway',
    '    network_method: str | None\n    browser_diagnostics: tuple[dict[str, str], ...] = ()\n\n\nclass SyntheticNavigationGateway',
)
# add empty browser diagnostics to early unavailable result
replace(
    "src/rasai/m23_apdex_profiles.py",
    '                network_method=None,\n            )\n\n        context = page = session = None\n',
    '                network_method=None,\n                browser_diagnostics=(),\n            )\n\n        context = page = session = None\n',
)
replace(
    "src/rasai/m23_apdex_profiles.py",
    '        context = page = session = None\n        cpu_method = network_method = None\n        try:\n',
    '        context = page = session = None\n        cpu_method = network_method = None\n        browser_diagnostics: list[dict[str, str]] = []\n        try:\n',
)
replace(
    "src/rasai/m23_apdex_profiles.py",
    '            context = self._browser.new_context(**context_options)\n            page = context.new_page()\n            session = context.new_cdp_session(page)\n',
    '''            context = self._browser.new_context(**context_options)\n            page = context.new_page()\n\n            def record(kind: str, message: str | None, url_value: str | None = None) -> None:\n                if len(browser_diagnostics) >= 60:\n                    return\n                item = {"type": kind, "message": _bounded(message or "", 512) or "-"}\n                if url_value:\n                    item["url"] = _bounded(url_value, 512) or "-"\n                browser_diagnostics.append(item)\n\n            page.on("console", lambda message: record("CONSOLE_ERROR", message.text) if str(message.type).lower() == "error" else None)\n            page.on("pageerror", lambda error: record("PAGE_ERROR", str(error)))\n            page.on("requestfailed", lambda request: record("REQUEST_FAILED", str(request.failure or "request failed"), request.url))\n            session = context.new_cdp_session(page)\n''',
)
# successful, timeout and navigation error returns
replace(
    "src/rasai/m23_apdex_profiles.py",
    '                    network_method=network_method,\n                )\n            except PlaywrightTimeoutError:',
    '                    network_method=network_method,\n                    browser_diagnostics=tuple(browser_diagnostics),\n                )\n            except PlaywrightTimeoutError:',
)
replace(
    "src/rasai/m23_apdex_profiles.py",
    '                    network_method=network_method,\n                )\n            except PlaywrightError as exc:',
    '                    network_method=network_method,\n                    browser_diagnostics=tuple(browser_diagnostics),\n                )\n            except PlaywrightError as exc:',
)
replace(
    "src/rasai/m23_apdex_profiles.py",
    '                    network_method=network_method,\n                )\n        except PlaywrightError as exc:',
    '                    network_method=network_method,\n                    browser_diagnostics=tuple(browser_diagnostics),\n                )\n        except PlaywrightError as exc:',
)
# invalid profile helper remains empty by default due dataclass default.

replace(
    "src/rasai/m23_persistence.py",
    '    network_method: str | None\n    cache_policy: str\n',
    '    network_method: str | None\n    browser_diagnostics: dict[str, Any]\n    cache_policy: str\n',
)
replace(
    "src/rasai/m23_persistence.py",
    '                    network_method TEXT,\n                    cache_policy TEXT NOT NULL,\n',
    '                    network_method TEXT,\n                    browser_diagnostics TEXT NOT NULL DEFAULT \'{}\',\n                    cache_policy TEXT NOT NULL,\n',
)
# migration for an existing development DB
replace(
    "src/rasai/m23_persistence.py",
    '                """\n            )\n\n    def upsert_run',
    '                """\n            )\n            columns = {row[1] for row in self.connection.execute("PRAGMA table_info(synthetic_apdex_samples)")}\n            if "browser_diagnostics" not in columns:\n                self.connection.execute("ALTER TABLE synthetic_apdex_samples ADD COLUMN browser_diagnostics TEXT NOT NULL DEFAULT \'{}\'")\n\n    def upsert_run',
)
replace(
    "src/rasai/m23_persistence.py",
    '                "INSERT OR REPLACE INTO synthetic_apdex_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n                (\n                    item.sample_id, item.audit_id, item.page_id, item.snapshot_id,\n                    item.device, item.url, item.run_index, item.task_id, item.profile_id,\n                    item.profile_version, item.status, item.classification, item.duration_ms,\n                    item.http_status, item.final_url, item.error_code, item.error_message,\n                    item.cpu_method, item.network_method, item.cache_policy, item.captured_at,\n                ),\n',
    '''                """INSERT OR REPLACE INTO synthetic_apdex_samples(\n                    sample_id,audit_id,page_id,snapshot_id,device,url,run_index,task_id,profile_id,\n                    profile_version,status,classification,duration_ms,http_status,final_url,error_code,\n                    error_message,cpu_method,network_method,browser_diagnostics,cache_policy,captured_at\n                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",\n                (\n                    item.sample_id, item.audit_id, item.page_id, item.snapshot_id,\n                    item.device, item.url, item.run_index, item.task_id, item.profile_id,\n                    item.profile_version, item.status, item.classification, item.duration_ms,\n                    item.http_status, item.final_url, item.error_code, item.error_message,\n                    item.cpu_method, item.network_method, _dump(item.browser_diagnostics),\n                    item.cache_policy, item.captured_at,\n                ),\n''',
)
replace(
    "src/rasai/m23_apdex.py",
    '            network_method=item.measurement.network_method,\n            cache_policy="COLD_CONTEXT",\n',
    '            network_method=item.measurement.network_method,\n            browser_diagnostics={"events": list(item.measurement.browser_diagnostics)},\n            cache_policy="COLD_CONTEXT",\n',
)

# Reporting: grouped whole-test summary, per-sample browser diagnostics and explicit non-causality.
replace(
    "src/rasai/m23_reporting.py",
    '    details = "".join(\n',
    '    browser_diagnostics = _browser_diagnostics_overview(samples)\n    details = "".join(\n',
)
replace(
    "src/rasai/m23_reporting.py",
    "</table></div></section><section class='panel'><div class='kicker'>Diagnóstico aprofundado</div>",
    "</table></div></section>{browser_diagnostics}<section class='panel'><div class='kicker'>Diagnóstico aprofundado</div>",
)
replace(
    "src/rasai/m23_reporting.py",
    "<details><summary>Ver todas as {len(samples)} tentativas/amostras persistidas</summary><div class='table-wrap'><table><thead><tr><th>#</th><th>Duração</th><th>Classe</th><th>Status</th><th>HTTP</th><th>Erro</th><th>CPU</th><th>Rede</th></tr></thead><tbody>{table_rows or '<tr><td colspan=\"8\">Sem amostras.</td></tr>'}</tbody></table></div></details></article>",
    "<details><summary>Ver todas as {len(samples)} tentativas/amostras persistidas</summary><div class='table-wrap'><table><thead><tr><th>#</th><th>Duração</th><th>Classe</th><th>Status</th><th>HTTP</th><th>Erro</th><th>Browser/console observado</th><th>CPU</th><th>Rede</th></tr></thead><tbody>{table_rows or '<tr><td colspan=\"9\">Sem amostras.</td></tr>'}</tbody></table></div></details></article>",
)
replace(
    "src/rasai/m23_reporting.py",
    'def _sample_row(row: sqlite3.Row) -> str:\n    return (\n',
    '''def _browser_events(row: sqlite3.Row) -> list[dict[str, str]]:\n    try:\n        raw = row["browser_diagnostics"]\n    except (IndexError, KeyError):\n        return []\n    if not raw:\n        return []\n    try:\n        parsed = json.loads(str(raw))\n    except (TypeError, ValueError, json.JSONDecodeError):\n        return []\n    events = parsed.get("events", []) if isinstance(parsed, dict) else []\n    return [item for item in events if isinstance(item, dict)]\n\n\ndef _browser_diagnostic_key(item: dict[str, str]) -> tuple[str, str, str]:\n    return (str(item.get("type") or "OTHER"), str(item.get("message") or "-"), str(item.get("url") or ""))\n\n\ndef _browser_diagnostic_severity(kind: str) -> str:\n    return {"PAGE_ERROR": "ALTA", "REQUEST_FAILED": "MÉDIA", "CONSOLE_ERROR": "REVISÃO"}.get(kind, "REVISÃO")\n\n\ndef _browser_diagnostics_overview(samples: list[sqlite3.Row]) -> str:\n    grouped: dict[tuple[str, str, str], set[int]] = defaultdict(set)\n    for row in samples:\n        for item in _browser_events(row):\n            grouped[_browser_diagnostic_key(item)].add(int(row["run_index"]))\n    if not grouped:\n        return "<section class='panel'><div class='kicker'>Browser diagnostics</div><h2>Console e falhas observadas durante as navegações</h2><p class='intro'>Nenhum console.error, page error ou requestfailed foi persistido nas amostras deste teste.</p></section>"\n    rows: list[str] = []\n    for (kind, message, url), runs in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1])):\n        location = url or "-"\n        rows.append(\n            f"<tr><td>{escape(kind)}</td><td>{escape(_browser_diagnostic_severity(kind))}</td><td>{len(runs)}</td>"\n            f"<td>{escape(', '.join(str(value) for value in sorted(runs)))}</td><td class='mono'>{escape(message)}</td><td class='mono'>{escape(location)}</td></tr>"\n        )\n    return (\n        "<section class='panel'><div class='kicker'>Browser diagnostics · teste completo</div><h2>Erros de console e browser agrupados</h2>"\n        "<p class='intro'>Os eventos abaixo são associados temporalmente à amostra em que ocorreram. Eles ajudam a investigação de experiência, mas não são tratados como causa comprovada da duração nem derrubam o Apdex por si só. Apenas application error, timeout e navigation error continuam alterando a classificação Apdex.</p>"\n        "<div class='table-wrap'><table><thead><tr><th>Tipo</th><th>Criticidade diagnóstica</th><th>Amostras afetadas</th><th># amostras</th><th>Mensagem</th><th>URL/recurso</th></tr></thead><tbody>"\n        + "".join(rows) + "</tbody></table></div></section>"\n    )\n\n\ndef _sample_browser_diagnostics(row: sqlite3.Row) -> str:\n    events = _browser_events(row)\n    if not events:\n        return "-"\n    grouped: dict[tuple[str, str, str], int] = {}\n    for item in events:\n        key = _browser_diagnostic_key(item)\n        grouped[key] = grouped.get(key, 0) + 1\n    items = "".join(\n        f"<li><strong>{escape(kind)}</strong> ×{count}: {escape(message)}"\n        + (f" <span class='mono'>{escape(url)}</span>" if url else "") + "</li>"\n        for (kind, message, url), count in grouped.items()\n    )\n    return f"<details class='browser-diagnostics'><summary>{len(events)} evento(s)</summary><ul>{items}</ul></details>"\n\n\ndef _sample_row(row: sqlite3.Row) -> str:\n    return (\n''',
)
replace(
    "src/rasai/m23_reporting.py",
    '        f"<td>{escape(str(row[\'error_code\'] or \'-\'))}</td>"\n        f"<td>{escape(str(row[\'cpu_method\'] or \'-\'))}</td>"\n',
    '        f"<td>{escape(str(row[\'error_code\'] or \'-\'))}</td>"\n        f"<td>{_sample_browser_diagnostics(row)}</td>"\n        f"<td>{escape(str(row[\'cpu_method\'] or \'-\'))}</td>"\n',
)
replace(
    "src/rasai/m23_reporting.py",
    '.apdex-card{margin-bottom:18px}.apdex-card details{margin-top:14px}\n',
    '.apdex-card{margin-bottom:18px}.apdex-card details{margin-top:14px}.browser-diagnostics{margin:0;min-width:220px}.browser-diagnostics summary{padding:5px 7px}.browser-diagnostics ul{margin:.4rem 0;padding-left:1rem;max-width:none}\n',
)

# ---------------------------------------------------------------------------
# 4. Report CSS and executive indicator hierarchy.
# ---------------------------------------------------------------------------
replace(
    "src/rasai/report_site.py",
    'p{margin:.55rem 0}.lead,.intro{max-width:84ch;color:#4b5565}\n',
    'p{margin:.55rem 0}.lead,.intro{max-width:100%;width:100%;color:#4b5565}\n',
)
replace(
    "src/rasai/report_navigation.py",
    '.app-main{max-width:1560px;padding:32px clamp(20px,3vw,42px) 60px}.app-main>*{width:min(100%,1280px);margin-left:auto;margin-right:auto}\n',
    '.app-main{max-width:1720px;padding:32px clamp(20px,3vw,42px) 60px}.app-main>*{width:100%;max-width:100%;margin-left:auto;margin-right:auto}\n',
)
replace(
    "src/rasai/report_navigation.py",
    'strong{font-weight:640}.lead,.intro,.hero>p,.panel>p,.page-card>p,.detail-body>p,.notice>p{max-width:78ch}\n.panel ul,.panel ol,.detail-body ul,.detail-body ol{max-width:84ch}\n',
    'strong{font-weight:640}.lead,.intro,.hero>p,.panel>p,.page-card>p,.detail-body>p,.notice>p{max-width:100%;width:100%}\n.panel ul,.panel ol,.detail-body ul,.detail-body ol{max-width:100%;width:100%;padding-right:clamp(4px,1vw,14px)}\n',
)
replace(
    "src/rasai/report_navigation.py",
    'pre{background:#2f394a;color:#edf1f7;border-radius:9px}.footer{max-width:78ch}\n',
    'pre{background:#2f394a;color:#edf1f7;border-radius:9px}.footer{max-width:100%;width:100%}\n',
)

# Dashboard markup: SARI in a primary tier, four complementary indicators in a balanced second tier.
replace(
    "src/rasai/rasai_readiness_reporting.py",
    'def _dashboard(data: dict[str, Any], report_dir: Path) -> str:\n    cards: list[str] = []\n',
    'def _dashboard(data: dict[str, Any], report_dir: Path) -> str:\n    sari_cards: list[str] = []\n    cards: list[str] = []\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '        cards.append(_indicator_card(\n            f"Search & AI Readiness - {label}", value, detail, RASAI_FILE,\n            "RASAi - SARI-001", condition, condition_label,\n        ))\n',
    '        sari_cards.append(_indicator_card(\n            f"Search & AI Readiness - {label}", value, detail, RASAI_FILE,\n            "RASAi - SARI-001", condition, condition_label, primary=True,\n        ))\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '        + f"<div class=\'grid indicator-grid\'>{\'\'.join(cards)}</div></section>"\n',
    '        + "<div class=\'indicator-tier-label\'>Índice proprietário de readiness</div>"\n        + f"<div class=\'indicator-primary-grid\'>{\'\'.join(sari_cards) if sari_cards else \"<div class=\'notice warn\'>SARI-001 não disponível.</div>\"}</div>"\n        + "<div class=\'indicator-tier-label indicator-tier-supporting\'>Indicadores complementares - independentes do SARI-001</div>"\n        + f"<div class=\'grid indicator-grid indicator-supporting-grid\'>{\'\'.join(cards)}</div></section>"\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '    condition_label: str = "Informativo",\n) -> str:\n',
    '    condition_label: str = "Informativo",\n    primary: bool = False,\n) -> str:\n',
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '        f"<article class=\'ref-card indicator-card condition-{escape(condition, quote=True)}\'>"\n',
    '        f"<article class=\'ref-card indicator-card {\'indicator-primary\' if primary else \'indicator-supporting\'} condition-{escape(condition, quote=True)}\'>"\n',
)

replace(
    "src/rasai/report_semantics.py",
    '.indicator-grid{grid-template-columns:repeat(auto-fit,minmax(280px,1fr));align-items:stretch}.indicator-card{display:flex;flex-direction:column;min-width:0}.indicator-card h3{font-size:1rem;line-height:1.25;min-height:2.5em}.indicator-card .intro{font-size:.88rem}.indicator-score{font-size:clamp(1.35rem,2.3vw,2rem)!important;line-height:1.08;overflow-wrap:normal;word-break:normal;white-space:nowrap}.indicator-values{display:flex;gap:12px;flex-wrap:wrap;margin:.45rem 0}.indicator-device{display:flex;flex-direction:column;gap:2px;min-width:92px}.indicator-device small{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em}.indicator-device strong{font-size:clamp(1.25rem,2vw,1.8rem);line-height:1.05;white-space:nowrap}.indicator-condition',
    '.indicator-tier-label{margin:.85rem 0 .45rem;color:var(--muted);font-size:.72rem;font-weight:760;text-transform:uppercase;letter-spacing:.07em}.indicator-tier-supporting{margin-top:1.1rem}.indicator-primary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:12px;align-items:stretch}.indicator-grid{grid-template-columns:repeat(4,minmax(0,1fr));align-items:stretch}.indicator-card{display:flex;flex-direction:column;min-width:0}.indicator-card.indicator-primary{min-height:0}.indicator-card h3{font-size:1rem;line-height:1.25;min-height:2.5em}.indicator-primary h3{min-height:auto}.indicator-card .intro{font-size:.88rem;max-width:100%}.indicator-score{font-size:clamp(1.5rem,2vw,1.9rem)!important;line-height:1.06;overflow-wrap:normal;word-break:normal;white-space:nowrap}.indicator-values{display:flex;gap:12px;flex-wrap:wrap;margin:.45rem 0}.indicator-device{display:flex;flex-direction:column;gap:2px;min-width:92px}.indicator-device small{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em}.indicator-device strong{font-size:clamp(1.5rem,2vw,1.9rem);line-height:1.06;white-space:nowrap}.indicator-condition',
)
replace(
    "src/rasai/report_semantics.py",
    '@media(max-width:700px){.result-tag,.priority-tag{white-space:normal}.priority-tag{margin-left:0;margin-top:4px}}\n',
    '@media(max-width:1120px){.indicator-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n@media(max-width:700px){.indicator-grid,.indicator-primary-grid{grid-template-columns:1fr}.result-tag,.priority-tag{white-space:normal}.priority-tag{margin-left:0;margin-top:4px}}\n',
)

# ---------------------------------------------------------------------------
# 5. Documentation and regression tests.
# ---------------------------------------------------------------------------
for path, addition in {
    "docs/CONFIGURATION.md": """\n\n## Persistência do console e precedência de configuração\n\nO console usa `rasai-console.ini` (ou o caminho indicado por `RASAI_CONSOLE_INI`) como contrato persistente de parâmetros não sensíveis. Ao salvar, o RASAi grava o estado operacional e uma seção `[environment]` com variáveis reconhecidas não secretas. Chaves, tokens, passwords e credenciais continuam fora do INI.\n\nNa inicialização, a ordem é: valor já presente no processo/Windows > valor persistido em `[environment]` > valor persistido nas seções funcionais do INI > default. O INI é lido antes da execução e seus valores não secretos são projetados novamente para o ambiente dos adapters. Assim, `RASAI_AI_CONTENT_REMEDIATION`, `RASAI_AI_TECHNICAL_REMEDIATION`, Web Performance, timeouts, modelo/reasoning selecionados e Synthetic Navigation Apdex sobrevivem a Save -> fechar -> reabrir.\n\n`RASAI_AI_CONTENT_REMEDIATION` controla conteúdo. `RASAI_AI_TECHNICAL_REMEDIATION` controla somente a remediação técnica advisory de crawling/discovery. Nenhuma das duas eleva SARI/Confidence por opinião da IA.\n""",
    "docs/INTERACTIVE_CONSOLE.md": """\n\n## Save, fechamento e restauração\n\nSalvar a configuração materializa todos os parâmetros não sensíveis reconhecidos no INI. A seção `[environment]` preserva overrides editados pelo menu de variáveis; secrets permanecem exclusivamente na sessão/Windows User. Ao reabrir, o console lê o INI antes de montar o estado efetivo e reaplica os parâmetros aos adapters. Uma variável exibida como ligada durante a sessão não deve voltar ao default após reinício quando ela é persistível e o usuário executou **Salvar configuração INI**.\n\nO item de remediações IA mostra separadamente **conteúdo** (`RASAI_AI_CONTENT_REMEDIATION`) e **técnica crawling/discovery** (`RASAI_AI_TECHNICAL_REMEDIATION`).\n""",
    "docs/SCORING_GUIDE.md": """\n\n### Transparência de robots.txt e sitemap no SARI\n\nA página canônica **Search & AI Readiness** expõe uma seção `SARI - inputs técnicos de descoberta` com BR-GEO-003, BR-GEO-017 e BR-GEO-018, seus resultados persistidos e o papel efetivo no score. BR-GEO-017 e BR-GEO-018 compartilham o grupo `ROBOTS`, portanto o SCORE-GEO-004 usa a regra representativa mais restritiva do grupo por dispositivo para evitar peso duplicado. Os diagnósticos aprofundados M24 continuam advisory/non-scoring; isso não remove a participação das regras determinísticas básicas no SARI.\n""",
    "docs/SYNTHETIC_APDEX.md": """\n\n## Console/browser diagnostics por amostra\n\nSynthetic Navigation Apdex persiste, de forma limitada e sem response bodies, `console.error`, `pageerror` e `requestfailed` observados durante cada navegação. O HTML lista esses eventos por amostra e também os agrupa para o teste completo por tipo/mensagem/recurso e quantidade de amostras afetadas. Essa associação é temporal e diagnóstica: um console error não é tratado automaticamente como causa da duração e não reduz o Apdex por si só. Somente application error, timeout e navigation error continuam alterando a classificação Apdex.\n""",
}.items():
    value = text(path)
    marker = addition.strip().splitlines()[0]
    if marker not in value:
        write(path, value.rstrip() + addition + "\n")

# Permanent regression coverage.
test_path = ROOT / "tests/test_post_smoke_adherence_20260908.py"
test_path.write_text(r'''from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.console_config import State as BaseState, build_command
from rasai.console_m23 import State
from rasai.console_settings import load_console_config, save_console_config
from rasai.m23_apdex_profiles import NavigationMeasurement
from rasai.m23_persistence import M23Persistence
from rasai.persistence import AuditWorkspace


def test_ini_roundtrip_restores_nonsecret_environment_and_both_remediations(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "rasai-console.ini"
    state = State()
    state.ai_provider = "none"
    state.content_remediation = True
    state.technical_remediation = True
    state.web_performance = True
    state.synthetic_apdex = True
    state.apdex_threshold = 2.5
    state.apdex_samples = 100
    monkeypatch.setenv("RASAI_OPENAI_REASONING_EFFORT", "LOW")
    save_console_config(state, path)
    payload = path.read_text(encoding="utf-8")
    assert "[environment]" in payload
    assert "RASAI_AI_CONTENT_REMEDIATION = true" in payload
    assert "RASAI_AI_TECHNICAL_REMEDIATION = true" in payload
    assert "RASAI_APDEX_THRESHOLD_SECONDS = 2.5" in payload
    assert "API_KEY" not in payload

    for name in ("RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", "RASAI_APDEX_THRESHOLD_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    restored = State()
    result = load_console_config(restored, path)
    assert not result.warnings
    assert restored.content_remediation is True
    assert restored.technical_remediation is True
    assert os.environ["RASAI_AI_CONTENT_REMEDIATION"] == "true"
    assert os.environ["RASAI_AI_TECHNICAL_REMEDIATION"] == "true"
    assert os.environ["RASAI_APDEX_THRESHOLD_SECONDS"] == "2.5"


def test_build_command_explicitly_propagates_technical_remediation() -> None:
    state = BaseState(target="https://example.com", content_remediation=True, technical_remediation=True)
    command = build_command(state)
    assert "--ai-content-remediation" in command
    assert "--ai-technical-remediation" in command


def test_navigation_measurement_has_browser_diagnostics_contract() -> None:
    item = NavigationMeasurement(
        status="SUCCESS", duration_ms=100, http_status=200, final_url="https://example.com/",
        error_code=None, error_message=None, profile_applied=True, cpu_method="cpu", network_method="net",
        browser_diagnostics=({"type": "CONSOLE_ERROR", "message": "boom"},),
    )
    assert item.browser_diagnostics[0]["type"] == "CONSOLE_ERROR"


def test_report_sources_expose_discovery_scoring_and_balanced_dashboard() -> None:
    readiness = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    semantics = Path("src/rasai/report_semantics.py").read_text(encoding="utf-8")
    premium = Path("src/rasai/report_navigation.py").read_text(encoding="utf-8")
    assert "SARI - inputs técnicos de descoberta" in readiness
    assert "BR-GEO-003" in readiness and "BR-GEO-017" in readiness and "BR-GEO-018" in readiness
    assert "indicator-primary-grid" in readiness
    assert "indicator-supporting-grid" in readiness
    assert "repeat(4,minmax(0,1fr))" in semantics
    assert "max-width:100%;width:100%" in premium


def test_apdex_reporting_groups_browser_diagnostics_without_claiming_causality() -> None:
    source = Path("src/rasai/m23_reporting.py").read_text(encoding="utf-8")
    assert "Erros de console e browser agrupados" in source
    assert "não são tratados como causa comprovada" in source
    assert "CONSOLE_ERROR" in source and "REQUEST_FAILED" in source and "PAGE_ERROR" in source


def test_m24_copy_separates_advisory_layer_from_scored_base_rules() -> None:
    source = Path("src/rasai/m24_reporting.py").read_text(encoding="utf-8")
    assert "BR-GEO-003, BR-GEO-017 e BR-GEO-018 permanecem inputs do SARI-001" in source
    assert "IA técnica de crawling/discovery" in source
''', encoding="utf-8", newline="\n")

print("post-smoke remediation patches applied")
