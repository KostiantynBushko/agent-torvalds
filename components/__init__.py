"""
Torvalds AI Agent - Components Module

Provides reusable components for the agent:
- SpinnerController: Console spinner with pause/resume capabilities
- StateHandler: Agent state management during workflow execution
- EventConsumer: Real-time workflow event consumption
- SignalHandler: Graceful shutdown signal handling
- WhiptailPasswordPrompter: Terminal dialog-based password prompting

The modules are imported when one of their names is asked for, and not
before.  The event consumer carries the workflow engine of llama_index,
and the import of it costs the better part of a second: every program
that touched any component of the agent paid that price -- and most of
them never speak to the event consumer at all.
"""
import importlib
import pkgutil

#: The module of the package that carries every name of it.
_MODULES = {
    "SpinnerController": "spinner_controller",
    "StateHandler": "state_handler",
    "EventConsumer": "event_consumer",
    "SignalHandler": "signal_handler",
    "WhiptailPasswordPrompter": "whiptail_password",
    "get_prompter": "whiptail_password",
    "prompt_sudo_password_whiptail": "whiptail_password",
}


def _submodule(name):
    """The module of the package with that name, when there is one.

    Args:
        name: The name that was asked for.

    Returns:
        The module, or None when the package carries no such module.
    """
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name == name:
            return importlib.import_module(f"{__name__}.{name}")
    return None


def __getattr__(name):
    """The names of the package, imported when they are asked for.

    Args:
        name: The name that was asked for.

    Returns:
        The object the name carries.

    Raises:
        AttributeError: The package carries no such name.
    """
    module_name = _MODULES.get(name)
    if module_name is not None:
        module = importlib.import_module(f"{__name__}.{module_name}")
        value = getattr(module, name)
        globals()[name] = value
        return value

    module = _submodule(name)
    if module is not None:
        globals()[name] = module
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """The names of the package: the loaded ones and the ones that are not."""
    return sorted(set(globals()) | set(_MODULES))


__all__ = [
    "SpinnerController",
    "StateHandler",
    "EventConsumer",
    "SignalHandler",
    "WhiptailPasswordPrompter",
    "get_prompter",
    "prompt_sudo_password_whiptail",
]
