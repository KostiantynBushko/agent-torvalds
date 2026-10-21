"""
Compatibility layer for the optional validation dependency.

The MikroTik RouterOS toolkit is a *reusable library*. It must import cleanly
on a machine where none of the optional dependencies (``pydantic``,
``asyncssh``, ``routeros_api``) are installed, so that the surrounding agent
still boots (MODULE_SPECIFICATION.md R3/R4, D3/D10).

``pydantic`` is used for the validation layer (``MikroTikTarget``,
``CommandResult``, ``RouterIdentity``). It is declared as an *optional*
dependency, so this module exposes a small, self-contained fallback
implementation for the case where ``pydantic`` cannot be imported.

The fallback is deliberately minimal. It supports exactly the feature set this
package uses:

* class-level annotations with defaults
* :func:`Field` defaults and descriptions
* :func:`field_validator` post-validation hooks
* :class:`SecretStr` with a redacted ``repr``
* ``model_dump()`` / ``model_dump_json()`` / ``model_validate()``

When ``pydantic`` *is* installed its real implementation is re-exported
unchanged, so production behaviour is always pydantic's.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import json
import types
import typing
from pathlib import Path
from typing import Any, Callable, Optional, Union, get_args, get_origin

__all__ = [
    "BaseModel",
    "Field",
    "SecretStr",
    "field_validator",
    "PYDANTIC_AVAILABLE",
]


# ---------------------------------------------------------------------------
# Try the real pydantic first
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depends on the environment
    from pydantic import BaseModel, Field, SecretStr, field_validator

    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the "no deps" test
    PYDANTIC_AVAILABLE = False

    # ------------------------------------------------------------------
    # Fallback implementation
    # ------------------------------------------------------------------

    _UNSET = object()

    #: Attribute used to tag a function as a field validator.
    _VALIDATOR_FIELDS = "__mikrotik_validator_fields__"

    class SecretStr:  # type: ignore[no-redef]
        """Minimal stand-in for ``pydantic.SecretStr``.

        The value is never rendered in ``repr``/``str``; it must be extracted
        explicitly with :meth:`get_secret_value`.
        """

        __slots__ = ("_value",)

        def __init__(self, value: str = "") -> None:
            self._value = str(value)

        def get_secret_value(self) -> str:
            """Return the wrapped secret in clear text."""
            return self._value

        def __repr__(self) -> str:
            return "SecretStr('**********')"

        def __str__(self) -> str:
            return "**********"

        def __eq__(self, other: object) -> bool:
            if isinstance(other, SecretStr):
                return self._value == other._value
            return NotImplemented

        def __hash__(self) -> int:
            return hash(("SecretStr", self._value))

    class _FieldInfo:  # noqa: D401 - internal helper
        """Carries the default value and description of a model field."""

        __slots__ = ("default", "description", "required")

        def __init__(
            self,
            default: Any = _UNSET,
            description: str = "",
            required: bool = False,
        ) -> None:
            self.default = default
            self.description = description
            self.required = required

    def Field(  # noqa: N802 - mirrors the pydantic spelling
        default: Any = _UNSET,
        *,
        description: str = "",
        **_: Any,
    ) -> Any:
        """Declare a model field with an optional default and description."""
        return _FieldInfo(default=default, description=description)

    def _coerce(value: Any, annotation: Any) -> Any:
        """Best-effort coercion of *value* to *annotation*."""
        if annotation is Any or annotation is None:
            return value

        origin = get_origin(annotation)

        # Optional[...] / Union[...]
        if origin is Union or origin is types.UnionType:
            args = get_args(annotation)
            if value is None and type(None) in args:
                return None
            for arg in args:
                if arg is type(None):
                    continue
                try:
                    return _coerce(value, arg)
                except (TypeError, ValueError):
                    continue
            return value

        # Literal[...]
        if origin is typing.Literal:
            allowed = get_args(annotation)
            if value not in allowed:
                raise ValueError(f"expected one of {allowed!r}, got {value!r}")
            return value

        if origin in (list, tuple, set, frozenset):
            if not isinstance(value, (list, tuple, set, frozenset)):
                raise TypeError(f"expected {origin.__name__}, got {type(value).__name__}")
            args = get_args(annotation)
            item_type = args[0] if args else Any
            items = [_coerce(v, item_type) for v in value]
            return origin(items)

        if origin is dict:
            if not isinstance(value, dict):
                raise TypeError(f"expected dict, got {type(value).__name__}")
            return dict(value)

        if annotation is SecretStr:
            if value is None:
                return None
            return value if isinstance(value, SecretStr) else SecretStr(str(value))

        if annotation is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "false", "yes", "no", "1", "0"):
                return value.lower() in ("true", "yes", "1")
            raise TypeError(f"expected bool, got {type(value).__name__}")

        if annotation is int:
            if isinstance(value, bool):
                raise TypeError("expected int, got bool")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
                return int(value.strip())
            if isinstance(value, float) and value.is_integer():
                return int(value)
            raise TypeError(f"expected int, got {type(value).__name__}")

        if annotation is float:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, str):
                return float(value)
            raise TypeError(f"expected float, got {type(value).__name__}")

        if annotation is str:
            if isinstance(value, str):
                return value
            raise TypeError(f"expected str, got {type(value).__name__}")

        if annotation is Path:
            if isinstance(value, Path):
                return value
            if isinstance(value, str):
                return Path(value).expanduser()
            raise TypeError(f"expected Path, got {type(value).__name__}")

        return value

    def _invoke_validator(validator: Callable[..., Any], cls: type, value: Any) -> Any:
        """Call a validator, supporting both ``(cls, value)`` and ``(value)``."""
        func = getattr(validator, "__func__", validator)
        try:
            return func(cls, value)
        except TypeError as exc:
            if "positional argument" not in str(exc):
                raise
            return func(value)

    class BaseModel:  # type: ignore[no-redef]
        """Minimal stand-in for ``pydantic.BaseModel``.

        Supports the subset of the pydantic API this package relies on. It is
        only used when pydantic is not installed.
        """

        __validators__: dict[str, list[Callable[..., Any]]] = {}

        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            # Collect the validators declared in this class body.
            collected: dict[str, list[Callable[..., Any]]] = {}
            for attr in vars(cls).values():
                func = getattr(attr, "__func__", attr)
                tagged = getattr(func, _VALIDATOR_FIELDS, None)
                if not tagged:
                    continue
                for name in tagged:
                    collected.setdefault(name, []).append(func)
            cls.__validators__ = collected

        # -- field discovery ------------------------------------------------
        @classmethod
        def _fields(cls) -> dict[str, Any]:
            fields: dict[str, Any] = {}
            for klass in reversed(cls.__mro__):
                annotations = klass.__dict__.get("__annotations__", {}) or {}
                for name, annotation in annotations.items():
                    if name.startswith("_"):
                        continue
                    default = klass.__dict__.get(name, _UNSET)
                    if isinstance(default, _FieldInfo):
                        fields[name] = (annotation, default)
                    else:
                        fields[name] = (annotation, _FieldInfo(default=default))
            return fields

        def __init__(self, **data: Any) -> None:
            fields = type(self)._fields()
            validators = type(self).__validators__

            for name, (annotation, info) in fields.items():
                if name in data:
                    value = data.pop(name)
                elif not info.required and info.default is not _UNSET:
                    value = info.default
                else:
                    raise ValueError(f"{type(self).__name__}: field {name!r} is required")

                try:
                    value = _coerce(value, annotation)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{type(self).__name__}: invalid value for {name!r}: {exc}"
                    ) from exc

                for validator in validators.get(name, ()):
                    value = _invoke_validator(validator, type(self), value)

                object.__setattr__(self, name, value)

            if data:
                # pydantic's default is to ignore extra fields.
                pass

        # -- serialisation --------------------------------------------------
        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            """Return the model as a plain dictionary."""
            return {name: getattr(self, name) for name in type(self)._fields()}

        def model_dump_json(self, **kwargs: Any) -> str:
            """Return the model as a JSON string."""
            return json.dumps(self.model_dump(), default=str, **kwargs)

        @classmethod
        def model_validate(cls, obj: Any) -> "BaseModel":
            """Build a model from a dictionary."""
            if not isinstance(obj, dict):
                raise TypeError("model_validate expects a dict")
            return cls(**obj)

        # -- dunder ---------------------------------------------------------
        def __repr__(self) -> str:
            inner = ", ".join(
                f"{name}={getattr(self, name)!r}" for name in type(self)._fields()
            )
            return f"{type(self).__name__}({inner})"

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, BaseModel):
                return NotImplemented
            return type(self) is type(other) and self.model_dump() == other.model_dump()

    def field_validator(*fields: str, **_kwargs: Any) -> Callable[[Any], Any]:
        """Register a post-validation hook for one or more fields.

        The decorated function may be written either as a ``classmethod``
        (pydantic style, ``(cls, value)``) or as a plain function
        (``(value)``); both are supported.
        """

        def decorator(fn: Any) -> Any:
            # ``fn`` may be a plain function or a ``classmethod`` object. In
            # both cases the *underlying* function carries the tag; a
            # ``classmethod`` object does not proxy attribute lookups to it,
            # so the tag is set on the function and read back via ``__func__``.
            target = getattr(fn, "__func__", fn)
            setattr(target, _VALIDATOR_FIELDS, tuple(fields))
            return fn

        return decorator
