"""
Configuration layer: targets, the target registry and the YAML loader.

A *target* describes one MikroTik router: where it is, how to authenticate
against it and how strict to be about its host key. Targets are registered in
a :class:`TargetRegistry`, which the agent adapter consults by logical id.

Secrets (password, key passphrase) are held as ``SecretStr`` so they are
redacted in ``repr``/``str`` output, in logs and in exception messages
(MODULE_SPECIFICATION.md R7 / D9).

The loader is deliberately **tolerant**: a missing configuration file yields
an empty registry instead of raising, so importing the adapter can never
break the agent boot.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterator, Optional

from ._compat import BaseModel, Field, SecretStr, field_validator

__all__ = [
    "MikroTikTarget",
    "TargetRegistry",
    "load_targets",
    "DEFAULT_TARGETS_PATH",
    "ENV_PASSWORD",
    "ENV_KEY",
]


#: Default location of the target configuration file, next to the repository root.
DEFAULT_TARGETS_PATH = "mikrotik_targets.yaml"

#: Environment variable holding the fallback password for key-less targets.
ENV_PASSWORD = "MIKROTIK_PASSWORD"

#: Environment variable holding the fallback private-key path.
ENV_KEY = "MIKROTIK_KEY"

#: A target id must be a safe slug: it ends up in file names, log lines and
#: command arguments, so whitespace, shell metacharacters and path
#: separators are not allowed.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class MikroTikTarget(BaseModel):
    """A validated connection target.

    Attributes:
        id: Logical name used by the agent, e.g. ``"core-rtr-01"``. Must be a
            safe Python identifier so it can be used safely in file names,
            log lines and command arguments.
        host: Hostname or IP address of the router.
        port: TCP port of the SSH service.
        username: SSH username. ``"admin"`` by default; a dedicated restricted
            account is strongly recommended (spec Q4).
        password: Password, redacted in all representations.
        key_path: Path to a private key file.
        key_passphrase: Passphrase for the private key, redacted.
        group: Optional group name, used to filter the target list.
        known_hosts: Path to an OpenSSH ``known_hosts`` file.
        allow_unknown_host_key: Opt-in insecure mode that disables host-key
            verification. Never enable this in production.
        connect_timeout: Connection timeout in seconds.
        command_timeout: Default command timeout in seconds.
        console_login_params: RouterOS console parameters appended to the
            username with ``+``. The default ``"c"`` disables console colours,
            which removes ANSI escapes from the output and makes parsing
            reliable (investigation report §3.4).
    """

    id: str = Field(description="Logical target id, a safe Python identifier")
    host: str = Field(description="Hostname or IP address of the router")
    port: int = Field(default=22, description="SSH service port")
    username: str = Field(default="admin", description="SSH username")
    password: Optional[SecretStr] = Field(default=None, description="SSH password")
    key_path: Optional[Path] = Field(default=None, description="Private key file")
    key_passphrase: Optional[SecretStr] = Field(default=None, description="Key passphrase")
    group: Optional[str] = Field(default=None, description="Optional group name")
    known_hosts: Optional[Path] = Field(default=None, description="known_hosts file")
    allow_unknown_host_key: bool = Field(
        default=False, description="Disable host-key verification (insecure)"
    )
    connect_timeout: int = Field(default=10, description="Connection timeout in seconds")
    command_timeout: int = Field(default=30, description="Default command timeout in seconds")
    console_login_params: str = Field(
        default="c", description="RouterOS console parameters appended as 'user+params'"
    )

    # -- validators ------------------------------------------------------
    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        """Reject an id that is not a safe slug.

        The id is used in file names, log lines and command arguments, so it
        must not contain whitespace, shell metacharacters or a path
        separator. The rule is deliberately *not* "must be a Python
        identifier": the documented example id, ``core-rtr-01``, contains a
        hyphen and would be rejected by that stricter rule.
        """
        if not value:
            raise ValueError("target id must be a non-empty string")
        if not _SAFE_ID_RE.match(value):
            raise ValueError(
                f"target id {value!r} must consist of letters, digits, '-', '_' "
                "and '.', and must start with a letter or digit"
            )
        if ".." in value:
            raise ValueError(f"target id {value!r} must not contain '..'")
        return value

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        """Reject an empty host."""
        if not value or not value.strip():
            raise ValueError("target host must be a non-empty string")
        return value.strip()

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        """Reject a port outside the valid TCP range."""
        if not (1 <= value <= 65535):
            raise ValueError(f"port {value} is outside the valid range 1-65535")
        return value

    @field_validator("connect_timeout")
    @classmethod
    def _validate_connect_timeout(cls, value: int) -> int:
        """Reject a non-positive connection timeout."""
        if value <= 0:
            raise ValueError("connect_timeout must be a positive number of seconds")
        return value

    @field_validator("command_timeout")
    @classmethod
    def _validate_command_timeout(cls, value: int) -> int:
        """Reject a non-positive command timeout."""
        if value <= 0:
            raise ValueError("command_timeout must be a positive number of seconds")
        return value

    # -- derived values --------------------------------------------------
    @property
    def login_username(self) -> str:
        """The username with the console parameters appended.

        RouterOS documents the ``login_name ::= user_name ['+' parameters]``
        syntax. The default ``"c"`` parameter disables console colours.
        """
        if not self.console_login_params:
            return self.username
        return f"{self.username}+{self.console_login_params}"

    @property
    def has_password(self) -> bool:
        """Whether a password is configured."""
        return self.password is not None

    @property
    def has_key(self) -> bool:
        """Whether a private key is configured."""
        return self.key_path is not None

    def secret_values(self) -> list[str]:
        """Return every secret this target holds, in clear text.

        The adapter uses this to scrub a secret out of any outgoing string.
        Empty strings are never included, so the redaction helper cannot
        accidentally blank out the whole message.
        """
        values: list[str] = []
        if self.password is not None:
            values.append(self.password.get_secret_value())
        if self.key_passphrase is not None:
            values.append(self.key_passphrase.get_secret_value())
        return [v for v in values if v]

    def public_dict(self) -> dict:
        """Return a description of this target **without** any secret.

        This is what ``list_mikrotik_targets()`` returns.
        """
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "group": self.group,
            "auth": "key" if self.has_key else ("password" if self.has_password else "none"),
            "known_hosts": str(self.known_hosts) if self.known_hosts else None,
            "allow_unknown_host_key": self.allow_unknown_host_key,
        }


class TargetRegistry:
    """An in-memory registry of :class:`MikroTikTarget` objects, keyed by id.

    The registry is intentionally simple: a dict plus a little validation.
    It is not thread-safe by design - it is populated once at import time and
    then read.
    """

    def __init__(self, targets: Optional[list[MikroTikTarget]] = None) -> None:
        self._targets: dict[str, MikroTikTarget] = {}
        for target in targets or []:
            self.register(target)

    def register(self, target: MikroTikTarget) -> MikroTikTarget:
        """Register (or replace) a target.

        Args:
            target: The target to register.

        Returns:
            The registered target.

        Raises:
            TypeError: If *target* is not a :class:`MikroTikTarget`.
            ValueError: If the id is already taken by a *different* target.
        """
        if not isinstance(target, MikroTikTarget):
            raise TypeError(
                f"register() expects a MikroTikTarget, got {type(target).__name__}"
            )
        existing = self._targets.get(target.id)
        if existing is not None and existing != target:
            raise ValueError(
                f"target id {target.id!r} is already registered with a different definition"
            )
        self._targets[target.id] = target
        return target

    def get(self, target_id: str) -> Optional[MikroTikTarget]:
        """Return the target with this id, or ``None``."""
        return self._targets.get(target_id)

    def list_targets(self, group: Optional[str] = None) -> list[MikroTikTarget]:
        """Return the registered targets, optionally filtered by group.

        Args:
            group: When given, only targets in this group are returned.

        Returns:
            The matching targets, sorted by id.
        """
        targets = list(self._targets.values())
        if group is not None:
            targets = [t for t in targets if t.group == group]
        return sorted(targets, key=lambda t: t.id)

    def unregister(self, target_id: str) -> bool:
        """Remove a target.

        Returns:
            ``True`` if a target was removed, ``False`` if the id was unknown.
        """
        return self._targets.pop(target_id, None) is not None

    def groups(self) -> list[str]:
        """Return the distinct group names, sorted."""
        found = {t.group for t in self._targets.values() if t.group}
        return sorted(found)

    def clear(self) -> None:
        """Remove every registered target."""
        self._targets.clear()

    def __len__(self) -> int:
        return len(self._targets)

    def __contains__(self, target_id: object) -> bool:
        return target_id in self._targets

    def __iter__(self) -> Iterator[MikroTikTarget]:
        return iter(self.list_targets())

    def __repr__(self) -> str:
        return f"TargetRegistry({sorted(self._targets)!r})"


def _load_yaml(path: Path) -> Any:
    """Parse a YAML file, returning ``None`` when PyYAML is unavailable.

    PyYAML is a hard dependency of the agent, but this module must not fail
    to import if it is missing.
    """
    try:
        import yaml  # noqa: PLC0415 - optional import, deliberately lazy
    except ImportError:  # pragma: no cover - PyYAML is present in this repo
        return None
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _target_from_mapping(data: dict) -> MikroTikTarget:
    """Build a :class:`MikroTikTarget` from a plain mapping.

    Unknown keys are ignored, so a configuration file may carry extra
    documentation fields without breaking the loader.
    """
    known = {
        "id",
        "host",
        "port",
        "username",
        "password",
        "key_path",
        "key_passphrase",
        "group",
        "known_hosts",
        "allow_unknown_host_key",
        "connect_timeout",
        "command_timeout",
        "console_login_params",
    }
    kwargs = {k: v for k, v in data.items() if k in known}
    return MikroTikTarget(**kwargs)


def load_targets(path: str | Path = DEFAULT_TARGETS_PATH) -> TargetRegistry:
    """Load the configured targets from a YAML file.

    The loader is **tolerant** by design:

    * a missing file yields an empty registry (it never raises);
    * a malformed entry is skipped rather than aborting the whole load;
    * ``MIKROTIK_PASSWORD`` and ``MIKROTIK_KEY`` supply the fallback
      credentials for targets that do not carry their own.

    Args:
        path: Path to the YAML file. Defaults to ``mikrotik_targets.yaml``.

    Returns:
        A :class:`TargetRegistry`. Empty when the file is absent or unusable.
    """
    registry = TargetRegistry()
    config_path = Path(path).expanduser()

    if not config_path.is_file():
        return registry

    try:
        data = _load_yaml(config_path)
    except Exception:  # noqa: BLE001 - a broken file must not break the boot
        return registry

    if not isinstance(data, dict):
        return registry

    entries = data.get("targets")
    if not isinstance(entries, list):
        # Tolerate a bare list of targets as the document root.
        entries = data if isinstance(data, list) else []

    env_password = os.environ.get(ENV_PASSWORD)
    env_key = os.environ.get(ENV_KEY)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            target = _target_from_mapping(entry)
        except Exception:  # noqa: BLE001 - skip a malformed entry
            continue

        # Environment fallbacks: only fill in what the file did not provide.
        if target.password is None and env_password:
            target = _with_password(target, env_password)
        if target.key_path is None and env_key:
            target = _with_key(target, env_key)

        try:
            registry.register(target)
        except (TypeError, ValueError):
            # A duplicate id with a different definition - keep the first.
            continue

    return registry


def _with_password(target: MikroTikTarget, password: str) -> MikroTikTarget:
    """Return a copy of *target* with the given password."""
    return MikroTikTarget(
        id=target.id,
        host=target.host,
        port=target.port,
        username=target.username,
        password=SecretStr(password),
        key_path=target.key_path,
        key_passphrase=target.key_passphrase,
        group=target.group,
        known_hosts=target.known_hosts,
        allow_unknown_host_key=target.allow_unknown_host_key,
        connect_timeout=target.connect_timeout,
        command_timeout=target.command_timeout,
        console_login_params=target.console_login_params,
    )


def _with_key(target: MikroTikTarget, key_path: str) -> MikroTikTarget:
    """Return a copy of *target* with the given private key path."""
    return MikroTikTarget(
        id=target.id,
        host=target.host,
        port=target.port,
        username=target.username,
        password=target.password,
        key_path=Path(key_path).expanduser(),
        key_passphrase=target.key_passphrase,
        group=target.group,
        known_hosts=target.known_hosts,
        allow_unknown_host_key=target.allow_unknown_host_key,
        connect_timeout=target.connect_timeout,
        command_timeout=target.command_timeout,
        console_login_params=target.console_login_params,
    )
