from __future__ import annotations

import ast
import unittest
from pathlib import Path


class LegacyProviderNamespaceRemovalTests(unittest.TestCase):
    def test_historical_provider_namespace_is_fully_removed(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        forbidden = (
            "gpt_exporter.providers.gpt",
            "gpt_exporter.providers.discord",
        )
        violations: list[str] = []

        candidate_paths = [
            path
            for path in repo_root.rglob("*.py")
            if ".git" not in path.parts and "__pycache__" not in path.parts
        ]

        for path in sorted(candidate_paths):
            relative = path.relative_to(repo_root)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module_name = node.module
                    if module_name and module_name.startswith(forbidden):
                        violations.append(
                            f"{relative.as_posix()}:{node.lineno}: from {module_name} import ..."
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden):
                            violations.append(
                                f"{relative.as_posix()}:{node.lineno}: import {alias.name}"
                            )

        self.assertEqual(
            violations,
            [],
            "Historical concrete-provider imports remain:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
