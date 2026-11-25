"""Salesforce CRM ingestion: watermark-driven incremental loads.

Layers: raw JSON (as the API returned it) -> SRC (schema-checked) ->
PRE (upserts, full history) -> SEM (current state, deletes applied).
See README.md for the architecture and the delta behaviour.
"""

__version__ = "0.2.0"
