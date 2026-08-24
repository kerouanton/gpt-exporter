# Windows packaging

GPT Exporter uses PyInstaller to produce a self-contained Windows `onedir` build. The default build uses the Windows GUI subsystem, so launching `GPT Exporter.exe` does not open a console window.

## Local build

From the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv-packaging
.\.venv-packaging\Scripts\python.exe -m pip install --upgrade pip
.\.venv-packaging\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-packaging\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\gpt_exporter.spec
```

The application is produced under:

```text
dist\GPT Exporter\
```

Launch it with:

```powershell
& ".\dist\GPT Exporter\GPT Exporter.exe"
```

The application version is available from `Help → About GPT Exporter…` and from the Windows file properties for `GPT Exporter.exe`. The PE version resource is generated automatically from `gpt_exporter.version`, so the GUI, project metadata and Windows executable share the same version source.

The packaged non-Python resources are expected under:

```text
dist\GPT Exporter\_internal\gpt_exporter\resources\
```

and include `HELP.md`, `HISTORY.md`, and `collect_chatgpt_archive.js`.

## Diagnostic console build

The same spec can still produce a console build for diagnostics. Set `GPT_EXPORTER_CONSOLE=1` only for that build:

```powershell
$env:GPT_EXPORTER_CONSOLE = "1"
.\.venv-packaging\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\gpt_exporter.spec
Remove-Item Env:GPT_EXPORTER_CONSOLE
```

The console build supports a visible command-line version check:

```powershell
& ".\dist\GPT Exporter\GPT Exporter.exe" --version
```

The normal windowed build has no console by design; use `Help → About GPT Exporter…` or Windows file properties for its version.

## CI build artifact

The `Windows onedir build` GitHub Actions workflow builds the windowed spec with Python 3.13, verifies the PE GUI subsystem, Windows product/file version metadata and packaged resources, then uploads the complete `dist\GPT Exporter` directory as the `GPT-Exporter-Windows-onedir` CI artifact.

## GitHub release

The `Windows release` workflow publishes final non-development versions from `main`. It runs the unit tests, builds the same windowed `onedir` application, verifies executable metadata and packaged resources, creates a versioned ZIP plus SHA-256 checksum, and publishes both as GitHub Release assets.

The release ZIP contains the complete `GPT Exporter` application directory plus the repository `LICENSE` at the archive root. For v2.9.0 the release assets are:

```text
GPT-Exporter-2.9.0-Windows-x64.zip
GPT-Exporter-2.9.0-Windows-x64.zip.sha256
```

The release is tagged `v2.9.0` and uses `docs/RELEASE_NOTES_V2.9.md` as its release notes. GitHub also provides source archives for the tag.
