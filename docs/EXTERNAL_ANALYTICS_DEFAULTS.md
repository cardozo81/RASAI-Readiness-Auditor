# Defaults - External Analytics

Baseline empacotada:

```ini
RASAI_COMMON_CRAWL_ENABLED = true
RASAI_COMMON_CRAWL_MAX_URLS = 3
RASAI_COMMON_CRAWL_INDEX_COUNT = 2
RASAI_CLARITY_ENABLED = false
RASAI_CLARITY_DAYS = 1
RASAI_CLARITY_DIMENSIONS = URL,Device
```

CrUX History permanece AUTO por `RASAI_CRUX_API_KEY` e não grava a key no INI.

A baseline prioriza máximo valor seguro sem credenciais obrigatórias. Common Crawl é read-only/bounded; Clarity permanece opt-in por quota diária limitada.
