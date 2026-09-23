"""Human-facing labels and shared visual helpers."""
from rasai.catalog_report_model import *  # noqa: F401,F403
from rasai.time_contract import localize_html_timestamps
from rasai.catalog_report_public_labels import public_label, public_text
from rasai.report_presentation import public_label as common_public_label

_EMPTY = "-"
_RICH_TOKEN_RE = re.compile(
    r"(\[[^\]\n]+\]\(https?://[^)\s]+\)|`[^`\n]+`|https?://[^\s<>()]+)",
    re.I,
)

def _ui_text(value: Any) -> str:
    return str(value or "").replace("\u2014", "-")


def _translated_text(pt_br: Any, original: Any) -> _Html:
    translated = _ui_text(pt_br or _EMPTY)
    source = str(original or "").strip()
    if not source or translated.casefold() == source.casefold():
        return _Html(escape(translated))
    return _Html(
        escape(translated)
        + " <span class='translation-mark' title='"
        + escape(source, quote=True)
        + "' aria-label='Tradução; texto original: "
        + escape(source, quote=True)
        + "'>🌐</span>"
    )

def _internal_value_label(value: Any) -> _Html | None:
    raw = str(value or "").strip()
    label = public_label(raw)
    return _Html(escape(label)) if label else None

def _rich_text(value: Any) -> _Html:
    if isinstance(value, _Html):
        return value
    text = _ui_text(value).strip()
    if not text or text == "-":
        return _Html(_EMPTY)
    internal = _internal_value_label(text)
    if internal is not None:
        return internal
    out: list[str] = []
    cursor = 0
    for match in _RICH_TOKEN_RE.finditer(text):
        out.append(escape(public_text(text[cursor:match.start()])))
        token = match.group(0)
        markdown = re.fullmatch(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", token, re.I)
        if markdown:
            label, href = markdown.group(1), markdown.group(2)
            out.append(
                "<a class='external-link' href='" + escape(href, quote=True)
                + "' target='_blank' rel='noopener noreferrer'>"
                + escape(label) + " ↗</a>"
            )
        elif token.startswith("`") and token.endswith("`"):
            out.append("<code>" + escape(token[1:-1]) + "</code>")
        else:
            href = token
            trailing = ""
            while href and href[-1] in ".,;:":
                trailing = href[-1] + trailing
                href = href[:-1]
            out.append(
                "<a class='external-link' href='" + escape(href, quote=True)
                + "' target='_blank' rel='noopener noreferrer'>"
                + escape(href) + " ↗</a>" + escape(trailing)
            )
        cursor = match.end()
    out.append(escape(public_text(text[cursor:])))
    return _Html("".join(out).replace("\n", "<br>"))

_PLAIN_STATE_LABELS = {
    "automático": ("Automático","neutral"),
    "automática": ("Automático","neutral"),
    "auto": ("Automático","neutral"),
    "não aplicável": ("Não aplicável","neutral"),
    "nao aplicavel": ("Não aplicável","neutral"),
    "not applicable": ("Não aplicável","neutral"),
    "não determinado": ("Não determinado","neutral"),
    "não determinada": ("Não determinada","neutral"),
    "nao determinado": ("Não determinado","neutral"),
    "nao determinada": ("Não determinada","neutral"),
    "indeterminado": ("Indeterminado","neutral"),
    "indeterminada": ("Indeterminada","neutral"),
    "não determinável": ("Não determinável","neutral"),
    "nao determinavel": ("Não determinável","neutral"),
    "não determinável com os dados desta auditoria": ("Não determinável com os dados desta auditoria","neutral"),
    "não solicitado": ("Não solicitado","neutral"),
    "nao solicitado": ("Não solicitado","neutral"),
    "não solicitada": ("Não solicitada","neutral"),
    "nao solicitada": ("Não solicitada","neutral"),
    "não habilitado": ("Não habilitado","neutral"),
    "nao habilitado": ("Não habilitado","neutral"),
    "não habilitada": ("Não habilitada","neutral"),
    "nao habilitada": ("Não habilitada","neutral"),
    "não definida": ("Não definida","neutral"),
    "nao definida": ("Não definida","neutral"),
    "desabilitado": ("Desabilitado","neutral"),
    "desabilitada": ("Desabilitada","neutral"),
    "ignorado": ("Ignorado","neutral"),
    "não encontrado": ("Não encontrado","neutral"),
    "nao encontrado": ("Não encontrado","neutral"),
    "não encontrada": ("Não encontrada","neutral"),
    "nao encontrada": ("Não encontrada","neutral"),
    "informativo": ("Informativo","neutral"),
    "criado": ("Criado","neutral"),
    "cancelado": ("Cancelado","neutral"),
    "não observado": ("Não observado","neutral"),
    "nao observado": ("Não observado","neutral"),
    "não comparável": ("Não comparável","neutral"),
    "nao comparavel": ("Não comparável","neutral"),
    "sem amostra": ("Sem amostra","neutral"),
    "não disponível": ("Não disponível","bad"),
    "nao disponivel": ("Não disponível","bad"),
    "indisponível": ("Indisponível","bad"),
    "indisponivel": ("Indisponível","bad"),
    "dados indisponíveis": ("Dados indisponíveis","bad"),
    "dados indisponiveis": ("Dados indisponíveis","bad"),
    "sem evidência": ("Sem evidência","warn"),
    "sem evidencia": ("Sem evidência","warn"),
    "sem dados": ("Sem dados","neutral"),
    "sem dados disponíveis": ("Sem dados disponíveis","bad"),
    "sem dados disponiveis": ("Sem dados disponíveis","bad"),
    "não executado": ("Não executado","neutral"),
    "nao executado": ("Não executado","neutral"),
    "não executada": ("Não executada","neutral"),
    "nao executada": ("Não executada","neutral"),
    "não elegível": ("Não elegível","neutral"),
    "nao elegivel": ("Não elegível","neutral"),
    "desabilitado para esta aud": ("Desabilitado para esta AUD","neutral"),
    "não materializado": ("Não materializado","warn"),
    "não materializada": ("Não materializada","warn"),
    "nao materializado": ("Não materializado","warn"),
    "nao materializada": ("Não materializada","warn"),
    "executado sem dados": ("Executado sem dados","warn"),
    "sem resultado": ("Sem resultado","warn"),
    "dados insuficientes": ("Dados insuficientes","warn"),
    "não configurado": ("Não configurado","warn"),
    "nao configurado": ("Não configurado","warn"),
    "não configurada": ("Não configurada","warn"),
    "nao configurada": ("Não configurada","warn"),
    "concluído": ("Concluído","good"),
    "concluido": ("Concluído","good"),
    "aprovado": ("Aprovado","good"),
    "válido": ("Válido","good"),
    "valido": ("Válido","good"),
    "coerente": ("Coerente","good"),
    "consistente": ("Consistente","good"),
    "alinhado": ("Alinhado","good"),
    "satisfatória": ("Satisfatória","good"),
    "satisfatoria": ("Satisfatória","good"),
    "bom": ("Bom","good"),
    "consolidado": ("Consolidado","good"),
    "disponível": ("Disponível","good"),
    "disponivel": ("Disponível","good"),
    "medido": ("Medido","good"),
    "gerado": ("Gerado","good"),
    "pronto": ("Pronto","good"),
    "ok": ("OK","good"),
    "executado com dados": ("Executado com dados","good"),
    "interpretado": ("Interpretado","good"),
    "íntegro - sha-256 confere": ("Íntegro - SHA-256 confere","good"),
    "integro - sha-256 confere": ("Íntegro - SHA-256 confere","good"),
    "atenção": ("Atenção","warn"),
    "atencao": ("Atenção","warn"),
    "parcial": ("Parcial","warn"),
    "precisa melhorar": ("Precisa melhorar","warn"),
    "tolerável": ("Tolerável","warn"),
    "toleravel": ("Tolerável","warn"),
    "pendente": ("Pendente","warn"),
    "incompleto": ("Incompleto","warn"),
    "preliminar": ("Preliminar","warn"),
    "inicializando": ("Inicializando","warn"),
    "descobrindo urls": ("Descobrindo URLs","warn"),
    "coletando páginas": ("Coletando páginas","warn"),
    "coletando paginas": ("Coletando páginas","warn"),
    "analisando": ("Analisando","warn"),
    "comparando": ("Comparando","warn"),
    "calculando pontuação": ("Calculando pontuação","warn"),
    "calculando pontuacao": ("Calculando pontuação","warn"),
    "gerando recomendações": ("Gerando recomendações","warn"),
    "gerando recomendacoes": ("Gerando recomendações","warn"),
    "gerando relatórios": ("Gerando relatórios","warn"),
    "gerando relatorios": ("Gerando relatórios","warn"),
    "em processamento": ("Em processamento","warn"),
    "em execução": ("Em execução","warn"),
    "em execucao": ("Em execução","warn"),
    "aguardando dados": ("Aguardando dados","warn"),
    "expirado": ("Expirado","warn"),
    "em execução": ("Em execução","warn"),
    "em execucao": ("Em execução","warn"),
    "em processamento": ("Em processamento","warn"),
    "aguardando dados": ("Aguardando dados","warn"),
    "com limitação": ("Com limitação","warn"),
    "com limitacao": ("Com limitação","warn"),
    "concluído com limitações": ("Concluído com limitações","warn"),
    "concluido com limitacoes": ("Concluído com limitações","warn"),
    "executado parcialmente": ("Executado parcialmente","warn"),
    "não consolidado": ("Não consolidado","warn"),
    "nao consolidado": ("Não consolidado","warn"),
    "solicitado, não executado": ("Solicitado, não executado","warn"),
    "solicitado, nao executado": ("Solicitado, não executado","warn"),
    "não aprovado": ("Não aprovado","bad"),
    "nao aprovado": ("Não aprovado","bad"),
    "falha": ("Falha","bad"),
    "falhou": ("Falhou","bad"),
    "falha reprocessável": ("Falha reprocessável","bad"),
    "falha reprocessavel": ("Falha reprocessável","bad"),
    "falha terminal": ("Falha terminal","bad"),
    "falha permanente": ("Falha permanente","bad"),
    "falha fatal": ("Falha fatal","bad"),
    "erro": ("Erro","bad"),
    "erro técnico": ("Erro técnico","bad"),
    "erro tecnico": ("Erro técnico","bad"),
    "erro da aplicação": ("Erro da aplicação","bad"),
    "erro da aplicacao": ("Erro da aplicação","bad"),
    "erro de resposta contratual": ("Erro de resposta contratual","bad"),
    "tempo limite excedido": ("Tempo limite excedido","bad"),
    "navegador indisponível": ("Navegador indisponível","bad"),
    "navegador indisponivel": ("Navegador indisponível","bad"),
    "amostra inválida": ("Amostra inválida","bad"),
    "amostra invalida": ("Amostra inválida","bad"),
    "bloqueado": ("Bloqueado","bad"),
    "inválido": ("Inválido","bad"),
    "invalido": ("Inválido","bad"),
    "incoerente": ("Incoerente","bad"),
    "inconsistente": ("Inconsistente","bad"),
    "contraditório": ("Contraditório","bad"),
    "contraditorio": ("Contraditório","bad"),
    "ruim": ("Ruim","bad"),
    "frustrada": ("Frustrada","bad"),
    "executado com erro e sem dados": ("Executado com erro e sem dados","bad"),
    "inconsistente - sha-256 divergente": ("INCONSISTENTE - SHA-256 divergente","bad"),
}


def _plain_state_display(value: Any) -> _Html|None:
    text=_ui_text(value).strip()
    if not text:
        return None
    key=text.casefold()
    item=_PLAIN_STATE_LABELS.get(key)
    if item is None:
        raw=_norm(text)
        if raw=="AUTO":
            item=("Automático","neutral")
        elif raw in {"CREATED","CANCELLED","NO_AI"}:
            item=(_status_label(raw),"neutral")
        elif raw in {"INITIALIZING","DISCOVERING","ACQUIRING","ANALYZING","COMPARING","SCORING","RECOMMENDING","REPORTING","DEGRADED"}:
            item=(_status_label(raw),"warn")
        elif raw=="FULL":
            item=(_status_label(raw),"good")
        elif raw=="FAILED":
            item=(_status_label(raw),"bad")
        elif raw in _STATUS_SUCCESS:
            item=(_status_label(raw),"good")
        elif raw in _STATUS_PENDING or raw in {"WARNING","NEEDS_IMPROVEMENT","TOLERATING","INCOMPLETE","PRELIMINARY"}:
            item=(_status_label(raw),"warn")
        elif raw in _STATUS_FAILURE or raw in {"FAIL","INVALID","INCOHERENT","INCONSISTENT","CONTRADICTORY","POOR","FRUSTRATED"}:
            item=(_status_label(raw),"bad")
        elif raw in _STATUS_NEUTRAL or raw in {"NOT_DETERMINABLE","UNKNOWN"}:
            item=(_status_label(raw),"neutral")
    if item is None:
        if (
            key.startswith((
                "não determinável","nao determinavel",
                "não determinado","nao determinado",
                "não determinada","nao determinada",
                "indeterminado","indeterminada",
                "não se aplica","nao se aplica",
                "não aplicável","nao aplicavel",
                "não elegível","nao elegivel",
            ))
            or key.endswith((
                "não determinado","nao determinado",
                "não determinada","nao determinada",
                "não determinável","nao determinavel",
                "não solicitado","nao solicitado",
                "não solicitada","nao solicitada",
                "não aplicável","nao aplicavel",
                "não habilitado","nao habilitado",
                "não habilitada","nao habilitada",
                "não elegível","nao elegivel",
                "desabilitado","desabilitada",
            ))
        ):
            item=(text,"neutral")
        elif key.startswith((
            "parcial",
            "etapa parcial","etapa pendente",
            "execução parcial","execucao parcial",
            "execução com limitações","execucao com limitacoes",
            "concluído com limitações","concluido com limitacoes",
            "dados insuficientes",
            "não configurado","nao configurado",
            "solicitado, não executado","solicitado, nao executado",
            "executado parcialmente",
            "executado sem dados ·",
            "expirado para conclusão","expirado para conclusao",
        )) or key.endswith((
            "não configurado","nao configurado",
            "não configurada","nao configurada",
            "não consolidado","nao consolidado",
            "com limitações","com limitacoes",
        )):
            item=(text,"warn")
        elif key.startswith((
            "falha",
            "erro",
            "bloqueado",
            "não aprovado","nao aprovado",
            "inconsistente",
        )) or key.endswith((
            "indisponível","indisponivel",
            "bloqueado",
        )) or key in {"provider temporariamente indisponível","provider temporariamente indisponivel"}:
            item=(text,"bad")
        elif key.startswith((
            "concluído","concluido",
            "etapa concluída","etapa concluida",
            "execução completa","execucao completa",
            "aprovado",
            "válido","valido",
            "coerente",
            "consistente",
            "disponível","disponivel",
            "medido",
            "gerado",
            "interpretado",
            "executado com dados ·",
        )):
            item=(text,"good")
        else:
            return None
    label,tone=item
    return _Html(f"<span class='state-text {tone}'>{escape(label)}</span>")


def _display_value(value: Any) -> _Html:
    if isinstance(value, _Html):
        return value
    semantic=_plain_state_display(value)
    return semantic if semantic is not None else _rich_text(value)

def _temporal_mode_label(value: Any) -> _Html:
    return _internal_value_label(value) or _rich_text(value)



def _status_label(value: Any) -> str:
    raw=_norm(value)
    mapping={
        "CREATED":"Criado","INITIALIZING":"Inicializando","DISCOVERING":"Descobrindo URLs",
        "ACQUIRING":"Coletando páginas","ANALYZING":"Analisando","COMPARING":"Comparando",
        "SCORING":"Calculando pontuação","RECOMMENDING":"Gerando recomendações","REPORTING":"Gerando relatórios",
        "CANCELLED":"Cancelado","FAILED":"Falhou",
        "SUCCESS":"Concluído","COMPLETE":"Concluído","COMPLETED":"Concluído","FINAL":"Concluído",
        "READY":"Disponível","AVAILABLE":"Disponível","MEASURED":"Medido","GENERATED":"Gerado","CONSOLIDATED":"Consolidado",
        "PASS":"Aprovado","FAIL":"Não aprovado","WARNING":"Atenção","INFO":"Informativo",
        "PARTIAL":"Parcial","FAILED_RETRYABLE":"Falha reprocessável","FAILED_TERMINAL":"Falha terminal","FAILED_PERMANENT":"Falha permanente",
        "FAILED_FATAL":"Falha fatal","FAILURE":"Falha","ERROR":"Erro","TECHNICAL_ERROR":"Erro técnico",
        "CONTRACT_ERROR":"Erro de resposta contratual","BLOCKED":"Bloqueado","DISABLED":"Desabilitado",
        "NOT_REQUESTED":"Não solicitado","REQUESTED_NOT_EXECUTED":"Solicitado, não executado","NOT_CONFIGURED":"Não configurado",
        "NOT_APPLICABLE":"Não aplicável","SKIPPED":"Ignorado","ABSENT":"Não encontrado","UNAVAILABLE":"Sem dados disponíveis",
        "NO_DATA":"Sem dados","INCOMPLETE":"Incompleto","PRELIMINARY":"Preliminar","VALID":"Válido","EXPIRED":"Expirado",
        "RUNNING":"Em execução","PENDING":"Pendente","PROCESSING":"Em processamento","WAITING_FOR_DATA":"Aguardando dados",
        "NOT_DETERMINABLE":"Não determinável com os dados desta auditoria","UNKNOWN":"Não determinado",
        "COMPLETE_WITH_LIMITATIONS":"Concluído com limitações","COMPLETED_WITH_LIMITATIONS":"Concluído com limitações",
        "APPLICATION_ERROR":"Erro da aplicação","INVALID_SAMPLE":"Amostra inválida","BROWSER_UNAVAILABLE":"Navegador indisponível",
        "TIMEOUT":"Tempo limite excedido","NAVIGATION_ERROR":"Erro de navegação",
    }
    mapped=public_label(value)
    common=common_public_label(raw)
    common_mapped=common if common and common != raw else None
    return mapping.get(raw, mapped or common_mapped or str(value or _EMPTY).replace("_"," ").title())


def _assessment_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "PASS":"Aprovado",
        "FAIL":"Não aprovado",
        "GOOD":"Bom",
        "NEEDS_IMPROVEMENT":"Precisa melhorar",
        "POOR":"Ruim",
        "NOT_APPLICABLE":"Não aplicável",
        "UNAVAILABLE":"Sem dados disponíveis",
        "INCOMPLETE":"Incompleto",
    }.get(raw,_status_label(value))


