"""Public labels for the independent presentation, without runtime imports."""
LABELS = {
    'scores': 'Índice de Prontidão Search & IA e dimensões',
    'findings': 'Achados da auditoria', 'evidence': 'Evidências persistidas',
    'page_snapshots': 'Capturas de páginas', 'pages': 'Páginas auditadas',
    'audits': 'Identificação da auditoria', 'audit_targets': 'Alvos da auditoria',
    'directed_analysis_actions': 'Ações da análise direcionada',
    'recommendations': 'Recomendações', 'recommendation_governance': 'Decisões de governança',
    'score_contributions': 'Composição dos índices', 'rule_executions': 'Resultados das regras',
    'web_performance_observations': 'Lighthouse e CrUX',
    'synthetic_apdex_summaries': 'Apdex de navegação — sínteses',
    'synthetic_ux_apdex_summaries': 'Apdex de experiência — sínteses',
    'ai_provider_attempts': 'Tentativas de IA e integrações',
    'content_remediation_attempts': 'Tentativas de remediação de conteúdo',
    'value': 'Valor persistido', 'performance_score': 'Lighthouse Performance',
    'accessibility_score': 'Lighthouse Accessibility', 'apdex_score': 'Apdex sintético',
    'coverage': 'Cobertura', 'confidence': 'Confiança declarada na fonte',
    'device': 'Dispositivo', 'url': 'URL', 'field_scope': 'Escopo de campo',
    'profile_id': 'Perfil', 'valid_samples': 'Amostras válidas',
    'severity': 'Severidade', 'priority': 'Prioridade', 'priority_class': 'Prioridade',
    'validation': 'Como validar', 'verification': 'Verificação',
    'expected_condition': 'Esperado', 'observed_value': 'Observado',
    'lcp_p75_ms': 'LCP de campo p75 (ms)',
}


def label(value):
    return LABELS.get(value, value.replace('_', ' '))
