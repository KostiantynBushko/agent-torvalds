"""
The RouterOS session: the SSH transport and the CLI state machine.

Two transports are supported:

``exec``
    A one-shot ``ssh host 'command'``. The router's error text arrives on
    **stderr** with a non-zero exit status, so stdout and stderr are cleanly
    separated without any parsing heuristics. This is the preferred transport
    for stateless read commands.
``session``
    One SSH connection, many commands. Required for stateful operations
    (``cd`` changes the CLI context) and for commands whose output must be
    captured verbatim, such as ``/export``.

The hard constraint of the MikroTik SSH server is that it provides **no
pseudo-terminal**. A multi-line script therefore cannot be delivered over SSH
at all; such a command is rejected with
:class:`~.exceptions.MultilineUnsupportedError` rather than being truncated
on the router.

``asyncssh`` is imported lazily, inside :meth:`RouterOSSession.connect`, so
this module imports cleanly on a machine without it.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Optional

from .config import MikroTikTarget
from .exceptions import (
    AuthError,
    CommandRejectedError,
    CommandTimeoutError,
    ConnectionError_,
    HostKeyError,
    InteractiveInputRequiredError,
    MikroTikError,
    MultilineUnsupportedError,
    PagingError,
)
from .models import CommandResult
from .parser import parse_print_table
from .safety import contains_injection_patterns

__all__ = [
    "RouterOSSession",
    "PROMPT_RE",
    "CONTINUATION_RE",
    "VALUE_REQUEST_RE",
    "PAGING_RE",
    "SAFE_MODE_MARKER",
    "SAFE_MODE_ENTER",
    "SAFE_MODE_EXIT",
]


# ---------------------------------------------------------------------------
# Prompt detection (validated - see INVESTIGATION_REPORT.md section 5.3)
# ---------------------------------------------------------------------------

#: Matches a RouterOS prompt **at the end** of the buffer. The anchoring is
#: what makes the detection reliable: a prompt-like string quoted inside log
#: output does not end the buffer and therefore does not match.
PROMPT_RE = re.compile(
    r"\[(?P<user>[^\]\r\n]{1,64})@(?P<host>[^\]\r\n]{1,64})\]"   # [user@host]
    r"(?:\s*<SAFE>)?"                                            # safe-mode marker
    r"(?P<path>(?:\s*/[^\s<>\r\n]+)*"                            # slash path, e.g. /ip/route
    r"|(?:\s+[^\s<>\r\n]+(?:\s+[^\s<>\r\n]+)*)?)?"                # or space-separated path
    r"(?:\s*<(?P<bracket>[^>\r\n]*)>)?"                           # bracketed path form
    r"(?:\s*>)?\s*$"                                            # optional trailing '>'
)

#: A multi-line continuation prompt ("line 2 of 3>"). The MikroTik SSH
#: server cannot deliver a multi-line command, so seeing one means the
#: command was truncated and must be reported.
CONTINUATION_RE = re.compile(r"line\s+\d+\s+of\s+\d+\s*>\s*$")

#: A value-request prompt ("old password: "). Such a command needs
#: interactive input that a non-interactive channel cannot supply.
VALUE_REQUEST_RE = re.compile(r"^[A-Za-z0-9 _\-/()']+:\s*$")

#: The paging prompt. RouterOS asks the operator to press a key to see the
#: next screenful; over SSH there is nobody to press it.
PAGING_RE = re.compile(r"--\[Q\s*\|\s*more\s*\]--", re.IGNORECASE)

#: The safe-mode marker, as it appears in the prompt.
SAFE_MODE_MARKER = "<SAFE>"

#: Ctrl+X - enters RouterOS safe mode.
SAFE_MODE_ENTER = "\x18"

#: Ctrl+D - leaves RouterOS safe mode without saving.
SAFE_MODE_EXIT = "\x04"

#: RouterOS error messages the session layer recognises.
_ERROR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"invalid command name\s+(?P<what>\S+)", re.IGNORECASE), "invalid command name"),
    (re.compile(r"bad command name\s+(?P<what>\S+)", re.IGNORECASE), "bad command name"),
    (re.compile(r"no such item(?: \(?\d*\)?)?", re.IGNORECASE), "no such item"),
    (re.compile(r"failure:\s*already have such address", re.IGNORECASE), "failure: already have such address"),
    (re.compile(r"syntax error \(line \d+ column \d+\)", re.IGNORECASE), "syntax error"),
    (re.compile(r"\berror:\s*", re.IGNORECASE), "router error"),
    (re.compile(r"^\s*unknown command", re.IGNORECASE), "unknown command"),
    (re.compile(r"not enough parameters", re.IGNORECASE), "not enough parameters"),
    (re.compile(r"too many parameters", re.IGNORECASE), "too many parameters"),
)


def _detect_error(text: str) -> Optional[str]:
    """Return the recognised RouterOS error in *text*, or ``None``."""
    if not text:
        return None
    for pattern, label in _ERROR_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _strip_prompt(text: str) -> tuple[str, Optional[str]]:
    """Remove the trailing prompt from *text*.

    Returns:
        ``(body, prompt_path)``. ``prompt_path`` is the CLI path the router
        was in (``"/ip/route"``), or ``None`` when there was no prompt.
    """
    if not text:
        return "", None
    match = PROMPT_RE.search(text)
    if not match:
        return text, None
    body = text[: match.start()]
    path = (match.group("path") or "").strip()
    if not path:
        path = (match.group("bracket") or "").strip()
    return body, path or None


def _is_safe_mode(text: str) -> bool:
    """Whether the prompt in *text* carries the safe-mode marker."""
    match = PROMPT_RE.search(text or "")
    if not match:
        return SAFE_MODE_MARKER in (text or "")
    if SAFE_MODE_MARKER in (match.group(0) or ""):
        return True
    return (match.group("bracket") or "").upper() == "SAFE"


def _needs_paging_suffix(command: str) -> bool:
    """Whether *command* is a ``print`` that needs the ``without-paging`` suffix."""
    text = " ".join((command or "").strip().split())
    if not text:
        return False
    lowered = text.lower()
    if "without-paging" in lowered:
        return False
    # Only a print-style command can page.
    return bool(re.search(r"(^|/)\S*print(\s|$)", lowered))


def _add_without_paging(command: str) -> str:
    """Append ``without-paging`` to a print command when it is missing."""
    text = command.strip()
    if not _needs_paging_suffix(text):
        return text
    if text.lower().endswith("print"):
        return f"{text} without-paging"
    return f"{text} without-paging"


class RouterOSSession:
    """An async RouterOS CLI session over SSH.

    The session is an async context manager::

        async with RouterOSSession(target) as session:
            result = await session.run("/system/resource/print")

    Attributes:
        target: The router this session is bound to.
    """

    def __init__(self, target: MikroTikTarget) -> None:
        self._target = target
        self._conn: Any = None
        self._writer: Any = None
        self._reader: Any = None
        self._closed = True
        self._safe_mode = False

    # -- properties ------------------------------------------------------
    @property
    def target(self) -> MikroTikTarget:
        """The router this session is bound to."""
        return self._target

    @property
    def is_connected(self) -> bool:
        """Whether the session currently holds a live connection."""
        return self._conn is not None and not self._closed

    # -- context manager -------------------------------------------------
    async def __aenter__(self) -> "RouterOSSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # -- connection ------------------------------------------------------
    async def connect(self) -> "RouterOSSession":
        """Open the SSH connection and consume the banner.

        Key authentication is preferred; password authentication is used when
        no key is configured. The host-key policy is applied as configured on
        the target.

        Returns:
            ``self``, so the call can be chained.

        Raises:
            AuthError: The credentials were rejected.
            HostKeyError: The host key did not match the stored fingerprint.
            ConnectionError_: The router could not be reached.
            MikroTikError: ``asyncssh`` is not installed.
        """
        try:
            import asyncssh  # noqa: PLC0415 - deliberately lazy
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise MikroTikError(
                "the 'asyncssh' package is required for the MikroTik SSH transport "
                "but is not installed",
                code="UNREACHABLE",
            ) from exc

        target = self._target
        kwargs: dict[str, Any] = {
            "port": target.port,
            "username": target.login_username,
            "encoding": "utf-8",
            "errors": "replace",
            "known_hosts": self._known_hosts_arg(),
        }

        if target.key_path is not None:
            kwargs["client_keys"] = [str(target.key_path)]
            if target.key_passphrase is not None:
                kwargs["passphrase"] = target.key_passphrase.get_secret_value()
        elif target.password is not None:
            kwargs["password"] = target.password.get_secret_value()
        else:
            kwargs["client_keys"] = None
            kwargs["agent_path"] = None

        try:
            conn = await asyncssh.connect(target.host, **kwargs)
        except Exception as exc:  # noqa: BLE001 - classified below
            raise self._classify_connect_error(exc) from exc

        self._conn = conn
        self._closed = False

        # Open the interactive channel. The MikroTik server provides no
        # pseudo-terminal, but a plain session channel is still required for
        # the stateful CLI.
        try:
            writer, reader, _ = await conn.open_session(
                term_type=None, term_size=None
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            await self.close()
            raise self._classify_connect_error(exc) from exc

        self._writer = writer
        self._reader = reader

        # Consume the banner: logo, upgrade notice, /system note, and the
        # "Please press Enter to continue!" prompt of demo builds.
        await self._read_banner()

        return self

    def _known_hosts_arg(self) -> Any:
        """Build the ``known_hosts`` argument for asyncssh.

        ``None`` disables verification entirely and is only used when the
        operator explicitly opted in.
        """
        target = self._target
        if target.allow_unknown_host_key:
            return None
        if target.known_hosts is not None:
            return str(target.known_hosts)
        # No explicit known_hosts file: fall back to asyncssh's default
        # (~/.ssh/known_hosts). Passing "" would mean "trust nothing", which
        # would make every fresh router unusable.
        return ()

    def _classify_connect_error(self, exc: Exception) -> MikroTikError:
        """Turn an asyncssh connection error into a typed toolkit error."""
        name = type(exc).__name__
        text = str(exc)

        if name in ("HostKeyNotVerifiable", "KeyImportError"):
            return HostKeyError(
                f"the host key of {self._target.host} did not match the expected "
                f"fingerprint - the router may have been re-imaged, or the "
                f"connection may be intercepted ({text})"
            )
        if name in ("PermissionDenied", "PasswordRequired", "PublicKeyRejected"):
            return AuthError(
                f"the router rejected the credentials for user "
                f"'{self._target.username}' ({text})"
            )
        if name in ("HostKeyNotVerifiableError",):
            return HostKeyError(text)
        if name in ("ConnectionLost", "ConnectionRefused", "TimeoutError", "OSError"):
            return ConnectionError_(
                f"could not reach {self._target.host}:{self._target.port} ({text})"
            )
        return ConnectionError_(
            f"could not connect to {self._target.host}:{self._target.port} "
            f"({name}: {text})"
        )

    async def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        conn = self._conn
        self._conn = None
        self._writer = None
        self._reader = None
        self._closed = True
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - closing must not raise
                pass

    # -- banner ----------------------------------------------------------
    async def _read_banner(self) -> str:
        """Read the banner up to the first prompt.

        Tolerates the RouterOS logo, an upgrade notice, a ``/system note``
        message and the "Please press Enter to continue!" prompt of demo
        builds. When the banner asks the operator to press Enter, the
        toolkit sends it.

        Returns:
            The raw banner text.
        """
        buffer, _ = await self._read_until_prompt(self._target.connect_timeout)
        # A demo build may ask for Enter before showing the prompt.
        if "press enter" in buffer.lower():
            await self._write("\n")
            buffer, _ = await self._read_until_prompt(self._target.connect_timeout)
        return buffer

    # -- low level IO ----------------------------------------------------
    async def _write(self, data: str) -> None:
        """Write to the channel and flush."""
        writer = self._writer
        if writer is None:
            raise ConnectionError_("the session is not connected")
        writer.write(data)
        await writer.drain()

    async def _read_until_prompt(self, timeout: float) -> tuple[str, Optional[str]]:
        """Read until a RouterOS prompt appears at the end of the buffer.

        Args:
            timeout: Maximum number of seconds to wait.

        Returns:
            ``(buffer, prompt_path)``. When the timeout expires, the raw
            buffer is returned with a ``None`` prompt path - the caller
            decides whether that is an error.

        Raises:
            CommandTimeoutError: The timeout expired.
            PagingError: The router started paging its output.
            InteractiveInputRequiredError: The router asked for a value.
        """
        reader = self._reader
        if reader is None:
            raise ConnectionError_("the session is not connected")

        buffer = ""
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandTimeoutError(
                    f"no RouterOS prompt within {timeout:g}s"
                )
            try:
                chunk = await asyncio.wait_for(
                    reader.read(4096), timeout=min(remaining, 1.0)
                )
            except asyncio.TimeoutError:
                continue

            if chunk in (None, ""):
                raise ConnectionError_("the router closed the session")

            buffer += chunk

            if PAGING_RE.search(buffer):
                raise PagingError(
                    "the router paged its output; append 'without-paging' to the command"
                )

            if CONTINUATION_RE.search(buffer):
                raise MultilineUnsupportedError(
                    "the router asked for a multi-line continuation; MikroTik's SSH "
                    "server cannot deliver a multi-line command"
                )

            if VALUE_REQUEST_RE.search(buffer.rstrip("\r\n").splitlines()[-1] if buffer.strip() else ""):
                raise InteractiveInputRequiredError(
                    "the command requires interactive input and cannot be run "
                    "over a non-interactive SSH channel"
                )

            if PROMPT_RE.search(buffer):
                # Every prompt updates the safe-mode state, so the flag is
                # always current - including after a command that put the
                # router into (or out of) safe mode.
                self._safe_mode = _is_safe_mode(buffer)
                _, prompt_path = _strip_prompt(buffer)
                return buffer, prompt_path

    # -- commands --------------------------------------------------------
    async def run(self, command: str, timeout: Optional[float] = None) -> CommandResult:
        """Run one command on the interactive channel.

        Args:
            command: The command to run. It must be a single line.
            timeout: Timeout in seconds. Defaults to the target's
                ``command_timeout``.

        Returns:
            A :class:`~.models.CommandResult`. A command the router refused
            is reported through ``ok=False`` and the ``error`` code rather
            than by raising, so a caller can present the router's message.

        Raises:
            MultilineUnsupportedError: The command was multi-line or chained.
            CommandTimeoutError: The command did not complete in time.
        """
        self._guard_multiline(command)

        timeout = float(timeout if timeout is not None else self._target.command_timeout)
        started = time.monotonic()
        safe_command = _add_without_paging(command)

        await self._write(safe_command + "\n")

        try:
            buffer, prompt_path = await self._read_until_prompt(timeout)
        except CommandTimeoutError:
            # The prompt was never seen. Return the raw buffer so the caller
            # is not left guessing, and flag it as PROMPT_NOT_DETECTED.
            return CommandResult(
                command=command,
                stdout="",
                stderr="",
                exit_status=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                transport="session",
                ok=False,
                error="PROMPT_NOT_DETECTED",
                safe_mode=self._safe_mode,
                prompt_path=None,
            )

        body = self._strip_echo(buffer, safe_command)
        body, _ = _strip_prompt(body)
        body = body.strip("\r\n")
        body = body.rstrip()

        error = _detect_error(body)
        safe_mode = self._safe_mode

        rows = None
        if error is None and body:
            parsed = parse_print_table(body)
            if parsed:
                rows = parsed

        return CommandResult(
            command=command,
            stdout=body,
            stderr=body if error else "",
            exit_status=1 if error else 0,
            duration_ms=int((time.monotonic() - started) * 1000),
            transport="session",
            ok=error is None,
            error="COMMAND_REJECTED" if error else None,
            rows=rows,
            safe_mode=safe_mode,
            prompt_path=prompt_path,
        )

    async def run_exec(self, command: str, timeout: Optional[float] = None) -> CommandResult:
        """Run one command over a one-shot ``exec`` channel.

        The router's error text arrives on stderr with a non-zero exit
        status, so stdout and stderr are cleanly separated.

        Args:
            command: The command to run. It must be a single line.
            timeout: Timeout in seconds. Defaults to the target's
                ``command_timeout``.

        Returns:
            A :class:`~.models.CommandResult`.
        """
        self._guard_multiline(command)

        timeout = float(timeout if timeout is not None else self._target.command_timeout)
        started = time.monotonic()
        safe_command = _add_without_paging(command)

        try:
            import asyncssh  # noqa: PLC0415 - deliberately lazy
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise MikroTikError(
                "the 'asyncssh' package is required for the MikroTik SSH transport "
                "but is not installed",
                code="UNREACHABLE",
            ) from exc

        kwargs: dict[str, Any] = {
            "port": self._target.port,
            "username": self._target.login_username,
            "encoding": "utf-8",
            "errors": "replace",
            "known_hosts": self._known_hosts_arg(),
        }
        if self._target.key_path is not None:
            kwargs["client_keys"] = [str(self._target.key_path)]
            if self._target.key_passphrase is not None:
                kwargs["passphrase"] = self._target.key_passphrase.get_secret_value()
        elif self._target.password is not None:
            kwargs["password"] = self._target.password.get_secret_value()

        try:
            result = await asyncio.wait_for(
                asyncssh.connect(self._target.host, **kwargs).then(
                    lambda conn: conn.run(safe_command, check=False)
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            return CommandResult(
                command=command,
                stdout="",
                stderr="",
                exit_status=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                transport="exec",
                ok=False,
                error="TIMEOUT",
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            raise self._classify_connect_error(exc) from exc

        stdout = (result.stdout or "").strip("\r\n")
        stderr = (result.stderr or "").strip("\r\n")
        exit_status = result.exit_status
        ok = exit_status == 0 and not _detect_error(stderr)

        rows = None
        if ok and stdout:
            parsed = parse_print_table(stdout)
            if parsed:
                rows = parsed

        return CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_status=exit_status,
            duration_ms=int((time.monotonic() - started) * 1000),
            transport="exec",
            ok=ok,
            error=None if ok else "COMMAND_REJECTED",
            rows=rows,
            safe_mode=self._safe_mode,
            prompt_path=None,
        )

    # -- safe mode -------------------------------------------------------
    async def enter_safe_mode(self) -> CommandResult:
        """Enter RouterOS safe mode (Ctrl+X).

        In safe mode the configuration is written to disk only when safe mode
        is turned off, so a mistake can be discarded.
        """
        await self._write(SAFE_MODE_ENTER)
        buffer, prompt_path = await self._read_until_prompt(self._target.command_timeout)
        self._safe_mode = _is_safe_mode(buffer)
        return CommandResult(
            command="<ctrl-x>",
            stdout="",
            stderr="",
            exit_status=0,
            duration_ms=0,
            transport="session",
            ok=True,
            error=None,
            safe_mode=self._safe_mode,
            prompt_path=prompt_path,
        )

    async def exit_safe_mode(self, save: bool = False) -> CommandResult:
        """Leave RouterOS safe mode.

        Args:
            save: When ``True`` the configuration is written to disk. The
                default is ``False``, which discards the changes - the safe
                choice.

        Returns:
            A :class:`~.models.CommandResult` reflecting the new state.
        """
        await self._write(SAFE_MODE_EXIT)
        buffer, prompt_path = await self._read_until_prompt(self._target.command_timeout)
        self._safe_mode = _is_safe_mode(buffer)
        return CommandResult(
            command="<ctrl-d>" if not save else "<ctrl-d> (save)",
            stdout="",
            stderr="",
            exit_status=0,
            duration_ms=0,
            transport="session",
            ok=True,
            error=None,
            safe_mode=self._safe_mode,
            prompt_path=prompt_path,
        )

    # -- helpers ---------------------------------------------------------
    def _guard_multiline(self, command: str) -> None:
        """Reject a multi-line or chained command.

        Raises:
            MultilineUnsupportedError: The command contains a newline, a
                chain operator or a script block.
        """
        if not command:
            raise MultilineUnsupportedError("the command is empty")
        patterns = contains_injection_patterns(command)
        if patterns:
            raise MultilineUnsupportedError(
                "the command contains an unsupported or unsafe construct "
                f"({', '.join(patterns)}); MikroTik's SSH server cannot deliver "
                "a multi-line or chained command"
            )

    def _strip_echo(self, buffer: str, command: str) -> str:
        """Remove the echoed command from the front of *buffer*."""
        for prefix in (command + "\r\n", command + "\n", command):
            if buffer.startswith(prefix):
                return buffer[len(prefix) :]
        return buffer

