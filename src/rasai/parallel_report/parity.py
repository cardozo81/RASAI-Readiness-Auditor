"""Source-local receipt: no comparison to or read from another output."""


def compare(tables, root):
    """Preserve source counts without claiming cross-report parity.

    The only authority for presentation values is the sealed audit.db already
    read by the renderer. Equality against that same source is not a parity test.
    """
    names = ('scores', 'web_performance_observations', 'synthetic_apdex_summaries',
             'synthetic_ux_apdex_summaries', 'findings',
             'directed_analysis_actions', 'recommendations')
    return {
        'status': 'NOT_VERIFIED',
        'reference': 'audit.db',
        'html_parity': 'NOT_VERIFIED',
        'reason': 'Paridade com outra saída não verificada nesta apresentação.',
        'comparisons': {
            name: {'status': 'NOT_VERIFIED',
                   'source_count': len(tables[name]) if name in tables else None}
            for name in names
        },
        'differences': [],
    }