def _device_label(value: Any) -> str:
    raw=_norm(value)
    return {"MOBILE":"Dispositivo móvel","DESKTOP":"Desktop","TABLET":"Tablet"}.get(
        raw, public_label(value) or str(value or _EMPTY).replace("_"," ").title()
    )


def _architecture_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "STATIC_OR_SSR":"Estática ou renderizada no servidor (SSR)",
        "HYDRATED":"Renderizada no servidor com hidratação",
        "CSR_SPA":"SPA renderizada no cliente (CSR)",
        "MIXED":"Mista",
        "UNKNOWN":"Não determinada",
    }.get(raw, public_label(value) or str(value or _EMPTY).replace("_"," ").title())


def _classification_label(value: Any) -> str:
    raw=_norm(value)
    return {"SATISFIED":"Satisfatória","TOLERATING":"Tolerável","FRUSTRATED":"Frustrada"}.get(
        raw, public_label(value) or str(value or _EMPTY).replace("_"," ").title()
    )


def _level_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "CRITICAL":"Crítica","VERY_HIGH":"Muito alta","HIGH":"Alta","MEDIUM":"Média","LOW":"Baixa","VERY_LOW":"Muito baixa",
        "INFO":"Informativa","WARNING":"Atenção","P1":"Prioridade 1","P2":"Prioridade 2","P3":"Prioridade 3","P4":"Prioridade 4",
    }.get(raw,public_label(value) or str(value or _EMPTY).replace("_"," ").title())


