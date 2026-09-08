from __future__ import annotations

import unittest
from pathlib import Path


class ProviderSelectorWindowsTests(unittest.TestCase):
    def test_hidden_root_selector_maps_before_grab(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "gpt_exporter"
            / "ui"
            / "provider_selector.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("self.transient(parent)", source)
        show_modal = source.split("def show_modal", 1)[1]
        self.assertLess(show_modal.index("self.deiconify()"), show_modal.index("self.grab_set()"))
        self.assertLess(show_modal.index("self.wait_visibility()"), show_modal.index("self.grab_set()"))
        self.assertIn("dialog.show_modal()", source)


if __name__ == "__main__":
    unittest.main()
