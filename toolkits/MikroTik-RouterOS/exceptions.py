"""
Typed error hierarchy for the MikroTik RouterOS toolkit.

Every error carries a **machine-readable** ``code`` so that the agent adapter
can return a structured error without parsing prose (MODULE_SPECIFICATION.md
§6.3). The codes are the contract between the core package and the
LlamaIndex adapter.

::

    MikroTikError
    ├── AuthError                   AUTH_FAILED
    ├── HostKeyError                HOST_KEY_MISMATCH
    ├── ConnectionError_            UNREACHABLE
    ├── CommandTimeoutError         TIMEOUT
    ├── CommandRejectedError        COMMAND_REJECTED
    ├── MultilineUnsupportedError   MULTILINE_UNSUPPORTED
    ├── InteractiveInputRequiredError INTERACTIVE_INPUT_REQUIRED
    ├── SafeModeError               SAFE_MODE_ACTIVE
    ├── PagingError                 PAGING_DETECTED
    └── NotAuthorizedError          NOT_AUTHORIZED

Two further codes exist in the taxonomy but are not transport errors and
therefore have no dedicated class:

``PROMPT_NOT_DETECTED``
    The session never saw a RouterOS prompt. The session layer reports this
    through :class:`CommandResult.error` rather than by raising, because the
    raw buffer is still useful to the caller.
``UNKNOWN_TARGET``
    The requested target id is not in the registry. The adapter reports this
    in the result dictionary.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

__all__ = [
    "MikroTikError",
    "AuthError",
    "HostKeyError",
    "ConnectionError_",
    "CommandTimeoutError",
    "CommandRejectedError",
    "MultilineUnsupportedError",
    "InteractiveInputRequiredError",
    "SafeModeError",
    "PagingError",
    "NotAuthorizedError",
    "ERROR_CODES",
]


class MikroTikError(Exception):
    """Base class for every error raised by the MikroTik RouterOS toolkit.

    Attributes:
        code: Machine-readable error code (e.g. ``"AUTH_FAILED"``).
        message: Human-readable description. Never contains a secret.
        details: Optional structured context (never contains a secret).
    """

    #: Default machine-readable code for this class.
    code: str = "MIKROTIK_ERROR"

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message or self.__class__.__doc__ or self.__class__.__name__
        if code is not None:
            self.code = code
        self.details: dict = dict(details or {})
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of this error."""
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class AuthError(MikroTikError):
    """The router rejected the supplied credentials."""

    code = "AUTH_FAILED"


class HostKeyError(MikroTikError):
    """The server host key does not match the stored fingerprint.

    This is a **hard stop**: it may indicate a man-in-the-middle attack or a
    re-imaged router. It must never be retried automatically.
    """

    code = "HOST_KEY_MISMATCH"


class ConnectionError_(MikroTikError):
    """The router could not be reached (refused, timed out, no route).

    The trailing underscore avoids shadowing the builtin ``ConnectionError``.
    """

    code = "UNREACHABLE"


class CommandTimeoutError(MikroTikError):
    """The command did not complete within the allotted time."""

    code = "TIMEOUT"


class CommandRejectedError(MikroTikError):
    """The router refused the command (bad syntax, unknown item, failure)."""

    code = "COMMAND_REJECTED"


class MultilineUnsupportedError(MikroTikError):
    """The command contained a newline, ``;``, ``&&`` or ``|``.

    MikroTik's SSH server provides no pseudo-terminal, so a multi-line script
    cannot be delivered over SSH. A multi-line command is also a common
    prompt-injection vector, so it is rejected outright.
    """

    code = "MULTILINE_UNSUPPORTED"


class InteractiveInputRequiredError(MikroTikError):
    """The command asked for interactive input (e.g. ``old password:``).

    Such a command cannot be driven over a non-interactive SSH channel. The
    operator has to run it manually.
    """

    code = "INTERACTIVE_INPUT_REQUIRED"


class SafeModeError(MikroTikError):
    """The router is in safe mode and the operation is not permitted."""

    code = "SAFE_MODE_ACTIVE"


class PagingError(MikroTikError):
    """The router paged its output instead of returning it in one block.

    Automation must always append ``without-paging``; a paging prompt means
    the command needs that suffix (or a smaller result set).
    """

    code = "PAGING_DETECTED"


class NotAuthorizedError(MikroTikError):
    """The router's policy forbids this operation for the current user."""

    code = "NOT_AUTHORIZED"


#: Every machine-readable error code the toolkit can produce.
ERROR_CODES: frozenset[str] = frozenset(
    {
        "AUTH_FAILED",
        "HOST_KEY_MISMATCH",
        "UNREACHABLE",
        "TIMEOUT",
        "COMMAND_REJECTED",
        "MULTILINE_UNSUPPORTED",
        "INTERACTIVE_INPUT_REQUIRED",
        "SAFE_MODE_ACTIVE",
        "PAGING_DETECTED",
        "NOT_AUTHORIZED",
        "PROMPT_NOT_DETECTED",
        "UNKNOWN_TARGET",
    }
)
