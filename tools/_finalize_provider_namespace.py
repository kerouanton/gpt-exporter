from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tests" / "test_legacy_provider_namespace_removal.py"
SHIM = ROOT / "gpt_exporter" / "providers" / "__init__.py"
SELF = Path(__file__).resolve()
WORKFLOW = ROOT / ".github" / "workflows" / "finalize-provider-namespace.yml"

REPLACEMENTS = {
    "gpt_exporter.providers.gpt": "export_provider_chatgpt",
    "gpt_exporter.providers.discord": "export_provider_discord",
    '"providers.gpt.cli"': '"export_provider_chatgpt.cli"',
}

changed: list[str] = []
for path in sorted(ROOT.rglob("*.py")):
    if path in {AUDIT, SHIM, SELF} or ".git" in path.parts or "__pycache__" in path.parts:
        continue
    original = path.read_text(encoding="utf-8")
    updated = original
    for old, new in REPLACEMENTS.items():
        updated = updated.replace(old, new)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())

AUDIT.write_text(
    '''from __future__ import annotations\n\nimport ast\nimport unittest\nfrom pathlib import Path\n\n\nclass LegacyProviderNamespaceRemovalTests(unittest.TestCase):\n    def test_historical_provider_namespace_is_fully_removed(self) -> None:\n        repo_root = Path(__file__).resolve().parents[1]\n        forbidden = (\n            "gpt_exporter.providers.gpt",\n            "gpt_exporter.providers.discord",\n        )\n        violations: list[str] = []\n\n        candidate_paths = [\n            path\n            for path in repo_root.rglob("*.py")\n            if ".git" not in path.parts and "__pycache__" not in path.parts\n        ]\n\n        for path in sorted(candidate_paths):\n            relative = path.relative_to(repo_root)\n            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))\n            for node in ast.walk(tree):\n                if isinstance(node, ast.ImportFrom):\n                    module_name = node.module\n                    if module_name and module_name.startswith(forbidden):\n                        violations.append(\n                            f"{relative.as_posix()}:{node.lineno}: from {module_name} import ..."\n                        )\n                elif isinstance(node, ast.Import):\n                    for alias in node.names:\n                        if alias.name.startswith(forbidden):\n                            violations.append(\n                                f"{relative.as_posix()}:{node.lineno}: import {alias.name}"\n                            )\n\n        self.assertEqual(\n            violations,\n            [],\n            "Historical concrete-provider imports remain:\\n" + "\\n".join(violations),\n        )\n        self.assertFalse(\n            (repo_root / "gpt_exporter" / "providers").exists(),\n            "The legacy gpt_exporter.providers compatibility namespace must be removed.",\n        )\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

if SHIM.exists():
    SHIM.unlink()
providers_dir = SHIM.parent
if providers_dir.exists():
    try:
        providers_dir.rmdir()
    except OSError:
        pass

print(f"Retargeted {len(changed)} Python file(s):")
for name in changed:
    print(f"  {name}")
print("Removed legacy provider namespace shim.")