def _confidence_label(value: Any) -> str:
    raw=_norm(value)
    if raw in {"HIGH","MEDIUM","LOW","VERY_HIGH","VERY_LOW"}:
        return _level_label(value)
    if raw in {"UNAVAILABLE","NOT_AVAILABLE"}:
        return "Sem dados para estimar"
    if raw in {"NOT_APPLICABLE","N/A"}:
        return "Não aplicável"
    if raw in {"UNKNOWN","NOT_DETERMINABLE"}:
        return "Não determinada"
    try:
        number=float(value)
        return f"{number*100:.0f}%" if 0<=number<=1 else f"{number:g}"
    except (TypeError,ValueError):
        return str(value or _EMPTY).replace("_"," ")


def _session_label(value: Any) -> str:
    raw=_norm(value)
    return {"COLD":"Sessão nova, sem reaproveitamento","WARM":"Sessão reutilizada","COLD_CONTEXT":"Contexto novo, sem reaproveitamento de cache","WARM_CONTEXT":"Contexto com reaproveitamento"}.get(
        raw, public_label(value) or str(value or "-").replace("_"," ").title()
    )


def _error_scope_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "ALL":"Todos os erros observados",
        "FIRST_PARTY":"Somente falhas atribuídas a recursos do próprio domínio; erros de console/JavaScript sem origem confiável permanecem diagnósticos",
        "OWNER":"Somente falhas atribuídas a recursos do próprio domínio",
        "NAVIGATION":"Somente erro da ação/navegação principal",
    }.get(raw,public_label(value) or str(value or "-").replace("_"," ").title())


