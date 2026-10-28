"""Spendly HTTP API — a thin FastAPI layer over the existing Python modules.

All financial calculations stay in ``src/`` and ``sql/``; this package only
validates requests, picks the right database and serializes results.
"""
