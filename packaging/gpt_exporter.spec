# Reproducible PyInstaller configuration for the Windows onedir diagnostic build.

from pathlib import Path


ROOT = Path(SPECPATH).parent.resolve()
RESOURCE_DIRECTORY = ROOT / "gpt_exporter" / "resources"
RESOURCE_NAMES = (
    "HELP.md",
    "HISTORY.md",
    "collect_chatgpt_archive.js",
)


datas = [
    (str(RESOURCE_DIRECTORY / name), "gpt_exporter/resources")
    for name in RESOURCE_NAMES
]


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
    name="GPT Exporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GPT Exporter",
)