def _score_impact_label(value: Any) -> str:
    raw=_norm(value)
    return {"NONE":"Sem impacto direto na pontuação","BOUNDED_AI_RESOURCE_ASSESSMENT":"Avaliação limitada e vinculada a evidências","NON_SCORING":"Não participa da pontuação"}.get(
        raw, public_label(value) or str(value or "-").replace("_"," ").title()
    )


def _domain_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "ACCESSIBILITY":"Acessibilidade","PERFORMANCE":"Desempenho","SEMANTICS_STRUCTURE":"Estrutura semântica",
        "CONTENT":"Conteúdo","SEARCH_RANKING":"Busca e posicionamento","FILES_DISCOVERY":"Arquivos de descoberta",
        "TECHNICAL_HTML":"HTML e estrutura técnica","BEST_PRACTICES":"Boas práticas","SECURITY":"Segurança passiva",
        "AI_ACCESS":"Acesso por agentes de IA",
    }.get(raw,public_label(value) or str(value or "-").replace("_"," ").title())


def _capability_label(value: Any) -> str:
    raw=str(value or "")
    return {
        "domain-discovery":"Descoberta e acesso técnico","standards":"Padrões e compatibilidade web",
        "accessibility":"Acessibilidade","content-suggestions":"Conteúdo, semântica e dados estruturados",
        "web-performance":"Desempenho web","search-intelligence":"Inteligência de busca / SERP",
        "google-search-console":"Google Search Console","ai-visibility":"Visibilidade em respostas de IA",
        "observability":"Observabilidade externa","apdex-navigation":"Apdex de navegação",
        "apdex-experience":"Apdex de experiência","deep-analysis":"Análise profunda e melhorias",
        "remediation":"Remediações","passive-security":"Segurança passiva",
    }.get(raw,public_label(value) or raw.replace("-"," ").replace("_"," ").title() or "-")


