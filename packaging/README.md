# Windows packaging

GPT Exporter uses PyInstaller to produce a self-contained Windows `onedir` build. The diagnostic build intentionally keeps a console window so packaging failures and tracebacks remain visible while v2.9 is under development.

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

Smoke-test the executable with:

```powershell
& ".\dist\GPT Exporter\GPT Exporter.exe" --version
& ".\dist\GPT Exporter\GPT Exporter.exe"
```

The packaged non-Python resources are expected under:

```text
dist\GPT Exporter\_internal\gpt_exporter\resources\
```

and include `HELP.md`, `HISTORY.md`, and `collect_chatgpt_archive.js`.

## CI artifact

The `Windows onedir build` GitHub Actions workflow builds the same spec with Python 3.13, verifies the executable version surface and packaged resources, and uploads the complete `dist\GPT Exporter` directory as the `GPT-Exporter-Windows-onedir` artifact.

This is not yet the final release configuration. Windowed mode, Windows version metadata, an application icon, and any optional `onefile` distribution are intentionally deferred until the `onedir` build is stable.
