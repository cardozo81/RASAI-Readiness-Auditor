"""Concrete SERP provider adapters."""
from .fixture import FixtureSerpProvider
from .serpapi import SerpApiProvider

__all__ = ["FixtureSerpProvider", "SerpApiProvider"]