def _plan_detail_label(value: Any) -> str:
    text=str(value or "").strip()
    match=re.fullmatch(r"mix=mobile=(\d+(?:\.\d+)?)",text,re.I)
    if match:
        return f"Distribuição de dispositivos: {match.group(1)}% mobile"
    return text.replace("_"," ") if text else "-"


def _attempt_count_label(value: Any) -> str:
    try:
        number=int(value)
    except (TypeError,ValueError):
        return str(value or "-")
    return "Não contabilizada neste item" if number==0 else str(number)


def _tone_for_status(value: Any) -> str:
    raw=_norm(value)
    if raw in _STATUS_FAILURE or any(t in raw for t in ("FAIL","ERROR","BLOCK")):
        return "bad"
    if raw in _STATUS_PENDING or any(t in raw for t in ("PARTIAL","LIMIT","PENDING")):
        return "warn"
    if raw in _STATUS_SUCCESS or any(t in raw for t in ("SUCCESS","COMPLETE","CONCLU")):
        return "good"
    return "neutral"


_STATE_GOOD = {"PASS","VALID","COHERENT","CONSISTENT","ALIGNED","SATISFIED","GOOD"}
_STATE_WARN = {"WARNING","PARTIAL","NEEDS_IMPROVEMENT","TOLERATING","ATTENTION"}
_STATE_BAD = {"FAIL","INVALID","INCOHERENT","INCONSISTENT","MISALIGNED","CONTRADICTORY","POOR","FRUSTRATED"}


