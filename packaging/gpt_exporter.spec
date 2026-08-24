# Reproducible PyInstaller configuration for the Windows onedir build.

import os
import sys
from pathlib import Path


ROOT = Path(SPECPATH).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_exporter.version import APP_NAME, LICENSE_ID, display_version, windows_version_tuple


RESOURCE_DIRECTORY = ROOT / "gpt_exporter" / "resources"
RESOURCE_NAMES = (
    "HELP.md",
    "HISTORY.md",
    "collect_chatgpt_archive.js",
)
CONSOLE_BUILD = os.environ.get("GPT_EXPORTER_CONSOLE", "").strip() == "1"
VERSION_INFO_PATH = Path(SPECPATH) / ".gpt_exporter-version-info.txt"


def _write_windows_version_info() -> None:
    numeric_version = windows_version_tuple()
    human_version = display_version()
    version_text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric_version!r},
    prodvers={numeric_version!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'FileDescription', u'{APP_NAME}'),
          StringStruct(u'FileVersion', u'{human_version}'),
          StringStruct(u'InternalName', u'{APP_NAME}'),
          StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
          StringStruct(u'ProductName', u'{APP_NAME}'),
          StringStruct(u'ProductVersion', u'{human_version}'),
          StringStruct(u'Comments', u'Licensed under {LICENSE_ID}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    VERSION_INFO_PATH.write_text(version_text, encoding="utf-8")


_write_windows_version_info()


datas = [
    (str(RESOURCE_DIRECTORY / name), "gpt_exporter/resources")
    for name in RESOURCE_NAMES
]
datas.append((str(ROOT / "LICENSE"), "."))


a = Analysis(
    [str(ROOT / "gpt_exporter_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE_BUILD,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_INFO_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
