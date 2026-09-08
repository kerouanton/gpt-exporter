"""Top-level application composition for selectable conversation providers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.ui.provider_selector import choose_provider
from gpt_exporter.version import APP_NAME, display_version

ProviderLauncher = Callable[[list[str]], int]


def _provider_package_missing(error: ModuleNotFoundError, package: str) -> bool:
    return bool(error.name and (error.name == package or error.name.startswith(package + ".")))


def build_provider_registry() -> ProviderRegistry:
    """Register concrete providers at the application boundary.

    Concrete imports live here rather than in ``gpt_exporter.core`` so the core
    remains usable when any provider package is absent.
    """
    registry = ProviderRegistry()

    try:
        from gpt_exporter.providers.gpt.provider import ChatGPTProvider
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.gpt"):
            raise
    else:
        registry.register(ChatGPTProvider())

    try:
        from gpt_exporter.providers.discord.provider import DiscordProvider
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.discord"):
            raise
    else:
        registry.register(DiscordProvider())

    return registry


def _run_provider_main(provider_main: Callable[[], int], arguments: list[str]) -> int:
    previous = sys.argv
    try:
        sys.argv = [previous[0], *arguments]
        return int(provider_main())
    finally:
        sys.argv = previous


def _launch_gpt(arguments: list[str]) -> int:
    from gpt_exporter.providers.gpt.ui import app as provider_app

    return _run_provider_main(provider_app.main, arguments)


def _launch_discord(arguments: list[str]) -> int:
    from gpt_exporter.providers.discord.ui import app as provider_app

    return _run_provider_main(provider_app.main, arguments)


def build_provider_launchers() -> dict[str, ProviderLauncher]:
    """Return lazy launchers for provider UIs installed with this application."""
    launchers: dict[str, ProviderLauncher] = {}

    try:
        from gpt_exporter.providers.gpt import provider as _gpt_provider  # noqa: F401
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.gpt"):
            raise
    else:
        launchers["gpt"] = _launch_gpt

    try:
        from gpt_exporter.providers.discord import provider as _discord_provider  # noqa: F401
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.discord"):
            raise
    else:
        launchers["discord"] = _launch_discord

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