def _state_tone(value: Any) -> str:
    raw=_norm(value)
    if raw in _STATE_GOOD:
        return "good"
    if raw in _STATE_WARN:
        return "warn"
    if raw in _STATE_BAD:
        return "bad"
    return _tone_for_status(value)


def _state_text(value: Any, label: Any|None=None) -> _Html:
    text=_status_label(value) if label is None else _ui_text(label)
    tone=_state_tone(value)
    return _Html(f"<span class='state-text {tone}'>{escape(text)}</span>")


def _result_value(value: Any, tone: str="neutral") -> _Html:
    safe_tone=tone if tone in {"good","warn","low","bad","neutral"} else "neutral"
    return _Html(f"<strong class='result-value {safe_tone}'>{_display_value(value)}</strong>")


def _score_result_tone(value: Any) -> str:
    text=str(value or "").replace("\u00a0"," ")
    text=re.sub(r"(?<=\d)\s+(?=\d)","",text)
    match=re.search(r"-?\d+(?:[.,]\d+)?",text)
    if not match:
        return "neutral"
    try:
        number=float(match.group(0).replace(",","."))
    except ValueError:
        return "neutral"
    if number >= 75:
        return "good"
    if number >= 60:
        return "warn"
    if number >= 40:
        return "low"
    return "bad"


