from __future__ import annotations

import ast
import unittest
from pathlib import Path


class LegacyProviderNamespaceRemovalTests(unittest.TestCase):
    def test_shared_host_does_not_import_historical_provider_namespaces(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        package_root = repo_root / "gpt_exporter"
        forbidden = (
            "gpt_exporter.providers.gpt",
            "gpt_exporter.providers.discord",
        )
        violations: list[str] = []

        for path in sorted(package_root.rglob("*.py")):
            relative = path.relative_to(package_root)
            if relative.parts and relative.parts[0] == "providers":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module_name = None
                if isinstance(node, ast.ImportFrom):
                    module_name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden):
                            violations.append(
                                f"{relative}:{node.lineno}: import {alias.name}"
                            )
                if module_name and module_name.startswith(forbidden):
                    violations.append(
                        f"{relative}:{node.lineno}: from {module_name} import ..."
                    )

        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
