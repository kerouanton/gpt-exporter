"""Install and manage provider wheel artifacts in isolated per-user storage."""

from __future__ import annotations

import configparser
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.parser import Parser
from pathlib import Path, PurePosixPath

from gpt_exporter.core.provider_discovery import PROVIDER_ENTRY_POINT_GROUP


_DISTRIBUTION_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_MANIFEST_NAME = ".msne-provider.json"
_MANIFEST_SCHEMA_VERSION = 1


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


@dataclass(frozen=True, slots=True)
class ManagedProviderInfo:
    """Provenance for one distribution managed by MSNE."""

    root: Path
    distribution_name: str
    version: str
    sha256: str
    entry_points: tuple[tuple[str, str], ...]
    source_filename: str = ""
    installed_at: str = ""

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(name for name, _value in self.entry_points)

    @property
    def provenance_complete(self) -> bool:
        return bool(self.sha256 and self.source_filename and self.installed_at)


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


def _validate_distribution_name(name: str) -> str:
    if not _DISTRIBUTION_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid provider distribution name: {name!r}")
    return name


def _safe_member_path(name: str) -> PurePosixPath:
    # Wheel member names are POSIX paths. Reject native Windows separators outright so
    # a crafted member cannot be reinterpreted by Path.joinpath during extraction.
    if not name or "\\" in name or "\x00" in name:
        raise ValueError(f"Unsafe path in provider wheel: {name!r}")
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError(f"Unsafe path in provider wheel: {name!r}")
    if member.parts and re.match(r"^[A-Za-z]:$", member.parts[0]):
        raise ValueError(f"Unsafe drive path in provider wheel: {name!r}")
    return member


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_entry_points(text: str) -> tuple[tuple[str, str], ...]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(text)
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
    return entry_points


