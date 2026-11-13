"""Display states are independent from numeric values and rule outcomes."""


def state(value, reason=None):
    token = str(value or '').upper()
    cause = str(reason) if reason else 'causa não persistida'
    if token in {'NOT_APPLICABLE', 'N/A'}:
        return 'Não aplicável — ' + cause
    if token in {'FAILED', 'ERROR', 'TIMEOUT', 'FAILED_RETRYABLE'}:
        return 'Falhou — ' + cause
    if token in {'PARTIAL', 'COMPLETE_WITH_LIMITATIONS', 'NOT_CONSOLIDATED'}:
        return 'Parcial — ' + cause
    if token in {'NOT_REQUESTED', 'DISABLED'}:
        return 'Não medido — não solicitado'
    if token in {'SUCCESS', 'COMPLETE', 'COMPLETED', 'AVAILABLE', 'CONSOLIDATED'}:
        return 'Medido'
    return 'Não medido — estado de medição não determinado'


def display(value):
    return 'N/D' if value is None else str(value)
