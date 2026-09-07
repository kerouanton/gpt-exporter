"""Lazy compatibility facade for ChatGPT asset-manifest analysis."""


def _implementation():
    from gpt_exporter.providers.gpt.archive import manifest as implementation
    return implementation


def collect_asset_manifest(*args, **kwargs):
    return _implementation().collect_asset_manifest(*args, **kwargs)


def build_asset_manifest(*args, **kwargs):
    return _implementation().build_asset_manifest(*args, **kwargs)


def render_console_summary(*args, **kwargs):
    return _implementation().render_console_summary(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = [
    "AssetManifestResult",
    "NoConversationFilesError",
    "build_asset_manifest",
    "collect_asset_manifest",
    "render_console_summary",
]