def inspect_provider_wheel(path: Path | str) -> ProviderArtifactInfo:
    """Validate a wheel and return the provider metadata needed before installation."""
    wheel_path = Path(path).expanduser().resolve()
    if wheel_path.suffix.casefold() != ".whl":
        raise ValueError("Provider installation currently accepts .whl files only")
    if not wheel_path.is_file():
        raise FileNotFoundError(wheel_path)

    digest = _sha256(wheel_path)

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
        _validate_distribution_name(distribution_name)

        entry_points_name = str(dist_info_dir / "entry_points.txt")
        try:
            entry_points_text = archive.read(entry_points_name).decode("utf-8")
        except KeyError as error:
            raise ValueError(
                f"Provider wheel does not declare {PROVIDER_ENTRY_POINT_GROUP!r} entry points"
            ) from error
        except UnicodeDecodeError as error:
            raise ValueError("Provider wheel entry_points.txt is not UTF-8") from error
        entry_points = _parse_entry_points(entry_points_text)

    return ProviderArtifactInfo(
        path=wheel_path,
        distribution_name=distribution_name,
        version=version,
        sha256=digest,
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

    def _legacy_info(self, root: Path) -> ManagedProviderInfo | None:
        """Read a pre-manifest managed install created by the first Stage C installer."""
        metadata_files = tuple(root.glob("*.dist-info/METADATA"))
        if len(metadata_files) != 1:
            return None
        metadata_file = metadata_files[0]
        try:
            metadata = Parser().parsestr(metadata_file.read_text(encoding="utf-8"))
            distribution_name = (metadata.get("Name") or "").strip()
            version = (metadata.get("Version") or "").strip()
            _validate_distribution_name(distribution_name)
            entry_points_file = metadata_file.parent / "entry_points.txt"
            entry_points = _parse_entry_points(entry_points_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        if not version:
            return None
        return ManagedProviderInfo(
            root=root,
            distribution_name=distribution_name,
            version=version,
            sha256="",
            entry_points=entry_points,
        )

    def _info_for_root(self, root: Path) -> ManagedProviderInfo | None:
        manifest_path = root / _MANIFEST_NAME
        if not manifest_path.is_file():
            return self._legacy_info(root)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if int(payload.get("schema_version", 0)) != _MANIFEST_SCHEMA_VERSION:
                return self._legacy_info(root)
            distribution_name = str(payload["distribution_name"])
            version = str(payload["version"])
            sha256 = str(payload["sha256"])
            source_filename = str(payload.get("source_filename", ""))
            installed_at = str(payload.get("installed_at", ""))
            raw_entry_points = payload["entry_points"]
            entry_points = tuple(
                (str(item[0]), str(item[1])) for item in raw_entry_points
            )
            _validate_distribution_name(distribution_name)
            if not version or not re.fullmatch(r"[0-9a-f]{64}", sha256):
                raise ValueError("invalid managed provider manifest")
            if not entry_points:
                raise ValueError("invalid managed provider manifest")
        except (KeyError, TypeError, ValueError, OSError, UnicodeError, json.JSONDecodeError):
            return self._legacy_info(root)
        return ManagedProviderInfo(
            root=root,
            distribution_name=distribution_name,
            version=version,
            sha256=sha256,
            entry_points=entry_points,
            source_filename=source_filename,
            installed_at=installed_at,
        )

    def managed_distributions(self) -> tuple[ManagedProviderInfo, ...]:
        """Return provenance for all locally managed provider distributions."""
        result: list[ManagedProviderInfo] = []
        for root in self.installed_roots():
            info = self._info_for_root(root)
            if info is not None:
                result.append(info)
        return tuple(result)

    def managed_for_provider(self, provider_id: str) -> ManagedProviderInfo | None:
        """Return the managed distribution declaring one provider entry-point name."""
        provider_id = provider_id.strip()
        matches = [
            info
            for info in self.managed_distributions()
            if provider_id in info.provider_ids
        ]
        if len(matches) > 1:
            raise ValueError(
                f"Multiple managed distributions declare provider id {provider_id!r}"
            )
        return matches[0] if matches else None

    def destination_for(self, artifact: ProviderArtifactInfo) -> Path:
        _validate_distribution_name(artifact.distribution_name)
        root = self.root.expanduser().resolve()
        destination = (root / artifact.directory_name).resolve()
        if destination.parent != root:
            raise ValueError(f"Unsafe provider installation destination: {destination}")
        return destination

    @staticmethod
    def _same_approved_artifact(
        approved: ProviderArtifactInfo,
        current: ProviderArtifactInfo,
    ) -> bool:
        return (
            approved.distribution_name == current.distribution_name
            and approved.version == current.version
            and approved.sha256 == current.sha256
            and approved.entry_points == current.entry_points
        )

    @staticmethod
    def _write_manifest(staging: Path, artifact: ProviderArtifactInfo) -> ManagedProviderInfo:
        installed_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "distribution_name": artifact.distribution_name,
            "version": artifact.version,
            "sha256": artifact.sha256,
            "entry_points": [list(item) for item in artifact.entry_points],
            "source_filename": artifact.path.name,
            "installed_at": installed_at,
        }
        (staging / _MANIFEST_NAME).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ManagedProviderInfo(
            root=staging,
            distribution_name=artifact.distribution_name,
            version=artifact.version,
            sha256=artifact.sha256,
            entry_points=artifact.entry_points,
            source_filename=artifact.path.name,
            installed_at=installed_at,
        )

    def install(
        self,
        artifact_or_path: ProviderArtifactInfo | Path | str,
    ) -> ProviderArtifactInfo:
        """Install/update one wheel using verified bytes and an atomic directory swap."""
        approved = (
            artifact_or_path
            if isinstance(artifact_or_path, ProviderArtifactInfo)
            else inspect_provider_wheel(artifact_or_path)
        )

        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.destination_for(approved)
        staging_parent = Path(tempfile.mkdtemp(prefix=".install-", dir=self.root))
        staging = staging_parent / "payload"
        staging.mkdir()
        snapshot = staging_parent / "approved.whl"
        backup = destination.with_name(destination.name + ".previous")

        try:
            # Snapshot the selected bytes first. Re-inspect that immutable copy and compare
            # it with what the user approved before extracting any executable code.
            shutil.copyfile(approved.path, snapshot)
            current = inspect_provider_wheel(snapshot)
            if not self._same_approved_artifact(approved, current):
                raise ValueError(
                    "Provider artifact changed after confirmation; installation was cancelled"
                )

            with zipfile.ZipFile(snapshot) as archive:
                for info in archive.infolist():
                    member = _safe_member_path(info.filename)
                    if _is_symlink(info):
                        raise ValueError(
                            f"Provider wheel contains a symbolic link: {info.filename}"
                        )
                    target = staging.joinpath(*member.parts)
                    resolved_target = target.resolve()
                    staging_root = staging.resolve()
                    if staging_root not in resolved_target.parents and resolved_target != staging_root:
                        raise ValueError(f"Unsafe path in provider wheel: {info.filename!r}")
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)

            self._write_manifest(staging, approved)

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
        return approved

    def remove_provider(self, provider_id: str) -> ManagedProviderInfo:
        """Remove only the isolated managed copy for ``provider_id``.

        Bundled, editable, or globally installed providers are never deleted by this
        operation. A restart is required before relying on the resulting discovery set.
        """
        info = self.managed_for_provider(provider_id)
        if info is None:
            raise ValueError(f"Provider {provider_id!r} has no locally managed copy")

        root = self.root.expanduser().resolve()
        destination = info.root.expanduser().resolve()
        if destination.parent != root or not destination.is_dir():
            raise ValueError(f"Unsafe managed provider removal target: {destination}")

        trash = root / f".remove-{destination.name}-{uuid.uuid4().hex}"
        destination.replace(trash)
        importlib.invalidate_caches()
        shutil.rmtree(trash, ignore_errors=False)
        return info


__all__ = [
    "ManagedProviderInfo",
    "ProviderArtifactInfo",
    "ProviderArtifactStore",
    "default_provider_directory",
    "inspect_provider_wheel",
]
