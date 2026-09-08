"""Provider-neutral conversation browser package.

The historical browser module uses a bare ``import archive_core``. Install a
package-local compatibility alias before that module is imported so the shared
browser remains self-contained and continues to work when provider packages or
repository-root compatibility scripts are absent.
"""

from __future__ import annotations

import sys

from . import archive_core as _archive_core

sys.modules.setdefault("archive_core", _archive_core)

__all__: list[str] = []
