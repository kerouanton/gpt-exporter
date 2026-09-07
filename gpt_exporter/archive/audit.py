"""Lazy compatibility facade for ChatGPT asset-reference auditing."""


def _implementation():
    from gpt_exporter.providers.gpt.archive import audit as implementation
    return implementation


def audit_asset_references(*args, **kwargs):
    return _implementation().audit_asset_references(*args, **kwargs)


def collect_asset_audit(*args, **kwargs):
    return _implementation().collect_asset_audit(*args, **kwargs)


def docx_asset_references(*args, **kwargs):
    return _implementation().docx_asset_references(*args, **kwargs)


def markdown_asset_references(*args, **kwargs):
    return _implementation().markdown_asset_references(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = [
    "AssetAuditResult",
    "DEFAULT_REPORT_NAME",
    "audit_asset_references",
    "collect_asset_audit",
    "docx_asset_references",
    "markdown_asset_references",
]
