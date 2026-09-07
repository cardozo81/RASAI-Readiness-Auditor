"""Evidence-bound deterministic remediation recipes for actionable GEO reporting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RemediationRecipe:
    rule_id: str
    title: str
    target: str
    element: str | None
    location: str | None
    action: str
    description: str
    example: str | None
    acceptance: tuple[str, ...]
    validation: tuple[str, ...]
    human_decision: str | None = None
    fallback: bool = False

    def __post_init__(self) -> None:
        """Keep acceptance/revalidation steps as tuples even for one-item recipes."""

        acceptance = (self.acceptance,) if isinstance(self.acceptance, str) else tuple(self.acceptance)
        validation = (self.validation,) if isinstance(self.validation, str) else tuple(self.validation)
        object.__setattr__(self, "acceptance", acceptance)
        object.__setattr__(self, "validation", validation)


_CANONICAL = RemediationRecipe(
    rule_id="BR-GEO-013",
    title="Corrigir declaração canonical",
    target="Documento HTML",
    element='<link rel="canonical">',
    location="<head>",
    action="ADD_OR_CORRECT",
    description=(
        "Definir uma única declaração canonical válida e coerente com a URL preferencial. "
        "Quando a canonical estiver ausente, a equipe deve primeiro confirmar qual URL é realmente preferencial."
    ),
    example=(
        "<head>\n"
        "  ...\n"
        "  <link rel=\"canonical\" href=\"https://URL-PREFERENCIAL.example/...\">\n"
        "</head>"
    ),
    acceptance=(
        "Existe no máximo uma canonical efetiva quando aplicável.",
        "O href usa URL absoluta e tecnicamente válida.",
        "Não existe conflito entre declarações canonical.",
        "O destino corresponde à URL preferencial definida pela equipe.",
        "O resultado é consistente nos contextos Desktop e Mobile aplicáveis.",
    ),
    validation=(
        "Reexecutar BR-GEO-013 e confirmar PASS.",
        "Quando houver destino declarado, reexecutar também BR-GEO-014.",
        "Comparar RAW e RENDERED para excluir conflito introduzido por JavaScript (BR-GEO-015).",
    ),
    human_decision=(
        "Não assuma que a própria URL auditada é a preferencial. Confirme a estratégia de canonicalização "
        "antes de preencher o href."
    ),
)


_RECIPES: dict[str, RemediationRecipe] = {
    "BR-GEO-005": RemediationRecipe(
        "BR-GEO-005", "Restabelecer recuperação técnica da página", "Resposta HTTP", None, None,
        "RESTORE_ACCESS",
        "Corrigir a causa de DNS, TLS, conexão, timeout ou resposta indisponível registrada na evidência.",
        None,
        ("A URL produz resposta HTTP utilizável.", "A causa técnica registrada deixa de ocorrer."),
        ("Reexecutar a aquisição HTTP.", "Reexecutar BR-GEO-005 e confirmar PASS."),
    ),
    "BR-GEO-011": RemediationRecipe(
        "BR-GEO-011", "Resolver conflito de diretivas de indexação", "Metadados de indexação",
        '<meta name="robots"> / X-Robots-Tag', "<head> / headers HTTP", "RESOLVE_CONFLICT",
        "Alinhar meta robots, X-Robots-Tag e estado renderizado para que não existam diretivas contraditórias.",
        None,
        ("Não existem diretivas index/noindex contraditórias.", "A intenção de indexação é consistente entre fontes aplicáveis."),
        ("Inspecionar headers e DOM final.", "Reexecutar BR-GEO-011 e BR-GEO-015."),
        "Confirme a intenção editorial/SEO antes de alterar uma diretiva deliberada.",
    ),
    "BR-GEO-012": RemediationRecipe(
        "BR-GEO-012", "Revisar diretiva noindex explícita", "Metadados de indexação",
        '<meta name="robots"> / X-Robots-Tag', "<head> / headers HTTP", "REVIEW_DIRECTIVE",
        "Determinar se o noindex observado é intencional. Remova ou altere a diretiva somente se a página deva ser indexável.",
        None,
        ("A diretiva final corresponde à intenção aprovada para a URL.", "Não há conflito entre header, HTML e DOM renderizado."),
        ("Reexecutar BR-GEO-012.", "Revalidar BR-GEO-011 e BR-GEO-015."),
        "A decisão de remover noindex é humana; o auditor não presume que indexação seja desejada.",
    ),
    "BR-GEO-013": _CANONICAL,
    "BR-GEO-014": RemediationRecipe(
        "BR-GEO-014", "Corrigir destino canonical", "Documento HTML", '<link rel="canonical">', "<head>",
        "CORRECT_TARGET",
        "Corrigir o href somente após confirmar a URL preferencial e validar que o destino é tecnicamente utilizável e contextualmente plausível.",
        '<link rel="canonical" href="https://URL-PREFERENCIAL.example/...">',
        ("URL absoluta e válida.", "Destino tecnicamente utilizável quando verificável.", "Destino coerente com a estratégia de URL preferencial."),
        ("Reexecutar BR-GEO-013 e BR-GEO-014.",),
        "A escolha da URL preferencial não deve ser inferida pelo auditor quando a evidência não for suficiente.",
    ),
    "BR-GEO-017": RemediationRecipe(
        "BR-GEO-017", "Corrigir robots.txt não interpretável", "robots.txt", "robots.txt", "/robots.txt",
        "CORRECT_RESOURCE",
        "Corrigir status, sintaxe ou disponibilidade do robots.txt conforme o estado persistido. Ausência válida não deve ser tratada como defeito.",
        None,
        ("robots.txt, quando presente, é recuperável e interpretável.",),
        ("Readquirir /robots.txt.", "Reexecutar BR-GEO-017 e a avaliação por crawler."),
    ),
    "BR-GEO-018": RemediationRecipe(
        "BR-GEO-018", "Revisar acesso por crawler", "robots.txt", "User-agent / Disallow / Allow", "/robots.txt",
        "REVIEW_CRAWLER_POLICY",
        "Revisar individualmente a política do crawler afetado; OAI-SearchBot e GPTBot possuem finalidades distintas e não devem ser tratados como equivalentes.",
        None,
        ("A política final corresponde à intenção aprovada para cada crawler.", "A regra é interpretável e não contém conflito material."),
        ("Reexecutar BR-GEO-018 para todos os crawlers baseline.",),
        "Alterar bloqueios somente após confirmar a política de acesso desejada pela organização.",
    ),
    "BR-GEO-028": RemediationRecipe(
        "BR-GEO-028", "Tornar o título semanticamente representativo", "Título da página", "<title>", "<head>",
        "EDIT_CONTENT",
        "Ajustar o título para representar de forma explícita o tópico observado na página, sem introduzir claims ausentes do conteúdo.",
        "<title>[título descritivo sustentado pelo conteúdo]</title>",
        ("O título existe.", "O título representa o conteúdo principal.", "Nenhum fato novo é inventado."),
        ("Reexecutar BR-GEO-028 com as mesmas evidências atualizadas.",),
    ),
    "BR-GEO-029": RemediationRecipe(
        "BR-GEO-029", "Clarificar hierarquia semântica", "Conteúdo principal", "headings e seções", "<main>",
        "RESTRUCTURE_CONTENT",
        "Organizar headings e seções para que tópico e subtemas possam ser recuperados sem inferência excessiva.",
        "<section>\n  <h2>[subtema sustentado pela página]</h2>\n  <p>[conteúdo existente/revisado]</p>\n</section>",
        ("A hierarquia é compreensível.", "Os headings correspondem às seções que introduzem."),
        ("Reexecutar BR-GEO-029 e BR-GEO-030.",),
    ),
    "BR-GEO-030": RemediationRecipe(
        "BR-GEO-030", "Explicitar tópico principal e seções", "Conteúdo principal", "<main> / headings", "<main>",
        "RESTRUCTURE_CONTENT",
        "Tornar o tópico principal e as seções materiais explicitamente identificáveis usando somente informações sustentadas pela página.",
        None,
        ("O tópico principal é identificável.", "As seções principais possuem rótulos/estrutura coerentes."),
        ("Reexecutar BR-GEO-030.",),
    ),
    "BR-GEO-031": RemediationRecipe(
        "BR-GEO-031", "Explicitar entidade principal", "Conteúdo principal", "identificação da entidade", "<main>",
        "CLARIFY_ENTITY",
        "Nomear e contextualizar a entidade principal quando aplicável, sem inventar atributos, autoria ou relações.",
        None,
        ("A entidade principal é identificável nas evidências.",),
        ("Reexecutar BR-GEO-031.",),
    ),
    "BR-GEO-032": RemediationRecipe(
        "BR-GEO-032", "Clarificar relações entre entidades", "Conteúdo principal", "texto/estrutura de entidade", "<main>",
        "CLARIFY_ENTITY_RELATIONSHIPS",
        "Explicitar relações relevantes já suportadas pelo conteúdo, como produto→marca ou pessoa→organização.",
        None,
        ("As relações materiais são compreensíveis sem inferência indevida.",),
        ("Reexecutar BR-GEO-032.",),
    ),
    "BR-GEO-033": RemediationRecipe(
        "BR-GEO-033", "Reduzir ambiguidade material de entidade", "Conteúdo principal", "texto/identificadores", "<main>",
        "DISAMBIGUATE_ENTITY",
        "Adicionar contexto distintivo sustentado pelas evidências para diferenciar entidades potencialmente ambíguas.",
        None,
        ("A entidade relevante não depende de ambiguidade material para ser identificada.",),
        ("Reexecutar BR-GEO-033.",),
    ),
    "BR-GEO-034": RemediationRecipe(
        "BR-GEO-034", "Corrigir sintaxe de Dados Estruturados", "Dados Estruturados", "script[type=\"application/ld+json\"]", "<head> ou <body>",
        "CORRECT_STRUCTURED_DATA",
        "Corrigir a sintaxe do bloco existente. Não adicionar marcação para fatos ou tipos que não sejam suportados pelo conteúdo visível.",
        None,
        ("O JSON-LD é sintaticamente interpretável.", "Tipos/propriedades declarados correspondem ao conteúdo visível."),
        ("Reexecutar BR-GEO-034 e, quando aplicável, BR-GEO-036/037.",),
    ),
    "BR-GEO-035": RemediationRecipe(
        "BR-GEO-035", "Clarificar tipos e propriedades estruturadas", "Dados Estruturados", "JSON-LD", "<head> ou <body>",
        "CORRECT_STRUCTURED_DATA",
        "Ajustar tipos/propriedades do dado estruturado existente conforme a entidade realmente apresentada na página.",
        None,
        ("Tipos e propriedades relevantes são identificáveis.", "Nenhuma propriedade contradiz o conteúdo visível."),
        ("Reexecutar BR-GEO-035 e BR-GEO-036/037.",),
    ),
    "BR-GEO-036": RemediationRecipe(
        "BR-GEO-036", "Alinhar Dados Estruturados ao conteúdo visível", "Dados Estruturados", "JSON-LD", "<head> ou <body>",
        "ALIGN_STRUCTURED_DATA",
        "Remover ou corrigir valores estruturados que contradigam o conteúdo visível; não crie dados somente para melhorar readiness.",
        None,
        ("Valores estruturados e conteúdo visível são consistentes.",),
        ("Reexecutar BR-GEO-036.",),
    ),
    "BR-GEO-037": RemediationRecipe(
        "BR-GEO-037", "Alinhar entidades de Dados Estruturados", "Dados Estruturados", "JSON-LD", "<head> ou <body>",
        "ALIGN_ENTITY_MARKUP",
        "Ajustar entidades estruturadas para refletir as entidades realmente observadas na página.",
        None,
        ("Entidades declaradas e observadas são consistentes.",),
        ("Reexecutar BR-GEO-037.",),
    ),
    "BR-GEO-038": RemediationRecipe(
        "BR-GEO-038", "Explicitar a intenção principal atendida", "Conteúdo principal", "seção introdutória / heading", "<main>",
        "CLARIFY_INTENT",
        "Estruturar o conteúdo para que a finalidade principal identificada nas evidências fique explícita.",
        None,
        ("A intenção principal é identificável com evidência.",),
        ("Reexecutar BR-GEO-038.",),
    ),
    "BR-GEO-039": RemediationRecipe(
        "BR-GEO-039", "Responder explicitamente às perguntas principais", "Conteúdo principal", "seções de resposta", "<main>",
        "ADD_OR_RESTRUCTURE_ANSWER",
        "Adicionar ou reorganizar respostas apenas para lacunas efetivamente identificadas; não invente condições comerciais ou fatos.",
        "<section>\n  <h2>[pergunta/intenção evidenciada]</h2>\n  <p>[resposta sustentada pelo conteúdo/fonte aprovada]</p>\n</section>",
        ("As perguntas materiais aplicáveis possuem resposta explícita.", "As respostas permanecem factualmente sustentadas."),
        ("Reexecutar BR-GEO-039 e BR-GEO-040.",),
    ),
    "BR-GEO-040": RemediationRecipe(
        "BR-GEO-040", "Adicionar contexto suficiente às respostas", "Conteúdo principal", "texto de resposta", "<main>",
        "ADD_CONTEXT",
        "Completar respostas com o contexto necessário já sustentado pelas evidências, evitando fragmentos que dependam de inferência excessiva.",
        None,
        ("A resposta é compreensível no contexto da página.",),
        ("Reexecutar BR-GEO-040.",),
    ),
    "BR-GEO-041": RemediationRecipe(
        "BR-GEO-041", "Tornar claims factuais identificáveis", "Conteúdo principal", "texto factual", "<main>",
        "CLARIFY_CLAIMS",
        "Separar afirmações factuais de linguagem promocional quando a distinção for material, sem criar novos claims.",
        None,
        ("Claims materiais podem ser identificados de forma explícita.",),
        ("Reexecutar BR-GEO-041.",),
    ),
    "BR-GEO-042": RemediationRecipe(
        "BR-GEO-042", "Adicionar contexto factual necessário", "Conteúdo principal", "texto factual", "<main>",
        "ADD_FACTUAL_CONTEXT",
        "Adicionar quem/o quê/quando/escopo somente quando esses dados existirem em fonte aprovada ou no conteúdo evidenciado.",
        None,
        ("Claims avaliados contêm contexto suficiente para interpretação.",),
        ("Reexecutar BR-GEO-042.",),
    ),
    "BR-GEO-043": RemediationRecipe(
        "BR-GEO-043", "Qualificar números, datas e quantidades", "Conteúdo principal", "texto quantitativo", "<main>",
        "ADD_QUALIFIERS",
        "Associar unidade, moeda, período, data ou escopo aos valores quando isso for necessário e estiver sustentado por fonte aprovada.",
        None,
        ("Valores materiais possuem qualificadores necessários.",),
        ("Reexecutar BR-GEO-043.",),
    ),
    "BR-GEO-044": RemediationRecipe(
        "BR-GEO-044", "Reduzir inferência necessária", "Conteúdo principal", "texto e estrutura", "<main>",
        "MAKE_EXPLICIT",
        "Tornar explícitas relações e condições materiais já sustentadas pelo conteúdo, preservando precisão factual.",
        None,
        ("Informações importantes são compreensíveis sem inferência excessiva.",),
        ("Reexecutar BR-GEO-044.",),
    ),
    "BR-GEO-045": RemediationRecipe(
        "BR-GEO-045", "Adicionar atribuição ou suporte apropriado", "Conteúdo principal", "fonte/atribuição", "<main>",
        "ADD_ATTRIBUTION",
        "Incluir atribuição ou evidência somente quando houver fonte real e quando o claim exigir suporte. Nunca invente fonte.",
        None,
        ("Claims materiais aplicáveis possuem suporte/atribuição verificável.",),
        ("Reexecutar BR-GEO-045.",),
        "A seleção de fonte válida pode exigir revisão editorial ou jurídica.",
    ),
    "BR-GEO-046": RemediationRecipe(
        "BR-GEO-046", "Identificar responsável quando relevante", "Conteúdo principal", "autoria/responsabilidade", "página / metadata",
        "ADD_RESPONSIBILITY_SIGNAL",
        "Expor autor, publisher ou entidade responsável somente quando essa informação for verdadeira e aprovada.",
        None,
        ("O responsável relevante é identificável.", "Nenhuma autoria é fabricada."),
        ("Reexecutar BR-GEO-046.",),
        "Não invente autor ou publisher; confirme a responsabilidade real.",
    ),
    "BR-GEO-047": RemediationRecipe(
        "BR-GEO-047", "Alinhar sinais de publicação e atualização", "Metadados e conteúdo", "datas visíveis/metadata", "página",
        "ALIGN_FRESHNESS_SIGNALS",
        "Corrigir inconsistências entre sinais de data usando datas reais e verificáveis; não gere data de atualização artificial.",
        None,
        ("Sinais de publicação/atualização são internamente consistentes quando aplicáveis.",),
        ("Reexecutar BR-GEO-047.",),
        "Datas devem refletir eventos reais de publicação/alteração.",
    ),
    "BR-GEO-048": RemediationRecipe(
        "BR-GEO-048", "Cobrir intenções relevantes", "Conteúdo principal", "seções de conteúdo", "<main>",
        "CLOSE_INTENT_GAPS",
        "Reorganizar ou ampliar conteúdo somente para intents persistidas/evidenciadas que sejam realmente relevantes para a página.",
        None,
        ("A intenção principal e as secundárias relevantes são representadas.",),
        ("Reexecutar BR-GEO-048.",),
    ),
    "BR-GEO-049": RemediationRecipe(
        "BR-GEO-049", "Fechar lacunas de intenção evidenciadas", "Conteúdo principal", "seções de conteúdo", "<main>",
        "CLOSE_INTENT_GAPS",
        "Tratar apenas lacunas de intenção material suportadas pelas evidências e preservar o escopo editorial da página.",
        None,
        ("As lacunas materiais identificadas foram tratadas ou deliberadamente descartadas com justificativa editorial.",),
        ("Reexecutar BR-GEO-049.",),
    ),
}


def recipe_for(rule_id: str) -> RemediationRecipe:
    """Return a rule-specific recipe or an explicit conservative fallback."""

    recipe = _RECIPES.get(rule_id)
    if recipe is not None:
        return recipe
    return RemediationRecipe(
        rule_id=rule_id,
        title=f"Remediar {rule_id}",
        target="Condição registrada no finding",
        element=None,
        location=None,
        action="REVIEW_AND_CORRECT",
        description=(
            "Atender à condição esperada registrada no finding usando somente a evidência persistida. "
            "Este é um fallback porque ainda não existe recipe específica para a regra."
        ),
        example=None,
        acceptance=("A condição esperada do finding é atendida sem criar conflito com outras regras.",),
        validation=(f"Reexecutar {rule_id} e revisar as evidence_ids associadas.",),
        fallback=True,
    )