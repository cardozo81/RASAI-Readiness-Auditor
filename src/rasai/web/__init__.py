"""Optional Web/SaaS adapter for the RASAi control plane.

Importing :mod:`rasai.web` never imports FastAPI. HTTP dependencies remain optional
so the portable SQLite/CLI runtime is unaffected when ``.[web]`` is not installed.
"""