def _severity_tone(value: Any) -> str:
    raw=_norm(value)
    if raw in {"CRITICAL","VERY_HIGH","HIGH","CRITICA","MUITO_ALTA","ALTA"}:
        return "bad"
    if raw in {"MEDIUM","MEDIA"}:
        return "warn"
    return "neutral"


def _priority_tone(value: Any) -> str:
    raw=_norm(value)
    if raw in {"CRITICAL","VERY_HIGH","HIGH","P1","CRITICA","MUITO_ALTA","ALTA","PRIORIDADE_1"}:
        return "bad"
    if raw in {"MEDIUM","P2","MEDIA","PRIORIDADE_2"}:
        return "warn"
    return "neutral"


def _severity_text(value: Any) -> _Html:
    return _result_value(_level_label(value),_severity_tone(value))


def _priority_text(value: Any) -> _Html:
    return _result_value(_level_label(value),_priority_tone(value))


def _badge(text: str, tone: str|None=None) -> str:
    return f"<span class='badge {escape(tone or _tone_for_status(text))}'>{escape(text)}</span>"


def _metric(label: str, value: Any, note: str="") -> str:
    note_html=f"<small>{escape(_ui_text(note))}</small>" if note else ""
    return f"<div class='metric'><small>{escape(_ui_text(label))}</small><strong>{_display_value(value)}</strong>{note_html}</div>"


def _metric_result(label: str, value: Any, tone: str="neutral", note: str="") -> str:
    note_html=f"<small>{escape(_ui_text(note))}</small>" if note else ""
    safe_tone=tone if tone in {"good","warn","low","bad","neutral"} else "neutral"
    return f"<div class='metric'><small>{escape(_ui_text(label))}</small><strong class='result-value {safe_tone}'>{_display_value(value)}</strong>{note_html}</div>"


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    empty: str="Sem dados disponíveis para este contexto.",
    sortable: bool=False,
    page_size: int|None=None,
) -> str:
    if not rows:
        return f"<div class='notice'>{escape(empty)}</div>"
    head="".join(f"<th>{escape(_ui_text(h))}</th>" for h in headers)
    body="".join("<tr>"+"".join(f"<td>{_display_value(cell)}</td>" for cell in row)+"</tr>" for row in rows)
    interactive=bool(sortable or page_size)
    attrs=""
    if interactive:
        attrs=" data-interactive-table='true'"
        attrs+=f" data-sortable='{'true' if sortable else 'false'}'"
        if page_size:
            attrs+=f" data-page-size='{max(1,int(page_size))}'"
    table=f"<div class='table-wrap'><table{attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    if page_size:
        table+="<div class='table-controls'><button type='button' data-table-prev>Página anterior</button><span class='table-page-info'></span><button type='button' data-table-next>Próxima página</button></div>"
    return table


def _kv(items: Sequence[tuple[str,Any]]) -> str:
    pairs=[]
    for label,value in items:
        pairs.append(f"<dt>{escape(label.replace('-','-'))}</dt><dd>{_display_value(value)}</dd>")
    return "<dl class='kv'>"+"".join(pairs)+"</dl>"


def _modal(modal_id: str, title: str, context: str, body: str) -> str:
    return f"""<dialog id='{escape(modal_id)}' class='rasai-modal'><div class='modal-head'><div><h2>{escape(_ui_text(title))}</h2><p>{escape(_ui_text(context))}</p></div><button class='modal-close' type='button' data-modal-close aria-label='Fechar'>Fechar</button></div><div class='modal-body'>{body}</div></dialog>"""


def _modal_button(modal_id: str, label: str="Ver detalhes") -> _Html:
    return _Html(f"<button type='button' class='action' data-modal-open='{escape(modal_id)}'>{escape(label)}</button>")


