r"""
The configuration file — ``~/.config/torvalds/config.toml``.

The agent had **forty-five environment variables** and no file.  A shell
profile is a poor home for forty-five settings: it is loaded into every
shell, it is shared with every other program, and it cannot hold a comment
that explains what a value is for.  The operator asked for a config file
on 2026-10-29:

> *"we do not have a torvalds config file let say i=under ~/.config folder
> but I would like to introduce such folder with name 'torvalds' and under
> this folder we can have a config"*

The location follows the convention of the platform the agent runs on:

    Linux and the BSDs   ~/.config/torvalds/config.toml
    macOS                ~/Library/Application Support/torvalds/config.toml
    Windows              %APPDATA%\torvalds\config.toml

``$XDG_CONFIG_HOME`` is honoured on **every** platform when it is set —
it is an explicit choice by the operator.

Only the configuration file moves to the convention of the platform.  The
**data does not move** — it completes the triad the project already
keeps, and it stays where it is on every system:

    ~/.torvalds/chat_manager.db         what the agent produced
    ~/.torvalds/logs/                   what the agent produced
    ~/.cache/torvalds/agent_cache.json  what the agent produced

Moving those would break the sessions, the logs and the cache of
everybody who already has one.

The **precedence chain** is the one the project already uses — the flag
beats the environment variable — with the file inserted underneath:

    flag  >  environment variable  >  config file  >  built-in default

The file sits **below** the environment variables on purpose.  Every
operator who has been running this agent has environment variables in
their shell profile, and a config file that outranked them would change
the behaviour of every one of them the moment they upgraded — a different
model, a different host, silently.  With the file underneath, nothing
changes for anybody who has no file, the environment variables keep
winning for those who have both, and the file becomes the "set it once,
in one place" layer.

The file is **optional**.  The agent boots exactly as it did before when
there is no file, and a file that cannot be read is a **warning**, not a
failed boot.

**Everything the file contributes reports where it came from.**  Four
layers without provenance is a debugging nightmare — "why is my model X?"
must have an answer.  ``\\config`` prints the effective configuration with
the source of every value, the way the context window already reports its
own source.

The format is **TOML**: ``tomllib`` is in the standard library since
Python 3.11, so it costs no dependency, and a syntax error is a hard
error with a line number — YAML, by contrast, turns a malformed document
into ``None`` and has the Norway problem.

Category: Infrastructure / Configuration
Retriever Keywords: config, configuration, config file, toml, xdg, settings,
                    environment variables, precedence, configuration file
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

__all__ = [
    "APP_DIR_NAME",
    "CONFIG_FILENAME",
    "CONFIG_PATH_ENV",
    "Config",
    "Effective",
    "Setting",
    "SETTINGS",
    "Source",
    "default_config_dir",
    "default_config_path",
]


# ---------------------------------------------------------------------------
# The location
# ---------------------------------------------------------------------------

#: The XDG variable that holds the root of the user's configuration.
#:
#: It is honoured on **every** platform, not only on the ones the XDG
#: Base Directory standard speaks for.  It is an explicit choice by the
#: operator, and it is how the tests point the agent at a temporary
#: directory on any system.
CONFIG_HOME_ENV = "XDG_CONFIG_HOME"

#: The Windows variable that holds the per-user application data.
#: ``C:\Users\<user>\AppData\Roaming`` on a normal installation.
WINDOWS_APP_DATA_ENV = "APPDATA"

#: The macOS directory that holds the application data.
MACOS_APP_SUPPORT_DIR = "~/Library/Application Support"

#: The Windows directory that holds the application data, when
#: ``%APPDATA%`` is not set.
WINDOWS_APP_DATA_FALLBACK = "~/AppData/Roaming"

#: The name of the application's directory inside it.
APP_DIR_NAME = "torvalds"

#: The name of the configuration file.
CONFIG_FILENAME = "config.toml"

#: The environment variable that points at another configuration file.
#: It exists for the tests, for a second installation, and for the
#: operator who keeps the configuration of several machines in one place.
CONFIG_PATH_ENV = "TORVALDS_CONFIG"


def default_config_dir(environ: Optional[Mapping[str, str]] = None) -> Path:
    """The directory that holds the configuration file.

    The directory follows the convention of the platform the agent runs
    on:

    | | |
    |---|---|
    | **Windows** | ``%APPDATA%\\torvalds`` — ``C:\\Users\\<user>\\AppData\\Roaming\\torvalds`` |
    | **macOS** | ``~/Library/Application Support/torvalds`` |
    | **Linux and the BSDs** | ``$XDG_CONFIG_HOME/torvalds``, or ``~/.config/torvalds`` |

    ``$XDG_CONFIG_HOME`` is honoured on **every** platform when it is
    set: it is an explicit choice by the operator, and it beats the
    convention of the system.

    The file is **named** the same everywhere — ``config.toml`` — so the
    documentation of the project describes one file, and the operator
    who moves between the three systems finds it in the place the system
    expects.

    Args:
        environ: The environment to read.  Defaults to ``os.environ``.

    Returns:
        The directory that holds the configuration file.
    """
    env = os.environ if environ is None else environ

    # -- the explicit choice, on any platform ---------------------------
    explicit = (env.get(CONFIG_HOME_ENV) or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_absolute():
            return candidate / APP_DIR_NAME
        # A relative path is **invalid**: the XDG standard says so, and a
        # relative path would make the configuration of the agent depend
        # on the directory it was started in.

    # -- the convention of the platform ---------------------------------
    if sys.platform == "win32":
        app_data = (env.get(WINDOWS_APP_DATA_ENV) or "").strip()
        if app_data:
            candidate = Path(app_data).expanduser()
            if candidate.is_absolute():
                return candidate / APP_DIR_NAME
        return Path(WINDOWS_APP_DATA_FALLBACK).expanduser() / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path(MACOS_APP_SUPPORT_DIR).expanduser() / APP_DIR_NAME

    return Path("~/.config").expanduser() / APP_DIR_NAME


def default_config_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """The path of the configuration file.

    ``$TORVALDS_CONFIG`` when it is set, and the XDG location otherwise.
    """
    env = os.environ if environ is None else environ
    raw = (env.get(CONFIG_PATH_ENV) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return default_config_dir(env) / CONFIG_FILENAME


# ---------------------------------------------------------------------------
# The sources
# ---------------------------------------------------------------------------

class Source:
    """Where a value came from.

    The names are the ones the ``\\config`` command prints, so that the
    operator reads the same words the log writes.
    """

    FLAG = "flag"
    ENVIRONMENT = "environment variable"
    FILE = "config file"
    DEFAULT = "default"

    @staticmethod
    def environment(var: str) -> str:
        return f"environment variable {var}"

    @staticmethod
    def file(path: Path) -> str:
        return f"config file {path}"


# ---------------------------------------------------------------------------
# The settings
# ---------------------------------------------------------------------------

#: The kinds of value a setting can hold.
KIND_STRING = "string"
KIND_INTEGER = "integer"
KIND_BOOLEAN = "boolean"
KIND_RAW = "raw"


@dataclass(frozen=True)
class Setting:
    """One setting of the agent: where it is written, and what it means.

    Attributes:
        key: The dotted name, and the path inside the TOML file —
            ``llm.model`` is ``[llm] model = ...``.
        env_var: The environment variable that overrides the file, or
            ``None`` when the setting has none.
        default: The value used when neither the variable nor the file
            carries it.
        kind: How the value is coerced.  ``raw`` hands the value over
            untouched, for the settings whose validation belongs to the
            command line parser.
        description: One line, for the template and for ``\\config``.
        example: The value shown in the template when there is no default
            — a setting that is "not set" still has to show the operator
            what it may hold.
        choices: The values the setting accepts, when it does not accept
            every value.  A value outside them is a problem, not a crash.
    """

    key: str
    env_var: Optional[str]
    default: Any
    kind: str = KIND_STRING
    description: str = ""
    example: Any = None
    choices: Optional[tuple[str, ...]] = None

    @property
    def section(self) -> str:
        """The TOML table the setting lives in."""
        return self.key.split(".", 1)[0]

    @property
    def option(self) -> str:
        """The name of the setting inside its table."""
        return self.key.split(".", 1)[1] if "." in self.key else self.key


#: Every setting the configuration file may carry.
#:
#: The defaults are the ones the agent uses today.  They are **not** all
#: the same in the two orchestrators — the classic agent allows fifty
#: iterations and the multi-window agent five hundred, and the classic
#: agent has verbose events off while the multi-window agent has them on.
#: The orchestrator therefore passes its own default where it differs, so
#: that the file cannot change what the agent does today.
SETTINGS: tuple[Setting, ...] = (
    # -- the model ------------------------------------------------------
    Setting("llm.model", "TORVALDS_MODEL",
            "richardyoung/qwen3.6-27b-abliterated:Q4_K_M", KIND_STRING,
            "The chat model."),
    Setting("llm.host", "TORVALDS_OLLAMA_HOST",
            "http://localhost:11434", KIND_STRING,
            "The Ollama endpoint that serves the chat model."),
    Setting("llm.context_length", "TORVALDS_CONTEXT_LENGTH",
            None, KIND_INTEGER,
            "The context window to assume, in tokens.",
            example=8192),
    Setting("llm.max_iterations", "TORVALDS_MAX_ITERATIONS",
            50, KIND_INTEGER,
            "How many tool-calling rounds one request may take."),
    Setting("llm.request_timeout", "TORVALDS_REQUEST_TIMEOUT",
            99999, KIND_INTEGER,
            "The timeout of one model request, in seconds."),

    # -- the agent ------------------------------------------------------
    Setting("agent.top_k", "TORVALDS_SIMILARITY_TOP_K",
            8, KIND_INTEGER,
            "How many tools the retriever returns for a query."),
    Setting("agent.event_streaming", "TORVALDS_EVENT_STREAMING",
            True, KIND_BOOLEAN,
            "Stream the workflow events while the agent works."),
    Setting("agent.verbose_events", "TORVALDS_VERBOSE_EVENTS",
            False, KIND_BOOLEAN,
            "Log every event, not only the important ones."),
    Setting("agent.prompt_injection", "TORVALDS_PROMPT_INJECTION",
            True, KIND_BOOLEAN,
            "Add the tool recommendations to the system prompt."),
    Setting("agent.tool_recommendations", "TORVALDS_INCLUDE_RECOMMENDATIONS",
            True, KIND_BOOLEAN,
            "List the available tools in the system prompt."),
    Setting("agent.prompt_template", "TORVALDS_PROMPT_TEMPLATE",
            "", KIND_STRING,
            "The path of a custom system prompt template.",
            example="~/prompts/torvalds.md"),
    Setting("agent.context_guard", "TORVALDS_CONTEXT_GUARD",
            False, KIND_BOOLEAN,
            "Trim the prompt to the context window of the model."),

    # -- the human in the loop -------------------------------------------
    Setting("hitl.enabled", "TORVALDS_HITL_ENABLED",
            True, KIND_BOOLEAN,
            "Ask the operator before a risky tool call."),
    Setting("hitl.method", "TORVALDS_HITL_METHOD",
            "console", KIND_STRING,
            "How the question is asked: 'console' or 'whiptail'."),
    Setting("hitl.timeout", "TORVALDS_HITL_TIMEOUT",
            -1, KIND_INTEGER,
            "How long to wait for an answer, in seconds. -1 waits forever."),
    Setting("hitl.default_answer", "TORVALDS_HITL_DEFAULT_ANSWER",
            "", KIND_STRING,
            "The answer used when nobody replies in time."),
    Setting("hitl.runtime_toggle", "TORVALDS_HITL_RUNTIME_TOGGLE",
            True, KIND_BOOLEAN,
            "Allow the runtime toggle commands of the HITL."),

    # -- the statistics --------------------------------------------------
    Setting("stats.enabled", "TORVALDS_STATS_ENABLED",
            True, KIND_BOOLEAN,
            "Show the statistics of every request."),
    Setting("stats.format", "TORVALDS_STATS_FORMAT",
            "compact", KIND_STRING,
            "How the statistics are rendered: compact, detailed or json."),
    Setting("stats.verbose", "TORVALDS_STATS_VERBOSE",
            False, KIND_BOOLEAN,
            "Show the detailed statistics."),
    Setting("stats.persist", "TORVALDS_STATS_PERSIST",
            True, KIND_BOOLEAN,
            "Keep the statistics between the runs."),
    Setting("stats.max_history", "TORVALDS_STATS_MAX_HISTORY",
            500, KIND_INTEGER,
            "How many requests the statistics keep."),

    # -- the logging -----------------------------------------------------
    Setting("logging.level", None,
            "INFO", KIND_STRING,
            "The logging level: DEBUG, INFO, WARNING, ERROR or CRITICAL.",
            choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")),
    Setting("logging.file", "TORVALDS_LOG_FILE",
            None, KIND_STRING,
            "The log file. A bare name goes into the log directory.",
            example="agent.log"),
    Setting("logging.dir", "TORVALDS_LOG_DIR",
            "~/.torvalds/logs", KIND_STRING,
            "The directory that holds the log, the symlink and the rotations."),
    Setting("logging.max_size", "TORVALDS_LOG_MAX_SIZE",
            "10MB", KIND_RAW,
            "The size at which the log is rotated: B, KB, MB or GB."),
    Setting("logging.max_files", "TORVALDS_LOG_MAX_FILES",
            5, KIND_RAW,
            "How many rotated generations are kept."),
    Setting("logging.symlink", "TORVALDS_LOG_SYMLINK",
            None, KIND_STRING,
            "The name of the symlink to the live log file.",
            example="agent-current.log"),
)


def _render_toml(value: Any, kind: str) -> str:
    """Render a value the way it would be written in the file.

    An integer is a number and a boolean is ``true`` — the template must
    not teach the operator to quote them, because a quoted number is a
    string, and a string where a number belongs is a typo waiting to
    happen.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if kind == KIND_INTEGER and isinstance(value, int):
        return str(value)
    if value is None:
        return '""'
    return f'"{value}"'


