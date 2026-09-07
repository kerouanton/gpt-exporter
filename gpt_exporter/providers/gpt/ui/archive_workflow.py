"""Public ChatGPT archive-workflow API after provider relocation.

The historical GUI implementation is retained byte-for-byte in
``_archive_workflow``. This adapter fixes path semantics that depended on the
old repository-root location and binds provider-local pipeline/resources.
"""

from __future__ import annotations

import sys
from pathlib import Path

import gpt_exporter.resources as _generic_resources
from gpt_exporter.providers.gpt.pipeline import archive_bundle as _provider_archive_bundle
from gpt_exporter.providers.gpt.resources import collector_path as _provider_collector_path

# The historical implementation still imports ``collector_path`` from the old
# generic resources namespace. Bind that name from inside the provider before
# importing the retained implementation; the generic resources module itself
# remains provider-neutral and contains no ChatGPT resource or dependency.
_generic_resources.collector_path = _provider_collector_path

from . import _archive_workflow as _implementation


def _application_root() -> Path:
    """Return the same application/repository root used before relocation."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[4]


ROOT = _application_root()
COLLECTOR_PATH = _provider_collector_path()

# Rebind globals used dynamically by methods in the historical implementation.
_implementation.ROOT = ROOT
_implementation.COLLECTOR_PATH = COLLECTOR_PATH
_implementation.archive_bundle = _provider_archive_bundle

_original_worker = _implementation.run_archive_pipeline_worker
_original_read_collector_source = _implementation.read_collector_source


def run_archive_pipeline_worker(
    events,
    *,
    archive_root: Path,
    source_bundle: Path | None,
    legacy_root: Path = ROOT,
) -> None:
    """Run the worker with the pre-relocation application root by default."""
    # Preserve the historical patch/test surface: callers may replace the
    # public ``archive_bundle`` attribute on this module before invoking the
    # worker. The retained implementation resolves its own module global.
    _implementation.archive_bundle = archive_bundle
    return _original_worker(
        events,
        archive_root=archive_root,
        source_bundle=source_bundle,
        legacy_root=legacy_root,
    )


def read_collector_source(path: Path = COLLECTOR_PATH) -> str:
    """Read the collector from the ChatGPT provider resource directory."""
    return _original_read_collector_source(path)


# Methods on the historical Tk classes resolve these names from their defining
# module, so update that module as well as this public facade.
_implementation.run_archive_pipeline_worker = run_archive_pipeline_worker
_implementation.read_collector_source = read_collector_source

for _name in dir(_implementation):
    if not _name.startswith("_") and _name not in {
        "ROOT",
        "COLLECTOR_PATH",
        "run_archive_pipeline_worker",
        "read_collector_source",
    }:
        globals()[_name] = getattr(_implementation, _name)

__all__ = [
    name
    for name in globals()
    if not name.startswith("_") and name not in {"sys", "Path"}
]
