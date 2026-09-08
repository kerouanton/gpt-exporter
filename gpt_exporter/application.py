"""Top-level application composition for selectable conversation providers."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass

from gpt_exporter.core import ConversationProvider, ProviderRegistry
from gpt_exporter.ui.provider_selector import choose_provider
from gpt_exporter.version import APP_NAME, display_version

ProviderLauncher = Callable[[list[str]], int]


@dataclass(frozen=True, slots=True)
class ProviderApplicationSpec:
    provider_module: str
    provider_class: str
    ui_module: str


_PROVIDER_SPECS = (
    ProviderApplicationSpec(
        provider_module="gpt_exporter.providers.gpt.provider",
        provider_class="ChatGPTProvider",
        ui_module="gpt_exporter.providers.gpt.ui.app",
    ),
    ProviderApplicationSpec(
        provider_module="gpt_exporter.providers.discord.provider",
        provider_class="DiscordProvider",
        ui_module="gpt_exporter.providers.discord.ui.app",
    ),
)


def _load_provider(spec: ProviderApplicationSpec) -> ConversationProvider | None:
    try:
        module = importlib.import_module(spec.provider_module)
    except ModuleNotFoundError as error:
        provider_package = spec.provider_module.rsplit(".", 1)[0]
        if error.name and (
            error.name == provider_package or error.name.startswith(provider_package + ".")
        ):
            return None
        raise
    provider_type = getattr(module, spec.provider_class)
    return provider_type()


def build_provider_registry() -> ProviderRegistry:
    """Register concrete providers at the application boundary."""
    registry = ProviderRegistry()
    for spec in _PROVIDER_SPECS:
        provider = _load_provider(spec)
        if provider is not None:
            registry.register(provider)
    return registry


def _make_launcher(spec: ProviderApplicationSpec) -> ProviderLauncher:
    def launch(arguments: list[str]) -> int:
        module = importlib.import_module(spec.ui_module)
        provider_main = getattr(module, "main")
        previous = sys.argv
        try:
            sys.argv = [previous[0], *arguments]
            return int(provider_main())
        finally:
            sys.argv = previous

    return launch


def build_provider_launchers() -> dict[str, ProviderLauncher]:
    """Return lazy launchers for provider UIs installed with this application."""
    launchers: dict[str, ProviderLauncher] = {}
    for spec in _PROVIDER_SPECS:
        provider = _load_provider(spec)
        if provider is not None:
            launchers[provider.descriptor.provider_id] = _make_launcher(spec)
    return launchers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Choose and launch a conversation provider application"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {display_version()}",
        help="Show the application version and exit.",
    )
    parser.add_argument(
        "--provider",
        help="Launch a provider directly by provider id instead of showing the selector.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    arguments, provider_arguments = build_parser().parse_known_args(raw_arguments)
    registry = build_provider_registry()
    launchers = build_provider_launchers()

    available = tuple(
        descriptor
        for descriptor in registry.descriptors()
        if descriptor.provider_id in launchers
    )
    if not available:
        raise RuntimeError("No conversation providers with a GUI are installed.")

    if arguments.provider:
        provider_id = arguments.provider
        if provider_id not in {descriptor.provider_id for descriptor in available}:
            raise ValueError(f"Unknown or unavailable provider: {provider_id}")
    else:
        provider_id = choose_provider(available, default_provider_id="gpt")
        if provider_id is None:
            return 0

    return int(launchers[provider_id](provider_arguments))


if __name__ == "__main__":
    raise SystemExit(main())
