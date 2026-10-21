"""
Configuration for the Shodan toolkit.

The toolkit is configured through a combination of environment variables and
an optional JSON/YAML-free config file.  Resolution order (highest priority
first):

1. Explicit arguments passed to :class:`ShodanConfig` / the factory functions.
2. Environment variables (``SHODAN_TOOLKIT_*``).
3. The JSON config file (``~/.config/shodan-toolkit/config.json`` by default).
4. Built-in defaults.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "ShodanConfig",
    "load_config",
    "default_config_path",
    "ENV_PREFIX",
]

ENV_PREFIX = "SHODAN_TOOLKIT_"

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RESULTS = 100
DEFAULT_SHODAN_CONFIG_DIR = "~/.config/shodan"


def default_config_path() -> Path:
    """Return the default location of the toolkit's config file."""
    override = os.environ.get(f"{ENV_PREFIX}CONFIG")
    if override:
        return Path(override).expanduser()
    return Path("~/.config/shodan-toolkit/config.json").expanduser()


@dataclass
class ShodanConfig:
    """Runtime configuration for the toolkit.

    Attributes:
        executable: The Shodan CLI executable (name or absolute path).
        timeout: Per-command timeout in seconds.
        max_results: Default cap on the number of results returned by a search.
        shodan_config_dir: Directory where the Shodan CLI stores its API key.
        api_key: Optional explicit API key.  When set it is exported to the
            child process as ``SHODAN_API_KEY``.
        config_path: Path to the toolkit's JSON config file.
        extra_env: Additional environment variables for the child process.
    """

    executable: str = "shodan"
    timeout: float = DEFAULT_TIMEOUT
    max_results: int = DEFAULT_MAX_RESULTS
    shodan_config_dir: str = DEFAULT_SHODAN_CONFIG_DIR
    api_key: Optional[str] = None
    config_path: Optional[str] = None
    extra_env: Dict[str, str] = field(default_factory=dict)

    # -- construction -----------------------------------------------------

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShodanConfig:
        """Build a config from a plain dictionary, ignoring unknown keys."""
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_env(cls, base: Optional[ShodanConfig] = None) -> ShodanConfig:
        """Overlay environment variables onto an existing config."""
        config = base or cls()

        executable = os.environ.get(f"{ENV_PREFIX}EXECUTABLE")
        if executable:
            config.executable = executable

        timeout = os.environ.get(f"{ENV_PREFIX}TIMEOUT")
        if timeout:
            with contextlib.suppress(ValueError):
                config.timeout = float(timeout)

        max_results = os.environ.get(f"{ENV_PREFIX}MAX_RESULTS")
        if max_results:
            with contextlib.suppress(ValueError):
                config.max_results = int(max_results)

        shodan_dir = os.environ.get(f"{ENV_PREFIX}SHODAN_CONFIG_DIR")
        if shodan_dir:
            config.shodan_config_dir = shodan_dir

        api_key = os.environ.get(f"{ENV_PREFIX}API_KEY") or os.environ.get(
            "SHODAN_API_KEY"
        )
        if api_key:
            config.api_key = api_key

        return config

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> ShodanConfig:
        """Load a config from a JSON file (missing file yields defaults)."""
        target = Path(path).expanduser() if path else default_config_path()
        config = cls(config_path=str(target))

        if not target.exists():
            return config

        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config

        if isinstance(data, dict):
            loaded = cls.from_dict(data)
            loaded.config_path = str(target)
            return loaded

        return config

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict (the API key is redacted)."""
        data = asdict(self)
        if data.get("api_key"):
            data["api_key"] = "***redacted***"
        return data

    def save(self, path: Optional[str] = None) -> Path:
        """Persist the config to disk as JSON."""
        target = Path(path).expanduser() if path else (
            Path(self.config_path) if self.config_path else default_config_path()
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        data = asdict(self)
        data["config_path"] = str(target)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target


def load_config(
    config_path: Optional[str] = None,
    use_env: bool = True,
) -> ShodanConfig:
    """Load the effective configuration.

    Args:
        config_path: Optional explicit path to a JSON config file.
        use_env: Whether to overlay environment variables.

    Returns:
        The resolved :class:`ShodanConfig`.
    """
    config = ShodanConfig.from_file(config_path)
    if use_env:
        config = ShodanConfig.from_env(config)
    return config
