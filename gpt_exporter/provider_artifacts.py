"""Install provider wheel artifacts into an isolated per-user MSNE directory."""

from __future__ import annotations

import configparser
import hashlib
import importlib
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath

from gpt_exporter.core.provider_discovery import PROVIDER_ENTRY_POINT_GROUP


@dataclass(frozen=True, slots=True)
class ProviderArtifactInfo:
    """Validated metadata for one provider wheel artifact."""

    path: Path
    distribution_name: str
    version: str
    sha256: str
    entry_points: tuple[tuple[str, str], ...]

    @property
    def directory_name(self) -> str:
        return re.sub(r"[-_.]+", "-", self.distribution_name).lower()


def default_provider_directory() -> Path:
    """Return the isolated per-user directory used for managed provider packages."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    return base / "GPT Exporter" / "providers"


def _safe_member_path(name: str) -> PurePosixPath:
    member = PurePosixPath(name)
    if not name or member.is_absolute() or ".." in member.parts:
        raise ValueError(f"Unsafe path in provider wheel: {name!r}")
    if member.parts and re.match(r"^[A-Za-z]:$", member.parts[0]):
        raise ValueError(f"Unsafe drive path in provider wheel: {name!r}")
    return member


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def inspect_provider_wheel(path: Path | str) -> ProviderArtifactInfo:
    """Validate a wheel and return the provider metadata needed before installation."""
    wheel_path = Path(path).expanduser().resolve()
    if wheel_path.suffix.casefold() != ".whl":
        raise ValueError("Provider installation currently accepts .whl files only")
    if not wheel_path.is_file():
        raise FileNotFoundError(wheel_path)

    digest = hashlib.sha256()
    with wheel_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    try:
        archive = zipfile.ZipFile(wheel_path)
    except zipfile.BadZipFile as error:
        raise ValueError("Provider artifact is not a valid wheel/ZIP archive") from error

    with archive:
        members = archive.infolist()
        for info in members:
            _safe_member_path(info.filename)
            if _is_symlink(info):
                raise ValueError(f"Provider wheel contains a symbolic link: {info.filename}")

        metadata_names = [
            info.filename
            for info in members
            if PurePosixPath(info.filename).name == "METADATA"
            and PurePosixPath(info.filename).parent.name.endswith(".dist-info")
        ]
        if len(metadata_names) != 1:
            raise ValueError("Provider wheel must contain exactly one .dist-info/METADATA file")

        metadata_name = metadata_names[0]
        dist_info_dir = PurePosixPath(metadata_name).parent
        try:
            metadata_text = archive.read(metadata_name).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Provider wheel METADATA is not UTF-8") from error
        metadata = Parser().parsestr(metadata_text)
        distribution_name = (metadata.get("Name") or "").strip()
        version = (metadata.get("Version") or "").strip()
        if not distribution_name or not version:
            raise ValueError("Provider wheel METADATA must define Name and Version")

        entry_points_name = str(dist_info_dir / "entry_points.txt")
        try:
            entry_points_text = archive.read(entry_points_name).decode("utf-8")
        except KeyError as error:
            raise ValueError(
                f"Provider wheel does not declare {PROVIDER_ENTRY_POINT_GROUP!r} entry points"
            ) from error
        except UnicodeDecodeError as error:
            raise ValueError("Provider wheel entry_points.txt is not UTF-8") from error

        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read_string(entry_points_text)
        except configparser.Error as error:
            raise ValueError("Provider wheel has invalid entry_points.txt metadata") from error
        if not parser.has_section(PROVIDER_ENTRY_POINT_GROUP):
            raise ValueError(
                f"Provider wheel does not declare {PROVIDER_ENTRY_POINT_GROUP!r} entry points"
            )
        entry_points = tuple(
            (name.strip(), value.strip())
            for name, value in parser.items(PROVIDER_ENTRY_POINT_GROUP)
            if name.strip() and value.strip()
        )
        if not entry_points:
            raise ValueError("Provider wheel declares an empty provider entry-point group")
        for name, value in entry_points:
            module_name, separator, attribute = value.partition(":")
            if not separator or not module_name.strip() or not attribute.strip():
                raise ValueError(f"Invalid provider entry point {name!r}: {value!r}")

    return ProviderArtifactInfo(
        path=wheel_path,
        distribution_name=distribution_name,
        version=version,
        sha256=digest.hexdigest(),
        entry_points=entry_points,
    )


class ProviderArtifactStore:
    """Manage isolated per-user provider wheel installations."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or default_provider_directory()).expanduser()

    def installed_roots(self) -> tuple[Path, ...]:
        """Return managed distribution roots that can safely be added to ``sys.path``."""
        if not self.root.is_dir():
            return ()
        result: list[Path] = []
        for child in sorted(self.root.iterdir(), key=lambda item: item.name.casefold()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if any(child.glob("*.dist-info/METADATA")):
                result.append(child)
        return tuple(result)

    def destination_for(self, artifact: ProviderArtifactInfo) -> Path:
        return self.root / artifact.directory_name

    def install(self, path: Path | str) -> ProviderArtifactInfo:
        """Install one validated wheel using a staging directory and atomic directory swap."""
        artifact = inspect_provider_wheel(path)
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.destination_for(artifact)
        staging_parent = Path(tempfile.mkdtemp(prefix=".install-", dir=self.root))
        staging = staging_parent / "payload"
        staging.mkdir()
        backup = destination.with_name(destination.name + ".previous")

        try:
            with zipfile.ZipFile(artifact.path) as archive:
                for info in archive.infolist():
                    member = _safe_member_path(info.filename)
                    if _is_symlink(info):
                        raise ValueError(
                            f"Provider wheel contains a symbolic link: {info.filename}"
                        )
                    target = staging.joinpath(*member.parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)

            if backup.exists():
                shutil.rmtree(backup)
            if destination.exists():
                destination.replace(backup)
            try:
                staging.replace(destination)
            except Exception:
                if backup.exists() and not destination.exists():
                    backup.replace(destination)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if staging_parent.exists():
                shutil.rmtree(staging_parent, ignore_errors=True)

        importlib.invalidate_caches()
        return artifact


__all__ = [
    "ProviderArtifactInfo",
    "ProviderArtifactStore",
    "default_provider_directory",
    "inspect_provider_wheel",
]
