import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Compatibility CLI and import surface for the packaged archive indexer."""

import contextlib
import io


with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.index import _legacy_indexer as _implementation


for _name in dir(_implementation):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_implementation, _name)


if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())
