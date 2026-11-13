"""Versioned display proposals never change persisted scores."""
import json
from pathlib import Path


def load():
    data = json.loads((Path(__file__).parent / 'assets' / 'thresholds.json').read_text(encoding='utf-8'))
    for item in data:
        if item['origin'] not in {'PUBLIC_STANDARD', 'PERSISTED_CONTRACT', 'PRODUCT_PROPOSAL'}:
            raise ValueError('Invalid threshold origin')
        if item['thresholds'] != sorted(item['thresholds']):
            raise ValueError('Unordered thresholds')
    return data