#: The values that count as "yes".
TRUE_VALUES = ("true", "1", "yes", "on")
#: The values that count as "no".
FALSE_VALUES = ("false", "0", "no", "off")


@dataclass(frozen=True)
class Effective:
    """One setting, with the value that won and where it came from."""

    key: str
    value: Any
    source: str
    description: str = ""


class _Unset:
    """The marker of "the caller did not pass a default"."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unset>"


UNSET = _Unset()


# ---------------------------------------------------------------------------
# The configuration
# ---------------------------------------------------------------------------

class Config:
    """The configuration of the agent, and the source of every value.

    The file is read **once**, when the object is created.  A file that
    is absent is not an error — that is the normal state of a fresh
    installation.  A file that cannot be read is a **warning**: the
    agent boots with the defaults, and the operator is told why.
    """

    def __init__(
        self,
        path: Optional[Path | str] = None,
        environ: Optional[Mapping[str, str]] = None,
        settings: Iterable[Setting] = SETTINGS,
    ) -> None:
        self.environ = os.environ if environ is None else environ
        self.path = (
            Path(path).expanduser()
            if path is not None
            else default_config_path(self.environ)
        )
        self.settings: dict[str, Setting] = {s.key: s for s in settings}

        #: The problems found in the file.  They are reported, never fatal.
        self.problems: list[str] = []

        #: The file that was **created** by :meth:`ensure_default`, when
        #: it was.  ``None`` when nothing was created.
        self.created: Optional[Path] = None

        #: The problems that were already reported.  A problem is reported
        #: **once**: the file is validated when it is read, and again
        #: when a setting is resolved, and the operator must not see the
        #: same line twice.
        self._reported: set[str] = set()

        #: The source of every value that was resolved.
        self._sources: dict[str, str] = {}

        self._data: dict[str, Any] = {}
        self.present = False
        self._load()

    # -- the file ---------------------------------------------------------

    def _load(self) -> None:
        """Read the file, if there is one."""
        if not self.path.is_file():
            return

        self.present = True
        try:
            with self.path.open("rb") as handle:
                self._data = tomllib.load(handle)
        except OSError as exc:
            self.problems.append(
                f"the config file {self.path} could not be read ({exc}) — "
                f"the defaults are used"
            )
            self._data = {}
            return
        except tomllib.TOMLDecodeError as exc:
            self.problems.append(
                f"the config file {self.path} is not valid TOML ({exc}) — "
                f"the defaults are used"
            )
            self._data = {}
            return

        self._check_keys()
        self._check_values()

    def _check_values(self) -> None:
        """Validate every setting the file carries.

        The file is checked **as a whole**, when it is read, and not only
        when a setting happens to be resolved: the operator must see
        every problem of the file at once, and not only the ones of the
        settings the agent happened to ask for.
        """
        for key, setting in self.settings.items():
            raw, present = self._file_value(key)
            if present:
                self._coerce(setting, raw)

    def _check_keys(self) -> None:
        """Report the keys the agent does not know.

        A typo in the file is invisible otherwise: the agent would simply
        ignore the setting and the operator would wonder why nothing
        changed.
        """
        known_sections = {s.section for s in self.settings.values()}
        for section, table in self._data.items():
            if not isinstance(table, dict):
                self._problem(
                    f"the section [{section}] of {self.path} is not a table"
                )
                continue
            if section not in known_sections:
                self._problem(
                    f"the section [{section}] of {self.path} is not known to "
                    f"the agent — it is ignored"
                )
                continue
            known_options = {
                s.option for s in self.settings.values() if s.section == section
            }
            for option in table:
                if option not in known_options:
                    self._problem(
                        f"the setting [{section}] {option} of {self.path} is "
                        f"not known to the agent — it is ignored"
                    )

    def _problem(self, message: str) -> None:
        """Report a problem — once."""
        if message in self._reported:
            return
        self._reported.add(message)
        self.problems.append(message)

    # -- the values -------------------------------------------------------

    def _file_value(self, key: str) -> tuple[Any, bool]:
        """The value the file carries for a setting, and whether it has one."""
        setting = self.settings.get(key)
        if setting is None:
            return None, False
        table = self._data.get(setting.section)
        if not isinstance(table, dict):
            return None, False
        if setting.option not in table:
            return None, False
        return table[setting.option], True

    def _coerce(self, setting: Setting, raw: Any) -> tuple[Any, bool]:
        """Coerce a value to the kind of the setting.

        Returns the value and whether it could be coerced.  A value that
        cannot be coerced is a **problem**, and the setting falls back to
        its default — the agent must not die because a file has a typo.
        """
        if setting.kind == KIND_RAW:
            return raw, True

        if setting.kind == KIND_INTEGER:
            if isinstance(raw, bool):
                self._problem(
                    f"the setting {setting.key} must be a number, not a "
                    f"boolean"
                )
                return None, False
            try:
                return int(raw), True
            except (TypeError, ValueError):
                self._problem(
                    f"the setting {setting.key} must be a number, not {raw!r}"
                )
                return None, False

        if setting.kind == KIND_BOOLEAN:
            if isinstance(raw, bool):
                return raw, True
            text = str(raw).strip().lower()
            if text in TRUE_VALUES:
                return True, True
            if text in FALSE_VALUES:
                return False, True
            self._problem(
                f"the setting {setting.key} must be true or false, not {raw!r}"
            )
            return None, False

        # A string.
        if isinstance(raw, (dict, list)):
            self._problem(
                f"the setting {setting.key} must be a single value, not "
                f"{raw!r}"
            )
            return None, False
        value = str(raw)

        if setting.choices:
            for choice in setting.choices:
                if choice.lower() == value.strip().lower():
                    return choice, True
            self._problem(
                f"the setting {setting.key} must be one of "
                f"{', '.join(setting.choices)} — not {raw!r}"
            )
            return None, False

        return value, True

    def get(self, key: str, default: Any = UNSET) -> Any:
        """The value of a setting, and where it came from.

        The chain is **environment variable, then config file, then the
        default**.  The flag is not part of it — the flag is applied by
        the orchestrator, and it is recorded with :meth:`flag`.

        Args:
            key: The dotted name of the setting, e.g. ``llm.model``.
            default: Overrides the default of the setting.  ``None``
                     therefore means "no default at all", which is how
                     the caller asks whether the file carries a value.

        Returns:
            The value that won.
        """
        setting = self.settings.get(key)
        if setting is None:
            raise KeyError(f"unknown setting: {key}")

        fallback = setting.default if default is UNSET else default

        # 1. The environment variable.
        if setting.env_var:
            raw = self.environ.get(setting.env_var)
            if raw is not None and str(raw).strip():
                value, ok = self._coerce(setting, raw)
                if ok:
                    self._sources[key] = Source.environment(setting.env_var)
                    return value

        # 2. The config file.
        raw, present = self._file_value(key)
        if present:
            value, ok = self._coerce(setting, raw)
            if ok:
                self._sources[key] = Source.file(self.path)
                return value

        # 3. The default.
        self._sources[key] = Source.DEFAULT
        return fallback

    def flag(self, key: str, value: Any) -> Any:
        """Record that the **flag** won for a setting, and return the value.

        The orchestrators apply the flags themselves — they already did,
        long before this file existed.  This only records where the value
        came from, so that ``\\config`` can tell the operator that their
        flag beat their file.
        """
        self._sources[key] = Source.FLAG
        return value

    def source(self, key: str) -> str:
        """Where the value of a setting came from."""
        return self._sources.get(key, Source.DEFAULT)

    def effective(self) -> list[Effective]:
        """Every setting, with the value that won and where it came from.

        The settings that were never resolved are skipped — the caller
        decides which ones the agent actually uses.
        """
        rows: list[Effective] = []
        # The order of the registry, not the order of the resolution: the
        # table the operator reads must not depend on which setting
        # happened to be asked for first.
        for key, setting in self.settings.items():
            if key not in self._sources:
                continue
            rows.append(
                Effective(
                    key=key,
                    value=self.get(key),
                    source=self.source(key),
                    description=setting.description,
                )
            )
        return rows

    # -- the template -----------------------------------------------------

    def default_template(self) -> str:
        """A commented configuration file with every setting and its default.

        It is what ``--write-default-config`` writes, and it is the
        answer to "what can I put in there?".
        """
        lines = [
            "# The configuration of the Torvalds agent.",
            "#",
            "# Every setting below is shown with its default.  Uncomment a",
            "# line and change the value to make it yours.",
            "#",
            "# The environment variable of a setting overrides this file, and",
            "# the command line flag overrides both.  The order is:",
            "#",
            "#     flag  >  environment variable  >  this file  >  default",
            "#",
            "# A broken file is a warning, not a failed boot: the agent",
            "# starts with the defaults and tells you what it could not read.",
            "",
        ]
        section = None
        for setting in SETTINGS:
            if setting.section != section:
                section = setting.section
                lines.append("")
                lines.append(f"[{section}]")
            if setting.description:
                lines.append(f"# {setting.description}")
            if setting.env_var:
                lines.append(f"# Overrides: {setting.env_var}")
            value = setting.default
            if value is None:
                value = setting.example
            lines.append(
                f"# {setting.option} = {_render_toml(value, setting.kind)}"
            )
        lines.append("")
        return "\n".join(lines)

    def ensure_default(self) -> Optional[Path]:
        """Create the configuration file, if it is not there yet.

        The agent writes the **template** into the default location when
        it starts and the file is not there.  The template carries **no
        settings** — every one of its lines is a comment — so the file
        changes nothing about the way the agent runs.  It is a starting
        point for the operator, not a change of behaviour.

        Only the **default** location is written to.  A file the operator
        named with ``TORVALDS_CONFIG`` is theirs: they pointed at it on
        purpose, and a file that is not there is not an invitation to
        create one.

        Nothing here is fatal.  A home directory that cannot be written
        to is a **problem**, and the agent boots.

        Returns:
            The path that was created, or ``None`` when nothing was
            written.
        """
        env = self.environ
        if (env.get(CONFIG_PATH_ENV) or "").strip():
            # The operator named the file with the environment variable.
            # They pointed at it on purpose, and a file that is not there
            # is not an invitation to create one.
            return None
        if self.path != default_config_dir(env) / CONFIG_FILENAME:
            # It is not the default location either — it was named in the
            # code, or by the caller.  It is not ours to create.
            return None

        if self.path.is_symlink():
            self.problems.append(
                f"the configuration file {self.path} is a symbolic link — "
                f"the defaults are used"
            )
            return None

        if self.path.exists():
            # It is there, and it is never overwritten.
            self.present = self.path.is_file()
            return None

        try:
            written = self.write_default()
        except OSError as exc:
            if isinstance(exc, FileExistsError) and self.path.exists():
                # Another agent created it between the check and the
                # write.  The file is there, and it is not ours.
                self.present = True
                return None
            self.problems.append(
                f"the configuration file {self.path} could not be created "
                f"({exc}) — the defaults are used"
            )
            return None

        self.present = True
        self.created = written
        return written

    def write_default(
        self,
        path: Optional[Path | str] = None,
        overwrite: bool = False,
    ) -> Path:
        """Write the commented template, and return the path it was written to.

        The file is created with the mode ``0600`` **at creation**: it may
        hold a host, a model and a path, and it belongs to the operator
        alone — a file that is briefly readable by every account on the
        box is a file that was exposed.  Creating it with the mode is
        the only way to be sure there is no such moment.

        On **Windows** the mode is not a mode: there are no POSIX
        permissions there, and the access is decided by the ACL of the
        directory.  The mode is still asked for — it costs nothing, and
        it keeps the file writable, which is what the agent needs.

        An existing file is **not** overwritten.  The template is a
        starting point, and the settings the operator wrote into it are
        worth more than a fresh copy of the defaults: running
        ``--write-default-config`` twice must not throw away what was
        written in between.

        A symbolic link is **never** written through.  The link and the
        file it points at are two different things, and only the operator
        knows which one they meant.

        Args:
            path: Where to write.  The configured path when it is omitted.
            overwrite: Write over an existing file.  Off by default.

        Returns:
            The path that was written.

        Raises:
            FileExistsError: The file is there already, or the path is a
                symbolic link, and nothing was written.
        """
        target = Path(path).expanduser() if path is not None else self.path

        if target.is_symlink():
            raise FileExistsError(
                f"{target} is a symbolic link — the template was not written"
            )
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"{target} already exists — the template was not written, "
                f"and the file was left as it is"
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        # O_EXCL makes the creation atomic: the file is either created
        # here, or it was there already and nothing is written to it.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if not overwrite:
            flags |= os.O_EXCL
        handle = os.open(target, flags, 0o600)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(self.default_template())
        except BaseException:
            # A half-written template is worse than no template.
            try:
                os.unlink(target)
            except OSError:
                pass
            raise

        try:
            os.chmod(target, 0o600)
        except OSError:
            # A filesystem without the mode is not a reason to fail.
            pass
        return target


#: The configuration of the running agent.
#:
#: It is read once, when the module is imported, because the
#: orchestrators read their settings at import time — that is where the
#: environment variables were read before, and the file must not be read
#: later than the environment.
config = Config()