def _section(section_id: str, title: str, body: str, kicker: str="") -> str:
    k=f"<div class='kicker'>{escape(kicker)}</div>" if kicker else ""
    return f"<section id='{escape(section_id)}' class='panel'>{k}<h2>{escape(title)}</h2>{body}</section>"


def _outline(items: Sequence[tuple[str,str]]) -> str:
    return "<nav class='outline' aria-label='Atalhos desta página'>"+"".join(f"<a href='#{escape(a)}'>{escape(l)}</a>" for a,l in items)+"</nav>"


def _navigation(current: str) -> str:
    out=[]; group=None
    for page in CATALOG_REPORT_PAGES:
        if page.group != group:
            out.append(f"<div class='nav-group'>{escape(page.group)}</div>"); group=page.group
        active=" active" if page.filename==current else ""
        aria=" aria-current='page'" if active else ""
        nav_label=CATALOG_BY_ID[page.catalog_id].label if page.catalog_id in CATALOG_BY_ID else page.label
        out.append(f"<a class='{active.strip()}' href='{escape(page.filename)}'{aria}>{escape(nav_label)}</a>")
    return "".join(out)


def _shell(page: CatalogReportPage, audit_id: str, body: str) -> str:
    html=f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(page.label)} · RASAi</title><link rel='stylesheet' href='css/site.css'></head><body data-report-contract='{CATALOG_REPORT_CONTRACT_VERSION}' data-page='{escape(page.id)}'><aside class='app-nav' data-shared-report-menu='{CATALOG_REPORT_CONTRACT_VERSION}'><div class='brand'><small>RASAi · relatório por catálogos</small><strong>{escape(audit_id)}</strong></div><nav aria-label='Relatórios'>{_navigation(page.filename)}</nav></aside><main class='app-main'>{body}<footer class='footer'>Projeção somente para leitura de dados persistidos · {CATALOG_REPORT_CONTRACT_VERSION} · nenhuma coleta, integração, IA ou cálculo de pontuação é executado pelo HTML.</footer></main><script>{_JS}</script></body></html>"""
    return localize_html_timestamps(html)


def _audit_state(data: _ReportData) -> str:
    if data.fulfillment:
        return _status_label(data.fulfillment.get("processing_status"))
    return _status_label(data.audit.get("completion_status") or data.audit.get("status"))


def _audit_hero(data: _ReportData, title: str, subtitle: str) -> str:
    target=data.targets[0] if data.targets else _EMPTY
    project=str(data.audit.get("project_name") or _EMPTY)
    return f"<header class='hero'><div class='eyebrow'>Auditoria {escape(data.audit_id)}</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p><div class='metric-grid'>{_metric('URL auditada',target)}{_metric('Projeto',project)}{_metric('Resultado da execução',_audit_state(data))}{_metric('Catálogos selecionados',len(data.selected))}</div></header>"


def _score_value(row: Mapping[str,Any]) -> str:
    try:
        return f"{float(row.get('value')):.1f}"
    except (TypeError,ValueError):
        return _plain(row.get("value")) or _EMPTY


def _score_table(data: _ReportData, *, include_overall: bool=True, context: str|None=None) -> str:
    rows=[]
    for row in sorted(data.scores,key=lambda x:(str(x.get("device","")),str(x.get("dimension","")))):
        dim=str(row.get("dimension") or "")
        if not include_overall and dim=="OVERALL_READINESS":
            continue
        if context and _DIMENSION_CONTEXT.get(dim)!=context:
            continue
        consolidation=_norm(row.get("consolidation_status"))
        structured_absent=(dim=="STRUCTURED_DATA" and consolidation=="NOT_APPLICABLE" and row.get("value") is None)
        score_value=_score_value(row)
        value="Não aplicável" if structured_absent else _result_value(score_value,_score_result_tone(score_value))
        confidence="Não aplicável - nenhum dado estruturado foi observado" if structured_absent else _confidence_label(row.get("confidence"))
        dimension_label = public_label(dim) or _DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        rows.append((dimension_label,_device_label(row.get("device")),value,row.get("coverage",_EMPTY),confidence,_status_label(row.get("consolidation_status")),row.get("scoring_version",_EMPTY)))
    return _table(("Indicador","Contexto","Valor","Cobertura","Confiança","Consolidação","Método"),rows)


__all__ = [name for name in globals() if not name.startswith("__")]
